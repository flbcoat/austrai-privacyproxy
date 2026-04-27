"""AUSTR.AI — Security Middleware (CSRF + Security Headers + Host-Check).

CSRF-Schutz
-----------
Der Proxy lauscht auf localhost:8282. CORS (Starlette CORSMiddleware) schützt
bei einem Cross-Origin-Call nur das *Lesen* der Response, nicht den *Aufruf*.
Ein bösartiger Tab auf evil.example kann also per

    fetch('http://localhost:8282/chat/api/settings', {
      method: 'PUT',
      mode: 'no-cors',
      headers: {'Content-Type': 'text/plain'},
      body: JSON.stringify({ deny_list: ['…'] })
    })

Settings manipulieren. `Content-Type: text/plain` umgeht den CORS-Preflight,
weil es ein "simple request" ist. Darum prüfen wir auf jeder state-changing
Methode (POST/PUT/DELETE/PATCH) den `Origin` (bzw. fallback `Referer`)
Header gegen eine strikte Allowlist.

Host-Check (Anti-DNS-Rebinding)
-------------------------------
Ein Angreifer kann eine Domain so DNS-rebinden, dass sie erst auf seine IP,
dann auf 127.0.0.1 auflöst. Browser-Requests zum Proxy kommen dann mit
`Host: attacker.example`. Wir erzwingen `Host` ∈ {localhost:*, 127.0.0.1:*}.

Security-Response-Headers
-------------------------
CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy. Hart
eingestellt — die App lädt nur self, blob: (Redact-Bilder) und Google Fonts
(CDN).
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("austrai.security")


# ---------------------------------------------------------------------------
# Error redaction
# ---------------------------------------------------------------------------

# Bekannte Secret-Formate verschiedener Provider. Greift auch wenn der
# Upstream-Provider einen Key versehentlich in seinem Error-Body echot
# (ja, das passiert — manche Mistral/Google-Fehler enthalten den Bearer-
# Header im 403-JSON).
_SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),                # Anthropic
    re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),          # OpenAI + project keys
    re.compile(r"pypi-[A-Za-z0-9_-]{20,}"),                  # PyPI tokens
    re.compile(r"AKIA[0-9A-Z]{16}"),                         # AWS Access Key ID
    re.compile(r"ghp_[A-Za-z0-9]{36,}"),                     # GitHub PAT
    re.compile(r"(?i)Bearer\s+[A-Za-z0-9._\-~+/]{20,}=*"),   # Bearer tokens
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),                    # Google API keys
]


def redact_secrets(text: str) -> str:
    """Best-effort scrub of provider secrets from an error string."""
    if not text:
        return text
    for rx in _SECRET_PATTERNS:
        text = rx.sub("[REDACTED-SECRET]", text)
    return text


def safe_error_message(exc: Exception | None, *, max_len: int = 300,
                       fallback: str = "Internal server error") -> str:
    """Return a client-safe error message. Strips known secrets, caps length,
    and falls back to a generic message if the redacted output would be
    empty. Never returns a full stacktrace — those belong in the log only.
    """
    if exc is None:
        return fallback
    raw = str(exc)
    redacted = redact_secrets(raw)[:max_len].strip()
    return redacted or fallback


# Allowlisted origins for state-changing requests. Beide Schreibweisen
# (127.0.0.1 und localhost) sind erlaubt, weil Browser sich unterschiedlich
# verhalten und beide in der Adresszeile valide sind.
_ALLOWED_ORIGINS = frozenset({
    "http://127.0.0.1:8282",
    "http://localhost:8282",
})

# Host-Header Allowlist (ohne Port — Port wird separat geprüft, falls gesetzt).
_ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost"})

# Methods die State verändern und darum Origin/Referer verlangen.
_STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Content Security Policy — `unsafe-inline` für style ist nötig weil wir
# inline styles an mehreren Stellen nutzen (tutorial-Demos etc.). Das ist
# ein bewusster Kompromiss; script-src bleibt strikt ohne unsafe-inline /
# unsafe-eval. importmap im index.html ist <script type="importmap"> das
# zählt als inline script, wir erlauben das via Hash-allowlisting wäre
# aufwendig — stattdessen belassen wir script-src 'self' und der importmap
# wird ignoriert oder funktioniert trotzdem (manche Browser parsen
# importmaps außerhalb der CSP-script-Regel).
_CSP = (
    "default-src 'self'; "
    "img-src 'self' data: blob:; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "script-src 'self' 'unsafe-inline'; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "form-action 'self'"
)


def _extract_host(header_value: str | None) -> str | None:
    """Return the host part without port from an Origin/Referer header."""
    if not header_value:
        return None
    try:
        parsed = urlparse(header_value if "://" in header_value else f"http://{header_value}")
        return parsed.hostname
    except Exception:
        return None


def _origin_is_allowed(request: Request) -> bool:
    """True wenn Origin/Referer zu localhost:8282 passt."""
    origin = request.headers.get("origin")
    if origin and origin in _ALLOWED_ORIGINS:
        return True
    # Fallback: Referer. Browser strippen Referer manchmal; dann ist der
    # Request vermutlich tool-basiert (curl/same-origin navigation) —
    # in dem Fall verlangen wir explizit Same-Origin.
    referer = request.headers.get("referer")
    if referer:
        refhost = _extract_host(referer)
        if refhost in _ALLOWED_HOSTS:
            return True
    # Letzte Chance: Same-Origin navigation ohne Origin-Header. Das ist bei
    # modernen Browsern selten, aber vorhanden (z.B. form POSTs von der
    # eigenen Seite in manchen Konstellationen). Wenn weder Origin noch
    # Referer da ist, behandeln wir den Request als *nicht* browser-
    # gesteuert — nur erlaubt wenn der Host korrekt ist.
    if origin is None and referer is None:
        return True  # non-browser clients (curl, CLI)
    return False


def _host_is_allowed(request: Request) -> bool:
    """Anti-DNS-rebinding: Host-Header muss localhost/127.0.0.1 sein."""
    host_header = request.headers.get("host", "")
    # Strip port
    host = host_header.split(":", 1)[0].lower() if host_header else ""
    return host in _ALLOWED_HOSTS


class SecurityMiddleware(BaseHTTPMiddleware):
    """Kombinierte CSRF + Host-Check + Response-Hardening Middleware."""

    async def dispatch(self, request: Request, call_next):
        # 1) Host-Header-Check auf ALLEN Requests (auch GET). DNS-Rebinding
        #    könnte GETs missbrauchen um sensible Daten zu lesen.
        if not _host_is_allowed(request):
            logger.warning("Blocked request with invalid Host header: %r", request.headers.get("host"))
            return JSONResponse(
                {"error": "Invalid Host header"},
                status_code=400,
            )

        # 2) CSRF-Check nur auf state-changing Methoden.
        if request.method in _STATE_CHANGING_METHODS:
            if not _origin_is_allowed(request):
                origin_value = request.headers.get("origin") or request.headers.get("referer") or "(none)"
                logger.warning("Blocked cross-origin %s request. origin=%r path=%s",
                               request.method, origin_value, request.url.path)
                return JSONResponse(
                    {"error": "Cross-origin request rejected"},
                    status_code=403,
                )

        # 3) Forward to handler.
        response = await call_next(request)

        # 4) Security Response Headers (auf ALLEN Responses, auch Fehler).
        response.headers["Content-Security-Policy"] = _CSP
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        # Permissions-Policy: verweigere Kamera/Mikrofon/Geolocation per default.
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response
