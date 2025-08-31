# spond_integration/tasks.py
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from .models import SpondMember, SpondGroup
from .services import SpondClient, run_async, fetch_groups_and_members
from django.utils.dateparse import parse_datetime
from datetime import datetime, timedelta

from .models import SpondEvent, SpondAttendance, SpondGroup, SpondMember, SpondTransaction
from .services import SpondClient, run_async, fetch_events_between


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

def _int_minor(amount):
    """
    Normalize incoming amount (float/decimal/str/int) to integer minor units (pennies).
    - If payload is already minor units, set settings.SPOND_AMOUNTS_ARE_MINOR=True
    """
    as_minor = getattr(settings, "SPOND_AMOUNTS_ARE_MINOR", False)
    if amount is None:
        return 0
    if as_minor:
        return int(amount)
    # major → minor
    return int(round(float(amount) * 100))

@shared_task
@shared_task
def sync_spond_events(days_back=14, days_forward=120):
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
    now_dt = timezone.now()

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
            lat = loc.get("latitude")
            lng = loc.get("longitude")

            # --- match parsing (NEW) ---
            is_match = bool(ev.get("matchEvent") or (ev.get("matchInfo") is not None))
            mi = ev.get("matchInfo") or {}

            def _ha(x):
                v = (x or "").upper()
                # keep raw if Spond introduces new values
                return v if v in {"HOME", "AWAY", "NEUTRAL"} else v

            def _to_int(x):
                try:
                    return int(x) if x is not None else None
                except (TypeError, ValueError):
                    return None

            match_home_away = _ha(mi.get("type"))
            team_name       = (mi.get("teamName") or "").strip()
            opponent_name   = (mi.get("opponentName") or "").strip()
            team_score      = _to_int(mi.get("teamScore"))
            opponent_score  = _to_int(mi.get("opponentScore"))

            scores_final    = bool(mi.get("scoresFinal"))
            scores_public   = bool(mi.get("scoresPublic"))
            scores_set      = bool(mi.get("scoresSet"))
            scores_set_ever = bool(mi.get("scoresSetEver"))

            kind = "MATCH" if is_match else "EVENT"

            # Primary group
            group_id = (ev.get("group") or {}).get("id") \
                       or ((ev.get("recipients") or {}).get("group") or {}).get("id")
            group_obj = group_by_id.get(group_id) if group_id else None

            # Upsert event (includes NEW match fields)
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
                    "last_synced_at": now_dt,

                    # NEW: match fields
                    "kind": kind,
                    "is_match": is_match,
                    "match_home_away": match_home_away,
                    "team_name": team_name,
                    "opponent_name": opponent_name,
                    "team_score": team_score,
                    "opponent_score": opponent_score,
                    "scores_final": scores_final,
                    "scores_public": scores_public,
                    "scores_set": scores_set,
                    "scores_set_ever": scores_set_ever,
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
                    # optionally create a dedicated "absent" status in model choices
                    return "declined"
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
                        "checked_in_at": (now_dt if status == "attended" else None),
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


@shared_task
def sync_spond_transactions(days_back=120, days_forward=1):
    user = getattr(settings, "SPOND_USERNAME", "")
    pwd  = getattr(settings, "SPOND_PASSWORD", "")
    if not user or not pwd:
        return "SPOND creds missing"

    start = datetime.now() - timedelta(days=int(days_back))
    end   = datetime.now() + timedelta(days=int(days_forward))

    async def _fetch():
        async with SpondClient(user, pwd) as session:
            return await session.fetch_transactions_between(start, end) or []

    raw_txns = run_async(_fetch())
    now = timezone.now()

    upserts = 0
    linked  = 0

    # quick caches
    groups = {g.spond_group_id: g for g in SpondGroup.objects.all()}
    events = {e.spond_event_id: e for e in SpondEvent.objects.all()}
    members = {m.spond_member_id: m for m in SpondMember.objects.all()}

    # helper to resolve player by member
    def _player_for_member(sm: SpondMember):
        if not sm:
            return None
        link = sm.player_links.filter(active=True).select_related("player").first()
        return link.player if link else None

    with transaction.atomic():
        for t in raw_txns:
            txn_id = t.get("id") or t.get("uuid")
            if not txn_id:
                continue

            # fields (adapt names if your payload differs)
            t_type   = (t.get("type") or "").upper()         # PAYMENT / REFUND / CHARGE
            status   = (t.get("status") or "").upper()
            desc     = (t.get("description") or "")[:510]
            currency = (t.get("currency") or "GBP").upper()
            amount   = _int_minor(t.get("amount"))           # normalize to pennies

            created  = _parse_aware(t.get("createdTime") or t.get("created_at"))
            settled  = _parse_aware(t.get("settledTime") or t.get("settled_at"))

            group_id = (t.get("group") or {}).get("id") or t.get("groupId")
            event_id = (t.get("event") or {}).get("id") or t.get("eventId")
            member_id = (t.get("member") or {}).get("id") or t.get("memberId")

            reference = t.get("reference") or t.get("externalReference") or ""

            grp = groups.get(group_id) if group_id else None
            evt = events.get(event_id) if event_id else None
            mem = members.get(member_id) if member_id else None

            # opportunistic creation for missing group/event (optional; comment out if you prefer strict)
            if group_id and not grp:
                grp, _ = SpondGroup.objects.get_or_create(
                    spond_group_id=group_id,
                    defaults={"name": group_id, "data": {}},
                )
                groups[group_id] = grp
            if event_id and not evt:
                # we avoid creating placeholder events; leave null
                pass

            player = _player_for_member(mem)

            obj, _created = SpondTransaction.objects.update_or_create(
                spond_txn_id=txn_id,
                defaults={
                    "type": t_type,
                    "status": status,
                    "description": desc,
                    "amount_minor": amount,
                    "currency": currency,
                    "created_at": created,
                    "settled_at": settled,
                    "group": grp,
                    "event": evt,
                    "member": mem,
                    "player": player,
                    "reference": reference[:120],
                    "metadata": t,
                    "last_synced_at": now,
                },
            )
            upserts += 1
            if player:
                linked += 1

    return f"Transactions upserted: {upserts}; linked to players: {linked}"