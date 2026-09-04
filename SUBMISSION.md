# Submission checklist — Binance Agent OS Mini Hackathon (Track A)

**Deadline: Sept 8, 2026, 23:59 UTC** (~11:59pm Lagos time on the 8th).
Do NOT leave this for the last hour.

Entry rule (from the announcement): follow @Binance & repost → reply/quote with
your submission (video/demo + GitHub) → complete the survey.

---

## [ ] 0. Pre-flight (30 min)
- [ ] Confirm you're comfortable entering (see eligibility note below).
- [ ] Have a **GitHub** account and a **Binance** account.
- [ ] Push the repo (`agent-skeptic/`) to a **public** GitHub repo.
      - `git init`, `git add .`, commit, `git remote add origin <url>`, `git push`.
- [ ] Double-check the repo runs from a clean clone: `python3 agentos_demo.py && python3 demo.py`.

## [ ] 1. Video (the part that wins) — 60–90s
- [ ] Record per `VIDEO_SCRIPT.md`. Lead with `python3 agentos_demo.py` (shows the
      MCP server + the real "built with Agent OS" flow), then `python3 console.py`.
- [ ] The "money shot" MUST show the agent **refusing a bad trade** + explaining why.
- [ ] Show the Reflection table (trades 19→4, drawdown −81%, fees −78%, 93 stopped).
- [ ] Voiceover + English subtitles. Upload to **YouTube/Vimeo/Streamable** and
      set it **public / unlisted**. Grab the link (a direct URL, no login needed).

## [ ] 2. GitHub repo ready
- [ ] Public repo with `README.md` (the pitch) — already written.
- [ ] Include `agentos_demo.py`, `skeptic_server.py`, `demo.py`, `console.py`, `src/`,
      `requirements.txt`, `PRD.md`, `VIDEO_SCRIPT.md`.
- [ ] A `LICENSE` (MIT) for polish — optional but good.
- [ ] Keep the demo reproducible: note the `--seed` and default data source.

## [ ] 3. Enter
- [ ] **Follow @Binance** on X.
- [ ] **Repost** the announcement post.
- [ ] **Reply or quote-repost** with your submission. Template:

  > 🛡️ Built **The Skeptic** for #BinanceAgentOS — an Agent OS agent that vets
  > every order before it reaches Binance, explains the why in plain English,
  > and lets YOU approve.
  > ▶️ Demo: <video link>
  > 🔗 Code: <github link>
  > #AgentOS #Binance

- [ ] **Complete the survey** (the link Binance posted). This is the actual
      entry mechanism — the X reply is for visibility, the survey is for entry.
- [ ] Save a copy of your X reply URL + survey confirmation.

## [ ] 4. Post-submit (don't stop here)
- [ ] Set a reminder for **Sep 8 ~23:00 UTC** to verify links still load.
- [ ] Watch the thread for the winners announcement; the prizes are listed in the
      follow-up post (Track A: 1st $2,000 / 2nd $1,500 / 3rd $1,000 / 50×$300).

---

## ⚠️ Eligibility — read this
The post says it's not available to **US, UK, EEA, Hong Kong, Singapore** and
Binance's **prohibited list**. That list is **US, Canada, Netherlands, Cuba,
North Korea, Iran, Syria, Crimea/non-government-controlled Ukraine**.

**Nigeria is not on the prohibited list.** Binance supports Nigerian users for
crypto-to-crypto (naira services were discontinued in 2024). So on the published
rules you're eligible. **Nonetheless, the survey is the final authority** — if it
rejects your region, that's Binance's call and there's no workaround. Enter
honestly; don't misrepresent your location.

## Tips to actually place
- The judging criteria (per the ecosystem's precedent) are **technical execution,
  originality, real-world relevance, demo.** The Skeptic hits originality
  (risk-governance, not another bot) and real-world relevance (the trust problem).
- **Demo is heaviest.** A clear, 90-second video beats a longer, muddier one.
- Don't claim profits. Judges respect the honest "stops bleeding out" framing
  far more than a fake PnL.
