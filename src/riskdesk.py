"""The Skeptic's judgement: turn an incoming order intent into a verdict + rationale.

This is the 'confirm-before-execute' brain from Agent OS. It evaluates an intent
against the rulebook and produces a human-readable `why`, then the human approves.
"""
from __future__ import annotations

import dataclasses
from typing import Dict, List, Optional

from .rulebook import Rule


@dataclasses.dataclass
class OrderIntent:
    symbol: str
    side: str            # "BUY" | "SELL"
    notional: float      # USD value of the intended order
    price: float         # ref price
    vol: float           # recent annualised-ish volatility (decimal)
    agent_why: str = ""  # the trading agent's own stated reason
    is_risk_reducing: bool = False   # e.g. trimming to reduce exposure
    base_unit: float = 0.0           # the agent's 'base' sizing; for greed check


@dataclasses.dataclass
class Finding:
    rule: str
    blocked: bool
    message: str


@dataclasses.dataclass
class Verdict:
    action: str            # "APPROVE" | "DOWNSIZE" | "BLOCK"
    proposed_notional: float
    findings: List[Finding]

    @property
    def rationale(self) -> List[str]:
        return [f.indicator() for f in self.findings]


def evaluate(intent: OrderIntent, rulebook: List[Rule], *, equity: float,
             open_exposure: float, peak_equity: float, fees_paid: float) -> Verdict:
    """Judge `intent`. Returns a verdict and the human-facing explanation.

    severity/decisions:
      - risk-reducing orders are always fine (trim exposure).
      - otherwise we apply the strictest rule set: any BLOCK -> reject.
      - WARN rules downgrade size but don't stop it.
    """
    if intent.is_risk_reducing:
        return Verdict("APPROVE", intent.notional,
                       [Finding("rebalance_target", False,
                                "Risk-reducing order — allowed.")])

    findings: List[Finding] = []
    final_notional = intent.notional
    any_block = False

    for r in rulebook:
        kind = r.kind

        if kind == "max_position_pct":
            cap = r.params["max"] * equity
            if intent.notional > cap:
                any_block = True
                findings.append(Finding(kind, True, (
                    f"{intent.symbol} {intent.notional:,.0f} USDC is {intent.notional/equity:.0%} of the "
                    f"account, above the {r.params['max']:.0%} single-position cap "
                    f"({cap:,.0f} USDC)."
                )))
                final_notional = min(final_notional, cap)
            else:
                findings.append(Finding(kind, False, f"Size OK ({intent.notional/equity:.0%} of account)."))

        elif kind == "max_total_exposure":
            proj = open_exposure + intent.notional
            cap = r.params["max"] * equity
            if open_exposure > 0 and proj > cap:
                any_block = True
                findings.append(Finding(kind, True, (
                    f"Adding {intent.notional:,.0f} would push total exposure to {proj/equity:.0%}, "
                    f"over the {r.params['max']:.0%} cap."
                )))
                final_notional = min(final_notional, cap - open_exposure)
            elif open_exposure == 0:
                findings.append(Finding(kind, False, "No other open exposure — fine."))

        elif kind == "drawdown_guard":
            dd = (peak_equity - equity) / peak_equity if peak_equity else 0
            if dd >= r.params["max_dd"]:
                any_block = True
                findings.append(Finding(kind, True, (
                    f"Account is down {dd:.1%} from its peak ({r.params['max_dd']:.0%} guard) — "
                    f"no new risk until it recovers."
                )))
            else:
                findings.append(Finding(kind, False, f"Drawdown {dd:.1%} is within guard."))

        elif kind == "volatility_band":
            lo, hi = r.params["min"], r.params["max"]
            if intent.vol > hi:
                any_block = True
                findings.append(Finding(kind, True, (
                    f"Recent volatility {intent.vol:.2%} is above the {hi:.2%} ceiling — "
                    f"buying the spike, not the trend."
                )))
            elif intent.vol < lo:
                any_block = True
                findings.append(Finding(kind, True, (
                    f"Recent volatility {intent.vol:.2%} is below the {lo:.2%} floor — "
                    f"no edge, just noise."
                )))
            else:
                findings.append(Finding(kind, False, f"Volatility {intent.vol:.2%} is in band."))

        elif kind == "fee_budget":
            projected = fees_paid + intent.notional * 0.001 * 2  # round-trip fee
            if projected > r.params["max_fees"]:
                any_block = True
                findings.append(Finding(kind, True, (
                    f"~{projected:,.2f} USDC of round-trip fees would exceed the "
                    f"{r.params['max_fees']:,.2f} fee budget."
                )))
            else:
                findings.append(Finding(kind, False, f"Fees (≈{projected:,.2f}) within budget."))

        elif kind == "max_sizing_multiplier":
            if intent.base_unit > 0 and intent.notional > intent.base_unit * r.params["max_mult"]:
                any_block = True
                findings.append(Finding(kind, True, (
                    f"Intended size is {intent.notional/intent.base_unit:.1f}x base unit — "
                    f"that's streak-driven greed."
                )))
                final_notional = intent.base_unit * r.params["max_mult"]
            else:
                findings.append(Finding(kind, False, "Sizing within cap."))

    # A DOWNSIZE if we shrank the order but nothing forced a full block,
    # or if the only findings were WARN-style caps that reduce size.
    if any_block:
        action = "BLOCK"
    elif final_notional < intent.notional * 0.999:
        action = "DOWNSIZE"
    else:
        action = "APPROVE"

    return Verdict(action, max(0.0, final_notional), findings)


def plain_english(verdict: Verdict, intent: OrderIntent) -> str:
    """One tight paragraph the user reads / a narrator says.

    Prefer the most *decision-relevant* finding: for a block pick the first hard
    stop; for a downsized order pick the finding that shrank it.
    """
    if verdict.action == "BLOCK":
        core = next((f.message for f in verdict.findings if f.blocked), "")
        why = intent.agent_why or f"the trading agent wants to {intent.side} {intent.symbol}"
        return (f"I'd stop this one. {why} — but {core or 'it breaks your rules.'} "
                f"Nothing's been placed.")
    if verdict.action == "DOWNSIZE":
        # the finding that shrank it is the cap/limit message
        shrink = next((f.message for f in verdict.findings
                       if any(k in f.rule for k in ("max_position", "max_total", "max_sizing"))), "")
        return (f"Not a hard no — but I'd cut it to {verdict.proposed_notional:,.0f} USDC "
                f"({verdict.proposed_notional/intent.notional*100:.0f}% of what was asked). "
                f"{shrink or 'It exceeds your sizing limits.'}")
    # APPROVE
    ok = next((f.message for f in verdict.findings if not f.blocked), "")
    return f"This fits the rules ({ok}). Going ahead at {intent.notional:,.0f} USDC after your OK."
