"""Active trade management — where profit is actually protected and let run.

Per open position, each bar we may:
  1. Time-stop   — cut a stagnating trade that hasn't reached min R.
  2. Scale out   — bank a partial at +1R (de-risk, lock some gain).
  3. Break-even  — move the stop to entry once +1R is reached (free trade).
  4. Trail       — ratchet the stop behind price once beyond +1R (let it run).

All stop moves only ever tighten (favorable side), honoring the cardinal rule
that a stop is never widened. Pure decisions + broker mutations; returns any
ClosedTrade produced (scale-outs / time-stops) so the caller can journal/learn.
"""

from __future__ import annotations

from app.core.config import ExitConfig
from app.core.constants import Action
from app.risk.stop_manager import trail_stop


def manage_position(broker, pos, price: float, atr: float, policy: ExitConfig) -> list:
    """Apply active management to one open position at the current price."""
    if not policy.enabled:
        return []
    produced = []
    r = pos.r_multiple(price)

    # 1) Time-stop: stagnating and not enough progress.
    if pos.bars_held >= policy.time_stop_bars and r < policy.time_stop_min_r:
        trade = broker.close(pos.symbol, price, "time_stop")
        return [trade] if trade else []

    # 2) Scale out a partial at the first R target.
    if not pos.scaled_out and r >= policy.scale_out_at_r and policy.scale_out_fraction > 0:
        trade = broker.partial_close(pos.symbol, policy.scale_out_fraction, price, "scale_out")
        if trade:
            produced.append(trade)
        if pos.symbol not in broker.positions:   # fully closed by the partial
            return produced

    # 3) Break-even: move stop to entry once we are +breakeven_at_r.
    if not pos.moved_to_breakeven and r >= policy.breakeven_at_r:
        if pos.action == Action.LONG:
            pos.stop_loss = max(pos.stop_loss, pos.entry)
        else:
            pos.stop_loss = min(pos.stop_loss, pos.entry)
        pos.moved_to_breakeven = True

    # 4) Trail behind price once beyond the trail threshold (only tightens).
    if r >= policy.trail_after_r and atr > 0:
        pos.stop_loss = trail_stop(pos.stop_loss, price, atr, pos.action, policy.trail_atr_mult)

    return produced
