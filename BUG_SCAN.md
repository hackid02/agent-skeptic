# The Skeptic — Bug-scan handoff for another AI

You're reviewing a small Python project. **Clone it, run it, then hunt for bugs.**
Report findings in the template at the bottom. I've listed what I already found so
you can verify and extend — don't just repeat it.

---

## What the project is

**The Skeptic** — an Agent OS risk-governor for the Binance Agent OS Mini
Hackathon (Track A). It sits between an AI trading agent and the money. It vets
every order intent against a user-owned rulebook and returns **BLOCK / DOWNSIZE /
APPROVE** with a plain-English reason, requires human approval, runs a same-market
A/B, and proposes rulebook updates. Built *with* Agent OS: it is an MCP server and
an MCP client of Binance's Agent OS server.

**No real funds, no keys, no withdrawals.** The demo runs on a simulated backend
by default; live mode uses an OAuth Authorization Code + PKCE flow.

## Where to get the code

Public repo: **https://github.com/hackid02/agent-skeptic**

```bash
git clone https://github.com/hackid02/agent-skeptic.git
cd agent-skeptic
python3 -m pip install -r requirements.txt
```

## How to run it (the 4 smoke tests)

```bash
python3 agentos_demo.py --mode sim            # full Gate + Reflection, simulated Agent OS
python3 demo.py                               # scripted terminal demo
python3 console.py                            # regenerates reports/console.html
python3 agentos_demo.py --mode auto --probe   # prints the Agent OS connect path + a read-only probe
```

Every run must exit 0 with **zero** tracebacks. `console.py` prints
`Console → reports/console.html (211 KB)`.

## The file map

- `demo.py` — scripted terminal orchestrator (The Gate + Reflection).
- `console.py` — generates the designed `reports/console.html` (embedded base64 fonts, inline JS canvas).
- `agentos_demo.py` — MCP-client → The-Skeptic-server demo; also `--login` (OAuth), `--probe`.
- `skeptic_server.py` — launcher for the MCP server (`src/skeptic_mcp.main`).
- `src/skeptic_mcp.py` — The Skeptic MCP server (6 tools: `vet_order`, `get_rulebook`, `approve`, `reject`, `run_ab`, `propose_rulebook_update`).
- `src/agentos.py` — Agent OS client (`LiveAgentOS`, `SimulatedAgentOS`, `connect()` factory).
- `src/agentos_oauth.py` — OAuth 2.0 Authorization Code + PKCE flow.
- `src/riskdesk.py` — `OrderIntent` → `evaluate()` → `Verdict` + `plain_english()`.
- `src/rulebook.py` — `Rule`, `DEFAULT_RULES`, `applicable_rules()`.
- `src/engine.py` — `SubAccount`, `FlawedTrader` (backing the A/B).
- `src/reflection.py` — `run_reflection()` A/B + `propose_updates()`.
- `src/market.py` — live/synthetic klines.

## Scan areas (prioritised)

### A. Correctness / logic
1. `riskdesk.evaluate()` — is the verdict logic sound? Trace a BLOCK, a DOWNSIZE,
   and an APPROVE by hand. Does `proposed_notional` ever go negative? Does a
   `max_total_exposure` trim correctly when `cap - open_exposure` is negative?
2. `engine.FlawedTrader.run()` — the `streak` bookkeeping and the `peak` update.
   Any off-by-one or unreachable branch? Does it correctly honour `DOWNSIZE`
   (the `elif v.action == "DOWNSIZE"` path)?
3. `reflection.stats()` / `propose_updates()` — are the A/B numbers self-consistent?
4. `agentos.LiveAgentOS` — the `_find_tool` keyword mapping; `_json` parsing of
   Binance tool responses; the httpx client lifetime in `connect()`.

### B. Edge cases
- `symbol` variants: `BTC`, `BTCUSDT`, `BTC-USDT`, `BTC/USDT`, `BTC_USDT`, empty, `None`.
- `notional` = 0, negative, very large; `vol` = 0; `base_unit` = 0; `equity` = 0 (division by zero?).
- `vet_order` then `approve` with no pending order; `reject` with no pending.
- `run_ab` / `propose_rulebook_update` with a custom symbol.
- `get_klines` with an unreachable source (does it fall back cleanly?).

### C. Security / secrets
- Confirm `.gitignore` excludes `__pycache__/`, `*.pyc`, `.agentos_token.json`, `.env`.
- `agentos_oauth.py` — is the PKCE verifier handled securely? Is the callback
  server safe against a mismatched `state`? Any token leakage into logs/errors?
- `console.py` embeds fonts/subsets — any injection (XSS) from data in `body_html`?

### D. Concurrency / async
- `agentos` client `connect()`/`close()` — does the stack close cleanly (the
  MCP 2.x stdio teardown `ExceptionGroup`)? Is there a resource leak on live mode?
- `agentos_demo.run_stdio()`'s `BaseExceptionGroup` suppression — does it swallow
  real errors? (See `_real_error`.)

### E. Packaging / portability
- `requirements.txt` (`requests`, `mcp>=2.0`) — complete for all entry points?
- `console.py` needs the fonts in `src/embed_fonts.py` — are they self-contained?
- Does `skeptic_server.py` run from a clean clone (relative imports)?

## What I already found (verify these)

**Fixed (commit `386102e`):**
1. Symbol normalization — `_pair()` returned the symbol unchanged when it merely
   *ended* in `USDT`, so `BTC-USDT`/`BTC/USDT` produced a bogus default price
   (~117) instead of BTCUSDT. Now strips separators before the check.
2. `evaluate()` ignored each rule's `severity` field, so **DOWNSIZE was unreachable
   dead code** (every size-cap rule also set the "block" flag). Now BLOCK-severity
   rules refuse; WARN-severity rules downsize. Default rulebook is strict (all
   BLOCK), so the A/B proof is unchanged (4 trades / 0.40% dd / 3.47 fees / 93
   stopped), but a WARN rule genuinely returns DOWNSIZE.

**Cosmetic / open (why not fixed):**
3. Unused imports: `src/agentos.py` (`asyncio`, `statistics`, `_recent_vol`);
   `src/agentos_oauth.py` (`Optional`); `src/engine.py` (`Optional`);
   `src/market.py` (`math`); `src/reflection.py` (`statistics`,
   `recent_volatility`); `src/riskdesk.py` (`Dict`, `Optional`);
   `src/rulebook.py` (`Optional`); `demo.py` (`List`); agentos_demo (`meta`,
   `ref`); console.py (`eq_json`, `start_eq`, `dd_ratio`).
4. `src/reflection.py` — unused locals `pnls`, `savings`.
5. `agentos_demo.py`/`console.py` — a few f-strings missing placeholders;
   `agentos_demo.py` shebang not executable; ruff import-order nits.
6. `agentos_demo.probe` — in `auto` mode here, the live endpoint is unreachable
   from this network, so it falls back to sim. That's expected, not a bug.
7. **Design tension (not a bug):** making DOWNSIZE reachable by relaxing caps
   *weakens* the A/B story (93→72 blocks, dd 0.40%→0.75%). I kept the strict
   default rulebook so the demo numbers hold. Flag if you disagree.

## Output template

Report as:
```
### Critical (blocks submission)
- [ ] ...

### Should fix
- [ ] ...

### Nits / style
- [ ] ...

### Verified working
- [ ] agentos_demo --mode sim
- [ ] demo.py
- [ ] console.py
- [ ] --mode auto --probe
- [ ] A/B seed 30 = 4 / 0.40% / 3.47 / 93
```
