"""Binance Agent OS integration — The Skeptic is an Agent OS *consumer*.

The Skeptic is built *on* Agent OS. Your trading agent reaches the market and
your money through the official Binance Agent OS MCP server:

    https://agent.binance.com/mcp/agentic   (streamable-HTTP)

The Skeptic's job is to sit in front of that connection: it reads market data
and (only after a human approves) places the order into the isolated Agentic
sub-account. This module is a thin, capability-based client for Agent OS.

What The Skeptic deliberately is NOT:
  - It is not another order-guardrails wrapper. Agent OS already enforces
    sub-account isolation, no-withdrawal scope and confirm-before-execute.
  - The Skeptic adds what Agent OS cannot: a *user-owned, auditable rulebook*,
    plain-English rationale, a hard human approval gate, a same-market A/B and
    self-proposed rulebook updates on top of that security model.

Tool-contract note
------------------
Because The Skeptic needs only a handful of capabilities (market data, sub-account
balance, order placement), and Binance's exact tool names/schemas can change, the
live client discovers tools at connect time and maps each capability to whatever
the server actually exposes (matched on name/description keywords). If a needed
capability is missing, `connect(mode="auto")` transparently falls back to
`SimulatedAgentOS` — the same tool contract run on local data — so the dry-run
demo is deterministic and runs anywhere.
"""
from __future__ import annotations

import asyncio
import dataclasses
import statistics
from typing import List, Optional

from .market import Bar, get_klines as _get_klines, recent_volatility as _recent_vol, last_price as _last_price
from .engine import SubAccount

AGENT_OS_MCP_URL = "https://agent.binance.com/mcp/agentic"

# Ordered, capability -> keyword hints used to find the right tool on the live server.
CAPABILITY_HINTS = {
    "klines": ("kline", "klines", "candlestick", "candle"),
    "ticker": ("ticker", "price", "quote", "24h", "book", "ticker24hr"),
    "balance": ("balance", "account", "wallet", "assets", "balances"),
    "place_order": ("order", "place", "trade", "spot", "buy", "sell", "neworder"),
    "account": ("account", "balance", "positions", "sub-account", "agentic"),
}


@dataclasses.dataclass
class Ticker:
    symbol: str
    price: float
    change_24h: float = 0.0


@dataclasses.dataclass
class Balance:
    asset: str
    free: float


@dataclasses.dataclass
class OrderResult:
    order_id: str
    status: str
    symbol: str
    side: str
    executed_qty: float
    avg_price: float
    notional: float


# --------------------------------------------------------------------------
# Live client (talks to the real Binance Agent OS MCP server)
# --------------------------------------------------------------------------
class LiveAgentOS:
    """Connects to Agent OS over streamable-HTTP and calls discovered tools.

    Best-effort: wraps Binance tool calls. Any protocol/tool-schema mismatch is
    surfaced as a clear error so the caller can fall back to the simulator.
    """

    endpoint: str

    def __init__(self, endpoint: str = AGENT_OS_MCP_URL, token: Optional[str] = None) -> None:
        self.endpoint = endpoint
        self._token = token
        self._session = None
        self._stack = None
        self._tools: List = []
        self.mode = "live"

    async def connect(self) -> "LiveAgentOS":
        from mcp.client.streamable_http import streamable_http_client
        from mcp.client.session import ClientSession

        self._stack = __import__("contextlib").AsyncExitStack()
        try:
            client_kwargs = {}
            if self._token:
                # Attach the bearer token to the MCP transport via an http client
                # whose lifetime is bound to the same stack as the session.
                import httpx
                hc = await self._stack.enter_async_context(
                    httpx.AsyncClient(headers={"Authorization": f"Bearer {self._token}"},
                                      timeout=None))
                client_kwargs["http_client"] = hc
            streams = await self._stack.enter_async_context(
                streamable_http_client(self.endpoint, **client_kwargs))
            # SDK yields (read, write) in some versions, (read, write, _) in others.
            read, write = streams[0], streams[1]
            self._session = await self._stack.enter_async_context(ClientSession(read, write))
            await self._session.initialize()
            tools = await self._session.list_tools()
            self._tools = list(tools.tools)
        except BaseException:
            await self.close()
            raise
        return self

    async def close(self) -> None:
        if self._stack:
            await self._stack.aclose()
            self._stack = None
            self._session = None

    def _find_tool(self, cap: str) -> Optional[str]:
        hints = CAPABILITY_HINTS.get(cap, ())
        for t in self._tools:
            haystack = ((t.name or "") + " " + (t.description or "")).lower()
            for h in hints:
                if h in haystack:
                    return t.name
        return None

    async def _call(self, cap: str, arguments: dict):
        name = self._find_tool(cap)
        if not name:
            raise RuntimeError(
                f"Agent OS exposed no tool matching capability '{cap}'. "
                f"Available: {[t.name for t in self._tools]}"
            )
        try:
            result = await self._session.call_tool(name, arguments)
        except Exception as e:  # keep error actionable
            raise RuntimeError(f"Agent OS tool '{name}' failed: {e}") from e
        text = ""
        for c in (result.content or []):
            if getattr(c, "type", None) == "text":
                text += c.text
        return text

    async def get_klines(self, symbol: str, interval: str, limit: int = 200) -> List[Bar]:
        raw = await self._call("klines", {"symbol": symbol, "interval": interval, "limit": limit})
        rows = _json(raw)
        bars = []
        for x in rows:
            if isinstance(x, (list, tuple)):
                bars.append(Bar(float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5]), int(x[0])))
        if not bars:
            raise RuntimeError(f"Agent OS klines returned no rows: {raw[:120]}")
        return bars

    async def get_ticker(self, symbol: str) -> Ticker:
        raw = await self._call("ticker", {"symbol": symbol})
        d = _json(raw)
        d = d[0] if isinstance(d, list) and d else d
        price = float(d.get("lastPrice") or d.get("price") or d.get("last") or 0)
        change = float(d.get("priceChangePercent") or d.get("change24h") or 0)
        return Ticker(symbol, price, change)

    async def get_balance(self) -> List[Balance]:
        raw = await self._call("balance", {})
        d = _json(raw)
        d = d.get("balances") or d.get("data") or d if isinstance(d, dict) else d
        out = []
        for row in (d or []):
            if isinstance(row, dict) and ("asset" in row or "free" in row):
                out.append(Balance(str(row.get("asset", "USDT")), float(row.get("free", 0))))
        return out or [Balance("USDT", 0.0)]

    async def place_order(self, symbol: str, side: str, notional: float,
                          order_type: str = "MARKET", price: Optional[float] = None) -> OrderResult:
        args = {"symbol": symbol, "side": side.upper(), "type": order_type}
        # Prefer a quantity; fall back to quoteOrderQty if the tool expects it.
        if order_type.upper() == "MARKET" and price:
            args["quoteOrderQty"] = f"{notional:.2f}"
        elif price:
            args["quantity"] = f"{notional / price:.6f}"
        else:
            args["quoteOrderQty"] = f"{notional:.2f}"
        raw = await self._call("place_order", args)
        d = _json(raw)
        d = d[0] if isinstance(d, list) and d else d
        return OrderResult(
            order_id=str(d.get("orderId") or d.get("order_id") or "live"),
            status=str(d.get("status") or "FILLED"),
            symbol=str(d.get("symbol") or symbol),
            side=str(d.get("side") or side),
            executed_qty=float(d.get("executedQty") or d.get("executed_qty") or 0),
            avg_price=float(d.get("avgPrice") or d.get("avg_price") or price or 0),
            notional=notional,
        )

    def describe(self) -> str:
        return f"Binance Agent OS ({self.endpoint}) — {len(self._tools)} tools: {[t.name for t in self._tools]}"


# --------------------------------------------------------------------------
# Simulated client (same tool contract, runs anywhere / dry-run)
# --------------------------------------------------------------------------
class SimulatedAgentOS:
    """Deterministic stand-in with the identical capability surface.

    Uses the local deterministic feed + a modeled Agentic sub-account (see
    ``src.market`` and ``src.engine``). Mirrors Agent OS's security model:
    isolated sub-account, no external withdrawal, confirm-before-execute.
    """

    def __init__(self, source: str = "auto", seed: int = 7, cash: float = 10_000.0) -> None:
        self.source = source
        self.seed = seed
        self.sub = SubAccount(cash)
        self.mode = "sim"
        self.bars: List[Bar] = []

    async def connect(self) -> "SimulatedAgentOS":
        return self

    async def close(self) -> None:
        return None

    async def get_klines(self, symbol: str, interval: str, limit: int = 200) -> List[Bar]:
        self.bars = _get_klines(symbol, interval, limit, self.source, self.seed)
        return self.bars

    async def get_ticker(self, symbol: str) -> Ticker:
        bars = self.bars or await self.get_klines(symbol, "1h", 200)
        return Ticker(symbol, _last_price(bars))

    async def get_balance(self) -> List[Balance]:
        return [Balance("USDT", self.sub.cash)]

    async def place_order(self, symbol: str, side: str, notional: float,
                          order_type: str = "MARKET", price: Optional[float] = None) -> OrderResult:
        price = price or (_last_price(self.bars) if self.bars else 0.0)
        qty = notional / price if price else 0.0
        if side.upper() == "BUY":
            self.sub.cash -= notional
            self.sub.position += qty
            self.sub.entry = price
        else:
            self.sub.cash += notional
            self.sub.position -= qty
        return OrderResult("SIM", "FILLED", symbol, side.upper(), qty, price, notional)

    def describe(self) -> str:
        return (f"Simulated Agent OS ({self.source}, seed {self.seed}) — isolated "
                f"sub-account, same tool contract. Dry-run, no keys.")


# --------------------------------------------------------------------------
# Factory: try live, fall back to sim
# --------------------------------------------------------------------------
async def connect(endpoint: str = AGENT_OS_MCP_URL, mode: str = "auto",
                  source: str = "auto", seed: int = 7,
                  token: Optional[str] = None) -> "LiveAgentOS | SimulatedAgentOS":
    """Return a working Agent OS client.

    ``mode``:
      - "auto": try the live endpoint, fall back to the simulator on any failure.
      - "live": require the live endpoint (raise on failure).
      - "sim": always the simulated backend.
    ``token``: optional OAuth bearer token (from ``agentos_oauth.interactive_login``).
    """
    if mode == "sim":
        return await SimulatedAgentOS(source=source, seed=seed).connect()
    if mode == "live":
        return await LiveAgentOS(endpoint, token=token).connect()
    # auto
    try:
        return await LiveAgentOS(endpoint, token=token).connect()
    except Exception as e:
        # deterministic fallback
        sim = await SimulatedAgentOS(source=source, seed=seed).connect()
        sim._live_error = f"{type(e).__name__}: {e}"
        return sim


def _json(text: str):
    import json
    text = text.strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        return {"_raw": text}


# -- sync convenience (for the existing demo console) ----------------------
def get_klines(symbol="BTCUSDT", interval="1h", limit=200, source="auto", seed=7) -> List[Bar]:
    """Synchronous wrapper mirroring the old ``market.get_klines`` signature."""
    return _get_klines(symbol, interval, limit, source, seed)
