"""Trusted fixed frontend return configuration, never request-derived redirect hosts."""

from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured


def dashboard_return(origin, *, debug):
    if origin == "":
        return None
    try:
        if (
            not isinstance(origin, str)
            or len(origin) > 2048
            or any(ord(c) <= 32 or ord(c) >= 127 for c in origin)
            or any(c in origin for c in "\\?#")
        ):
            raise ValueError
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or parsed.port == 0
            or (
                parsed.scheme == "http"
                and (not debug or parsed.hostname not in {"localhost", "127.0.0.1", "::1"})
            )
        ):
            raise ValueError
        return origin.rstrip("/") + "/dashboard"
    except ValueError:
        raise ImproperlyConfigured(
            "SAAS_WEB_ORIGIN must be an HTTPS origin, or a debug-only loopback HTTP origin."
        ) from None
