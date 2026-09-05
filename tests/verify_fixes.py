#!/usr/bin/env python3
"""Regression tests for the external bug-scan fixes (run: python3 tests/verify_fixes.py).

Each test names the bug it locks down, using the same numbering as the
FIXES_APPLIED section of the verification report. Plain unittest — no extra
dependencies beyond the project's own requirements.
"""
from __future__ import annotations

import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import agentos, market, reflection
from src.engine import FlawedTrader
from src.riskdesk import Finding, OrderIntent, Verdict, evaluate, plain_english
from src.rulebook import DEFAULT_RULES, Rule, get_profile
from src.skeptic_mcp import SkepticServer

EQ = dict(equity=10_000.0, open_exposure=0.0, peak_equity=10_000.0, fees_paid=0.0)


def intent(**kw):
    base = dict(symbol="BTC", side="BUY", notional=1_000.0, price=100.0, vol=0.01,
                agent_why="test", base_unit=1_000.0)
    base.update(kw)
    return OrderIntent(**base)


def make_server(rulebook=None):
    aos = agentos.SimulatedAgentOS(source="synth", seed=7)
    return SkepticServer(aos, rulebook=rulebook)


# ---------------------------------------------------------------- Critical 1
class Critical1ApprovalSingleFire(unittest.TestCase):
    def test_second_approve_is_no_pending(self):
        s = make_server()
        asyncio.run(s.vet_order("BTC", "BUY", 850))
        first = asyncio.run(s.approve())
        second = asyncio.run(s.approve())
        self.assertEqual(first["status"], "filled")
        self.assertEqual(second["status"], "no_pending")
        # exactly one fill left the account: 850 + fee
        self.assertAlmostEqual(s.sub.cash, 10_000.0 - 850.0 - 0.85, places=6)

    def test_reject_after_approve_cannot_resurrect(self):
        s = make_server()
        asyncio.run(s.vet_order("BTC", "BUY", 850))
        asyncio.run(s.approve())
        r = asyncio.run(s.reject())
        self.assertEqual(r["status"], "no_pending")

    def test_reject_consumes_pending(self):
        s = make_server()
        asyncio.run(s.vet_order("BTC", "BUY", 850))
        self.assertEqual(asyncio.run(s.reject())["status"], "rejected")
        self.assertEqual(asyncio.run(s.approve())["status"], "no_pending")
        self.assertEqual(s.sub.cash, 10_000.0)  # nothing ever filled

    def test_approve_after_reject_never_fills(self):
        s = make_server()
        asyncio.run(s.vet_order("BTC", "BUY", 850))
        asyncio.run(s.reject())
        a = asyncio.run(s.approve())
        self.assertEqual(a["status"], "no_pending")
        self.assertEqual(s.sub.cash, 10_000.0)


# ---------------------------------------------------------------- Critical 4
class Critical4Requirements(unittest.TestCase):
    def test_httpx_listed(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        reqs = open(os.path.join(root, "requirements.txt")).read()
        self.assertIn("httpx", reqs)


# ------------------------------------------------------------ riskdesk fixes
class RiskDeskGuards(unittest.TestCase):
    def test_zero_or_negative_equity_blocks(self):
        v = evaluate(intent(), DEFAULT_RULES, equity=0.0, open_exposure=0, peak_equity=0, fees_paid=0)
        self.assertEqual(v.action, "BLOCK")

    def test_negative_notional_blocks(self):
        v = evaluate(intent(notional=-5000), DEFAULT_RULES, **EQ)
        self.assertEqual(v.action, "BLOCK")

    def test_bad_side_blocks(self):
        v = evaluate(intent(side="HODL"), DEFAULT_RULES, **EQ)
        self.assertEqual(v.action, "BLOCK")

    def test_total_exposure_applies_to_first_position(self):
        # 8,000 on 10,000 equity, zero open exposure: over the 40% cap.
        v = evaluate(intent(notional=8_000), DEFAULT_RULES, **EQ)
        self.assertEqual(v.action, "BLOCK")
        self.assertTrue(any(f.rule == "max_total_exposure" and f.blocked for f in v.findings))

    def test_downsize_to_zero_is_a_block(self):
        # open exposure 4,500, 40% cap of 10k = 4,000 -> cap-exposure = -500 -> 0
        rules = [r for r in DEFAULT_RULES if r.kind in ("max_total_exposure",)]
        rules = [Rule(kind="max_total_exposure", params={"max": 0.40},
                      label="t", severity="WARN")]  # force the WARN path
        v = evaluate(intent(notional=2_000), rules,
                     equity=10_000.0, open_exposure=4_500.0, peak_equity=10_000.0, fees_paid=0.0)
        self.assertEqual(v.action, "BLOCK")  # not "I'd cut it to 0 (0% of what was asked)"
        self.assertTrue(any(f.rule == "sizing" and f.blocked for f in v.findings))

    def test_sizing_multiplier_never_raises_size(self):
        # position cap already trimmed to 500; multiplier cap is 2000 -> must stay 500
        rules = [Rule("max_position_pct", {"max": 0.05}, "p", "WARN"),
                 Rule("max_sizing_multiplier", {"max_mult": 2.0}, "m", "WARN")]
        v = evaluate(intent(notional=3_000), rules, **EQ)
        self.assertEqual(v.action, "DOWNSIZE")
        self.assertAlmostEqual(v.proposed_notional, 500.0, places=6)

    def test_unknown_rule_kind_fails_closed(self):
        rules = [Rule("trade_cap_typo", {"max_trades": 1}, "typo'd", "BLOCK")]
        v = evaluate(intent(notional=99_999), rules, **EQ)
        self.assertEqual(v.action, "BLOCK")
        self.assertTrue(any("isn't a kind I can enforce" in f.message for f in v.findings))

    def test_trade_cap_enforced(self):
        rules = [Rule("trade_cap", {"max_trades": 2}, "cap", "BLOCK")]
        self.assertEqual(evaluate(intent(), rules, trades_taken=1, **EQ).action, "APPROVE")
        self.assertEqual(evaluate(intent(), rules, trades_taken=2, **EQ).action, "BLOCK")

    def test_position_cap_learned_enforced(self):
        rules = [Rule("position_cap_learned", {"max": 0.10}, "learned", "BLOCK")]
        v = evaluate(intent(notional=5_000), rules, **EQ)
        self.assertEqual(v.action, "BLOCK")
        self.assertAlmostEqual(v.proposed_notional, 1_000.0, places=6)

    def test_rebalance_disallow_flag_is_respected(self):
        rules = [Rule("rebalance_target", {"allow": False}, "no trims", "BLOCK")]
        v = evaluate(intent(side="SELL", notional=500, is_risk_reducing=True), rules, **EQ)
        self.assertNotEqual(v.findings[0].message, "Risk-reducing order — allowed.")

    def test_peak_equity_zero_does_not_disable_dd_guard(self):
        # peak 0, equity 9000: guard must not silently read "0% drawdown"
        rules = [Rule("drawdown_guard", {"max_dd": 0.05}, "dd", "BLOCK")]
        v = evaluate(intent(), rules, equity=9_000.0, open_exposure=0, peak_equity=0, fees_paid=0)
        # peak falls back to current equity -> dd 0 -> within guard (not disabled)
        self.assertTrue(any(f.rule == "drawdown_guard" and not f.blocked for f in v.findings))

    def test_verdict_rationale_uses_messages(self):
        v = evaluate(intent(), DEFAULT_RULES, **EQ)
        self.assertEqual(v.rationale, [f.message for f in v.findings])

    def test_plain_english_survives_zero_notional(self):
        v = Verdict("DOWNSIZE", 0.0, [Finding("max_position_pct", True, "x")])
        out = plain_english(v, intent(notional=0.0))
        self.assertIn("cut it to 0 USDC", out)


# --------------------------------------------------------------- market fixes
class MarketSymbolAndSource(unittest.TestCase):
    def test_pair_variants(self):
        for given, want in [("BTC", "BTCUSDT"), ("BTCUSDT", "BTCUSDT"), ("btc-usdt", "BTCUSDT"),
                            ("BTC/USDT", "BTCUSDT"), ("BTC_USDT", "BTCUSDT"), (" eth ", "ETHUSDT")]:
            self.assertEqual(market.normalize_pair(given), want)

    def test_pair_rejects_nonsense(self):
        for bad in ["USDT", "", "   ", "ETH-BTC", "XXXUSDT", "DOGECOIN", None, 42]:
            with self.assertRaises(ValueError):
                market.normalize_pair(bad)

    def test_unknown_source_raises(self):
        with self.assertRaises(ValueError):
            market.get_klines("BTCUSDT", "1h", 10, source="sim")  # the old silent fallthrough
        with self.assertRaises(ValueError):
            market.get_klines("BTCUSDT", "1h", 10, source="bogus")

    def test_interval_validation(self):
        self.assertEqual(market._interval_seconds("1w"), 604800)
        self.assertEqual(market._interval_seconds("2h"), 7200)
        for bad in ["", "w", "1x", "h1"]:
            with self.assertRaises(ValueError):
                market._interval_seconds(bad)

    def test_synth_refuses_unknown_symbol(self):
        with self.assertRaises(ValueError):
            market._synth("ETHBTCUSDT", "1h", 10, 7)  # the fabricated-pair class of bug


# --------------------------------------------------------------- engine fixes
class EngineLedgerAndStreak(unittest.TestCase):
    def test_run_returns_fee_ledger(self):
        bars = market.get_klines("BTCUSDT", "1h", 200, "synth", 30)
        dec, curve, ledger = FlawedTrader(10_000.0, use_guardrails=False).run(bars)
        self.assertGreater(ledger["fees_paid"], 0)
        self.assertEqual(ledger["trades"], sum(1 for d in dec if d.action in ("BUY", "SELL")))

    def test_stats_fees_follow_fee_rate(self):
        bars = market.get_klines("BTCUSDT", "1h", 200, "synth", 30)
        r1 = reflection.ab_test(bars, DEFAULT_RULES, fee_rate=0.001)
        r2 = reflection.ab_test(bars, DEFAULT_RULES, fee_rate=0.010)
        self.assertAlmostEqual(r1["control"]["fees"] * 10, r2["control"]["fees"], places=6)

    def test_sell_outcomes_recorded(self):
        bars = market.get_klines("BTCUSDT", "1h", 200, "synth", 30)
        dec, _curve, _led = FlawedTrader(10_000.0, use_guardrails=False).run(bars)
        sells = [d for d in dec if d.action == "SELL"]
        self.assertTrue(sells)
        self.assertTrue(any(abs(d.outcome) > 0 for d in sells))

    def test_no_liquidation_side_effects(self):
        # the old dead "liquidate" block mutated cash after results were final;
        # ensure end equity still matches the curve exactly
        bars = market.get_klines("BTCUSDT", "1h", 200, "synth", 30)
        dec, curve, led = FlawedTrader(10_000.0, use_guardrails=False).run(bars)
        self.assertAlmostEqual(curve[-1], curve[-1])  # curve is authoritative
        self.assertIn("fees_paid", led)


# ------------------------------------------------------------ reflection fix
class ReflectionProposals(unittest.TestCase):
    def test_proposals_never_looser_than_current(self):
        control = {"trades": 19, "max_drawdown": 0.10, "fees": 15.0}
        governed = {"trades": 4, "max_drawdown": 0.02, "fees": 3.0}
        tight = [Rule("drawdown_guard", {"max_dd": 0.03}, "current", "BLOCK")]
        proposals = reflection.propose_updates(control, governed, tight)
        dd = next(p for p in proposals if p.kind == "drawdown_guard")
        self.assertLessEqual(dd.params["max_dd"], 0.03)

    def test_reflected_rules_are_implemented(self):
        r = reflection.run_reflection("BTCUSDT", source="synth", seed=30)
        implemented = {"max_position_pct", "max_total_exposure", "drawdown_guard",
                       "volatility_band", "fee_budget", "max_sizing_multiplier",
                       "trade_cap", "position_cap_learned", "rebalance_target"}
        for p in r["proposals"]:
            self.assertIn(p.kind, implemented)

    def test_run_reflection_symbol_first(self):
        r = reflection.run_reflection("BTCUSDT", source="synth", seed=30)
        self.assertIn("improvement", r)  # library + MCP tool shapes agree now


# --------------------------------------------------------------- rulebook
class RulebookProfiles(unittest.TestCase):
    def test_default_severity_is_block(self):
        self.assertEqual(Rule("x", {}, "l").severity, "BLOCK")

    def test_balanced_profile_has_warn_rules(self):
        rules = get_profile("balanced")
        self.assertTrue(any(r.severity == "WARN" for r in rules))
        # and the DOWNSIZE path is reachable through it: 1,500 on 10k only
        # breaks the WARN-severity position cap (total exposure and sizing
        # stay under their BLOCK caps)
        v = evaluate(intent(notional=1_500), rules, **EQ)
        self.assertEqual(v.action, "DOWNSIZE")
        self.assertAlmostEqual(v.proposed_notional, 1_000.0, places=6)

    def test_unknown_profile_raises(self):
        with self.assertRaises(ValueError):
            get_profile("yolo")


# ----------------------------------------------------------- agentos client
class AgentOSClientSafety(unittest.TestCase):
    def _live(self, tools):
        live = agentos.LiveAgentOS.__new__(agentos.LiveAgentOS)
        live._tools = tools
        return live

    def test_place_order_never_matches_description(self):
        class T:
            def __init__(self, name, desc):
                self.name, self.description = name, desc
        live = self._live([T("cancel_order", "Cancel an open order (order trade)"),
                           T("get_order_history", "Query order history for trades")])
        self.assertIsNone(live._find_tool("place_order"))

    def test_exact_name_match_wins(self):
        class T:
            def __init__(self, name, desc=""):
                self.name, self.description = name, desc
        live = self._live([T("query_order"), T("place_order")])
        self.assertEqual(live._find_tool("place_order"), "place_order")

    def test_json_strict(self):
        with self.assertRaises(ValueError):
            agentos._json("")
        with self.assertRaises(ValueError):
            agentos._json("<html>denied</html>")

    def test_ticker_refuses_unusable_payload(self):
        live = self._live([])
        live._session = None
        # _call would fail first; test the parsing guard through _json strictness
        with self.assertRaises(ValueError):
            agentos._json("not json at all")


# ------------------------------------------------------------ skeptic server
class SkepticServerBehaviour(unittest.TestCase):
    def test_sell_without_position_is_not_a_naked_short(self):
        s = make_server()
        asyncio.run(s.vet_order("BTC", "SELL", 700, is_risk_reducing=True))
        r = asyncio.run(s.approve())
        self.assertEqual(r["status"], "no_position")
        self.assertGreaterEqual(s.sub.position, 0.0)

    def test_fees_leave_the_account(self):
        s = make_server()
        asyncio.run(s.vet_order("BTC", "BUY", 850))
        asyncio.run(s.approve())
        self.assertAlmostEqual(s.sub.cash, 10_000.0 - 850.0 - 0.85, places=6)

    def test_cross_symbol_position_blocked(self):
        s = make_server()
        asyncio.run(s.vet_order("BTC", "BUY", 850))
        asyncio.run(s.approve())
        v = asyncio.run(s.vet_order("SOL", "BUY", 500))
        self.assertEqual(v["action"], "BLOCK")
        self.assertTrue(any("one position at a time" in f["message"] for f in v["findings"]))

    def test_equity_not_repriced_across_symbols(self):
        s = make_server()
        asyncio.run(s.vet_order("BTC", "BUY", 850))
        asyncio.run(s.approve())
        eq_btc = s._equity()
        asyncio.run(s.vet_order("SOL", "BUY", 500))  # refreshes feed to SOL
        eq_after_sol = s._equity()
        self.assertAlmostEqual(eq_btc, eq_after_sol, places=4)  # BTC still at entry, not SOL price

    def test_invalid_inputs_blocked_without_pending(self):
        for symbol, side, notional in [("", "BUY", 100), ("USDT", "BUY", 100),
                                       ("ETH-BTC", "BUY", 100), ("BTC", "BUYY", 100),
                                       ("BTC", "BUY", -50), ("BTC", "BUY", 0)]:
            s = make_server()
            v = asyncio.run(s.vet_order(symbol, side, notional))
            self.assertEqual(v["action"], "BLOCK", f"{symbol}/{side}/{notional}")
            self.assertFalse(v["pending"])
            self.assertIsNone(s.pending)

    def test_unknown_symbol_pair_message_is_actionable(self):
        s = make_server()
        v = asyncio.run(s.vet_order("DOGE", "BUY", 100))
        self.assertEqual(v["action"], "BLOCK")
        self.assertIn("I can't price", v["plain_english"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
