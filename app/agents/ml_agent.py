"""ML agent — a *proposer* that forecasts next-bar direction.

Self-contained: a small numpy logistic regression (standardized features, L2,
gradient descent) so it runs with zero heavy dependencies. If xgboost or
scikit-learn is installed it transparently uses the stronger model instead.

Hard rule (spec): ML proposes, never decides. This is an analytic agent with
role "ml" and a low CIO weight; the Risk Manager and CIO still gate everything.
It deliberately abstains (score 0) when it lacks data or training signal.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.agents.base import AnalyticAgent
from app.models import AgentVote

_FEATURES = ["rsi", "macd_hist", "roc", "rvol", "d_ema50", "d_ema200", "ret1", "ret5"]


def _build_xy(df: pd.DataFrame):
    f = pd.DataFrame(index=df.index)
    close = df["close"]
    f["rsi"] = df.get("rsi", 50.0) / 100.0
    f["macd_hist"] = df.get("macd_hist", 0.0) / close
    f["roc"] = df.get("roc", 0.0) / 100.0
    f["rvol"] = df.get("rvol", 0.0)
    f["d_ema50"] = close / df.get("ema50", close) - 1
    f["d_ema200"] = close / df.get("ema200", close) - 1
    f["ret1"] = close.pct_change(1)
    f["ret5"] = close.pct_change(5)
    y = (close.shift(-1) > close).astype(float)   # 1 if next bar up
    data = f.join(y.rename("y")).replace([np.inf, -np.inf], np.nan).dropna()
    return data[_FEATURES].values, data["y"].values


class _NumpyLogReg:
    """Minimal standardized logistic regression (deterministic)."""

    def __init__(self, iters: int = 250, lr: float = 0.1, l2: float = 1e-3):
        self.iters, self.lr, self.l2 = iters, lr, l2

    def fit(self, X, y):
        self.mu = X.mean(axis=0)
        self.sd = X.std(axis=0) + 1e-9
        Xs = (X - self.mu) / self.sd
        n, d = Xs.shape
        self.w = np.zeros(d)
        self.b = 0.0
        for _ in range(self.iters):
            z = Xs @ self.w + self.b
            p = 1 / (1 + np.exp(-z))
            grad_w = Xs.T @ (p - y) / n + self.l2 * self.w
            grad_b = float(np.mean(p - y))
            self.w -= self.lr * grad_w
            self.b -= self.lr * grad_b
        self.train_acc = float(np.mean((self.predict_proba(X) > 0.5) == (y > 0.5)))
        return self

    def predict_proba(self, X):
        Xs = (X - self.mu) / self.sd
        return 1 / (1 + np.exp(-(Xs @ self.w + self.b)))


def _make_model():
    """Prefer xgboost/sklearn if present; else the numpy fallback."""
    try:
        from xgboost import XGBClassifier  # type: ignore

        return XGBClassifier(n_estimators=80, max_depth=3, learning_rate=0.1,
                             verbosity=0, use_label_encoder=False), "xgboost"
    except Exception:
        pass
    try:
        from sklearn.linear_model import LogisticRegression  # type: ignore

        return LogisticRegression(max_iter=300), "sklearn"
    except Exception:
        return _NumpyLogReg(), "numpy_logreg"


class MLAgent(AnalyticAgent):
    name = "ML_AI"
    role = "ml"
    min_bars = 160

    def analyze(self, asset: str, data: dict[str, pd.DataFrame]) -> AgentVote:
        df = data.get("1D")
        if df is None:
            df = next(v for k, v in data.items() if k != "_context")
        if len(df) < self.min_bars:
            return self._vote(asset, 0.0, 0.2, "ML: insufficient history")

        X, y = _build_xy(df)
        if len(X) < 120 or len(np.unique(y[:-1])) < 2:
            return self._vote(asset, 0.0, 0.2, "ML: not enough labeled signal")

        model, backend = _make_model()
        try:
            model.fit(X[:-1], y[:-1])          # never train on the row we predict
            if hasattr(model, "predict_proba"):
                proba = model.predict_proba(X[-1:].reshape(1, -1))
                p_up = float(proba[0][1]) if getattr(proba, "ndim", 1) == 2 else float(proba[-1])
            else:  # numpy fallback returns 1-D proba
                p_up = float(model.predict_proba(X[-1:]).reshape(-1)[-1])
        except Exception as exc:  # noqa: BLE001
            return self._vote(asset, 0.0, 0.2, f"ML: training failed ({type(exc).__name__})")

        score = float(np.clip((p_up - 0.5) * 200, -100, 100))
        acc = float(getattr(model, "train_acc", 0.55))
        confidence = float(np.clip((acc - 0.5) * 1.4, 0.2, 0.7))  # capped: ML is advisory
        return self._vote(asset, score, confidence,
                          f"ML[{backend}] p_up={p_up:.2f} acc={acc:.2f}", [],
                          {"p_up": p_up, "backend": backend})
