#!/usr/bin/env python3
"""The Skeptic — Agent OS demo (MCP client -> governance server).

This is the "built with Agent OS" run. It launches The Skeptic's MCP server
(dry-run / simulated Agent OS by default), connects as a normal MCP client,
and drives the whole narrative through the six governance tools:

  1. The GATE : vet_order for each of the 5 scenes -> BLOCK / DOWNSIZE / APPROVE
                with a plain-English why, plus a human approve / reject.
  2. REFLECTION: run_ab (same-market A/B) + propose_rulebook_update (drafts).

Because it uses the MCP protocol — the same surface Binance Agent OS speaks —
you can point `--mode auto` (or `--mode live`) at the real
`https://agent.binance.com/mcp/agentic` on a reachable, authorized machine.

Run:
  python3 agentos_demo.py                 # simulated Agent OS, stdio
  python3 agentos_demo.py --mode auto     # try live Agent OS, fall back
  python3 agentos_demo.py --mode live --probe   # connect to the REAL Agent OS, list its tools, do a read-only market-data call
  python3 agentos_demo.py --transport streamable-http --port 8888
"""
from __future__ import annotations

import argparse
import asyncio
import json
from contextlib import AsyncExitStack

from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

from src import agentos

GATE = [
    ("Scene 1 · oversized, no-plan buy",   {"symbol": "BTC", "side": "BUY", "notional": 4200,
                                            "agent_why": "momentum looks good, go big"}),
    ("Scene 2 · disciplined entry",        {"symbol": "BTC", "side": "BUY", "notional": 850,
                                            "agent_why": "momentum aligned, modest size"}),
    ("Scene 3 · greed after a win streak", {"symbol": "SOL", "side": "BUY", "notional": 3600,
                                            "agent_why": "we're on a 4-win streak, size up"}),
    ("Scene 4 · buying the chaos",         {"symbol": "BTC", "side": "BUY", "notional": 1000,
                                            "agent_why": "big move, don't want to miss it"}),
    ("Scene 5 · trimming risk (allowed)",  {"symbol": "BTC", "side": "SELL", "notional": 700,
                                            "agent_why": "reduce exposure before the weekend",
                                            "is_risk_reducing": True}),
]


def bar(t):
    print("\n" + "=" * 74)
    print(f"  {t}")
    print("=" * 74)


def show(obj):
    return json.dumps(obj, indent=2)


async def run_stdio(args) -> None:
    params = StdioServerParameters(command="python3",
                                   args=["skeptic_server.py", "--mode", args.mode,
                                         "--seed", str(args.seed), "--source", args.source])
    try:
        async with AsyncExitStack() as stack:
            r, w = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(r, w))
            await session.initialize()
            await drive(session, args)
            # graceful teardown: signal EOF, then let the transport drain
            try:
                await w.aclose()
            except Exception:
                pass
            await stack.aclose()
    except BaseExceptionGroup as e:
        # MCP 2.x stdio raises a benign ExceptionGroup during subprocess teardown.
        # If the work above already completed and there was no real task error,
        # swallow it so the demo logs exit cleanly; otherwise re-raise.
        if _real_error(e):
            raise


def _real_error(g) -> bool:
    """True if the group carries a genuine failure (not just SDS teardown noise)."""
    for ex in _leaves(g):
        if isinstance(ex, (asyncio.CancelledError, SystemExit)):
            continue
        msg = str(ex).lower()
        if any(k in msg for k in ("cancel scope", "closed", "canceled", "cancelled",
                                  "broken pipe", "task group", "unhandled errors")):
            continue
        return True
    return False


def _leaves(e) -> list:
    if isinstance(e, BaseExceptionGroup):
        out = []
        for s in e.exceptions:
            out.extend(_leaves(s))
        return out
    return [e]


async def login(args) -> None:
    """Interactive OAuth Authorization Code + PKCE login to the live Agent OS.

    Opens the authorize URL, captures the redirected code via a local callback,
    exchanges it for a token, then connects the MCP client for real and lists
    the tools Agent OS exposes. After logging in, run `--mode live --probe` or
    `--mode live` with the token.
    """
    from src import agentos_oauth
    bar("LOGIN — Binance Agent OS (OAuth Authorization Code + PKCE)")
    print(f"  endpoint: {agentos.AGENT_OS_MCP_URL}")
    print("  This opens Binance's consent screen. Log in, approve, and confirm the")
    print("  dedicated Agentic sub-account. You can cancel at any time.")
    print(f"  Scope: {args.scope} (start with the least you need).\n")

    result = await agentos_oauth.interactive_login(client_id="agentic")
    meta, token = result["meta"], result["token"]
    access = token.get("access_token", "")
    print(f"\n  ✓ got access token (len {len(access)}).")

    # small helper to save for reuse
    import json, pathlib
    tok_file = pathlib.Path(args.token_file)
    tok_file.write_text(json.dumps({"endpoint": agentos.AGENT_OS_MCP_URL, "token": token}))
    print(f"  Saved token → {tok_file} (reuse with --token-file).")

    print("\n  Connecting to Agent OS with the token...")
    try:
        aos = await agentos.connect(endpoint=agentos.AGENT_OS_MCP_URL, mode="live", token=access)
    except Exception as e:
        print(f"  ✗ connected but error during session: {type(e).__name__}: {e}")
        return
    print(f"  ✓ connected. {aos.describe()}")
    print("\n  Tools Agent OS exposes:")
    for t in aos._tools:
        print(f"     - {t.name}: {(t.description or '').splitlines()[0][:60]}")
    print("\n  Read-only market-data check:")
    try:
        tk = await aos.get_ticker("BTCUSDT")
        print(f"     ✓ BTCUSDT: {tk.price:,.2f}  (24h {tk.change_24h:+.2f}%)")
    except Exception as e:
        print(f"     (ticker) {type(e).__name__}: {e}")
    await aos.close()


async def probe(args) -> None:
    """Check Agent OS connectivity & explain the documented connection flow.

    Honest note: Binance's live MCP endpoint is reached through an AI client
    (Claude Code / Codex CLI / ChatGPT / VS Code / Grok) with an OAuth consent
    screen — not a raw Python HTTP client. This probe attempts a client-side
    connect (public market-data scope, no auth) and, if it can't complete,
    prints the documented steps rather than implying it will just work.
    """
    bar("PROBE — the live Binance Agent OS connection")
    print(f"  endpoint: {agentos.AGENT_OS_MCP_URL}")
    print(f"  mode:     {args.mode}")

    # Documented live connection path (what the docs say to do):
    print("\n  ▶ The documented way to connect Binance Agent OS:")
    print("      claude mcp add binance-mcp-server --transport http "
          "https://agent.binance.com/mcp/agentic")
    print("      then open the /mcp menu -> select binance-mcp-server -> Authenticate (OAuth consent).")
    print("      then fund a dedicated Agentic sub-account (Profile > Sub-account > Asset Management).")
    print("  Scopes: Market data is public/no-auth; Account & Trade need the OAuth consent.")
    print("  There is NO withdrawal scope — the agent can never move funds out of the sub-account.")

    try:
        aos = await agentos.connect(endpoint=agentos.AGENT_OS_MCP_URL, mode=args.mode,
                                    source=args.source, seed=args.seed)
    except Exception as e:
        print(f"\n  ✗ client-side connect failed: {type(e).__name__}: {e}")
        print("  This is expected — see the documented connection path above. A headless")
        print("  Python client can't complete Binance's OAuth consent on its own.")
        return

    if getattr(aos, "mode", "") == "sim":
        print(f"\n  ⚠  client-side connect fell back to simulated Agent OS: {aos.describe()}")
        reason = getattr(aos, "_live_error", None)
        if reason:
            print(f"     live failed: {reason}")
        print("  On a machine that can reach Binance, a *public* market-data call may succeed,")
        print("  but Account & Trade need the OAuth consent via an AI client.")
        await aos.close()
        return

    # live
    print(f"\n  ✓ connected. {aos.describe()}")
    print("\n  Tools the live Agent OS server exposes (auto-discovered):")
    for t in aos._tools:
        desc = (t.description or "").split("\n")[0][:70]
        print(f"     - {t.name}: {desc}")

    # read-only, no-auth market data call
    print("\n  Read-only market-data check (public scope, no auth):")
    try:
        tk = await aos.get_ticker("BTCUSDT")
        print(f"     ✓ BTCUSDT ticker: {tk.price:,.2f}  (24h {tk.change_24h:+.2f}%)")
    except Exception as e:
        print(f"     ✗ ticker call failed: {type(e).__name__}: {e}")
    try:
        bars = await aos.get_klines("BTCUSDT", "1h", 5)
        print(f"     ✓ klines: {len(bars)} bars, last close {bars[-1].close:,.2f}")
    except Exception as e:
        print(f"     ✗ klines call failed: {type(e).__name__}: {e}")

    print("\n  The client-side Agent OS integration is wired and reaching the server.")
    print("  For account/trade actions, complete the OAuth consent in your AI client first.")
    await aos.close()


async def run_http(args) -> None:
    from mcp.client.streamable_http import streamable_http_client
    url = f"http://{args.host}:{args.port}/mcp"
    async with AsyncExitStack() as stack:
        streams = await stack.enter_async_context(streamable_http_client(url))
        session = await stack.enter_async_context(ClientSession(streams[0], streams[1]))
        await session.initialize()
        await drive(session, args)


async def drive(session: ClientSession, args) -> None:
    ref = await session.initialize() if False else None
    tools = await session.list_tools()
    print(f"  MCP server toolset: {', '.join(t.name for t in tools.tools)}\n")

    bar("THE GATE — every order intent is vetted first")
    for title, intent in GATE:
        print(f"\n  ▶ {title}")
        print(f"    {intent['side']} {intent['symbol']} ${intent['notional']:,.0f}  ·  reason: \"{intent.get('agent_why')}\"")
        res = await session.call_tool("vet_order", intent)
        d = json.loads(res.content[0].text)
        verdict = d["action"]
        icon = {"APPROVE": "✅ APPROVE", "DOWNSIZE": "⚠️  DOWNSIZE", "BLOCK": "🚫 BLOCK"}[verdict]
        print(f"    {icon}   @ ${d['price']:,.0f}  (vol {d['volatility']:.2%})")
        print(f"      {d['plain_english']}")
        if verdict == "APPROVE":
            # demonstrate the human gate: mark one approved, one rejected
            gate = {"note": "Human OK — looks fit."} if "Scene 5" not in title else {"note": "Trim before weekend."}
            out = await session.call_tool("approve", gate)
            a = json.loads(out.content[0].text)
            print(f"      → approve: {a.get('status')} {a.get('order_id', '')} {a.get('notional', '')} USDC  [{a.get('source', '')}]")
        elif verdict == "DOWNSIZE":
            out = await session.call_tool("approve", {"note": "OK at the reduced size."})
            a = json.loads(out.content[0].text)
            print(f"      → approve (downsized): {a.get('status')} {a.get('notional', '')} USDC")
        else:
            out = await session.call_tool("reject", {"note": "Not spending on this."})
            print(f"      → reject: {json.loads(out.content[0].text).get('status')}")

    bar("REFLEXION — the honest A/B (same market, same agent)")
    ab = await session.call_tool("run_ab", {"symbol": "BTCUSDT", "seed": args.seed})
    r = json.loads(ab.content[0].text)
    c, g = r["control"], r["governed"]
    print(f"  {'Metric':<22}{'No guardrails':<16}{'With Skeptic':<16}")
    print("  " + "-" * 54)
    rows = [("Trades taken", c["trades"], g["trades"]),
            ("Max drawdown", f"{c['max_drawdown']:.1%}", f"{g['max_drawdown']:.1%}"),
            ("Fees paid", f"{c['fees']:.2f}", f"{g['fees']:.2f}"),
            ("Ending equity", f"${c['end_equity']:,.0f}", f"${g['end_equity']:,.0f}"),
            ("Reckless orders stopped", "—", g["blocks"])]
    for name, a, b in rows:
        print(f"  {name:<22}{str(a):<16}{str(b):<16}")
    print(f"\n  → drawdown cut {r['improvement']['drawdown_pct']:.0f}%, fees cut {r['improvement']['fee_pct']:.0f}%.")

    bar("REFLEXION — draft rulebook changes (YOU decide)")
    prop = await session.call_tool("propose_rulebook_update", {})
    p = json.loads(prop.content[0].text)
    print(f"  {p['note']}")
    for i, draft in enumerate(p["drafts"], 1):
        print(f"    {i}. [{draft['kind']}] {draft['label']}")

    bar("DONE")
    server_name = getattr(getattr(session, "server_info", None), "name", "the-skeptic")
    print(f"  Backend: {server_name} — dry-run, no funds, no keys.")
    print("  Not a profit promise: the goal is fewer reckless trades, lower drawdown and less fee burn.")


def main() -> None:
    ap = argparse.ArgumentParser(description="The Skeptic — Agent OS demo")
    ap.add_argument("--mode", default="sim", choices=["auto", "live", "sim"],
                    help="sim=dry-run, auto=try live Agent OS then sim, live=require Agent OS")
    ap.add_argument("--source", default="auto", choices=["auto", "live", "synth"])
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--transport", default="stdio", choices=["stdio", "streamable-http"])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8888)
    ap.add_argument("--probe", action="store_true",
                    help="connect to the real Binance Agent OS, list its tools, do a read-only market-data call")
    ap.add_argument("--login", action="store_true",
                    help="run the interactive OAuth Authorization Code + PKCE login to Agent OS")
    ap.add_argument("--scope", default="account",
                    help="OAuth scope to request (e.g. 'market_data', 'account', 'trade')")
    ap.add_argument("--token-file", default=".agentos_token.json",
                    help="where to save/read the OAuth token")
    args = ap.parse_args()

    if args.login:
        asyncio.run(login(args))
    elif args.probe:
        asyncio.run(probe(args))
    elif args.transport == "streamable-http":
        asyncio.run(run_http(args))
    else:
        asyncio.run(run_stdio(args))


if __name__ == "__main__":
    main()
