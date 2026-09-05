"""The Skeptic's judgement: turn an incoming order intent into a verdict + rationale.

This is the 'confirm-before-execute' brain from Agent OS. It evaluates an intent
against the rulebook and produces a human-readable `why`, then the human approves.
"""
from __future__ import annotations

import dataclasses
from typing import List

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
        return [f.message for f in self.findings]


def evaluate(intent: OrderIntent, rulebook: List[Rule], *, equity: float,
             open_exposure: float, peak_equity: float, fees_paid: float,
             trades_taken: int = 0) -> Verdict:
    """Judge `intent`. Returns a verdict and the human-facing explanation.

    severity/decisions:
      - risk-reducing orders are always fine (trim exposure), unless a
        rebalance_target rule has explicitly disallowed them.
      - a violated rule with severity "BLOCK" (or default) refuses the order.
      - a violated rule with severity "WARN" only downgrades size (DOWNSIZE).
      - size caps always trim the order to the cap, even when the order is
        otherwise blocked, so the "why" reflects the real ceiling.
      - a rule kind this evaluator doesn't implement is treated as violated
        (fail-closed) rather than silently ignored.
    """
    # -- input sanity: refuse nonsense before any rule runs -----------------
    if intent.side not in ("BUY", "SELL"):
        return Verdict("BLOCK", 0.0, [Finding("input", True, (
            f"Side '{intent.side}' isn't BUY or SELL — I can't vet that."))])
    if intent.notional != intent.notional or intent.notional <= 0:  # NaN or non-positive
        return Verdict("BLOCK", 0.0, [Finding("input", True, (
            f"Notional {intent.notional!r} isn't a positive size — refusing."))])
    if equity <= 0:
        return Verdict("BLOCK", 0.0, [Finding("account", True, (
            "Account equity is zero or negative — no new risk until that's fixed."))])

    if intent.is_risk_reducing:
        disallowed = any(r.kind == "rebalance_target" and r.params.get("allow") is False
                         for r in rulebook)
        if not disallowed:
            return Verdict("APPROVE", intent.notional,
                           [Finding("rebalance_target", False,
                                    "Risk-reducing order — allowed.")])
        # allow=False: fall through and vet it like any other order, with an
        # explicit finding so the verdict says why the trim wasn't auto-allowed.

    findings: List[Finding] = []
    final_notional = intent.notional
    blocked = False     # a hard BLOCK-severity violation -> refuse
    reduced = False     # a WARN-severity violation / a trimmed cap -> downsize

    for r in rulebook:
        kind = r.kind

        if kind == "rebalance_target":
            # Consumed by the risk-reducing gate above; if the user disallowed
            # trims, say so explicitly rather than silently vetting nothing.
            if r.params.get("allow") is False:
                findings.append(Finding(kind, True, (
                    "Risk-reducing orders are currently disallowed by your rulebook — "
                    "vetting this like any new risk.")))
                if r.severity == "WARN":
                    reduced = True
                else:
                    blocked = True
            continue

        if kind in ("max_position_pct", "position_cap_learned"):
            cap = r.params["max"] * equity
            if intent.notional > cap:
                findings.append(Finding(kind, True, (
                    f"{intent.symbol} {intent.notional:,.0f} USDC is {intent.notional/equity:.0%} of the "
                    f"account, above the {r.params['max']:.0%} single-position cap "
                    f"({cap:,.2f} USDC at current equity)."
                )))
                final_notional = min(final_notional, cap)
                if r.severity == "WARN":
                    reduced = True
                else:
                    blocked = True
            else:
                findings.append(Finding(kind, False, f"Size OK ({intent.notional/equity:.0%} of account)."))

        elif kind == "max_total_exposure":
            proj = open_exposure + intent.notional
            cap = r.params["max"] * equity
            if proj > cap:
                findings.append(Finding(kind, True, (
                    f"Adding {intent.notional:,.0f} would push total exposure to {proj/equity:.0%}, "
                    f"over the {r.params['max']:.0%} cap."
                )))
                final_notional = min(final_notional, cap - open_exposure)
                if r.severity == "WARN":
                    reduced = True
                else:
                    blocked = True
            elif open_exposure == 0:
                findings.append(Finding(kind, False, "No other open exposure — fine."))
            else:
                findings.append(Finding(kind, False, (
                    f"Total exposure would be {proj/equity:.0%} — within the "
                    f"{r.params['max']:.0%} cap.")))

        elif kind == "drawdown_guard":
            peak = peak_equity if peak_equity > 0 else equity  # never silently disables
            dd = (peak - equity) / peak if peak > 0 else 0.0
            if dd >= r.params["max_dd"]:
                findings.append(Finding(kind, True, (
                    f"Account is down {dd:.1%} from its peak ({r.params['max_dd']:.0%} guard) — "
                    f"no new risk until it recovers."
                )))
                if r.severity == "WARN":
                    reduced = True
                else:
                    blocked = True
            else:
                findings.append(Finding(kind, False, f"Drawdown {dd:.1%} is within guard."))

        elif kind == "volatility_band":
            lo, hi = r.params["min"], r.params["max"]
            if intent.vol > hi:
                findings.append(Finding(kind, True, (
                    f"Recent volatility {intent.vol:.2%} is above the {hi:.2%} ceiling — "
                    f"buying the spike, not the trend."
                )))
                if r.severity == "WARN":
                    reduced = True
                else:
                    blocked = True
            elif intent.vol < lo:
                findings.append(Finding(kind, True, (
                    f"Recent volatility {intent.vol:.2%} is below the {lo:.2%} floor — "
                    f"no edge, just noise."
                )))
                if r.severity == "WARN":
                    reduced = True
                else:
                    blocked = True
            else:
                findings.append(Finding(kind, False, f"Volatility {intent.vol:.2%} is in band."))

        elif kind == "fee_budget":
            projected = fees_paid + intent.notional * 0.001 * 2  # round-trip fee
            if projected > r.params["max_fees"]:
                findings.append(Finding(kind, True, (
                    f"~{projected:,.2f} USDC of round-trip fees would exceed the "
                    f"{r.params['max_fees']:,.2f} fee budget."
                )))
                if r.severity == "WARN":
                    reduced = True
                else:
                    blocked = True
            else:
                findings.append(Finding(kind, False, f"Fees (≈{projected:,.2f}) within budget."))

        elif kind == "max_sizing_multiplier":
            if intent.base_unit > 0 and intent.notional > intent.base_unit * r.params["max_mult"]:
                findings.append(Finding(kind, True, (
                    f"Intended size is {intent.notional/intent.base_unit:.1f}x base unit — "
                    f"that's streak-driven greed."
                )))
                # Take the minimum like every other cap — never size back up.
                final_notional = min(final_notional, intent.base_unit * r.params["max_mult"])
                if r.severity == "WARN":
                    reduced = True
                else:
                    blocked = True
            else:
                findings.append(Finding(kind, False, "Sizing within cap."))

        elif kind == "trade_cap":
            max_trades = int(r.params.get("max_trades", 0))
            if trades_taken + 1 > max_trades:
                findings.append(Finding(kind, True, (
                    f"This would be trade {trades_taken + 1} of the window — over the "
                    f"cap of {max_trades}."
                )))
                if r.severity == "WARN":
                    reduced = True
                else:
                    blocked = True
            else:
                findings.append(Finding(kind, False, (
                    f"Trade {trades_taken + 1} of {max_trades} allowed this window.")))

        else:
            # Unknown rule kind: fail closed. A typo'd rule in a user-owned
            # rulebook must never silently disable itself.
            findings.append(Finding(r.kind, True, (
                f"Rule '{r.kind}' ({r.label}) isn't a kind I can enforce — "
                f"I treat that as violated rather than guess."
            )))
            if r.severity == "WARN":
                reduced = True
            else:
                blocked = True

    # A DOWNSIZE if we only had WARN-severity warnings (flagged, not refused) or
    # the order was trimmed to a cap; a BLOCK if any BLOCK-severity rule fired.
    if final_notional <= 0:
        # "Downsize to zero" is a refusal wearing a nicer coat.
        blocked = True
        findings.append(Finding("sizing", True, (
            "After applying your caps there's nothing left of this order — "
            "that's a refuse, not a trim.")))
    if blocked:
        action = "BLOCK"
    elif reduced or final_notional < intent.notional * 0.999:
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
        if 0 < intent.notional and verdict.proposed_notional >= intent.notional * 0.995:
            # Trimmed by a hair (fees ate into the cap): say so plainly
            # instead of the confusing "cut to 1,000 (100% of what was asked)".
            return (f"Not a hard no — but I'd trim it right to the cap: "
                    f"{verdict.proposed_notional:,.2f} USDC. "
                    f"{shrink or 'It exceeds your sizing limits.'}")
        pct = (verdict.proposed_notional / intent.notional * 100) if intent.notional > 0 else 0.0
        return (f"Not a hard no — but I'd cut it to {verdict.proposed_notional:,.0f} USDC "
                f"({pct:.0f}% of what was asked). "
                f"{shrink or 'It exceeds your sizing limits.'}")
    # APPROVE
    ok = next((f.message for f in verdict.findings if not f.blocked), "")
    return f"This fits the rules ({ok}). Going ahead at {intent.notional:,.0f} USDC after your OK."
