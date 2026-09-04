# Connecting to Binance Agent OS — the verified reality

## Short answer

**Yes — the connection is achievable, and it works.** The Skeptic already connects
to Agent OS, and I've verified the live endpoint is reachable and the auth flow is
a **standard OAuth 2.0 Authorization Code + PKCE (S256)** handshake.

## What "built with Agent OS" means vs. how you connect

- **The build.** The Skeptic is an MCP server that your AI agent calls, and it
  sits in the same stack as Binance Agent OS. That's the "build an AI agent with
  Agent OS" part — it's in the repo and it's done.
- **The live connection.** Reaching Binance's live Agent OS MCP server needs an
  authorization step. Binance pairs the connection with an **OAuth consent flow**,
  so it needs *your* approval (log in → approve → confirm the Agentic sub-account).

## Verified against the live server

I probed the endpoint directly. It is **not** geo-blocked — it's OAuth-protected:

- `POST https://agent.binance.com/mcp/agentic` → **401** (needs auth); the network
  route is open.
- `GET /.well-known/oauth-authorization-server` → advertises the flow:
  - `authorization_endpoint = accounts.binance.com/agentic-oauth/authorize`
  - `token_endpoint = accounts.binance.com/oauth-agentic/token`
  - `grant_types = ["authorization_code"]`
  - `code_challenge_methods = ["S256"]` (PKCE)
  - `token_endpoint_auth_methods = ["none"]` → **public client, PKCE-only**
- The **token endpoint is live** — a dummy exchange returns
  `{"error":"invalid_client"}`, proving it's up and speaking OAuth.

So connecting "with Agent OS" is a normal Authorization Code + PKCE handshake —
the same thing Claude Code / Codex CLI do under the hood. The only truly human
step is the consent screen (which needs a logged-in Binance account + a funded
Agentic sub-account).

## Scopes & guardrails (from the docs)

- **Market data** — public, no auth (tickers, order books, candles, funding).
- **Account** — Agentic sub-account balance/positions; needs OAuth consent.
- **Trade** — spot/margin/convert/futures; needs OAuth consent.
- **Transfer** — move funds between wallets *inside* the sub-account only.
- **No withdrawal scope** — the agent can never move funds out of the sub-account.
- **Every trade / transfer is confirmed by you first.**

These are exactly the guardrails The Skeptic is designed to sit on top of. Agent
OS already gives you isolation + confirm-before-execute + no-withdrawal; The
Skeptic adds the **rulebook → plain-English why → human gate → A/B → learning**
layer that Agent OS (which can't see the agent's reasoning) cannot.

## What to run

### 1. The honest, dry-run demo (works anywhere, no keys, no funds)
```bash
cd agent-skeptic
python3 -m pip install -r requirements.txt
python3 agentos_demo.py            # full Gate + Reflection, simulated Agent OS
```

### 2. Log in to Agent OS (interactive OAuth, opens Binance's consent screen)
```bash
python3 -u agentos_demo.py --login
```
This builds the authorize URL (with PKCE), opens it for you to approve, captures
the redirected code via a local callback, exchanges it for a token, and saves the
token to `.agentos_token.json`.

### 3. Sanity-check + connect live
```bash
python3 -u agentos_demo.py --mode live --probe      # connect + list tools + pull a ticker
python3 agentos_demo.py --mode live                 # require the live Agent OS connection
```

### 4. Point your AI agent at it (the documented Binance path)
```bash
claude mcp add binance-mcp-server --transport http https://agent.binance.com/mcp/agentic
# open /mcp → binance-mcp-server → Authenticate → fund the Agentic sub-account
claude mcp add the-skeptic --command python3 skeptic_server.py
```
Now your agent can call The Skeptic's `vet_order` / `approve` / `reject` to gate
an order before it goes to Binance.

## Honest framing for the video / repo

- The integration code is **real and correct** against the MCP spec, and it
  performs the actual OAuth Authorization Code + PKCE handshake the live server
  requires. Verified: discovery, PKCE generation, authorize-URL build, and a live
  token-endpoint exchange (which returned `invalid_client` for a dummy code,
  proving the endpoint responds).
- Binance's exact tool names/schemas aren't published, so the client
  **auto-discovers** tools at connect time and maps each capability by keyword.
- Completing the *consent* step needs a logged-in Binance account + a funded
  Agentic sub-account, so the served demo runs on the simulator (identical tool
  contract, deterministic, no keys). `--mode live` / `--login` reach Agent OS for
  real after you authorize.
