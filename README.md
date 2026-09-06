# The Skeptic 🛡️

> **Your agent's risk desk, in plain English.**
> An **Agent OS** agent that sits between your AI trading agent and your money —
> it refuses reckless trades, tells you why in a sentence a human gets, and lets
> **you** make the final call.

**Track A · Binance Agent OS Mini Hackathon · $20,000 USDC pool**

**Repo:** [github.com/hackid02/agent-skeptic](https://github.com/hackid02/agent-skeptic) · **Author:** [@hackid02](https://github.com/hackid02)
**▶️ Demo video (88s):** [watch on X](https://x.com/web3_YSL/status/2096501565536305653)

---

## Why this exists

Everyone is racing to build "an agent that trades." That's the crowded part.

The Agent OS launch itself flagged the real question — **"how do we trust an
agent with money?"** — and the press hammered the same point: *"Binance can't see
your agent's reasoning, so what stops it from blowing up?"*

**The Skeptic is the answer to that question.** It doesn't promise profits (no
honest agent should). It makes an agent *safe to let near money*:

- It **vets every order before it executes** — the exact confirm-before-execute
  model Agent OS is built on.
- It explains **why** in plain English, based on **explicit rules you own** —
  the "your rules, your agents" thesis.
- It **refuses or downsizes** reckless trades and shows the math.
- It **reflects**: reviews how the agent actually behaved, runs a same-market
  A/B, and proposes rulebook updates (you approve them).

## The honest one-sentence pitch

> The Skeptic doesn't try to predict the market. It stops your agent from
> bleeding out — and tells you why.

---

## What it demonstrates

### 1. The Gate — vet every order (confirm-before-execute)
Incoming order intents are judged against an **auditable rulebook**:

| Rule | Guardrail |
|---|---|
| `max_position_pct` | ≤10% of account in a single position |
| `max_total_exposure` | ≤40% total open exposure |
| `drawdown_guard` | stop adding risk after −5% from peak |
| `volatility_band` | only trade inside a sane volatility band |
| `fee_budget` | cap cumulative round-trip fees |
| `max_sizing_multiplier` | kill streak-driven greed (≤2x base) |
| `rebalance_target` | risk-reducing trims are always allowed |

Each produces a **BLOCK / DOWNSIZE / APPROVE** verdict with a plain-English
paragraph — then **the human approves**. Risk-reducing orders are never blocked.

### 2. Reflection — does it actually help? (same-market A/B)
Same market, same trading agent, 200 hourly bars. Left unwatched vs under the
Skeptic:

| Metric | No guardrails | Under the Skeptic |
|---|---|---|
| Trades taken | 19 | **4** |
| Max drawdown | 2.2% | **0.4%** |
| Fees paid | 15.56 USDC | **3.47 USDC** |
| Ending equity | $9,855 | **$9,962** |
| Reckless orders stopped | — | **93** |

**Drawdown −81% · fees −78% · and it still ended ahead — while stopping 93 reckless orders.**

*(Reproducible with `python3 demo.py`; default seed 30. `--source live` uses real
candles; results vary with the market — that's the point. We never claim profit.)*

---

## Run it

```bash
cd agent-skeptic
# Use a venv — on PEP 668 systems (Ubuntu 24, Debian 12, Homebrew Python) a
# bare `pip install` fails with `externally-managed-environment`.
python3 -m venv .venv && source .venv/bin/activate
python3 -m pip install -r requirements.txt   # requests + mcp + httpx
python3 agentos_demo.py --mode live --probe  # ★ prove the real Agent OS connection (read-only, no auth)
python3 agentos_demo.py         # ★ built-with-Agent-OS demo: real MCP client → The Skeptic server
python3 agentos_demo.py --profile balanced   # same demo, oversized orders get DOWNSIZED, not refused
python3 demo.py                 # scripted terminal demo (auto-approves); best for the video
python3 demo.py --interactive   # you type Y/n for each order
python3 demo.py --source live   # real coin market data
python3 demo.py --seed 8        # other market paths
python3 console.py              # generate the designed Risk Verdict Console (HTML)
python3 skeptic_server.py --mode sim                    # run The Skeptic as an MCP server (stdio)
python3 skeptic_server.py --transport streamable-http --port 8888  # ...or over HTTP
```

Output: console narrative **+** `reports/reflection.html` (A/B report) **+**
`reports/console.html` — the signature **Risk Verdict Console** (see below).

---

## Architecture

```
agent-skeptic/
  agentos_demo.py        # ★ built-with-Agent-OS demo: MCP client → The Skeptic server
  skeptic_server.py      # run The Skeptic as an MCP server (stdio or streamable-HTTP)
  demo.py                # scripted terminal orchestrator: The Gate + Reflection
  src/
    market.py            # live (Binance→Coinbase) or deterministic synthetic feed
    agentos.py           # ★ Agent OS MCP client (live endpoint) + simulated backend
    rulebook.py          # the auditable rules YOU own
    riskdesk.py          # OrderIntent → Verdict (BLOCK/DOWNSIZE/APPROVE) + plain English
    engine.py            # simulated Agentic sub-account + flawed trading agent
    skeptic_mcp.py       # ★ The Skeptic governance MCP server (the agent)
    reflection.py        # A/B + proposes rulebook updates
  reports/reflection.html   # A/B report (terminal-style)
  reports/console.html      # ★ signature Risk Verdict Console (designed, live)
  brand/                    # console screenshots (dark/light/cb/motion-off)
  README.md · PRD.md · VIDEO_SCRIPT.md · SUBMISSION.md · requirements.txt
```

## How this is built **with** Agent OS 🛡️

The Skeptic is an **Agent OS agent**, not just a script that mentions it. It is
itself an **MCP server**, so it plugs into the *same* surface Binance Agent OS
speaks — and it **consumes the official Binance Agent OS MCP server**
(`https://agent.binance.com/mcp/agentic`) for market data and execution.

```
  AI agent (Claude/Cursor/…)  ──MCP──▶  The Skeptic (MCP server)  ──MCP──▶  Binance Agent OS
                                           │  vet_order,             │  market data,
                                           │  approve/reject,        │  Agentic sub-account,
                                           │  rulebook, A/B          │  order execution
```

- **It is a client of Agent OS for the data it needs.** `src/agentos.py` connects
  over streamable-HTTP, discovers the tools the server actually exposes (the docs
  don't publish a tool list — they're auto-discovered at connect time), and maps
  them to the few capabilities it needs. For the risk checks it needs **market
  data** (public, no auth). The live path for Account/Trade needs Binance's OAuth
  consent, which Binance routes through an AI client (Claude Code, Codex CLI, etc.)
  — so the served demo uses the simulated backend and never touches your account.
- **Two backends, one contract.** `--mode auto` tries the live Agent OS MCP
  endpoint and, on any failure (e.g. geo-block, no session), falls back to
  `SimulatedAgentOS` — the *identical* tool contract running on the local
  deterministic feed + modeled Agentic sub-account. So the demo is **dry-run,
  no funds, no keys** while the integration is the real thing.
  - `--mode sim` → always simulated. `--mode live` → require Agent OS.
- **What The Skeptic adds on top of Agent OS** (which already enforces the isolated
  sub-account, confirm-before-execute and no-withdrawal scope, and an Emergency
  stop, but cannot see agent reasoning): a **user-owned auditable rulebook**,
  **plain-English rationale**, a **hard human approval gate**, a **same-market
  A/B**, and **draft rulebook updates** the human can adopt or ignore. The
  Skeptic is the per-order *judgement* layer; Agent OS is the *containment*
  layer.

Run `python3 agentos_demo.py` and it launches the server, connects a real MCP
client, and drives the whole narrative through the six governance tools.

To point a real agent at it (the same command shape Agent OS uses):

```bash
claude mcp add the-skeptic --command python3 skeptic_server.py
```

**Connect a real agent to Binance Agent OS:** I verified the live endpoint is
reachable and uses a **standard MCP OAuth 2.0 Authorization Code + PKCE (S256)**
flow (advertised via `/.well-known/oauth-authorization-server`). The Skeptic
implements that handshake itself:

```bash
python3 -u agentos_demo.py --login              # opens consent, captures the code, saves a token
python3 -u agentos_demo.py --mode live --probe  # connect for real → list tools → pull a ticker
```

or the documented Binance path through an AI client:

```bash
claude mcp add binance-mcp-server --transport http https://agent.binance.com/mcp/agentic
# open the /mcp menu → select binance-mcp-server → Authenticate (OAuth consent)
# then fund a dedicated Agentic sub-account (Profile → Sub-account → Asset Management)
```

Scopes: **market data** is public/no-auth; **Account** and **Trade** need the OAuth
consent. There is **no withdrawal scope** — the agent can never move funds out of
the sub-account, and every trade/transfer is **confirmed by you first**. Those are
exactly the guardrails The Skeptic is designed to sit on top of.

The login/consent step needs a logged-in Binance account + funded Agentic
sub-account, so the served demo runs on the simulated backend (identical tool
contract, deterministic, no keys). `--mode live` / `--login` reach Agent OS for
real after you authorize.

## The Risk Verdict Console (design)

The demo's centerpiece is a single, self-contained **Risk Verdict Console**
(`reports/console.html`) — an intentional, well-arranged product UI, not a
generic dashboard.

- **Fonts:** **Fraunces** (display serif — the big verdicts) · **IBM Plex Mono**
  (all numerals/feeds) · **Manrope** (labels/UI). All embedded as base64, so it
  renders with zero network.
- **Live motion** (all disabled by the "reduce motion" toggle):
  - **Order-flow particle network** behind the hero — green/red "packets"
    drift between nodes (an image of risk moving through the system).
  - **Live streaming "Account Curve"** that draws in over time.
  - A **sweeping radar** on "Orders stopped" and a **pulsing** armed pill + a
    rotating shield mark.
  - Cards slide in / rows fade in.
- **Visual-first, de-densified:** rulebook is a row of **icon tiles**, text is
  kept short, and the numbers carry the story.
- **Layout:** a clean grid — hero verdict + KPI cards top, verdict feed +
  account curve + reflection below, rulebook strip at the bottom.
- **Color:** near-black + **Binance-gold** accent. Green = approve, red = block,
  amber = downsize (each chip also has an **icon**, so meaning never depends on
  colour alone).
- **Two themes:** **Dark** (default) and **Light**, toggled live.
- **Accessibility (♿ menu):**
  - **Reduce brightness** — mutes whites and the glow for sensitive eyes.
  - **Colour-blind safe** — swaps red/green for orange/blue.
  - **High contrast** — stronger borders & text.
  - **Reduce motion** — stops the animation.
- **The money shot:** the huge serif **"REFUSED SOL BUY"** hero verdict with the
  plain-English *why* and a **WAITING · you** approval state.
- Built on centralized **design tokens** (see `console.py`); change one value and
  the whole console restyles.

Generate it with `python3 console.py`. Screenshots of every mode are in `brand/`.

## Safety

Dry-run only. **No real funds, no orders, no keys.** Even with `--source live`,
nothing is traded. The modeled sub-account mirrors Agent OS's guardrails.

## ⚠️ Eligibility

Per Binance's rules this is not available to US, UK, EEA, Hong Kong, Singapore,
and prohibited-list jurisdictions. **Nigeria is not on the prohibited list**
(prohibited: US/CA/NL/Cuba/DPRK/Iran/Syria/Crimea). Confirm via the official
survey before relying on eligibility.
