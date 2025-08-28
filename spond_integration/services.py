# spond_integration/services.py
import asyncio
from datetime import datetime
from typing import Any, Callable, Type

def _resolve_client_factory() -> Callable[..., Any]:
    """
    Try a few likely layouts of the unofficial 'spond' package and return
    a callable that, given username/password, returns a SESSION-like object
    exposing the async methods we need (e.g., get_groups(), get_events_between()).
    """
    # 1) Top-level module
    try:
        import spond as m
        # Class candidates
        for name in ("Spond", "SpondClient", "Client", "API"):
            cls = getattr(m, name, None)
            if isinstance(cls, type):
                return lambda username, password: cls(username=username, password=password)
        # Factory function candidates
        for name in ("Spond", "client", "get_client", "login", "authenticate"):
            fn = getattr(m, name, None)
            if callable(fn):
                return lambda username, password: fn(username=username, password=password)
    except ImportError:
        pass

    # 2) Submodule (some releases export a submodule)
    try:
        from spond import spond as sub
        for name in ("Spond", "SpondClient", "Client", "API"):
            cls = getattr(sub, name, None)
            if isinstance(cls, type):
                return lambda username, password: cls(username=username, password=password)
        for name in ("Spond", "client", "get_client", "login", "authenticate"):
            fn = getattr(sub, name, None)
            if callable(fn):
                return lambda username, password: fn(username=username, password=password)
    except ImportError:
        pass

    # If we got here, the module is present but unexpected.
    try:
        import spond as m  # for diagnostics
        available = ", ".join(sorted(dir(m)))
        src = getattr(m, "__file__", "unknown")
    except Exception:
        available = "unavailable"
        src = "unavailable"

    raise ImportError(
        "Could not resolve a Spond client factory from the 'spond' package. "
        f"Available attributes: {available}. Module file: {src}. "
        "Please check the package version and API. (Try: pip show spond)"
    )

# Create a module-level factory once
_CLIENT_FACTORY = _resolve_client_factory()

class SpondClient:
    """
    Async context manager that yields a session-like object from the unofficial spond client.
    """
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self._session = None

    async def __aenter__(self):
        self._session = _CLIENT_FACTORY(self.username, self.password)
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        # Best-effort close of underlying aiohttp session if present
        clientsession = getattr(self._session, "clientsession", None)
        if clientsession and hasattr(clientsession, "close"):
            await clientsession.close()

def run_async(coro):
    return asyncio.run(coro)

# High-level helpers the tasks use
async def fetch_groups_and_members(session):
    return await session.get_groups()

async def fetch_events_between(session, start: datetime, end: datetime):
    return await session.get_events_between(start, end)
