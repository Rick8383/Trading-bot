"""Live-paper broker adapters (Phase 3b).

Two safe, real-but-fictional execution venues:
  * AlpacaPaperBroker  — US equities/ETF via Alpaca's *paper* API (fake money).
  * CcxtTestnetBroker  — crypto via an exchange *testnet* (fake money).

Both are gated behind the live-trading unlock and only constructed by the
factory when credentials are present. Both validate every order (stop mandatory)
before any network call. Neither risks real capital: Alpaca paper and exchange
testnets settle in fake balances.

These adapters are network-dependent and therefore exercised with mocks in the
test suite; end-to-end verification requires the founder's free testnet keys on
a host with open network egress.
"""

from __future__ import annotations

from app.core.constants import Action
from app.core.exceptions import LiveTradingLocked
from app.execution.order_validator import Order, validate


class AlpacaPaperBroker:
    """Alpaca paper-trading adapter (REST via httpx). Fake money only."""

    PAPER_URL = "https://paper-api.alpaca.markets"

    def __init__(self, key: str, secret: str, base_url: str | None = None, client=None,
                 unlocked: bool = False):
        if not unlocked:
            raise LiveTradingLocked("AlpacaPaperBroker requires the live unlock token")
        if not key or not secret:
            raise ValueError("Alpaca API key/secret required")
        import httpx  # optional dependency

        self.base_url = base_url or self.PAPER_URL
        self._client = client or httpx.Client(
            base_url=self.base_url,
            headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
            timeout=15.0,
        )

    def _post(self, path: str, json: dict) -> dict:
        resp = self._client.post(path, json=json)
        resp.raise_for_status()
        return resp.json()

    def _get(self, path: str) -> dict:
        resp = self._client.get(path)
        resp.raise_for_status()
        return resp.json()

    def submit(self, order: Order, decision_ref: str | None = None) -> dict:
        validate(order, max_leverage=1.0)  # stop mandatory, correct side, etc.
        side = "buy" if order.action == Action.LONG else "sell"
        payload = {
            "symbol": order.symbol,
            "qty": round(order.quantity, 4),
            "side": side,
            "type": "market",
            "time_in_force": "gtc",
            "order_class": "bracket",
            "stop_loss": {"stop_price": round(order.stop_loss, 2)},
        }
        if order.take_profit:
            payload["take_profit"] = {"limit_price": round(order.take_profit, 2)}
        return self._post("/v2/orders", payload)

    def close(self, symbol: str, price: float | None = None, reason: str = "manual") -> dict:
        resp = self._client.delete(f"/v2/positions/{symbol}")
        resp.raise_for_status()
        return resp.json()

    def positions(self) -> list[dict]:
        return self._get("/v2/positions")

    def equity(self, marks: dict[str, float] | None = None) -> float:
        return float(self._get("/v2/account")["equity"])

    def mark_to_market(self, marks: dict[str, float]) -> list:
        # Stops/targets are managed exchange-side by the bracket order.
        return []


class CcxtTestnetBroker:
    """Crypto exchange *testnet* adapter via ccxt sandbox mode. Fake money only."""

    def __init__(self, exchange: str, key: str, secret: str, unlocked: bool = False):
        if not unlocked:
            raise LiveTradingLocked("CcxtTestnetBroker requires the live unlock token")
        if not key or not secret:
            raise ValueError("exchange API key/secret required")
        import ccxt

        self.exchange = getattr(ccxt, exchange)({
            "apiKey": key, "secret": secret, "enableRateLimit": True,
        })
        self.exchange.set_sandbox_mode(True)  # route to testnet

    def submit(self, order: Order, decision_ref: str | None = None) -> dict:
        validate(order, max_leverage=1.0)
        side = "buy" if order.action == Action.LONG else "sell"
        entry = self.exchange.create_order(order.symbol, "market", side, order.quantity)
        # Best-effort protective stop on the exchange.
        stop_side = "sell" if side == "buy" else "buy"
        try:
            self.exchange.create_order(
                order.symbol, "stop_loss", stop_side, order.quantity, None,
                {"stopPrice": order.stop_loss},
            )
        except Exception:  # noqa: BLE001 — not all testnets support every stop type
            pass
        return entry

    def close(self, symbol: str, price: float | None = None, reason: str = "manual") -> dict:
        pos = self.exchange.fetch_balance()
        base = symbol.split("/")[0]
        qty = pos.get(base, {}).get("free", 0) if isinstance(pos.get(base), dict) else 0
        if qty:
            return self.exchange.create_order(symbol, "market", "sell", qty)
        return {"status": "no_position"}

    def equity(self, marks: dict[str, float] | None = None) -> float:
        bal = self.exchange.fetch_balance()
        return float(bal.get("total", {}).get("USDT", 0.0))

    def mark_to_market(self, marks: dict[str, float]) -> list:
        return []
