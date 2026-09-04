"""The Skeptic's rulebook: explicit, auditable risk rules a trader/approver owns.

Each rule has a kind, parameters, a plain-English explanation (what the humans
see), and a severity. Rules are the *contract* between the user and the agent —
they're what makes Agent OS's 'your rules, your agents' real. The agent can
propose rules (via Reflection) but the human owns them.
"""
from __future__ import annotations

import dataclasses
from typing import List, Optional


@dataclasses.dataclass
class Rule:
    kind: str
    params: dict
    label: str
    severity: str = "WARN"   # "BLOCK" (stop the order) | "WARN" (flag, allow)
    source: str = "policy"   # "policy" default, or "reflection" (learned)

    def describe(self) -> str:
        return self.label


DEFAULT_RULES: List[Rule] = [
    Rule(
        kind="max_position_pct",
        params={"max": 0.10},
        label="Never commit more than 10% of the account to a single position.",
        severity="BLOCK",
    ),
    Rule(
        kind="max_total_exposure",
        params={"max": 0.40},
        label="Keep total open exposure under 40% of equity.",
        severity="BLOCK",
    ),
    Rule(
        kind="drawdown_guard",
        params={"max_dd": 0.05},
        label="Stop adding risk if the account is already down 5% from its peak.",
        severity="BLOCK",
    ),
    Rule(
        kind="volatility_band",
        params={"min": 0.004, "max": 0.03},
        label="Only add risk when recent volatility is inside a sane band (no dead markets, no chaos).",
        severity="BLOCK",
    ),
    Rule(
        kind="fee_budget",
        params={"max_fees": 8.0},
        label="Don't let cumulative fees on this window exceed the fee budget.",
        severity="BLOCK",
    ),
    Rule(
        kind="max_sizing_multiplier",
        params={"max_mult": 2.0},
        label="Never size a position more than 2x your base unit — kills streak-based greed.",
        severity="BLOCK",
    ),
    Rule(
        kind="rebalance_target",
        params={"allow": True},
        label="Risk-reducing orders (trimming a big position) are always allowed.",
        severity="BLOCK",
    ),
]


def applicable_rules(rulebook: List[Rule]) -> List[Rule]:
    """Return rules that actually constrain (skip purely-allow rules)."""
    return [r for r in rulebook if r.kind != "rebalance_target"]
