# The Skeptic — 90-second demo video script

**Goal:** a judge watches 90 seconds and gets it instantly. Lead with the one
visceral beat — *the agent refuses a bad trade and explains why.* Then show it
improves outcomes. End on the one-liner.

Format: screen capture of the terminal (`python3 agentos_demo.py` for the
Agent OS / MCP run, then `python3 console.py` for the designed console),
optionally with a facing-camera or voiceover. Keep bullets on screen. 60–90s.

---

## Shot-by-shot

**00:00—00:08 · HOOK**
> Caption: *"Trading agents are getting money. Nobody's guarding them."*

Voice: "Everyone's racing to build an agent that trades. But the real question
Agent OS raised is *how do we trust an agent with money?*"

**00:08—00:14 · "Built with Agent OS" (show the real connection)**
> Type `python3 agentos_demo.py --mode live --probe` (or `--login` for the OAuth step)
> On screen: the MCP tool list Agent OS actually exposes + a live BTCUSDT price.

Voice: "This is the Skeptic. It's an Agent OS agent — it connects to Binance's
Agent OS server, discovers its tools, and sits between your trading agent and
your money."

**00:14—00:22 · The Gate**
> Type `python3 agentos_demo.py` (the MCP client → The Skeptic server run)

Voice: "It vets every order before it executes. Here's the flow: your agent calls
`vet_order`. The Skeptic checks it against your rulebook and returns a verdict —
with the reason in plain English."

**00:22—00:40 · THE MONEY SHOT (Scene 1: an oversized buy) — vet_order → BLOCK**
On screen: the agent wants **BUY BTC ~4,200 USDC**. The Skeptic shows:
- `✗ 4,200 USDC is 42% of the account, above the 10% cap`
- `✗ 4.2x base unit — that's streak-driven greed`

Voice: "Here's the moment. The agent wants to go big — 42% of the account, off a
win streak. The Skeptic says no, in plain English, before a cent moves. **You**
approve, not the bot."

**00:40—00:55 · PROOF (Reflection)**
> Cut to the `REFLECTION` table / `reports/reflection.html`

On screen: same market, same agent
- Trades **19 → 4**
- Drawdown **2.2% → 0.4%** (cut 81%)
- Fees **15.56 → 3.47** USDC
- Ended **$9,855 → $9,962**
- **93 reckless orders stopped**

Voice: "Same market, same agent. Unwatched it churned 19 trades and drew down
2.2%. Under the Skeptic it took 4, cut drawdown 81%, cut fees 78% — and actually
ended higher. And it stopped 93 reckless orders."

**00:55—01:15 · REFLECTION/LESSON (optional)**
> Show the rulebook it proposes
Voice: "It even reviews its own behaviour and proposes new rules — but *you* own
those. That's 'your rules, your agents.'"

**01:15—01:25 · CLOSE**
> End card: **The Skeptic — your agent's risk desk.** + repo handle
Voice: "The Skeptic doesn't predict the market. It stops your agent from bleeding
out — and tells you why. Built on Binance Agent OS. Link in bio."

---

## Production notes
- **Audio:** ~90s voiceover ≤300 words. Read at a calm pace.
- **Capture:** macOS QuickTime/Windows Game Bar or OBS; record the terminal at
  max width. Also screenshot `reports/reflection.html` for a clean visual.
- **Ethics:** never claim the agent "makes money." Say "stops it bleeding out /
  cut risk." That's the honest, defensible line.
- **Subtitles:** add English captions (binance judging may be non-native EN).

## One-liner card
> **The Skeptic — your agent's risk desk.**
> An Agent OS agent that vets every order before it reaches Binance.
> Explains why in plain English. You approve. Built on Binance Agent OS. #BinanceAgentOS
