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
                        state: str, redirect_uri: str = DEFAULT_REDIRECT_URI,
                        scope: Optional[str] = None) -> str:
    """Build the URL the user opens to approve access."""
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    if scope:
        params["scope"] = scope  # only request what was announced
    q = urllib.parse.urlencode(params)
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


async def refresh_token(meta: Dict, refresh_token: str, client_id: str = "agentic") -> Dict:
    """Refresh an access token. RFC 6749 §6: a public client (auth method
    'none') MUST authenticate with its client_id here."""
    data = {"grant_type": "refresh_token", "refresh_token": refresh_token,
            "client_id": client_id}
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(meta["token_endpoint"], data=data)
        body = resp.json()
        if resp.status_code != 200:
            raise RuntimeError(f"refresh failed ({resp.status_code}): {body}")
        return body


async def interactive_login(base_url: str = "https://agent.binance.com/mcp/agentic",
                            client_id: str = "agentic", redirect_uri: str = DEFAULT_REDIRECT_URI,
                            scope: Optional[str] = None) -> Dict:
    """Full Authorization Code + PKCE flow with a local callback server.

    Prints the authorize URL, opens it in the browser (if available), listens
    for the redirect, exchanges the code, and returns the token payload.

    NOTE: this is the *user-consent* step. It needs a logged-in Binance account
    and a funded Agentic sub-account. It cannot complete without a human.
    """
    meta = await discover(base_url)
    verifier, challenge = generate_pkce()
    state = _b64url(secrets.token_bytes(16))
    url = build_authorize_url(meta, client_id, challenge, state, redirect_uri, scope=scope)

    # optional: try to open the browser
    try:
        webbrowser.open(url)
    except Exception:
        pass

    print("\n  Open this URL in your browser and approve:")
    print(f"    {url}")

    # capture the code from a tiny local redirect server
    code = await _wait_for_code(state, redirect_uri)
    print("\n  ✓ received authorization code.")
    token = await exchange_code(meta, client_id, code, verifier, redirect_uri)
    return {"meta": meta, "token": token}


async def _wait_for_code(state: str, redirect_uri: str, timeout: int = 300) -> str:
    """Run a one-shot local callback server to capture the redirected code.

    The HTTP server runs in its own thread and never touches the asyncio loop
    (that thread has no running loop — the old loop.create_task call here was
    a live TypeError). The handler records the result and pokes a
    threading.Event; the async side polls and owns shutdown.
    """
    from urllib.parse import urlparse, parse_qs
    from http.server import BaseHTTPRequestHandler, HTTPServer
    import threading

    parsed = urlparse(redirect_uri)
    host, port = parsed.hostname or "127.0.0.1", parsed.port or 8080
    got: Dict = {}
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def _reply(self, ok: bool, title: str, body: str):
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                (f"<html><body style='font-family:sans-serif;padding:40px'>"
                 f"<h2>{title}</h2><p>{body}</p>"
                 f"</body></html>").encode("utf-8"))

        def do_GET(self):
            q = parse_qs(urlparse(self.path).query)
            # Provider error redirect (e.g. the user denied consent): fail
            # loudly and immediately — not as a misleading "state mismatch"
            # and not as a full 300-second hang.
            err = q.get("error", [None])[0]
            if err:
                desc = q.get("error_description", [""])[0]
                got["error"] = f"Authorization failed: {err}" + (f" ({desc})" if desc else "")
                self._reply(False, "\u274c Not connected", "You can close this tab.")
                done.set()
                return
            state_in = q.get("state", [None])[0]
            if state_in != state:
                got["error"] = "state mismatch (possible CSRF \u2014 aborting)"
                self._reply(False, "\u274c Not connected", "State check failed.")
                done.set()
                return
            code = q.get("code", [None])[0]
            if not code:
                got["error"] = "Redirect carried no authorization code."
                self._reply(False, "\u274c Not connected", "No code was returned.")
                done.set()
                return
            got["code"] = code
            self._reply(True, "\u2705 Connected to Agent OS",
                        "You can close this tab and return to the terminal.")
            done.set()

        def log_message(self, *a):
            pass

    server = HTTPServer((host, port), Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        # Poll from the async side; the handler thread only records + signals.
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            if got.get("code"):
                return got["code"]
            if got.get("error"):
                raise RuntimeError(got["error"])
            done.wait(timeout=0.1)
        raise TimeoutError("No authorization code received within timeout.")
    finally:
        server.shutdown()
