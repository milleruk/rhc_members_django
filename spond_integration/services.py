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

async def fetch_events_between(session, start, end):
    """
    Try several shapes of the unofficial client:
      - get_events_between(start, end)
      - get_events(start, end)
      - get_events() / list_events() then filter locally
      - get_calendar(start, end) style
    Returns a list[dict]-like.
    """
    # candidates that take (start, end)
    for name in ("get_events_between", "get_events", "list_events", "get_calendar", "fetch_events"):
        fn = getattr(session, name, None)
        if callable(fn):
            try:
                # Try passing both args
                return await fn(start, end)
            except TypeError:
                # Maybe it only takes no args; we'll handle that below
                try:
                    evs = await fn()
                    return _filter_events_by_range(evs, start, end)
                except TypeError:
                    pass

    # Last-ditch: try generic 'get_events()' no-arg then filter
    for name in ("get_events", "list_events"):
        fn = getattr(session, name, None)
        if callable(fn):
            evs = await fn()
            return _filter_events_by_range(evs, start, end)

    # If nothing matched, show what’s available for quick debugging
    attrs = ", ".join(a for a in dir(session) if not a.startswith("_"))
    raise AttributeError(
        f"Spond client has no compatible events method. "
        f"Tried get_events_between/get_events/list_events/get_calendar/fetch_events. "
        f"Session attrs: {attrs}"
    )


def _as_dt(val):
    """Best-effort parse of common event datetime fields."""
    from django.utils.dateparse import parse_datetime
    from django.utils import timezone
    if not val:
        return None
    if isinstance(val, (int, float)):  # epoch?
        try:
            return timezone.make_aware(datetime.fromtimestamp(val))
        except Exception:
            return None
    if isinstance(val, str):
        dt = parse_datetime(val)
        if dt and timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return dt
    return val if hasattr(val, "tzinfo") else None


def _filter_events_by_range(events, start, end):
    """Filter a list of event dicts to [start, end] using common keys."""
    out = []
    for ev in (events or []):
        # common keys we’ve seen
        s = _as_dt(
            ev.get("startTime") or ev.get("start") or
            (ev.get("time") or {}).get("start")
        )
        e = _as_dt(
            ev.get("endTime") or ev.get("end") or
            (ev.get("time") or {}).get("end")
        )
        # if no times, keep it (or skip—your choice). We'll keep if overlaps loosely.
        if not s and not e:
            out.append(ev)
            continue
        # overlap check
        if (not e and s <= end) or (not s and e >= start) or (s and e and not (e < start or s > end)):
            out.append(ev)
    return out
