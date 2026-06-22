"""Per-layer toggles + leave-one-out attribution."""

from app.agents import build_agents_from_settings
from app.core.config import load_config


def test_all_layers_on_by_default():
    s = load_config()
    L = s.layers
    assert L.smc and L.volume_profile and L.macro and L.news and L.social and L.ml
    roles = {a.role for a in build_agents_from_settings(s)}
    # External + ML + SMC + volume profile all present.
    assert {"ml", "news", "sentiment", "macro", "volume", "pattern"} <= roles


def test_disable_single_layer_removes_only_it():
    s = load_config()
    s.layers.ml = False
    s.layers.news = False
    names = {a.name for a in build_agents_from_settings(s)}
    assert "ML_AI" not in names and "NewsAI" not in names
    assert "SMC_AI" in names and "MacroAI" in names   # others untouched


def test_sync_layer_flags_mirrors_decision_layers():
    s = load_config()
    s.layers.structure_stops = False
    s.layers.smart_exits = False
    s.layers.cost_filter = False
    s.layers.portfolio = False
    s.sync_layer_flags()
    assert s.strategy.structure_stops is False
    assert s.exits.enabled is False
    assert s.execution.cost_aware is False
    assert s.portfolio.enabled is False


def test_layer_attribution_runs_and_ranks(tmp_path):
    from app.analysis.layer_attribution import run_layer_attribution
    from app.core.config import apply_risk_profile
    from app.data.market_data import SyntheticConfig, synthetic_ohlcv

    s = apply_risk_profile(load_config(), "aggressive")
    # Keep the test fast: only the 4 decision layers are attributed (agent
    # leave-one-out is exercised by scripts/layer_report.py, not the unit suite).
    for name in ("ml", "smc", "volume_profile", "macro", "news", "social"):
        setattr(s.layers, name, False)
    s.learning.store_path = str(tmp_path / "kb.json")
    s.learning.journal_path = str(tmp_path / "j.jsonl")
    hist = {f"C{i}": synthetic_ohlcv(f"C{i}", SyntheticConfig(bars=260, drift=0.003 * (1 if i % 2 else -1),
            volatility=0.025, seed=i)) for i in range(3)}
    rep = run_layer_attribution(s, hist, min_trades=10)
    assert rep.full_trades >= 0
    layer_names = {r.layer for r in rep.layers}
    # Decision layers + active agents are attributed (ml excluded above).
    assert {"structure_stops", "smart_exits", "cost_filter", "portfolio"} <= layer_names
    assert "ml" not in layer_names
    for r in rep.layers:
        assert r.verdict in ("BENEFICIAL", "HARMFUL", "NEUTRAL", "LOW_DATA")
