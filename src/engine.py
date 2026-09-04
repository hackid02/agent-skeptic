"""Simulated Agentic sub-account + a deliberately 'human-flawed' trading agent.

This backs the Reflection feature: it shows what happens when the same agent
trades WITHOUT the Skeptic's rules vs WITH them, on identical market data. The
sub-account mirrors Agent OS's security model: isolated, no external withdrawals,
confirm-before-execute.
"""
from __future__ import annotations

import dataclasses
import statistics
from typing import List, Optional

from .market import Bar


@dataclasses.dataclass
class Decision:
    ts: int
    symbol: str
    price: float
    action: str
    notional: float
    vol: float
    why: str
    outcome: float = 0.0
    tag: str = ""


class SubAccount:
    def __init__(self, cash: float):
        self.cash = cash
        self.position = 0.0
        self.entry = 0.0

    def equity(self, price: float) -> float:
        return self.cash + self.position * price


class FlawedTrader:
    """Chases momentum, oversizes after wins, overtrades, ignores volatility."""

    def __init__(self, cash: float, fee_rate: float = 0.001, use_guardrails: bool = False,
                 rulebook=None):
        self.cash0 = cash
        self.fee_rate = fee_rate
        self.use_guardrails = use_guardrails
        self.rulebook = rulebook or []

    def run(self, bars: List[Bar]) -> tuple[List[Decision], List[float]]:
        cash = self.cash0
        position = 0.0
        entry = 0.0
        peak = cash
        fees_paid = 0.0
        streak = 0
        decisions: List[Decision] = []
        equity_curve: List[float] = []
        base_unit = cash * 0.10  # base sizing
        open_exposure = 0.0

        def equity(price):
            return cash + position * price

        last_trade = -99
        for i in range(1, len(bars)):
            price = bars[i].close
            # momentum + vol
            closes = [b.close for b in bars[max(0, i-20):i]]
            momentum = (closes[-1] - closes[0]) / closes[0] if len(closes) > 1 else 0.0
            rets = [(closes[k]-closes[k-1])/closes[k-1] for k in range(1, len(closes))]
            vol = statistics.pstdev(rets) if len(rets) > 1 else 0.0

            action = "HOLD"
            notional = 0.0
            why = "no edge"
            tag = "hold"
            proposed = None

            if i - last_trade >= 3:
                if position > 0:
                    if momentum < -0.004 or vol > 0.03:
                        action, notional, why, tag = "SELL", position*price, "momentum faded; ring-fence", "exit"
                    else:
                        why = "in position"
                elif momentum > 0 and vol < 0.05:
                    notional = base_unit * (1 + min(streak, 4) * 0.25)
                    if streak >= 3:
                        why, tag = f"momentum {momentum:+.2%}; sizing up after {streak}-win streak", "overconfident"
                    else:
                        why, tag = f"momentum {momentum:+.2%} & calm vol", "entry"
                    action = "BUY"
                    proposed = notional

            # Guardrails: route through the risk desk if enabled
            if self.use_guardrails and proposed:
                from .riskdesk import OrderIntent, evaluate, plain_english
                from .rulebook import applicable_rules
                intent = OrderIntent(symbol="BTC", side="BUY", notional=proposed, price=price,
                                     vol=vol, agent_why=why, base_unit=base_unit)
                v = evaluate(intent, applicable_rules(self.rulebook), equity=equity(price),
                             open_exposure=open_exposure, peak_equity=max(peak, equity(price)),
                             fees_paid=fees_paid)
                if v.action == "BLOCK":
                    action, notional, why, tag = "HOLD", 0.0, f"REFUSED: {plain_english(v, intent)}", "blocked"
                elif v.action == "DOWNSIZE":
                    notional = v.proposed_notional
                    why += f" -> down-sized to {notional:,.0f} USDC by guardrails"

            # execute
            if action == "BUY":
                notional = min(notional, cash)
                if notional <= 0:
                    action, why, tag = "HOLD", "insufficient cash", "hold"
                else:
                    fee = notional * self.fee_rate
                    cash -= notional + fee
                    fees_paid += fee
                    position += notional / price
                    entry = price
                    open_exposure = notional
                    last_trade = i
                    streak = streak + 1 if (price > entry) else streak  # simple
            elif action == "SELL" and position > 0:
                gross = position * price
                fee = gross * self.fee_rate
                cash += gross - fee
                fees_paid += fee
                pnl = (price - entry) * position
                streak = streak + 1 if pnl > 0 else -1
                position = 0.0
                open_exposure = 0.0
                last_trade = i

            decisions.append(Decision(bars[i].timestamp, "BTC", price, action, notional, vol, why, tag=tag))
            equity_curve.append(equity(price))
            peak = max(peak, equity(price))

        # liquidate
        if position > 0:
            last = bars[-1]
            cash += position * last.close
            position = 0.0
        return decisions, equity_curve
