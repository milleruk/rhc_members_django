# spond_integration/tasks.py
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from .models import SpondMember, SpondGroup
from .services import SpondClient, run_async, fetch_groups_and_members

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
