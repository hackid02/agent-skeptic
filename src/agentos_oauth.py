"""OAuth 2.0 Authorization Code + PKCE client for Binance Agent OS.

Binance's Agent OS MCP server (`https://agent.binance.com/mcp/agentic`) is
protected by a standard MCP OAuth flow, which the server advertises via
`/.well-known/oauth-authorization-server`:

    grant_types          : ["authorization_code"]
    code_challenge_methods: ["S256"]          (PKCE)
    token_endpoint_auth_methods: ["none"]     (public client, PKCE only)
    client_id_metadata_document_supported: true

So connecting "with Agent OS" is a normal Authorization Code + PKCE handshake —
exactly what Claude Code / Codex CLI do under the hood. The only human step is
*you* authorizing (log in → approve → confirm the Agentic sub-account), which is
why Binance routes the connection through an AI client.

This module implements that flow so The Skeptic can connect for real:

  1. Discover the OAuth metadata (authorization + token endpoints).
  2. Generate a PKCE verifier + S256 challenge.
  3. Build the authorization URL for you to open in a browser.
  4. Exchange the returned authorization code for an access token.
  5. (See `agentos.LiveAgentOS`) use the bearer token on the MCP transport.

Because the token endpoint uses `token_endpoint_auth_methods: ["none"]`, the
client is a *public* client authenticated purely by PKCE + the code. The
client_id is provisioned from the metadata-document flow.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import secrets
import urllib.parse
import webbrowser
from typing import Dict, Optional

import httpx

WELL_KNOWN = "/.well-known/oauth-authorization-server"
PROTECTED_RESOURCE = "/.well-known/oauth-protected-resource/gateway-mcp"

DEFAULT_REDIRECT_URI = "http://localhost:8080/callback"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_pkce() -> tuple[str, str]:
    """Return (verifier, challenge) for PKCE (S256)."""
    verifier = _b64url(secrets.token_bytes(48))[:64]
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


async def discover(base_url: str = "https://agent.binance.com/mcp/agentic") -> Dict:
    """Fetch OAuth metadata from the server's well-known endpoints."""
    root = base_url.split("/mcp")[0]
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(root + WELL_KNOWN)
        resp.raise_for_status()
        meta = resp.json()
        if "token_endpoint" not in meta:
            raise RuntimeError(f"OAuth metadata missing token_endpoint: {meta}")
        return {"root": root, "base_url": base_url, **meta}


def build_authorize_url(meta: Dict, client_id: str, code_challenge: str,
                        state: str, redirect_uri: str = DEFAULT_REDIRECT_URI) -> str:
    """Build the URL the user opens to approve access."""
    q = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    })
    return meta["authorization_endpoint"] + "?" + q


async def exchange_code(meta: Dict, client_id: str, code: str, code_verifier: str,
                        redirect_uri: str = DEFAULT_REDIRECT_URI) -> Dict:
    """Exchange an authorization code for an access token."""
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": code_verifier,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(meta["token_endpoint"], data=data)
        body = resp.json()
        if resp.status_code != 200:
            raise RuntimeError(f"token exchange failed ({resp.status_code}): {body}")
        return body


async def refresh_token(meta: Dict, refresh_token: str) -> Dict:
    data = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(meta["token_endpoint"], data=data)
        body = resp.json()
        if resp.status_code != 200:
            raise RuntimeError(f"refresh failed ({resp.status_code}): {body}")
        return body


async def interactive_login(base_url: str = "https://agent.binance.com/mcp/agentic",
                            client_id: str = "agentic", redirect_uri: str = DEFAULT_REDIRECT_URI) -> Dict:
    """Full Authorization Code + PKCE flow with a local callback server.

    Prints the authorize URL, opens it in the browser (if available), listens
    for the redirect, exchanges the code, and returns the token payload.

    NOTE: this is the *user-consent* step. It needs a logged-in Binance account
    and a funded Agentic sub-account. It cannot complete without a human.
    """
    meta = await discover(base_url)
    verifier, challenge = generate_pkce()
    state = _b64url(secrets.token_bytes(16))
    url = build_authorize_url(meta, client_id, challenge, state, redirect_uri)

    # optional: try to open the browser
    try:
        webbrowser.open(url)
    except Exception:
        pass

    print(f"\n  Open this URL in your browser and approve:")
    print(f"    {url}")

    # capture the code from a tiny local redirect server
    code = await _wait_for_code(state, redirect_uri)
    print(f"\n  ✓ received authorization code.")
    token = await exchange_code(meta, client_id, code, verifier, redirect_uri)
    return {"meta": meta, "token": token}


async def _wait_for_code(state: str, redirect_uri: str, timeout: int = 300) -> str:
    """Run a one-shot local callback server to capture the redirected code."""
    from urllib.parse import urlparse, parse_qs
    from http.server import BaseHTTPRequestHandler, HTTPServer

    parsed = urlparse(redirect_uri)
    host, port = parsed.hostname or "127.0.0.1", parsed.port or 8080
    got: Dict = {}
    loop = asyncio.get_event_loop()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            q = parse_qs(urlparse(self.path).query)
            state_in = q.get("state", [None])[0]
            if state_in != state:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"state mismatch")
                got["error"] = "state mismatch"
                return
            got["code"] = q.get("code", [None])[0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(
                ("<html><body style='font-family:sans-serif;padding:40px'>"
                 "<h2>\u2705 Connected to Agent OS</h2>"
                 "<p>You can close this tab and return to the terminal.</p>"
                 "</body></html>").encode("utf-8"))
            loop.create_task(_shutdown(later_cb))

        def log_message(self, *a):
            pass

    def _shutdown():
        async def _stop():
            await asyncio.sleep(0.2)
            server.shutdown()
        return asyncio.create_task(_stop())

    later_cb = None
    server = HTTPServer((host, port), Handler)
    # run server in a thread; poll for the code
    import threading
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        for _ in range(timeout * 10):
            if got.get("code"):
                return got["code"]
            if got.get("error"):
                raise RuntimeError(got["error"])
            await asyncio.sleep(0.1)
        raise TimeoutError("No authorization code received within timeout.")
    finally:
        server.shutdown()
