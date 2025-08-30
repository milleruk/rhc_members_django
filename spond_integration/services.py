# spond_integration/services.py
import asyncio
from datetime import datetime
from typing import Any, Callable, Type


import logging
logger = logging.getLogger(__name__)

def _looks_like_txn_list(val):
    """Return True if val looks like a list of transaction-like dicts."""
    if not isinstance(val, list) or not val:
        return False
    if not all(isinstance(x, dict) for x in val):
        return False
    # common finance-ish keys we’ll accept any subset of
    keys_of_interest = {
        "id", "type", "status", "amount", "currency", "description",
        "createdTime", "created_at", "settledTime", "memberId", "member_id",
        "groupId", "group_id", "eventId", "event_id", "reference"
    }
    sample_keys = set()
    for x in val[:5]:
        sample_keys |= set(x.keys())
    return bool(sample_keys & keys_of_interest)

def _filter_txns_by_created(txs, start, end):
    out = []
    for t in (txs or []):
        created = (
            t.get("createdTime") or t.get("created_at")
            or t.get("created") or t.get("timestamp")
        )
        if _in_range(created, start, end):
            out.append(t)
    return out

def _resolve_client_factory() -> Callable[..., Any]:
    """
    Try a few likely layouts of the unofficial 'spond' package and return
    a callable that, given username/password, returns a SESSION-like object.
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

    # 2) Submodule variant
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

    # Fallback diagnostics
    try:
        import spond as m
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
    Async context manager that wraps the raw Spond client.
    Adds helper methods (transactions, events, generic get_json).
    """
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self._session = None  # actual underlying client

    def __getattr__(self, name):
        """Delegate to underlying session for unknown attrs."""
        if self._session is None:
            raise AttributeError(
                f"'SpondClient' not initialized yet while accessing {name!r}"
            )
        return getattr(self._session, name)

    async def __aenter__(self):
        self._session = _CLIENT_FACTORY(self.username, self.password)
        return self  # return wrapper, not raw session

    async def __aexit__(self, exc_type, exc, tb):
        clientsession = getattr(self._session, "clientsession", None)
        if clientsession and hasattr(clientsession, "close"):
            await clientsession.close()

    async def get_json(self, path, params=None):
        """Generic fallback REST-style call if underlying client supports it."""
        for cand in ("get_json", "get", "request"):
            fn = getattr(self._session, cand, None)
            if callable(fn):
                try:
                    return await fn(path, params=params)
                except TypeError:
                    try:
                        return await fn("GET", path, params=params)
                    except TypeError:
                        pass
        raise AttributeError(
            "Underlying Spond session has no get/get_json/request method"
        )

    async def fetch_transactions_between(self, start: datetime, end: datetime):
        """
        Fetch transactions between two datetimes, trying multiple client shapes.
        """

        # 1) Obvious candidate method names that may take (start, end)
        candidates = [
            # common
            "get_transactions_between", "get_transactions", "list_transactions", "fetch_transactions",
            # other libraries’ naming
            "get_payments_between", "get_payments", "list_payments", "fetch_payments",
            "get_finance_between", "get_finance", "finance",
            "get_ledger_between", "get_ledger", "ledger",
            "get_invoices_between", "get_invoices", "invoices",
        ]
        tried = []

        for name in candidates:
            fn = getattr(self._session, name, None)
            if not callable(fn):
                continue
            tried.append(name)
            # try (start, end)
            try:
                res = await fn(start, end)
                if _looks_like_txn_list(res):
                    return _filter_txns_by_created(res, start, end)
            except TypeError:
                pass
            except Exception as e:
                logger.debug("Spond.%s(start,end) failed: %s", name, e)

            # try no-arg, then filter by time
            try:
                res = await fn()
                if _looks_like_txn_list(res):
                    return _filter_txns_by_created(res, start, end)
            except TypeError:
                pass
            except Exception as e:
                logger.debug("Spond.%s() failed: %s", name, e)

        # 2) Heuristic probe: callables whose name looks finance-y
        patterns = ("trans", "pay", "finan", "ledger", "invoice", "bill", "fee")
        for attr in dir(self._session):
            if attr.startswith("_") or any(attr == c for c in candidates):
                continue
            if not any(p in attr.lower() for p in patterns):
                continue
            fn = getattr(self._session, attr, None)
            if not callable(fn):
                continue
            tried.append(attr)

            # try (start, end)
            try:
                res = await fn(start, end)
                if _looks_like_txn_list(res):
                    return _filter_txns_by_created(res, start, end)
            except TypeError:
                pass
            except Exception as e:
                logger.debug("Heuristic Spond.%s(start,end) failed: %s", attr, e)

            # try no-arg
            try:
                res = await fn()
                if _looks_like_txn_list(res):
                    return _filter_txns_by_created(res, start, end)
            except TypeError:
                pass
            except Exception as e:
                logger.debug("Heuristic Spond.%s() failed: %s", attr, e)

        # 3) REST-style fallback (only if your client implements it)
        try:
            params = {
                "start": int(start.timestamp() * 1000),
                "end": int(end.timestamp() * 1000),
            }
            data = await self.get_json("/transactions", params=params)
            if isinstance(data, dict):
                items = data.get("items") or data.get("data") or []
            else:
                items = data or []
            if _looks_like_txn_list(items):
                return _filter_txns_by_created(items, start, end)
        except AttributeError:
            # Underlying client has no generic HTTP method -> continue to final error
            pass
        except Exception as e:
            logger.debug("REST /transactions fallback failed: %s", e)

        # 4) Nothing worked — surface a helpful error
        raise AttributeError(
            "Could not find a transactions/finance method on the Spond client. "
            f"Tried: {', '.join(tried)}. "
            "If your client exposes a different name, tell me and I’ll wire it in."
        )


def run_async(coro):
    return asyncio.run(coro)


# High-level helpers for tasks
async def fetch_groups_and_members(session):
    return await session.get_groups()


async def fetch_events_between(session, start, end):
    """
    Try several shapes for fetching events.
    """
    for name in (
        "get_events_between",
        "get_events",
        "list_events",
        "get_calendar",
        "fetch_events",
    ):
        fn = getattr(session, name, None)
        if callable(fn):
            try:
                return await fn(start, end)
            except TypeError:
                try:
                    evs = await fn()
                    return _filter_events_by_range(evs, start, end)
                except TypeError:
                    pass

    # fallback
    for name in ("get_events", "list_events"):
        fn = getattr(session, name, None)
        if callable(fn):
            evs = await fn()
            return _filter_events_by_range(evs, start, end)

    attrs = ", ".join(a for a in dir(session) if not a.startswith("_"))
    raise AttributeError(
        f"Spond client has no compatible events method. "
        f"Tried get_events_between/get_events/list_events/get_calendar/fetch_events. "
        f"Session attrs: {attrs}"
    )


def _as_dt(val):
    """Best-effort parse of datetime-like values."""
    from django.utils.dateparse import parse_datetime
    from django.utils import timezone

    if not val:
        return None
    if isinstance(val, (int, float)):  # epoch
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
    out = []
    for ev in (events or []):
        s = _as_dt(
            ev.get("startTime")
            or ev.get("start")
            or (ev.get("time") or {}).get("start")
        )
        e = _as_dt(
            ev.get("endTime") or ev.get("end") or (ev.get("time") or {}).get("end")
        )
        if not s and not e:
            out.append(ev)
            continue
        if (not e and s <= end) or (not s and e >= start) or (
            s and e and not (e < start or s > end)
        ):
            out.append(ev)
    return out


def _in_range(created_val, start, end):
    """Check if created_val is within [start, end]."""
    from django.utils.dateparse import parse_datetime
    from django.utils import timezone

    if not created_val:
        return False
    if isinstance(created_val, (int, float)):
        dt = timezone.make_aware(
            datetime.fromtimestamp(
                created_val / 1000.0 if created_val > 10**12 else created_val
            )
        )
    else:
        dt = parse_datetime(created_val)
        if dt and timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return bool(dt and (start <= dt <= end))
