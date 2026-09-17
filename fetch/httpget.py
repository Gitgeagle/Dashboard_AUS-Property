"""Shared HTTP helper. Stdlib only - keeps the Actions run dependency-free."""
import gzip
import io
import json
import shutil
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
TIMEOUT = 25

_CTX = None


def _context():
    """TLS context that also trusts the Windows certificate store.

    Corporate networks that terminate TLS present a root Python's bundled CAs don't
    know about, which breaks every fetch locally while working fine in CI. Loading the
    OS store fixes local runs without weakening verification. No-op off Windows.
    """
    global _CTX
    if _CTX is not None:
        return _CTX
    ctx = ssl.create_default_context()
    if sys.platform == "win32":
        for store in ("ROOT", "CA"):
            try:
                for cert, enc, _trust in ssl.enum_certificates(store):
                    if enc == "x509_asn":
                        try:
                            ctx.load_verify_locations(cadata=cert)
                        except ssl.SSLError:
                            pass
            except Exception:  # noqa: BLE001 - store unavailable, keep defaults
                pass
    _CTX = ctx
    return ctx


def _curl(url, headers=None):
    """Fetch via the curl binary.

    On Windows curl uses Schannel, which validates against the live OS trust chain and
    can pull down roots on demand. OpenSSL cannot, so on a machine whose root store has
    been trimmed by group policy some genuine certificates fail to verify. This keeps
    full verification (no -k) while letting local runs work. CI runners never need it.
    """
    exe = shutil.which("curl")
    if not exe:
        raise RuntimeError("curl unavailable for TLS fallback")
    cmd = [exe, "-sSL", "--fail", "--max-time", str(TIMEOUT), "-A", UA]
    for k, v in (headers or {}).items():
        cmd += ["-H", f"{k}: {v}"]
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True, timeout=TIMEOUT + 15)
    if r.returncode != 0:
        raise RuntimeError(f"curl exit {r.returncode}: {r.stderr.decode(errors='replace')[:200]}")
    return r.stdout


def _is_tls_error(e):
    return isinstance(e, ssl.SSLError) or "CERTIFICATE_VERIFY_FAILED" in str(e)


def get(url, headers=None, retries=2, backoff=1.5):
    """GET a URL, returning bytes. Raises the last error if every attempt fails."""
    hdrs = {"User-Agent": UA, "Accept-Encoding": "gzip", "Accept": "*/*"}
    if headers:
        hdrs.update(headers)
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=_context()) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
                return raw
        except Exception as e:  # noqa: BLE001 - any failure is retryable here
            last = e
            if _is_tls_error(e):
                return _curl(url, headers)
            if attempt < retries:
                time.sleep(backoff * (attempt + 1))
    raise last


def get_text(url, headers=None, **kw):
    return get(url, headers, **kw).decode("utf-8", errors="replace")


def get_json(url, headers=None, **kw):
    return json.loads(get(url, headers, **kw).decode("utf-8", errors="replace"))
