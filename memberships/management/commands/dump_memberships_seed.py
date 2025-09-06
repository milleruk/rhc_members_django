from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

# Members side (adjust imports if your app or class names differ)
from members.models import Player  # used only for public ids if needed later
from members.models import (
    DynamicQuestion,
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
    Season,
)

# ---- Adjust this if your Player model uses a different public identifier field ----
PLAYER_PUBLIC_FIELD = "public_id"  # e.g. "public_uuid"


def _pt_key(pt) -> str:
    """Portable key for PlayerType: code → slug → name → pk."""
    return (
        getattr(pt, "code", None)
        or getattr(pt, "slug", None)
        or getattr(pt, "name", None)
        or str(pt.pk)
    )


class Command(BaseCommand):
    help = (
        "Export demo seed (Members + Memberships excluding Subscriptions and PlayerAnswers) to JSON. "
        "Includes: seasons, categories, products, plans, add-ons, match-fees, "
        "player types, positions, question categories, dynamic questions, teams, team memberships."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            "-o",
            default="seed_memberships.json",
            help="File path to write (default: seed_memberships.json)",
        )
        parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")

    # ---------------------
    # helpers
    # ---------------------
    def _get_player_public_id(self, player: Player) -> str | None:
        val = getattr(player, PLAYER_PUBLIC_FIELD, None)
        return str(val) if val is not None else None

    @transaction.atomic
    def handle(self, *args, **opts):
        output_path = Path(opts["output"]).resolve()

        # ------------- Memberships -------------
        seasons = [
            {
                "name": s.name,
                "start": s.start.isoformat(),
                "end": s.end.isoformat(),
                "is_active": s.is_active,
            }
            for s in Season.objects.all().order_by("start", "id")
        ]

        pt_by_id = {pt.id: _pt_key(pt) for pt in PlayerType.objects.all()}

        order_field = (
            "code" if "code" in {f.name for f in MembershipCategory._meta.get_fields()} else "id"
        )
        categories = []
        for c in MembershipCategory.objects.all().order_by(order_field):
            applies = [pt_by_id[pt.id] for pt in c.applies_to.all()]
            categories.append(
                {
                    "code": getattr(c, "code", str(c.pk)),
                    "label": c.label,
                    "description": c.description,
                    "is_selectable": c.is_selectable,
                    "applies_to": applies,
                }
            )

        products = []
        for p in MembershipProduct.objects.select_related("season", "category").all():
            plans = [
                {
                    "label": plan.label,
                    "instalment_amount_gbp": str(plan.instalment_amount_gbp),
                    "instalment_count": plan.instalment_count,
                    "frequency": plan.frequency,
                    "includes_match_fees": plan.includes_match_fees,
                    "active": plan.active,
                    "display_order": plan.display_order,
                }
                for plan in p.plans.all().order_by("display_order", "id")
            ]
            products.append(
                {
                    "season": p.season.name,
                    "category": getattr(p.category, "code", str(p.category_id)),
                    "name": p.name,
                    "sku": p.sku,
                    "list_price_gbp": str(p.list_price_gbp),
                    "active": p.active,
                    "notes": p.notes,
                    "requires_plan": p.requires_plan,
                    "pay_per_match": p.pay_per_match,
                    "plans": plans,
                }
            )

        addons = [
            {
                "season": a.season.name,
                "name": a.name,
                "amount_gbp": str(a.amount_gbp),
                "active": a.active,
            }
            for a in AddOnFee.objects.select_related("season")
            .all()
            .order_by("season__start", "name")
        ]

        match_fees = []
        for m in MatchFeeTariff.objects.select_related("season", "category", "product").all():
            match_fees.append(
                {
                    "season": m.season.name,
                    "name": m.name,
                    "amount_gbp": str(m.amount_gbp),
                    "category": getattr(m.category, "code", None) if m.category_id else None,
                    "product": getattr(m.product, "sku", None) if m.product_id else None,
                    "is_default": m.is_default,
                    "active": m.active,
                }
            )

        # ------------- Members (demo; no PlayerAnswer) -------------
        player_types = []
        for pt in PlayerType.objects.all().order_by("id"):
            key = _pt_key(pt)
            player_types.append(
                {
                    "key": key,
                    "label": getattr(pt, "label", getattr(pt, "name", key)),
                    "description": getattr(pt, "description", ""),
                    "active": getattr(pt, "active", True),
                }
            )

        positions = [
            {
                "code": getattr(
                    pos, "code", getattr(pos, "slug", getattr(pos, "name", str(pos.pk)))
                ),
                "label": getattr(pos, "label", getattr(pos, "name", "")),
                "description": getattr(pos, "description", ""),
                "active": getattr(pos, "active", True),
                "name": getattr(pos, "name", None),  # harmless if model lacks this
            }
            for pos in Position.objects.all().order_by("id")
        ]

        question_categories = [
            {
                "code": getattr(qc, "code", getattr(qc, "slug", getattr(qc, "name", str(qc.pk)))),
                "label": getattr(qc, "label", getattr(qc, "name", "")),
                "description": getattr(qc, "description", ""),
                "display_order": getattr(qc, "display_order", 0),
                "active": getattr(qc, "active", True),
                "name": getattr(qc, "name", None),
            }
            for qc in QuestionCategory.objects.all().order_by(
                (
                    "display_order"
                    if "display_order" in {f.name for f in QuestionCategory._meta.get_fields()}
                    else "id"
                ),
                "id",
            )
        ]

        dynamic_questions = []
        dq_order = (
            "sort_order"
            if "sort_order" in {f.name for f in DynamicQuestion._meta.get_fields()}
            else "id"
        )
        for q in DynamicQuestion.objects.select_related("category").all().order_by(dq_order, "id"):
            applies_keys = []
            if hasattr(q, "applies_to"):
                applies_keys = [_pt_key(pt) for pt in q.applies_to.all()]
            choices_val = getattr(q, "choices", [])
            if not isinstance(choices_val, (list, tuple)):
                choices_val = []
            dynamic_questions.append(
                {
                    "code": getattr(q, "code", getattr(q, "slug", getattr(q, "name", f"q{q.pk}"))),
                    "text": getattr(q, "text", getattr(q, "label", "")),
                    "help_text": getattr(q, "help_text", ""),
                    "field_type": getattr(q, "field_type", "text"),
                    "required": getattr(q, "required", False),
                    "active": getattr(q, "active", True),
                    "sort_order": getattr(q, "sort_order", 0),
                    "category": (
                        getattr(q.category, "code", getattr(q.category, "name", None))
                        if q.category_id
                        else None
                    ),
                    "applies_to": applies_keys,
                    "choices": list(choices_val),
                    "name": getattr(q, "name", None),
                    "label": getattr(q, "label", None),
                }
            )

        teams = []
        for t in Team.objects.all().order_by("name", "id"):
            teams.append(
                {
                    "code": getattr(
                        t, "code", getattr(t, "slug", getattr(t, "name", f"team{t.pk}"))
                    ),
                    "name": t.name,
                    "age_group": getattr(t, "age_group", ""),
                    "is_active": getattr(t, "is_active", True),
                }
            )

        team_memberships = []
        for tm in TeamMembership.objects.select_related("team", "player").all().order_by("id"):
            player_pub = self._get_player_public_id(tm.player)
            team_code = (
                getattr(
                    tm.team,
                    "code",
                    getattr(tm.team, "slug", getattr(tm.team, "name", f"team{tm.team_id}")),
                )
                if tm.team_id
                else None
            )
            if not (player_pub and team_code):
                continue
            team_memberships.append(
                {
                    "team": team_code,
                    "player_public_id": player_pub,
                    "role": getattr(tm, "role", ""),
                    "is_captain": getattr(tm, "is_captain", False),
                    "start": getattr(tm, "start", None),
                    "end": getattr(tm, "end", None),
                }
            )

        payload = {
            "_meta": {"version": 3, "notes": "No PlayerAnswer exported."},
            "memberships": {
                "seasons": seasons,
                "categories": categories,
                "products": products,
                "addons": addons,
                "match_fees": match_fees,
            },
            "members": {
                "player_types": player_types,
                "positions": positions,
                "question_categories": question_categories,
                "dynamic_questions": dynamic_questions,
                "teams": teams,
                "team_memberships": team_memberships,
                # no player_answers
            },
        }

        try:
            output_path.write_text(
                json.dumps(
                    payload, indent=2 if opts["pretty"] else None, ensure_ascii=False, default=str
                )
            )
        except Exception as e:
            raise CommandError(f"Failed to write seed: {e}")

        self.stdout.write(self.style.SUCCESS(f"Wrote seed to {output_path}"))
