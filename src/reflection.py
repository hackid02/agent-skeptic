"""Reflection: the Skeptic reviews how it (and the agent) actually behaved, then
proposes updates to its own rulebook. Keeps the honest 'we don't promise profit'
frame: the goal is fewer reckless trades, lower drawdown and less fee burn.

Also runs the A/B that makes the value visible: same market, no guardrails vs
guardrails on.
"""
from __future__ import annotations

from typing import Dict, List

from .engine import Decision, FlawedTrader
from .market import get_klines
from .rulebook import DEFAULT_RULES, Rule


def stats(equity_curve: List[float], decisions: List[Decision],
          ledger: Dict | None = None, fee_rate: float = 0.001) -> Dict:
    peak = -1e18
    max_dd = 0.0
    for e in equity_curve:
        peak = max(peak, e)
        max_dd = max(max_dd, (peak - e)/peak if peak else 0)
    # Fees come from the engine's own ledger (exact, respects fee_rate);
    # the estimate below is only a fallback for foreign callers.
    if ledger is not None and "fees_paid" in ledger:
        fees = float(ledger["fees_paid"])
    else:
        fees = sum(d.notional * fee_rate for d in decisions if d.action in ("BUY", "SELL"))
    return {
        "final_equity": equity_curve[-1] if equity_curve else 0.0,
        "start_equity": equity_curve[0] if equity_curve else 0.0,
        "max_drawdown": max_dd,
        "trades": sum(1 for d in decisions if d.action in ("BUY", "SELL")),
        "fees": fees,
        "blocks": sum(1 for d in decisions if d.tag == "blocked"),
    }


def ab_test(bars, rulebook, cash=10000.0, fee_rate=0.001) -> Dict:
    """Same data: flawed agent without guardrails vs with the Skeptic's rules."""
    _dec, eq_ctrl, led_ctrl = FlawedTrader(cash, fee_rate, use_guardrails=False).run(bars)
    dec_g, eq_gov, led_gov = FlawedTrader(cash, fee_rate, use_guardrails=True, rulebook=rulebook).run(bars)
    return {
        "control": stats(eq_ctrl, _dec, led_ctrl, fee_rate),
        "governed": stats(eq_gov, dec_g, led_gov, fee_rate),
        "ctrl_decisions": _dec,
        "gov_decisions": dec_g,
    }


def propose_updates(control: Dict, governed: Dict, rulebook: List[Rule] | None = None) -> List[Rule]:
    """Convert observed behaviour into proposed rulebook changes (human approves)."""
    rulebook = rulebook if rulebook is not None else DEFAULT_RULES
    # Drawdown tightening starts from the guard actually in force, so a
    # proposal can never be *looser* than what the user already set.
    current_dd = next((float(r.params.get("max_dd", 0.05)) for r in rulebook
                       if r.kind == "drawdown_guard"), 0.05)
    dd_imp = control["max_drawdown"] - governed["max_drawdown"]
    proposals: List[Rule] = []
    if control["trades"] > governed["trades"]:
        proposals.append(Rule(
            kind="trade_cap", params={"max_trades": governed["trades"] + 1},
            label="Cap trades per window to prevent fee churn.",
            severity="BLOCK", source="reflection",
        ))
    if dd_imp > 0.005:
        proposals.append(Rule(
            kind="drawdown_guard", params={"max_dd": max(0.02, current_dd - dd_imp)},
            label="Tighten the drawdown guard based on what I saw.",
            severity="BLOCK", source="reflection",
        ))
    proposals.append(Rule(
        kind="position_cap_learned", params={"max": 0.10},
        label="Learned: keep single-position risk near 10%.",
        severity="BLOCK", source="reflection",
    ))
    return proposals


def run_reflection(symbol: str = "BTCUSDT", source: str = "synth", seed: int = 7) -> Dict:
    """Reflect on a symbol. Symbol is the first positional argument."""
    bars = get_klines(symbol, "1h", 200, source=source, seed=seed)
    res = ab_test(bars, DEFAULT_RULES)
    proposals = propose_updates(res["control"], res["governed"], DEFAULT_RULES)
    return {
        "bars": bars,
        **res,
        "proposals": proposals,
        # Same "improvement" shape the MCP run_ab tool returns, so the library
        # and the tool agree on what the data looks like.
        "improvement": {
            "drawdown_pct": round((res["control"]["max_drawdown"] - res["governed"]["max_drawdown"])
                                  / max(res["control"]["max_drawdown"], 1e-9) * 100, 0),
            "fee_pct": round((res["control"]["fees"] - res["governed"]["fees"])
                             / max(res["control"]["fees"], 1e-9) * 100, 0),
        },
    }
