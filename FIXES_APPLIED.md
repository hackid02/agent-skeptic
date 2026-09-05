# Fixes applied from the external bug scan

**Repo:** `agent-skeptic` · **Scan reviewed:** `uploads/skeptic-bug-scan.md` @ `31490d4`
**Result:** all 4 criticals fixed, all "should fix" items fixed, all nits fixed.
**Verification:** `python3 tests/verify_fixes.py` → **43/43 pass**; all four smoke tests
exit 0 with zero tracebacks; A/B numbers unchanged from the documented baseline
(seed 30: 19→4 trades, 2.17%→0.40% drawdown, 15.56→3.47 fees, 93 stopped).

---

## Critical

| # | Finding | Fix |
|---|---|---|
| 1 | `approve()`/`reject()` never cleared `self.pending` — one approval could fire unlimited fills, and a rejected order could fill afterwards | `self.pending = None` is now set **before** the `place_order` await in `approve()` (and unconditionally in `reject()`). Locked down by 4 tests in `Critical1ApprovalSingleFire`. |
| 2 | `agentos_demo.py` hardcoded `command="python3"` — the flagship demo silently did nothing in any venv | `command=sys.executable`. `--mode sim` now produces the full 64-line run, exit 0, zero tracebacks. |
| 3 | `_real_error()` swallowed genuine failures by message substring (incl. the dead-subprocess TaskGroup) | Type-based whitelist (`anyio.ClosedResourceError`, `anyio.BrokenResourceError`, `asyncio.CancelledError`, `SystemExit`) **plus** a `_drive_complete` flag: teardown noise before the demo finishes is always a real error. |
| 4 | `requirements.txt` missing `httpx` — `--login` crashed on a clean clone | `httpx>=0.27` added. |

## Risk engine (`src/riskdesk.py`)

- `equity <= 0` → BLOCK (was `ZeroDivisionError`).
- `notional <= 0` / NaN and unknown `side` → BLOCK (validated in `evaluate()` *and* `vet_order`).
- `max_total_exposure` now applies to the **first** position (`open_exposure > 0` clause dropped); added an explicit within-cap finding when exposure exists.
- DOWNSIZE-to-0 is now a **BLOCK** with its own finding ("a refuse, not a trim").
- `max_sizing_multiplier` takes `min()` like every other cap — can never size an order back up.
- **Unknown rule kinds fail closed** (violated by severity) instead of silently disabling themselves.
- `trade_cap` and `position_cap_learned` are now **implemented** — the rules Reflection proposes actually do something (trade window cap; learned position cap).
- `rebalance_target {allow: false}` is respected: risk-reducing orders get vetted normally, with an explicit finding.
- `peak_equity = 0` no longer silently disables the drawdown guard (falls back to current equity).
- `Verdict.rationale` fixed (`f.message`, was `f.indicator()` — a landmine).
- `plain_english` guards the divide-by-`intent.notional`.

## Engine & A/B (`src/engine.py`, `src/reflection.py`)

- BUY-side streak update (always-false `price > entry`) removed; streak is honestly "consecutive profitable exits" and `Decision.outcome` is now recorded on SELLs.
- Orders are clamped to spendable cash **before** the risk desk sees them — the desk vets what can actually execute; no post-vet clamping.
- Dead "liquidate" block removed (it mutated final results and charged no fee).
- `stats()` fees come from the engine's **fee ledger** (respects `fee_rate`) instead of a hardcoded `0.001` re-derivation.
- `propose_updates` reads the live drawdown guard from the rulebook — a proposal can never be *looser* than what's in force.
- `run_reflection(symbol, ...)` — symbol is the first positional arg (calling `run_reflection('BTCUSDT')` no longer feeds the symbol into `source`), and the library now returns the same `improvement` shape as the MCP tool.

## Symbols & market data (`src/market.py`, `src/skeptic_mcp.py`)

- `normalize_pair()` validates against known assets: `"USDT"`, `""`, `"ETH-BTC"` (→ `ETHBTCUSDT`), `None`, unknown tickers → `ValueError`, never a fabricated pair. `_synth` refuses to price unknown symbols (no more default base 100).
- `get_klines` raises on unknown `source` (the `"sim"` silent-fallthrough is gone — callers now pass `"synth"`).
- `_fetch_live` treats an empty 200 response as a failure (no more `IndexError` in `last_price`); `_interval_seconds` validates input and supports `1w`.
- **Cross-symbol accounting**: the position is marked at the live price only when the feed matches the held symbol; otherwise at entry. Vetted orders for a *different* asset while holding are blocked ("one position at a time") with the rule findings still shown.
- `approve()` charges the fee against cash, clamps SELLs to the held position (**no naked shorts**), and reports the executed notional; partial SELLs leave `open_exposure` at the remaining position value.

## Agent OS client (`src/agentos.py`)

- `_find_tool`: for `place_order` only **name** matching counts, exact or leading-word-segment (`place_order` ✓, `cancel_order`/`query_order` ✗); descriptions never match money-movers.
- `_json` is strict — parse failures raise instead of returning `{"_raw": ...}` that turned into price `0.0` / balance `0.0` in the risk math; `get_ticker`/`get_balance` raise on unusable payloads.
- `connect(mode="auto")` catches `BaseExceptionGroup` too (the MCP teardown group), so the documented sim fallback always works; `close()` clears state in a `finally`.

## OAuth & secrets (`src/agentos_oauth.py`, `agentos_demo.py`)

- `_wait_for_code` rewritten: the handler thread no longer calls `loop.create_task` (a live `TypeError`); it records the result and signals a `threading.Event`, the async side owns shutdown.
- `error=access_denied` redirects fail fast with a real message (was misleading "state mismatch" or a 300 s hang); missing `code` handled.
- Token file written with `0600` permissions.
- `--scope` is actually passed into the authorize URL (was announced, never requested).
- `refresh_token()` sends `client_id` (RFC 6749 §6 for public clients).

## Console & packaging

- `console.py` HTML-escapes every dynamic row field (`why` embeds free-text agent reasons; the HTML is a shareable artifact).
- README install instructions use a venv (PEP 668 systems rejected the bare `pip install`).
- `Rule.severity` default is now `BLOCK` (fail-closed, matches the house rulebook).

## DOWNSIZE coverage (scan's point 7 — implemented as suggested)

New named profile `--profile balanced` (server + demo flag): identical rules except
`max_position_pct` and `fee_budget` are `WARN`, so oversized orders get trimmed instead
of refused. `agentos_demo.py --mode sim --profile balanced` exercises the full DOWNSIZE
path — verdict, plain-English, engine branch and downsized fill (999.91 USDC trimmed to
the 10% cap) — while the strict default keeps the headline A/B numbers untouched.

## Bonus fix found during verification

`agentos_demo.py --mode sim` used `--source auto`, so whenever Binance's public API was
reachable the "dry-run" demo ran on live data — a quiet live hour (vol under the 0.40%
floor) blocked the "disciplined entry" scene and the demo ended with zero fills. Sim runs
are now deterministic by default (`synth`), with `--source live/auto` as the explicit
opt-in.

## Suggested fix order — status

1. ✅ `self.pending = None` in `approve()`/`reject()`
2. ✅ `command=sys.executable`
3. ✅ Type-based whitelist in `_real_error`
4. ✅ `httpx>=0.27` in `requirements.txt`
5. ✅ `equity <= 0`, `notional <= 0`, `final_notional <= 0` guards
6. ✅ `trade_cap` / `position_cap_learned` implemented
7. ✅ WARN rules shipped (`--profile balanced`) and the DOWNSIZE path exercised
