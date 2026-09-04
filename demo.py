"""The Skeptic — demo orchestrator.

Two modes:
  1. THE GATE   : incoming order intents (as if the trading agent just proposed
                  them) -> the Skeptic vets each against the rulebook, gives a
                  plain-English verdict, and asks YOU to approve.
  2. REFLECTION : the Skeptic reviews how it behaved, runs a same-market A/B
                  (no guardrails vs guardrails), and proposes rulebook updates.

Run:
  python3 demo.py                # scripted, auto-approves (great for the video)
  python3 demo.py --interactive  # you type Y/n for each order
  python3 demo.py --source live  # real coin market data
"""
from __future__ import annotations

import argparse
import os
from typing import List

from src.rulebook import DEFAULT_RULES, applicable_rules
from src.riskdesk import OrderIntent, evaluate, plain_english, Verdict
from src.market import get_klines, recent_volatility, last_price
from src.reflection import run_reflection

ACCOUNT = 10_000.0


def header(t):
    print("\n" + "=" * 76)
    print(f"  {t}")
    print("=" * 76)


def intro():
    header("THE SKEPTIC — your agent's risk desk")
    print("""
  Trading agent : "I think we should buy."
  The Skeptic   : "Let me check your rules first."

  I sit between your AI agent and your money. I refuse reckless trades, tell you
  why in plain English, and YOU make the final call. Nothing executes without
  your OK. No real funds, no orders, no keys.
""")


def verdict_block(intent: OrderIntent, rulebook, *, equity, open_exposure, peak, fees, auto=True) -> Verdict:
    v = evaluate(intent, applicable_rules(rulebook), equity=equity, open_exposure=open_exposure,
                 peak_equity=peak, fees_paid=fees)
    print(f"\n  Agent wants: {intent.side} {intent.symbol} ~{intent.notional:,.0f} USDC"
          f"  (vol {intent.vol:.2%}, base {intent.base_unit:,.0f})")
    print(f"  Reason given: {intent.agent_why or '—'}")
    for f in v.findings:
        mark = "✗" if f.blocked else "·"
        print(f"    {mark} {f.message}")
    print(f"\n  ⚖  {plain_english(v, intent)}")
    action = v.action
    if action in ("APPROVE", "DOWNSIZE"):
        if auto:
            print("  ✅ Approved (auto, for the demo).")
        else:
            ans = input("  Approve this order? [Y/n]: ").strip().lower()
            if ans.startswith("n"):
                print("  ⏹  Skipped — you said no.")
    return v


def gate_demo(auto=True, source="synth", seed=7):
    bars = get_klines("BTCUSDT", "1h", 200, source=source, seed=seed)
    price = last_price(bars)
    vol = recent_volatility(bars)

    header("SCENE 1 — An oversized, no-plan buy")
    print(f"  (account {ACCOUNT:,.0f} USDC | market {price:,.0f} | recent vol {vol:.2%})")
    verdict_block(
        OrderIntent("BTC", "BUY", 4200, price, vol,
                    "momentum looks good, let's go big",
                    base_unit=1000),
        DEFAULT_RULES, equity=ACCOUNT, open_exposure=0, peak=ACCOUNT, fees=0, auto=auto)

    header("SCENE 2 — A disciplined entry")
    verdict_block(
        OrderIntent("BTC", "BUY", 850, price, vol,
                    "momentum aligned, size is modest",
                    base_unit=1000),
        DEFAULT_RULES, equity=ACCOUNT, open_exposure=0, peak=ACCOUNT, fees=0, auto=auto)

    header("SCENE 3 — Greed after a win streak")
    verdict_block(
        OrderIntent("SOL", "BUY", 3600, 150, vol,
                    "we're on a 4-win streak, let's size up",
                    base_unit=1000),
        DEFAULT_RULES, equity=ACCOUNT, open_exposure=850, peak=ACCOUNT, fees=1.5, auto=auto)

    header("SCENE 4 — Buying the chaos")
    verdict_block(
        OrderIntent("BTC", "BUY", 1000, price, min(0.08, vol + 0.05),
                    "big move, don't want to miss it",
                    base_unit=1000),
        DEFAULT_RULES, equity=ACCOUNT, open_exposure=850, peak=ACCOUNT, fees=1.5, auto=auto)

    header("SCENE 5 — Trimming risk (always allowed)")
    verdict_block(
        OrderIntent("BTC", "SELL", 700, price, vol,
                    "reduce exposure before the weekend",
                    base_unit=1000, is_risk_reducing=True),
        DEFAULT_RULES, equity=ACCOUNT, open_exposure=1500, peak=ACCOUNT, fees=2.0, auto=auto)


def reflection_demo(source="synth", seed=7):
    header("REFLECTION — does it actually help?")
    print("\n  Same market, same trading agent. One runs unwatched, one runs under")
    print("  the Skeptic's rules. Here's what happened:\n")

    r = run_reflection(source=source, seed=seed)
    c, g = r["control"], r["governed"]

    def fmt(v):
        return f"${v:,.0f}"

    print(f"  {'Metric':<26}{'No guardrails':<16}{'With Skeptic':<16}")
    print("  " + "-" * 56)
    rows = [
        ("Trades taken", c["trades"], g["trades"]),
        ("Max drawdown", f"{c['max_drawdown']:.1%}", f"{g['max_drawdown']:.1%}"),
        ("Fees paid", f"{c['fees']:.2f}", f"{g['fees']:.2f}"),
        ("Ending equity", fmt(c["final_equity"]), fmt(g["final_equity"])),
        ("Reckless orders stopped", "—", g["blocks"]),
    ]
    for name, a, b in rows:
        print(f"  {name:<26}{str(a):<16}{str(b):<16}")

    dd_imp = c["max_drawdown"] - g["max_drawdown"]
    fee_imp = c["fees"] - g["fees"]
    print("\n  → " + (f"Drawdown cut {dd_imp/max(c['max_drawdown'],1e-9)*100:.0f}% and fees cut "
                      f"{fee_imp/max(c['fees'],1e-9)*100:.0f}%."
                      if c["max_drawdown"] else "fees cut."))

    header("REFLECTION — the rulebook it proposes")
    print("  (I don't set these. They're drafts for YOU to own.)")
    for i, p in enumerate(r["proposals"], 1):
        print(f"    {i}. [{p.kind}] {p.label}")

    # write a standalone reflection report
    render_reflection_report(r, "reports/reflection.html", source=source, seed=seed)


def render_reflection_report(r, out_path, source="synth", seed=7):
    c, g = r["control"], r["governed"]
    dd_imp = c["max_drawdown"] - g["max_drawdown"]
    fee_imp = c["fees"] - g["fees"]
    props = "".join(
        f"<li><code>{p.kind}</code> — {p.label}</li>" for p in r["proposals"]
    ) or "<li>No changes proposed.</li>"

    def tbl(side, m):
        rows = [
            ("Trades taken", m["trades"]),
            ("Max drawdown", f"{m['max_drawdown']:.1%}"),
            ("Fees paid", f"{m['fees']:.2f} USDC"),
            ("Ending equity", f"{m['final_equity']:,.0f} USDC"),
            ("Reckless orders stopped", m["blocks"]),
        ]
        cells = "".join(f"<tr><td class='k'>{k}</td><td class='v'>{v}</td></tr>" for k, v in rows)
        return f"<h3>{side}</h3><table class='tbl'>{cells}</table>"

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Skeptic — Reflection</title><style>
:root{{--gold:#F3BA2F;--ink:#111;--mut:#666;--bg:#faf7f0;}}
*{{box-sizing:border-box}}body{{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
background:var(--bg);color:var(--ink);margin:0;padding:40px 16px;}}
.wrap{{max-width:860px;margin:0 auto;}}
h1{{font-size:28px;margin:0 0 4px;}}h1 .dot{{color:var(--gold);}}
.sub{{color:var(--mut);font-size:14px;margin-bottom:28px;}}
.hero{{background:#111;color:#fff;border-radius:16px;padding:24px;margin-bottom:24px;}}
.hero b{{color:var(--gold);}}
.cols{{display:grid;grid-template-columns:1fr 1fr;gap:18px;}}
.card{{background:#fff;border:1px solid #eee;border-radius:12px;padding:18px;}}
h3{{margin:0 0 12px;font-size:14px;color:var(--mut);text-transform:uppercase;letter-spacing:.04em;}}
.tbl{{width:100%;border-collapse:collapse;font-size:14px;}}
.tbl td{{padding:6px 0;border-bottom:1px solid #f2f2f2;}}
.tbl .k{{color:var(--mut);}}.tbl .v{{text-align:right;font-weight:600;}}
ul{{margin:0;padding-left:18px;font-size:14px;line-height:1.7;}}
code{{background:#f4f4f4;padding:1px 5px;border-radius:4px;font-size:12px;}}
.foot{{margin-top:26px;color:var(--mut);font-size:12px;text-align:center;}}
@media(max-width:640px){{.cols{{grid-template-columns:1fr}}}}
</style></head><body><div class="wrap">
<h1>The <span class="dot">●</span> Skeptic</h1>
<div class="sub">Your agent's risk desk, in plain English. Reflection report.</div>
<div class="hero"><b>The honest claim.</b> Same market, same agent, same 200 hourly bars
({source}, seed {seed}). Left unwatched it churned <b>{c['trades']}</b> trades and drew down
<b>{c['max_drawdown']:.1%}</b>. Run under the Skeptic it traded <b>{g['trades']}</b> times, cut drawdown by
<b>{dd_imp/max(c['max_drawdown'],1e-9)*100:.0f}%</b> and fees by
<b>{fee_imp/max(c['fees'],1e-9)*100:.0f}%</b> — and stopped <b>{g['blocks']}</b> reckless orders.
This is not a profit promise; it's a stop-blooding-out promise.</div>
<div class="cols">
<div class="card">{tbl("No guardrails", c)}</div>
<div class="card">{tbl("Under the Skeptic", g)}</div>
</div>
<div class="card" style="margin-top:18px"><h3>Rulebook it proposes (you own these)</h3>
<ul>{props}</ul></div>
<div class="foot">Simulated Agentic sub-account. No real funds, no orders, no keys.</div>
</div></body></html>"""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(html)
    print(f"\n  Reflection report → {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interactive", action="store_true", help="ask Y/n for each order")
    ap.add_argument("--source", default="synth", choices=["auto", "live", "synth"])
    ap.add_argument("--seed", type=int, default=30)
    ap.add_argument("--reflection-only", action="store_true")
    args = ap.parse_args()

    intro()
    if not args.reflection_only:
        gate_demo(auto=not args.interactive, source=args.source, seed=args.seed)
    reflection_demo(source=args.source, seed=args.seed)
    print("\n" + "=" * 76)
    print("  Done. That's the Skeptic: vet the trade, show the why, let you decide.")
    print("=" * 76)


if __name__ == "__main__":
    main()
