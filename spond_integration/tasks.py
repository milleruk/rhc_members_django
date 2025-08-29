# spond_integration/tasks.py
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from .models import SpondMember, SpondGroup
from .services import SpondClient, run_async, fetch_groups_and_members
from django.utils.dateparse import parse_datetime
from datetime import datetime, timedelta

from .models import SpondEvent, SpondAttendance, SpondGroup, SpondMember
from .services import SpondClient, run_async, fetch_events_between

from .services.spond_api import SpondClient

def _pick(*vals):
    """Return the first truthy trimmed string from candidates."""
    for v in vals:
        if isinstance(v, str) and v.strip():
            return v.strip()
        if v:
            return v
    return ""

def _parse_dt(val):
    """Parse ISO-like strings to aware datetimes if possible."""
    if not val:
        return None
    dt = parse_datetime(val)
    if dt and timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt

def _norm_status(raw, fallback="unknown"):
    raw = (raw or "").lower()
    if raw in {"going", "yes", "accepted"}:
        return "going"
    if raw in {"maybe", "tentative"}:
        return "maybe"
    if raw in {"no", "declined", "not_going", "notgoing"}:
        return "declined"
    if raw in {"attended", "checked_in", "checkedin"}:
        return "attended"
    return fallback

def _iter_participants(ev):
    """
    Yield tuples (payload, status_hint) from any of:
      * list of dicts
      * list of strings (member ids)
      * dict with buckets {'going': [...], 'declined': [...], 'maybe': [...]}
    """
    for key in ("participants", "attendees", "responses"):
        if key not in ev:
            continue
        block = ev[key]
        # Case A: list
        if isinstance(block, list):
            for item in block:
                yield item, None
            return
        # Case B: dict of buckets
        if isinstance(block, dict):
            for status_key, items in block.items():
                if not isinstance(items, list):
                    continue
                for item in items:
                    yield item, status_key  # status hint from key
            return
    # Nothing found
    return


def _extract_member_id(txn: dict) -> str | None:
    # Adjust to real path in your payload
    # e.g. txn["member"]["id"] or txn.get("spond_member_id")
    m = txn.get("member") or {}
    return m.get("id") or txn.get("spond_member_id")


def _parse_aware(val):
    if not val:
        return None
    dt = parse_datetime(val) if isinstance(val, str) else val
    if not dt:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt

@shared_task
def sync_spond_events(days_back=14, days_forward=60):
    user = getattr(settings, "SPOND_USERNAME", "")
    pwd  = getattr(settings, "SPOND_PASSWORD", "")
    if not user or not pwd:
        return "SPOND creds missing"

    start = datetime.now() - timedelta(days=int(days_back))
    end   = datetime.now() + timedelta(days=int(days_forward))

    async def _fetch():
        async with SpondClient(user, pwd) as session:
            return await fetch_events_between(session, start, end) or []

    raw_events = run_async(_fetch())
    now = timezone.now()

    created_or_updated = 0
    attendance_upserts = 0

    with transaction.atomic():
        group_by_id  = {g.spond_group_id: g for g in SpondGroup.objects.all()}
        member_by_id = {m.spond_member_id: m for m in SpondMember.objects.all()}

        for ev in raw_events:
            ev_id = ev.get("id") or ev.get("uuid")
            if not ev_id:
                continue

            # --- core fields ---
            title       = (ev.get("heading") or "").strip()
            description = ev.get("description") or ""
            start_at    = _parse_aware(ev.get("startTimestamp"))
            end_at      = _parse_aware(ev.get("endTimestamp"))
            meetup_at   = _parse_aware(ev.get("meetupTimestamp"))

            loc = ev.get("location") or {}
            location_name = loc.get("feature") or ""
            location_addr = loc.get("address") or ""
            lat = loc.get("latitude"); lng = loc.get("longitude")

            # Primary group
            group_id = (ev.get("group") or {}).get("id") \
                       or ((ev.get("recipients") or {}).get("group") or {}).get("id")
            group_obj = group_by_id.get(group_id) if group_id else None

            evt, _ = SpondEvent.objects.update_or_create(
                spond_event_id=ev_id,
                defaults={
                    "title": title,
                    "description": description,
                    "start_at": start_at,
                    "end_at": end_at,
                    "meetup_at": meetup_at,
                    "location_name": location_name,
                    "location_addr": location_addr,
                    "location_lat": lat,
                    "location_lng": lng,
                    "group": group_obj,
                    "data": ev,
                    "last_synced_at": now,
                },
            )
            created_or_updated += 1

            # --- Subgroups (STRICT): only what the payload lists for the invite ---
            # Priority: recipients.group.subGroups -> subGroups -> subGroupIds
            explicit_subs = None

            rg = (ev.get("recipients") or {}).get("group") or {}
            if isinstance(rg.get("subGroups"), list) and rg["subGroups"]:
                explicit_subs = rg["subGroups"]
            elif isinstance(ev.get("subGroups"), list) and ev["subGroups"]:
                explicit_subs = ev["subGroups"]
            elif isinstance(ev.get("subGroupIds"), list) and ev["subGroupIds"]:
                explicit_subs = ev["subGroupIds"]

            sub_objs = []
            if explicit_subs:
                for item in explicit_subs:
                    if isinstance(item, str):
                        gid, gname, gdata = item, "", {}
                    elif isinstance(item, dict):
                        gid = item.get("id")
                        gname = (item.get("name") or "").strip()
                        gdata = item
                    else:
                        continue
                    if not gid:
                        continue

                    grp = group_by_id.get(gid)
                    if not grp:
                        # Create if missing; if we know the parent (primary group), link it
                        grp, _ = SpondGroup.objects.get_or_create(
                            spond_group_id=gid,
                            defaults={
                                "name": gname or gid,
                                "parent": group_obj,  # ok if None
                                "data": gdata or {},
                            },
                        )
                        group_by_id[gid] = grp
                    # keep name fresh
                    if gname and grp.name != gname:
                        grp.name = gname
                        grp.save(update_fields=["name"])
                    # ensure correct parent if not set
                    if group_obj and grp.parent_id != getattr(group_obj, "id", None):
                        grp.parent = group_obj
                        grp.save(update_fields=["parent"])

                    sub_objs.append(grp)

            # Apply only the explicit subgroups; if none, clear.
            if sub_objs:
                evt.subgroups.set({g.pk: g for g in sub_objs}.values())
            else:
                evt.subgroups.clear()

            # --- Attendance ---
            resp = ev.get("responses") or {}
            accepted   = set(resp.get("acceptedIds") or [])
            declined   = set(resp.get("declinedIds") or [])
            unanswered = set(resp.get("unansweredIds") or [])
            reg_att    = resp.get("registeredAttendance") or {}

            def _status_for(member_id: str) -> str:
                ra = (reg_att.get(member_id) or "").upper()
                if ra == "ATTENDED":
                    return "attended"
                if ra == "ABSENT":
                    return "declined"  # or "absent" if you add that choice
                if member_id in accepted:
                    return "going"
                if member_id in declined:
                    return "declined"
                if member_id in unanswered:
                    return "unknown"
                return "unknown"

            member_ids = set().union(accepted, declined, unanswered, reg_att.keys())
            for mid in member_ids:
                sm = member_by_id.get(mid)
                if not sm:
                    continue
                status = _status_for(mid)
                SpondAttendance.objects.update_or_create(
                    event=evt, member=sm,
                    defaults={
                        "status": status,
                        "responded_at": None,
                        "checked_in_at": (now if status == "attended" else None),
                        "data": {"source": "responses", "memberId": mid},
                    },
                )
                attendance_upserts += 1

    return f"Events upserted: {created_or_updated}; attendance upserts: {attendance_upserts}"


@shared_task
def sync_spond_members():
    user = getattr(settings, "SPOND_USERNAME", "")
    pwd  = getattr(settings, "SPOND_PASSWORD", "")
    if not user or not pwd:
        return "SPOND creds missing"

    async def _fetch():
        async with SpondClient(user, pwd) as session:
            groups = await fetch_groups_and_members(session)

            # 1) Build a group index (id -> {name,parent,raw})
            group_index = {}
            def add_group_like(g, parent_id=None):
                gid = g.get("id") or g.get("uuid")
                if not gid:
                    return
                group_index[gid] = {
                    "name": g.get("name") or g.get("title") or "",
                    "parent": parent_id,
                    "raw": g,
                }
                # Nested children: Spond sometimes nests as 'subGroups' / 'children'
                for child in (g.get("subGroups") or g.get("children") or []):
                    # child may be id strings or dicts
                    if isinstance(child, dict):
                        add_group_like(child, gid)
                    else:
                        # child is just an id; we’ll still create a placeholder later
                        group_index.setdefault(child, {"name": "", "parent": gid, "raw": {"id": child}})

            for g in groups or []:
                add_group_like(g, parent_id=None)

            # 2) Flatten members
            members = []
            for g in groups or []:
                for m in (g.get("members") or []):
                    prof = m.get("profile") or {}
                    first = (m.get("firstName") or prof.get("firstName") or "").strip()
                    last  = (m.get("lastName")  or prof.get("lastName")  or "").strip()
                    full  = " ".join(p for p in [first, last] if p) \
                            or m.get("name") or m.get("fullName") or prof.get("name") or ""
                    email = (m.get("email") or prof.get("email") or "").lower()
                    subs  = m.get("subGroups") or []   # <-- list of subgroup IDs
                    members.append({
                        "id": m.get("id") or m.get("uuid"),
                        "full": full,
                        "email": email,
                        "raw": m,
                        "sub_ids": subs,
                    })

            return {"group_index": group_index, "members": members}

    pulled = run_async(_fetch())
    group_index = pulled["group_index"]
    members     = pulled["members"]

    now = timezone.now()

    # 3) Upsert groups (parents after children is fine since FK is nullable and we re-link)
    # First pass: create/update all groups without parents
    with transaction.atomic():
        # Ensure every referenced group has at least a placeholder name
        for gid, meta in group_index.items():
            name = meta["name"] or gid  # fallback to id if name unknown
            SpondGroup.objects.update_or_create(
                spond_group_id=gid,
                defaults={"name": name, "data": meta["raw"]},
            )

        # Second pass: set parents where known
        id_to_obj = {g.spond_group_id: g for g in SpondGroup.objects.filter(spond_group_id__in=group_index.keys())}
        updates = []
        for gid, meta in group_index.items():
            parent_id = meta.get("parent")
            if parent_id and parent_id in id_to_obj:
                gobj = id_to_obj[gid]
                pobj = id_to_obj[parent_id]
                if gobj.parent_id != pobj.id:
                    gobj.parent = pobj
                    updates.append(gobj)
        if updates:
            SpondGroup.objects.bulk_update(updates, ["parent"])

    # 4) Upsert members and attach subgroup M2M
    linked = 0
    with transaction.atomic():
        for m in members:
            sid = m["id"]
            if not sid:
                continue
            sm, _ = SpondMember.objects.update_or_create(
                spond_member_id=sid,
                defaults={
                    "full_name": m["full"],
                    "email": m["email"],
                    "data": m["raw"],
                    "last_synced_at": now,
                },
            )

            # Map IDs -> SpondGroup objects
            if m["sub_ids"]:
                sub_objs = list(SpondGroup.objects.filter(spond_group_id__in=m["sub_ids"]))
                # set() replaces existing; if you want additive, use add(*sub_objs)
                sm.groups.set(sub_objs)
            else:
                sm.groups.clear()
            linked += 1

    return f"Synced {linked} members; groups indexed: {len(group_index)}"



@transaction.atomic
def sync_spond_transactions(since: dt.datetime | None = None, until: dt.datetime | None = None, page_size: int = 100) -> dict:
    """
    Pull transactions from Spond and upsert into SpondTransaction.
    Returns a summary dict.
    """
    client = SpondClient()
    created = 0
    updated = 0
    seen = 0

    page = 1
    while True:
        payload = client.list_transactions(since=since, until=until, page=page, page_size=page_size)
        results = payload.get("results") or payload  # support both shapes
        if not results:
            break

        for item in results:
            seen += 1
            spond_txn_id = str(item.get("id") or item.get("transaction_id"))
            if not spond_txn_id:
                continue

            member_id = _extract_member_id(item)
            smember = SpondMember.objects.filter(spond_member_id=member_id).first() if member_id else None

            # resolve player via link (first match)
            player = None
            if smember:
                link = PlayerSpondLink.objects.select_related("player").filter(spond_member=smember).first()
                player = getattr(link, "player", None)

            defaults = {
                "spond_member": smember,
                "player": player,
                "amount_minor": int(item.get("amount_minor") or item.get("amount", 0)),
                "currency": item.get("currency") or "GBP",
                "status": (item.get("status") or "paid").lower(),
                "description": item.get("description") or "",
                "reference": item.get("reference") or "",
                "created_at": _parse_dt(item.get("created_at")) or now(),
                "paid_at": _parse_dt(item.get("paid_at")),
                "raw": item,
            }

            obj, is_created = SpondTransaction.objects.update_or_create(
                spond_txn_id=spond_txn_id,
                defaults=defaults,
            )
            created += 1 if is_created else 0
            updated += 0 if is_created else 1

        # paginated?
        next_url = payload.get("next")
        if next_url:
            page += 1
            continue
        break

    return {"created": created, "updated": updated, "seen": seen}