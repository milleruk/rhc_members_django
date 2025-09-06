from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction
from django.db.models import Q

# Members side
from members.models import (
    DynamicQuestion,
    Player,
    PlayerType,
    Position,
    QuestionCategory,
    Team,
    TeamMembership,
)

# Memberships side
from memberships.models import (
    AddOnFee,
    MatchFeeTariff,
    MembershipCategory,
    MembershipProduct,
    PaymentPlan,
    Season,
)

# ---- Adjust this if your Player model uses a different public identifier field ----
PLAYER_PUBLIC_FIELD = "public_id"  # e.g. "public_uuid"


def _pt_key(pt) -> str:
    """
    Portable key derivation for PlayerType.
    Prefer `code`, then `slug`, then `name`, else pk.
    """
    return (
        (getattr(pt, "code", None) or None)
        or (getattr(pt, "slug", None) or None)
        or getattr(pt, "name", None)
        or str(pt.pk)
    )


def _field_names(model) -> set[str]:
    """Concrete field names for a model (no reverse relations)."""
    return {f.name for f in model._meta.get_fields() if hasattr(f, "attname")}


def _choose_unique_field(model, candidates: list[str]) -> str:
    """Pick the first candidate that exists on model, else 'name' if present, else error."""
    names = _field_names(model)
    for c in candidates:
        if c in names:
            return c
    if "name" in names:
        return "name"
    raise CommandError(
        f"None of the candidate unique fields {candidates} exist on {model.__name__}. "
        f"Available: {sorted(names)}"
    )


def _filter_defaults(model, defaults: dict) -> dict:
    """Keep only defaults that are real fields on model."""
    names = _field_names(model)
    return {k: v for k, v in defaults.items() if k in names}


class Command(BaseCommand):
    help = (
        "Seed demo data for Members + Memberships from JSON (excludes Subscriptions and PlayerAnswers). "
        "Idempotent upserts keyed by natural identifiers."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "seed_path",
            nargs="?",
            default="seed_memberships.json",
            help="Path to the seed JSON (default: seed_memberships.json)",
        )
        parser.add_argument("--dry-run", action="store_true", help="Validate only (rollback).")
        parser.add_argument(
            "--purge",
            action="store_true",
            help="Purge existing rows for these models before seeding.",
        )

    def _load_json(self, path: Path) -> Dict[str, Any]:
        try:
            return json.loads(path.read_text())
        except Exception as e:
            raise CommandError(f"Failed to read/parse JSON at {path}: {e}")

    def _player_lookup(self) -> dict[str, Player]:
        # build index by public id/uuid
        idx: dict[str, Player] = {}
        for p in Player.objects.all():
            key = getattr(p, PLAYER_PUBLIC_FIELD, None)
            if key:
                idx[str(key)] = p
        return idx

    def _find_existing_playertype(self, key: str | None, label: str | None):
        """Find an existing PlayerType by any of code/slug/name/label matching key or label."""
        key = (key or "").strip()
        label = (label or "").strip()
        fields = _field_names(PlayerType)
        ors = Q()
        had_any = False
        for f in ("code", "slug", "name", "label"):
            if f in fields:
                if key:
                    ors |= Q(**{f: key})
                    had_any = True
                if label and label != key:
                    ors |= Q(**{f: label})
                    had_any = True
        if not had_any:
            return None
        return PlayerType.objects.filter(ors).first()

    @transaction.atomic
    def handle(self, *args, **opts):
        path = Path(opts["seed_path"]).resolve()
        payload = self._load_json(path)

        memberships = payload.get("memberships", {})
        members = payload.get("members", {})

        # -------- optional purge (children first) --------
        if opts["purge"]:
            # Members side
            TeamMembership.objects.all().delete()
            Team.objects.all().delete()
            DynamicQuestion.objects.all().delete()
            QuestionCategory.objects.all().delete()
            Position.objects.all().delete()
            PlayerType.objects.all().delete()

            # Memberships side
            PaymentPlan.objects.all().delete()
            MatchFeeTariff.objects.all().delete()
            MembershipProduct.objects.all().delete()
            AddOnFee.objects.all().delete()
            MembershipCategory.objects.all().delete()
            Season.objects.all().delete()

        # ======================
        # ===== MEMBERSHIPS ====
        # ======================

        # Seasons
        season_by_name: dict[str, Season] = {}
        for s in memberships.get("seasons", []):
            season_obj, created = Season.objects.update_or_create(
                name=s["name"],
                defaults={
                    "start": s["start"],
                    "end": s["end"],
                    "is_active": s.get("is_active", False),
                },
            )
            season_by_name[season_obj.name] = season_obj
            self._log("Season", season_obj.name, created)

        # ---------------------------------------------
        # Player Types FIRST (needed by categories/questions applies_to)
        # Robust lookup to avoid UNIQUE(name) conflicts.
        # ---------------------------------------------
        pt_by_key = {_pt_key(pt): pt for pt in PlayerType.objects.all()}
        for pt_row in members.get("player_types", []):
            key = pt_row.get("key")
            label = pt_row.get("label", key) or key

            # 1) Try our key map first (code/slug/name→key)
            obj = pt_by_key.get(key)

            # 2) If not found, try to find by any of code/slug/name/label == key or label
            if not obj:
                obj = self._find_existing_playertype(key, label)

            if obj:
                updated = False
                if hasattr(obj, "label") and getattr(obj, "label", None) != label:
                    obj.label = label
                    updated = True
                if hasattr(obj, "description") and getattr(obj, "description", "") != pt_row.get(
                    "description", ""
                ):
                    obj.description = pt_row.get("description", "")
                    updated = True
                if hasattr(obj, "active") and getattr(obj, "active", True) != pt_row.get(
                    "active", True
                ):
                    obj.active = pt_row.get("active", True)
                    updated = True
                if updated:
                    obj.save()
                self._log("PlayerType", key or label, False)
            else:
                # Create (filter to actual fields)
                create_kwargs = {
                    "code": key,
                    "slug": key,
                    "name": label,
                    "label": label,
                    "description": pt_row.get("description", ""),
                    "active": pt_row.get("active", True),
                }
                model_fields = _field_names(PlayerType)
                create_kwargs = {k: v for k, v in create_kwargs.items() if k in model_fields}
                try:
                    obj = PlayerType.objects.create(**create_kwargs)
                    self._log("PlayerType", key or label, True)
                except IntegrityError:
                    # Last-resort: fetch by name/label and update
                    fallback = self._find_existing_playertype(
                        None, label
                    ) or self._find_existing_playertype(key, None)
                    if not fallback:
                        raise
                    # Update fallback to reflect seed intent
                    changed = False
                    for fld, val in create_kwargs.items():
                        if getattr(fallback, fld, None) != val:
                            setattr(fallback, fld, val)
                            changed = True
                    if changed:
                        fallback.save()
                    obj = fallback
                    self._log("PlayerType", key or label, False)

            # refresh key map
            pt_by_key[_pt_key(obj)] = obj

        # Membership Categories (now safe: pt_by_key exists)
        category_by_code: dict[str, MembershipCategory] = {}
        for c in memberships.get("categories", []):
            code = c["code"]
            cat_defaults = _filter_defaults(
                MembershipCategory,
                {
                    "label": c.get("label"),
                    "description": c.get("description", ""),
                    "is_selectable": c.get("is_selectable", True),
                },
            )
            cat_obj, created = MembershipCategory.objects.update_or_create(
                code=code,
                defaults=cat_defaults,
            )
            category_by_code[code] = cat_obj
            self._log("MembershipCategory", code, created)

            applies_keys = c.get("applies_to", [])
            missing = [k for k in applies_keys if k not in pt_by_key]
            if missing:
                raise CommandError(
                    f"Unknown PlayerType keys for MembershipCategory {code}: {missing}"
                )
            cat_obj.applies_to.set([pt_by_key[k] for k in applies_keys])

        # Products + Plans
        for p in memberships.get("products", []):
            season = season_by_name.get(p["season"])
            if not season:
                raise CommandError(f"Unknown season '{p['season']}' for product {p.get('sku')}")
            category = category_by_code.get(p["category"])
            if not category:
                raise CommandError(f"Unknown category '{p['category']}' for product {p.get('sku')}")

            prod_defaults = _filter_defaults(
                MembershipProduct,
                {
                    "category": category,
                    "name": p.get("name"),
                    "list_price_gbp": p.get("list_price_gbp", "0"),
                    "active": p.get("active", True),
                    "notes": p.get("notes", ""),
                    "requires_plan": p.get("requires_plan", True),
                    "pay_per_match": p.get("pay_per_match", False),
                },
            )
            prod, created = MembershipProduct.objects.update_or_create(
                season=season,
                sku=p["sku"],
                defaults=prod_defaults,
            )
            self._log("MembershipProduct", f"{prod.sku} ({season.name})", created)

            seen_labels = set()
            for plan in p.get("plans", []):
                pl_defaults = _filter_defaults(
                    PaymentPlan,
                    {
                        "instalment_amount_gbp": plan.get("instalment_amount_gbp"),
                        "instalment_count": plan.get("instalment_count"),
                        "frequency": plan.get("frequency", "monthly"),
                        "includes_match_fees": plan.get("includes_match_fees", True),
                        "active": plan.get("active", True),
                        "display_order": plan.get("display_order", 0),
                    },
                )
                pl, plan_created = PaymentPlan.objects.update_or_create(
                    product=prod,
                    label=plan["label"],
                    defaults=pl_defaults,
                )
                self._log("PaymentPlan", f"{prod.sku} → {pl.label}", plan_created)
                seen_labels.add(pl.label)
            # Optional prune:
            # PaymentPlan.objects.filter(product=prod).exclude(label__in=seen_labels).delete()

        # Add-ons
        for a in memberships.get("addons", []):
            season = season_by_name.get(a["season"])
            if not season:
                raise CommandError(f"Unknown season '{a['season']}' for add-on {a.get('name')}")
            addon_defaults = _filter_defaults(
                AddOnFee,
                {"amount_gbp": a.get("amount_gbp"), "active": a.get("active", True)},
            )
            addon, created = AddOnFee.objects.update_or_create(
                season=season,
                name=a["name"],
                defaults=addon_defaults,
            )
            self._log("AddOnFee", f"{addon.name} ({season.name})", created)

        # Match fees
        for m in memberships.get("match_fees", []):
            season = season_by_name.get(m["season"])
            if not season:
                raise CommandError(f"Unknown season '{m['season']}' for match fee {m.get('name')}")

            category = None
            if m.get("category"):
                category = category_by_code.get(m["category"])
                if not category:
                    raise CommandError(
                        f"Unknown category '{m['category']}' for match fee {m.get('name')}"
                    )

            product = None
            if m.get("product"):
                product = MembershipProduct.objects.filter(season=season, sku=m["product"]).first()
                if not product:
                    raise CommandError(
                        f"Unknown product sku '{m['product']}' in season '{season.name}' for match fee {m.get('name')}"
                    )

            mf_defaults = _filter_defaults(
                MatchFeeTariff,
                {
                    "amount_gbp": m.get("amount_gbp"),
                    "is_default": m.get("is_default", False),
                    "active": m.get("active", True),
                },
            )
            mfee, created = MatchFeeTariff.objects.update_or_create(
                season=season,
                name=m["name"],
                category=category,
                product=product,
                defaults=mf_defaults,
            )
            scope = "season"
            if product:
                scope = f"product:{product.sku}"
            elif category:
                scope = (
                    f"category:{getattr(category, 'code', getattr(category, 'name', category.pk))}"
                )
            self._log("MatchFeeTariff", f"{mfee.name} ({season.name}) [{scope}]", created)

        # ======================
        # ======= MEMBERS ======
        # ======================

        # Positions
        pos_unique = _choose_unique_field(Position, ["code", "slug", "name"])
        for pos in members.get("positions", []):
            key_val = pos.get("code") or pos.get("slug") or pos.get("name") or pos.get("label")
            if not key_val:
                continue
            defaults = _filter_defaults(
                Position,
                {
                    "label": pos.get("label", key_val),
                    "description": pos.get("description", ""),
                    "active": pos.get("active", True),
                    "name": pos.get("name", key_val),
                },
            )
            pobj, created = Position.objects.update_or_create(
                **{pos_unique: key_val},
                defaults=defaults,
            )
            self._log("Position", key_val, created)

        # Question Categories
        qc_unique = _choose_unique_field(QuestionCategory, ["code", "slug", "name"])
        qc_by_code: dict[str, QuestionCategory] = {}
        for qc in members.get("question_categories", []):
            key_val = qc.get("code") or qc.get("slug") or qc.get("name") or qc.get("label")
            if not key_val:
                continue
            defaults = _filter_defaults(
                QuestionCategory,
                {
                    "label": qc.get("label", key_val),
                    "description": qc.get("description", ""),
                    "display_order": qc.get("display_order", 0),
                    "active": qc.get("active", True),
                    "name": qc.get("name", key_val),
                },
            )
            qcobj, created = QuestionCategory.objects.update_or_create(
                **{qc_unique: key_val},
                defaults=defaults,
            )
            qc_by_code[key_val] = qcobj
            self._log("QuestionCategory", key_val, created)

        # Dynamic Questions
        dq_unique = _choose_unique_field(DynamicQuestion, ["code", "slug", "name"])
        dq_by_code: dict[str, DynamicQuestion] = {}
        for q in members.get("dynamic_questions", []):
            qkey = q.get("code") or q.get("slug") or q.get("name") or q.get("label")
            if not qkey:
                continue

            category = None
            qcat_key = q.get("category")
            if qcat_key:
                category = qc_by_code.get(qcat_key)
                if not category:
                    raise CommandError(f"Unknown QuestionCategory '{qcat_key}' for question {qkey}")

            defaults = _filter_defaults(
                DynamicQuestion,
                {
                    "text": q.get("text", ""),
                    "help_text": q.get("help_text", ""),
                    "field_type": q.get("field_type", "text"),
                    "required": q.get("required", False),
                    "active": q.get("active", True),
                    "sort_order": q.get("sort_order", 0),
                    "category": category,
                    "choices": q.get("choices", []),
                    "name": q.get("name", qkey),
                    "label": q.get("label", qkey),
                },
            )
            dqobj, created = DynamicQuestion.objects.update_or_create(
                **{dq_unique: qkey},
                defaults=defaults,
            )
            dq_by_code[qkey] = dqobj
            self._log("DynamicQuestion", qkey, created)

            # Applies_to M2M by PlayerType key if present
            applies = q.get("applies_to", [])
            if hasattr(dqobj, "applies_to"):
                # refresh PlayerType lookup
                pt_by_key = {_pt_key(pt): pt for pt in PlayerType.objects.all()}
                missing = [k for k in applies if k not in pt_by_key]
                if missing:
                    raise CommandError(f"Unknown PlayerType keys for question {qkey}: {missing}")
                dqobj.applies_to.set([pt_by_key[k] for k in applies])

        # Teams (no Season FK expected)
        team_unique = _choose_unique_field(Team, ["code", "slug", "name"])
        team_by_key: dict[str, Team] = {}
        for t in members.get("teams", []):
            key_val = t.get("code") or t.get("slug") or t.get("name")
            if not key_val:
                continue
            defaults = _filter_defaults(
                Team,
                {
                    "name": t.get("name", key_val),
                    "age_group": t.get("age_group", ""),
                    "is_active": t.get("is_active", True),
                },
            )
            tobj, created = Team.objects.update_or_create(
                **{team_unique: key_val},
                defaults=defaults,
            )
            team_by_key[key_val] = tobj
            self._log("Team", key_val, created)

        # Team Memberships (requires existing players & teams)
        players_by_pub = self._player_lookup()
        for tm in members.get("team_memberships", []):
            pub = tm.get("player_public_id")
            team_key = tm.get("team")
            if not pub or not team_key:
                continue
            player = players_by_pub.get(pub)
            team = team_by_key.get(team_key)
            if not player or not team:
                continue
            tm_defaults = _filter_defaults(
                TeamMembership,
                {
                    "role": tm.get("role", ""),
                    "is_captain": tm.get("is_captain", False),
                    "start": tm.get("start", None),
                    "end": tm.get("end", None),
                },
            )
            tmobj, created = TeamMembership.objects.update_or_create(
                team=team,
                player=player,
                defaults=tm_defaults,
            )
            self._log("TeamMembership", f"{team_key} ← {pub}", created)

        # ---- dry-run rollback ----
        if opts["dry_run"]:
            raise CommandError("Dry-run complete. Transaction rolled back.")

        self.stdout.write(self.style.SUCCESS("Seeding complete."))

    def _log(self, model, key, created: bool):
        self.stdout.write(f"{model:<20} {key} -> {'created' if created else 'updated'}")
