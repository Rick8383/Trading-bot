# CLAUDE.md — guide for working in this repository

## What this is
A multi-agent, **risk-first**, **paper-first** algorithmic trading bot with a
**self-learning loop**. Capital preservation is the top priority; growth is
secondary. The system is allowed to stay flat/cash when there is no edge.

## Non-negotiable invariants (do not weaken without founder sign-off)
1. **Risk Manager veto is absolute.** `app/risk/risk_manager.py` can reject any
   trade. No agent or the CIO may override it.
2. **No stopless orders.** `app/execution/order_validator.py` and the
   `RiskManager` both refuse trades without a valid stop. Keep both gates.
3. **No leverage by default** (`default_leverage: 1.0`). Live trading stays
   locked behind `LIVE_TRADING_UNLOCK=I_UNDERSTAND_THE_RISK`.
4. **Per-trade risk never increases after wins.** See `decision/adaptive_risk.py`.
5. **Self-improvement proposes, never deploys.** `learning/improvement_engine.py`
   output is advisory only.
6. **No performance guarantees** anywhere in code, docs, or output.

## Architecture map
- `app/decision/` — the stable philosophy layer (EV, conviction, exposure,
  adaptive risk, capital preservation). Touch carefully; this is the spine.
- `app/agents/` — analytic agents produce `AgentVote`s; CIO produces
  `FinalDecision`; Audit records everything.
- `app/learning/` — journal → post-mortem → knowledge base → conviction
  penalties → improvement proposals. The feedback loop.
- `app/orchestration/pipeline.py` — the 10-step decision flow.
- `app/orchestration/session.py` — paper-trading walk-forward harness.

## Conventions
- Python 3.11, pydantic v2, pandas/numpy. Indicators are pure (no TA-Lib).
- Phase 1 data is synthetic & deterministic so everything is testable offline.
- Money math sizes from **stop distance**, never notional.
- Keep functions pure where possible; agents must not place orders.

## Workflow
- Run tests: `pytest -q` (must stay green).
- Paper demo: `python scripts/run_paper.py`.
- Backtest demo: `python scripts/run_backtest.py`.
- API: `uvicorn app.main:app --reload`.

## When adding a new agent
1. Subclass `AnalyticAgent`, set `name` + `role`, implement `analyze`.
2. Return scores in `[-100, 100]` via `self._vote(...)`.
3. Register it in `app/agents/__init__.py::DEFAULT_ANALYTIC_AGENTS`.
4. Add a test asserting valid vote bounds and expected sign on trending data.

## When changing risk behavior
Add/adjust a test in `tests/test_risk.py` or `tests/test_decision.py` first.
Risk changes without a corresponding test should not be merged.
