```claude
# Title
The Skeptic — an Agent OS risk-governor that vets, explains and constrains an AI trading agent.

# Purpose
Give a crypto trader a trustworthy way to let an AI agent touch money. The Skeptic sits between the agent and the funds, refuses/downsizes reckless orders, explains every decision in plain English, requires human approval, and learns/updates its own rulebook. It answers the launch-and-media question: "how do we trust an agent with money?"

# Scope
In:
- Vet incoming order intents against an auditable rulebook.
- Produce BLOCK / DOWNSIZE / APPROVE verdicts with a human-readable reason.
- Require user approval before any (simulated) execution.
- Run a same-market A/B to show risk improvement.
- Propose rulebook updates from observed behaviour.

Out:
- No profit prediction or guarantees.
- No external withdrawal capabilities (mirrors Agent OS sub-account guardrails).
- No live Agent OS execution exercised in the served demo (dry-run by default); the
  Agent OS MCP client is real and pointed at `https://agent.binance.com/mcp/agentic`,
  but demo execution uses the simulated backend so it needs no funds/keys/risk.

# User Personas
1. "Cautious Pablo" — retail crypto holder, small bag, scared to automate, wants a safety net he can read and veto.
2. "Overstretched Omar" — a quant/dev who automates but has been burned by a bot that overtraded or blew up; wants visible guardrails and post-hoc audit.
3. "Risk-aware Wale" — a Nigeria-based trader who understands the platform's restrictions and wants rules he fully owns.

# Functional Requirements
- FR-01: Accept an order intent (symbol, side, notional, price, volatility, stated reason).
- FR-02: Evaluate the intent against a user-owned rulebook (single-position cap, exposure cap, drawdown guard, volatility band, fee budget, sizing multiplier).
- FR-03: Return a verdict: APPROVE, DOWNSIZE, or BLOCK with a plain-English rationale.
- FR-04: Always allow risk-reducing orders (trims/rebalancing don't get blocked).
- FR-05: Require explicit human approval before executing; a "no" cancels the order.
- FR-06: Record every verdict with its reasoning (decision log) for review.
- FR-07: Run a same-market A/B (unguarded vs guarded) and report trades, drawdown, fees, and reckless orders stopped.
- FR-08: From observed behaviour, propose rulebook updates (e.g. trade cap, tighter drawdown guard) as drafts the user owns.
- FR-09: Support a deterministic synthetic feed (default) and optional live public candles.
- FR-10: Output a self-contained HTML reflection report with inline styling.
- FR-11: Run The Skeptic as an **MCP server** exposing governance tools
  (`vet_order`, `get_rulebook`, `approve`, `reject`, `run_ab`, `propose_rulebook_update`)
  over stdio and streamable-HTTP.
- FR-12: Consume the **Binance Agent OS MCP server** as a client (market data,
  sub-account balance, order execution), discovering its tools at connect time.
- FR-13: On approval, forward the order to Agent OS only after the human says so;
  a reject means it never reaches Agent OS.
- FR-14: Gracefully fall back to a simulated Agent OS backend (same tool contract)
  when the live endpoint is unreachable, so the demo stays dry-run.

# Non-Functional Requirements
- NFR-01: Zero real funds, zero API keys, zero orders (dry-run by default). Never withdraw.
- NFR-02: Reproducible output (seeded) so the demo is legible and defensible.
- NFR-03: Plain-English explanations use no jargon; a non-quant can read the why.
- NFR-04: Rules are explicit, auditable data, not hidden model logic.
- NFR-05: Runs on Python 3 with `requests` and `mcp` as dependencies.
- NFR-06: Self-contained HTML report (inline CSS) that renders in a sandboxed viewer.
- NFR-07: The Agent OS integration is dual-backend: `--mode auto` (live, fall back),
  `--mode live` (require), `--mode sim` (deterministic, no keys).

# Assumptions & Constraints
- Assumption: The value proposition is risk/discipline, not profit; we never claim returns.
- Assumption: The user owns the rulebook; the agent only proposes changes.
- Constraint: The agent connects to Binance **through Agent OS** (`https://agent.binance.com/mcp/agentic`); The Skeptic never holds API keys or a withdrawal scope.
- Constraint: This sandbox IP is geo-blocked by Binance (`api.binance.com` → 451, MCP endpoint unreachable), so the served demo uses the simulated Agent OS backend; the live client is real and documented.
- Constraint: Deadline Sept 8, 2026 23:59 UTC.

# Success Metrics
- SM-01: Guarded agent materially reduces drawdown vs unguarded on the same market.
- SM-02: Guarded agent reduces trades and fee burn vs unguarded.
- SM-03: Non-trivial count of reckless orders stopped (a visible, memorable number).
- SM-04: Every verdict is explainable in one plain-English sentence.
- SM-05: Clean, reproducible `python3 demo.py` run that produces console + HTML report.
- SM-06: `python3 agentos_demo.py` runs The Skeptic as a real MCP server, connects a client, and drives the gate + reflection with zero errors.
- SM-07: Submission-ready package: README, PRD, demo video script, submission checklist.

## Summary
The Skeptic is a risk-governor for AI trading agents, built for the Agent OS hackathon. It vets every order, explains the why in plain English, requires human approval, and lets users own the rules — directly answering the trust question the launch raised. It's honest (no profit claims), useful (stops bleeding out), original (risk governance, not another trading bot), and demo-able. It runs dry-run on public/synthetic data with a modeled Agent OS sub-account, requires no funds or keys, and is fully scoped to fit the deadline.
```
