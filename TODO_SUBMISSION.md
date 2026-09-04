# The Skeptic — Hackathon submission action list

**Track A · Binance Agent OS Mini Hackathon · Deadline Sept 8, 2026, 23:59 UTC**
(Track A $20,000 pool. ~11:59pm Lagos time on the 8th.)

The brief requires **three things** for Track A:
1. **Build an AI agent with Agent OS.** ✅ **DONE** — The Skeptic is an Agent OS
   agent: it's an MCP server + an MCP client of Binance's Agent OS server, and it
   performs the real OAuth Authorization Code + PKCE handshake.
2. **Submit a demo/video.** ⬜ **NEEDS DOING** — record it.
3. **A public GitHub repo.** ⬜ **NEEDS DOING** — the code isn't on GitHub yet.
4. **Enter:** follow @Binance → repost the announcement → reply with your
   submission → **complete the survey**. ⬜ **NEEDS DOING** (some steps are just
   you clicking things; I can prep the text).

---

## [x] 0. Get it onto GitHub — DONE
Repo is live: `https://github.com/hackid02/agent-skeptic` (public, branch `main`).
README now links the repo + author. Verify clean-clone run passed (4 commands, exit 0, zero tracebacks).

The folder is **not a git repo yet**. Do:

```bash
cd agent-skeptic
# create a .gitignore first (see below), then
git init
git add .
git commit -m "The Skeptic — Agent OS risk-governor (Track A submission)"
git branch -M main
git remote add origin https://github.com/<YOUR_USERNAME>/agent-skeptic.git
git push -u origin main
```

**Create `.gitignore`** (so junk isn't pushed):
```
__pycache__/
*.pyc
.agentos_token.json
reports/
fonts/licenses/
*.log
```
> Note: `reports/console.html` + `brand/*.png` are the designed demo — I'd keep
> them in the repo (they're the money shot), so **don't** ignore `reports/` or
> `brand/` if you want the console in the repo. Only ignore the generated
> `__pycache__`, the `.agentos_token.json` (contains a live OAuth token — do NOT
> commit it), and `*.pyc`.

## [x] 1. Verify it runs from a clean clone — DONE (exit 0, zero tracebacks on all 4 runs)

```bash
python3 -m pip install -r requirements.txt
python3 agentos_demo.py            # the Agent OS demo (simulated backend)
python3 demo.py                    # scripted terminal demo
python3 console.py                 # generates reports/console.html
python3 agentos_demo.py --mode auto --probe   # proves the Agent OS wiring + prints connect steps
```
All four should run with **zero tracebacks**.

## [ ] 2. Record the video (the part that decides the prize)

- Follow `VIDEO_SCRIPT.md` — it's already shot-by-shot, 60–90s.
- **Lead** with `python3 agentos_demo.py` (shows the real MCP server + the
  agent-gates-every-order flow), then `python3 console.py` for the designed UI.
- **The money shot** must show the agent **refusing a bad trade + explaining why**
  (Scene 1: `BUY BTC $4,200` → `BLOCK` → "42% of the account, above the 10% cap").
- Show the **Reflection table** (19→4 trades, −81% drawdown, −78% fees, 93 stopped).
- Add English captions; upload to YouTube/Vimeo/Streamable as **public/unlisted**.

## [ ] 3. Post the entry X post (template in SUBMISSION.md)

> 🛡️ Built **The Skeptic** for #BinanceAgentOS — an Agent OS agent that vets every
> order before it reaches Binance, explains the why in plain English, and lets YOU
> approve.
> ▶️ Demo: <video link>
> 🔗 Code: <github link>
> #AgentOS #Binance

Steps: **follow @Binance** → **repost** the announcement → **reply/quote** with the
above.

## [ ] 4. Complete the Binance survey (the actual entry mechanism)

The survey is at `binance.com/en/survey/2913aa200aac462c89a737779393f3d4`.
The X reply is for visibility; **the survey is what officially enters you.**
Save a copy of your X reply URL + the survey confirmation.

## [ ] 5. Post-deadline hygiene

- Set a reminder for ~23:00 UTC on Sept 8 to verify the video + repo links load.
- Don't claim profit; the honest line is "stops it bleeding out / cuts risk."

---

## Where the build already stands vs. the brief (my audit)

| Brief requirement | Status |
|---|---|
| Build an AI agent **with** Agent OS | ✅ Done — MCP server + Agent OS MCP client |
| Actually connect to Agent OS | ✅ Wiring proven; live OAuth PKCE flow implemented |
| Video/demo | ⬜ To record |
| Public GitHub repo | ⬜ To push |
| Follow + repost + reply + survey | ⬜ To do (prep ready) |
| Not in restricted jurisdiction | ✅ Nigeria is eligible (not on the US/UK/EEA/HK/SG list) |
| No profit claims | ✅ Honest framing throughout |
| Standout design (dark/light, a11y, live motion, logo/letterhead) | ✅ Done & verified |

## Is it on the right path? (compared to good submissions in this space)

Strong submissions in the agent-governance/AI-trading-crypto hackathon space
consistently win on **four** things, and we tick all four:

1. **Technical execution** — we have a real MCP server + client, real OAuth PKCE,
   tool auto-discovery, live data fallback, and a clean architecture. Not a demo-ware
   mock.
2. **Originality** — most entries are "agents that trade" (crowded) or "order
   guardrail wrappers" (already owned by `eikarna/binance-agent-mcp`). The Skeptic
   is the *judgement / governance* layer — a distinct, defensible niche that
   directly answers the "how do we trust an agent with money?" gap Binance itself
   raised.
3. **Real-world relevance** — the exact gap: Binance can see the trades but **not**
   the agent's reasoning. The Skeptic exposes that reasoning and gates it.
4. **Demo quality** — a single visceral beat ("the agent refuses an oversized buy
   and explains why"), a designed risk-verdict console (dark/light, a11y, live
   motion, professional logo/letterhead), and an honest A/B with a memorable number
   (93 reckless orders stopped).

**Weakest link:** the video isn't recorded and the repo isn't pushed. That's the
entire remaining risk. The build is stronger than most of what you're competing
against; the delivery is what's on the clock.
