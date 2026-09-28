from __future__ import annotations

from . import __version__

PRODUCT_NAME = "VSN-Lead-Engine"
PRODUCT_URL = "https://vertexsystemsnetwork.com/"


def default_user_agent() -> str:
    """Return the canonical versioned public-network user agent."""
    return f"{PRODUCT_NAME}/{__version__} (+{PRODUCT_URL})"
