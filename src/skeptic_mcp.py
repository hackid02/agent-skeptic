"""The Skeptic — an Agent OS governance server (MCP).

The Skeptic is itself an MCP server, so it plugs straight into the same tool
that Agent OS uses: `claude mcp add`. It sits between your AI trading agent
and your money, and it is *built on* Agent OS because it consumes the Binance
Agent OS MCP server for market data and execution.

Flow
----
  1. Your agent calls ``vet_order`` with an order intent.
  2. The Skeptic pulls live market data + sub-account state from Agent OS,
     judges the intent against your user-owned rulebook, and returns a
     verdict — BLOCK / DOWNSIZE / APPROVE — with a plain-English "why".
  3. If it's APPROVE/DOWNSIZE, it records a pending order that needs a human
     ``approve`` / ``reject``. Nothing reaches Agent OS without that OK.
  4. On ``approve`` it forwards the order to Agent OS (into the Agentic
     sub-account). On ``reject`` it never does.
  5. ``run_ab`` shows the honest same-market A/B; ``propose_rulebook_update``
     hands you draft rule changes that only you can adopt.

Everything here is dry-run by default: `--mode sim` uses the simulated
backend (no keys, no funds). Use `--mode auto` to try the real Binance Agent
OS endpoint and fall back, or `--mode live` to require it.

Run:
  python3 src/skeptic_mcp.py --mode sim            # stdio (what claude mcp add uses)
  python3 src/skeptic_mcp.py --transport streamable-http --port 8888   # also works over HTTP
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
from typing import List, Optional

from mcp.server.mcpserver import MCPServer

from . import agentos
from .engine import SubAccount
from .market import (get_klines as _get_klines, recent_volatility, last_price,
                     normalize_pair)
from .riskdesk import OrderIntent, evaluate, plain_english, Verdict, Finding
from .rulebook import DEFAULT_RULES, Rule, get_profile
from .reflection import run_reflection


@dataclasses.dataclass
class PendingOrder:
    intent: OrderIntent
    verdict: Verdict
    approved: Optional[bool] = None


# One-way taker fee the simulated ledger charges on fills. (The fee_budget rule
# projects round-trip costs; the ledger books what actually left the account.)
FEE_RATE = 0.001


class SkepticServer:
    """Stateful governance layer exposed over MCP."""

    def __init__(self, aos, account: float = 10_000.0, rulebook: Optional[List[Rule]] = None,
                 symbol: str = "BTCUSDT", seed: int = 7):
        self.aos = aos
        self.cash0 = account
        self.rulebook = rulebook if rulebook is not None else list(DEFAULT_RULES)
        self.symbol = symbol
        self.seed = seed
        self.sub = SubAccount(account)
        self.peak_equity = account
        self.fees_paid = 0.0
        self.open_exposure = 0.0
        self.trades = 0
        self.position_symbol: Optional[str] = None
        self.pending: Optional[PendingOrder] = None
        self._bars_last = None
        self._bars_symbol: Optional[str] = None

    # -- state helpers ----------------------------------------------------
    @staticmethod
    def _pair(symbol: str) -> str:
        """Normalise a base symbol to a USDT pair the feed understands.

        Tolerates variant spellings from an AI agent: "BTC", "BTCUSDT",
        "BTC-USDT", "BTC/USDT", "btc", "BTC_USDT" — all map to "BTCUSDT".
        Anything unpriceable raises ValueError instead of fabricating a pair.
        """
        return normalize_pair(symbol)

    def _equity(self) -> float:
        """Mark-to-market equity.

        The position is only marked at the *live feed* price when the feed is
        for the same symbol; otherwise it's carried at entry (cost basis) so a
        BTC position is never silently re-priced at SOL's price.
        """
        if self.sub.position and self.position_symbol:
            price = (self._last_price()
                     if self._bars_symbol == self.position_symbol else self.sub.entry)
            return self.sub.cash + self.sub.position * price
        return self.sub.cash

    def _last_price(self) -> float:
        if self._bars_last:
            return last_price(self._bars_last)
        return 0.0

    async def _refresh_market(self, symbol: str) -> float:
        pair = self._pair(symbol)
        try:
            self._bars_last = await self.aos.get_klines(pair, "1h", 200)
        except Exception:
            self._bars_last = _get_klines(pair, "1h", 200, "synth", self.seed)
        self._bars_symbol = pair
        return last_price(self._bars_last)

    def _block_response(self, message: str) -> dict:
        """A consistent BLOCK-shaped answer for invalid input."""
        return {
            "action": "BLOCK",
            "proposed_notional": 0.0,
            "plain_english": f"I'd stop this one. {message} Nothing's been placed.",
            "findings": [{"rule": "input", "blocked": True, "message": message}],
            "price": round(self._last_price(), 2),
            "volatility": 0.0,
            "equity": round(self._equity(), 2),
            "open_exposure": round(self.open_exposure, 2),
            "pending": False,
        }

    async def _vol(self) -> float:
        if self._bars_last is None:
            await self._refresh_market(self.symbol)
        return recent_volatility(self._bars_last) if self._bars_last else 0.0

    # -- MCP tools --------------------------------------------------------
    async def vet_order(self, symbol: str, side: str, notional: float,
                        agent_why: str = "", is_risk_reducing: bool = False) -> dict:
        """Vet an order intent. Returns a verdict + plain-English rationale.

        Required: symbol, side ("BUY"/"SELL"), notional (USD).
        Optional: agent_why, is_risk_reducing (trimming exposure = always allowed).
        """
        # -- validate the request before touching the market ------------------
        try:
            pair = self._pair(symbol)
        except (ValueError, AttributeError, TypeError) as e:
            return self._block_response(str(e))
        if not isinstance(side, str) or side.upper() not in ("BUY", "SELL"):
            return self._block_response(f"Side {side!r} isn't BUY or SELL.")
        try:
            amount = float(notional)
        except (TypeError, ValueError):
            return self._block_response(f"Notional {notional!r} isn't a number.")
        if amount != amount or amount <= 0:  # NaN or non-positive
            return self._block_response(f"Notional {amount!r} isn't a positive size.")

        # One governed position at a time — the scalar book can't honestly
        # track two, so trim what's open before adding a different asset.
        cross_position = (self.sub.position > 1e-9 and self.position_symbol
                          and pair != self.position_symbol)

        price = await self._refresh_market(symbol)
        vol = await self._vol()
        intent = OrderIntent(
            symbol=pair, side=side.upper(), notional=amount,
            price=price, vol=vol, agent_why=agent_why,
            is_risk_reducing=bool(is_risk_reducing),
            base_unit=self.cash0 * 0.10,
        )
        verdict = evaluate(intent, self.rulebook, equity=self._equity(),
                           open_exposure=self.open_exposure, peak_equity=self.peak_equity,
                           fees_paid=self.fees_paid, trades_taken=self.trades)
        if cross_position:
            verdict = dataclasses.replace(verdict, action="BLOCK", findings=[
                Finding("position", True, (
                    f"You already hold an open {self.position_symbol} position — I govern "
                    f"one position at a time. Trim that one first.")),
                *verdict.findings,
            ])
        self.pending = PendingOrder(intent, verdict)
        return {
            "action": verdict.action,
            "proposed_notional": round(verdict.proposed_notional, 2),
            "plain_english": plain_english(verdict, intent),
            "findings": [{"rule": f.rule, "blocked": f.blocked, "message": f.message}
                         for f in verdict.findings],
            "price": round(price, 2),
            "volatility": round(vol, 4),
            "equity": round(self._equity(), 2),
            "open_exposure": round(self.open_exposure, 2),
            "pending": True,
        }

    async def get_rulebook(self) -> dict:
        """Return the user-owned rules the Skeptic enforces."""
        return {
            "rules": [{"kind": r.kind, "label": r.label, "severity": r.severity,
                       "source": r.source, "params": r.params} for r in self.rulebook],
        }

    async def approve(self, note: str = "") -> dict:
        """Approve the pending order. Only then does the Skeptic act on Agent OS.

        The pending order is consumed *first* — one approval can ever fire one
        fill, and a second approve()/reject() during execution finds nothing.
        """
        if not self.pending:
            return {"status": "no_pending", "message": "Nothing pending to approve."}
        p = self.pending
        self.pending = None  # single-fire: consume before any await
        if p.verdict.action == "BLOCK":
            return {"status": "blocked", "message": "This order was blocked — nothing to approve."}
        notional = p.verdict.proposed_notional if p.verdict.action == "DOWNSIZE" else p.intent.notional
        price = await self._refresh_market(p.intent.symbol)
        if price <= 0:
            return {"status": "error", "message": "No usable market price — nothing was sent."}

        if p.intent.side.upper() == "BUY":
            result = await self.aos.place_order(p.intent.symbol, p.intent.side, notional, price=price)
            fee = notional * FEE_RATE
            self.sub.cash -= notional + fee          # fees leave the account too
            self.sub.position += notional / price
            self.sub.entry = price
            self.position_symbol = p.intent.symbol
            self.open_exposure += notional
            executed_notional = notional
        else:  # SELL — spot-only: never go negative (no naked shorts)
            held = self.sub.position if p.intent.symbol == self.position_symbol else 0.0
            if held <= 0:
                return {"status": "no_position",
                        "message": f"No {p.intent.symbol} position to sell — nothing was sent."}
            units = min(notional / price, held)
            executed_notional = units * price
            result = await self.aos.place_order(p.intent.symbol, p.intent.side,
                                                executed_notional, price=price)
            fee = executed_notional * FEE_RATE
            self.sub.cash += executed_notional - fee
            self.sub.position -= units
            if self.sub.position <= 1e-12:
                self.sub.position = 0.0
                self.position_symbol = None
            self.open_exposure = self.sub.position * price if self.position_symbol else 0.0

        self.fees_paid += fee
        self.trades += 1
        self.peak_equity = max(self.peak_equity, self._equity())
        p.approved = True
        return {
            "status": "filled",
            "order_id": result.order_id,
            "symbol": result.symbol,
            "side": result.side,
            "executed_qty": round(result.executed_qty, 6),
            "avg_price": round(result.avg_price, 2),
            "notional": round(executed_notional, 2),
            "fee": round(fee, 4),
            "source": self.aos.mode,
            "note": note or "Human approved — order sent.",
        }

    async def reject(self, note: str = "") -> dict:
        """Reject the pending order. It never reaches Agent OS."""
        if not self.pending:
            return {"status": "no_pending", "message": "Nothing pending to reject."}
        self.pending.approved = False
        self.pending = None  # consumed — a later approve() can't resurrect it
        return {"status": "rejected", "message": note or "Human rejected — order cancelled. Nothing was sent."}

    async def run_ab(self, symbol: str = "BTCUSDT", seed: int | None = None) -> dict:
        """Honest same-market A/B: the flawed agent unwatched vs under the Skeptic."""
        seed = seed if seed is not None else self.seed
        r = run_reflection(symbol=symbol, seed=seed,
                           source="synth" if self.aos.mode == "sim" else "auto")
        c, g = r["control"], r["governed"]
        return {
            "symbol": symbol,
            "control": {"trades": c["trades"], "max_drawdown": round(c["max_drawdown"], 4),
                        "fees": round(c["fees"], 2), "end_equity": round(c["final_equity"], 2)},
            "governed": {"trades": g["trades"], "max_drawdown": round(g["max_drawdown"], 4),
                         "fees": round(g["fees"], 2), "end_equity": round(g["final_equity"], 2),
                         "blocks": g["blocks"]},
            "improvement": {
                "drawdown_pct": round((c["max_drawdown"] - g["max_drawdown"]) / max(c["max_drawdown"], 1e-9) * 100, 0),
                "fee_pct": round((c["fees"] - g["fees"]) / max(c["fees"], 1e-9) * 100, 0),
            },
        }

    async def propose_rulebook_update(self) -> dict:
        """Return draft rule changes from Reflection. You own whether to adopt them."""
        r = run_reflection(seed=self.seed,
                           source="synth" if self.aos.mode == "sim" else "auto")
        return {
            "drafts": [{"kind": p.kind, "label": p.label, "severity": p.severity,
                        "source": p.source, "params": p.params} for p in r["proposals"]],
            "note": "These are drafts. You decide. I never change my own rules.",
        }


def build_server(skeptic: SkepticServer) -> MCPServer:
    server = MCPServer(name="the-skeptic", version="0.1.0",
                       title="The Skeptic",
                       description=("Risk-governor that vets every order intent against your "
                                    "auditable rulebook before it reaches Binance Agent OS."),
                       instructions=(
                           "This server is a risk-governor. Call vet_order with an order intent to "
                           "get a BLOCK / DOWNSIZE / APPROVE verdict plus a plain-English explanation. "
                           "Approve or reject to decide whether it reaches Agent OS. Uses your rulebook. "
                           "Never claims to guarantee profit."))

    @server.tool(name="vet_order", description="Vet an order intent against the user rulebook. Returns a verdict + plain-English why.")
    async def vet_order(symbol: str, side: str, notional: float, agent_why: str = "", is_risk_reducing: bool = False) -> dict:
        return await skeptic.vet_order(symbol, side, notional, agent_why, is_risk_reducing)

    @server.tool(name="get_rulebook", description="Return the user-owned rules currently in force.")
    async def get_rulebook() -> dict:
        return await skeptic.get_rulebook()

    @server.tool(name="approve", description="Approve the pending order so it can be sent to Agent OS.")
    async def approve(note: str = "") -> dict:
        return await skeptic.approve(note)

    @server.tool(name="reject", description="Reject the pending order. It never reaches Agent OS.")
    async def reject(note: str = "") -> dict:
        return await skeptic.reject(note)

    @server.tool(name="run_ab", description="Same-market A/B: the agent unwatched vs under the Skeptic.")
    async def run_ab(symbol: str = "BTCUSDT", seed: int = 0) -> dict:
        return await skeptic.run_ab(symbol, seed or None)

    @server.tool(name="propose_rulebook_update", description="Get draft rule changes from Reflection (you decide whether to adopt).")
    async def propose_rulebook_update() -> dict:
        return await skeptic.propose_rulebook_update()

    return server


async def _run_stdio(skeptic: SkepticServer) -> None:
    server = build_server(skeptic)
    await server.run_stdio_async()


async def _run_http(skeptic: SkepticServer, host: str, port: int) -> None:
    server = build_server(skeptic)
    await server.run_streamable_http_async(host=host, port=port, streamable_http_path="/mcp")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="The Skeptic — Agent OS governance server")
    ap.add_argument("--mode", default="sim", choices=["auto", "live", "sim"],
                    help="auto=try live Agent OS then sim, live=require Agent OS, sim=dry-run")
    ap.add_argument("--endpoint", default=agentos.AGENT_OS_MCP_URL, help="Binance Agent OS MCP URL")
    ap.add_argument("--transport", default="stdio", choices=["stdio", "streamable-http"])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8888)
    ap.add_argument("--account", type=float, default=10_000.0)
    ap.add_argument("--source", default="auto", choices=["auto", "live", "synth"])
    ap.add_argument("--profile", default="strict", choices=["strict", "balanced"],
                    help="strict = the house rulebook (default); balanced = sizing/fee rules "
                         "WARN + trim (DOWNSIZE) instead of refuse")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args(argv)

    aos = asyncio.run(agentos.connect(endpoint=args.endpoint, mode=args.mode,
                                      source=args.source, seed=args.seed))
    print(f"[The Skeptic] backend: {aos.describe()}", file=__import__("sys").stderr, flush=True)
    print(f"[The Skeptic] rulebook profile: {args.profile}", file=__import__("sys").stderr, flush=True)
    skeptic = SkepticServer(aos, account=args.account, seed=args.seed,
                            rulebook=get_profile(args.profile))

    if args.transport == "streamable-http":
        asyncio.run(_run_http(skeptic, args.host, args.port))
    else:
        asyncio.run(_run_stdio(skeptic))


if __name__ == "__main__":
    main()
