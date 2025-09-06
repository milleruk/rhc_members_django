from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import QuerySet

from members.models import (
    DynamicQuestion,
    Player,
    PlayerAnswer,
    PlayerType,
    Position,
)

# Public identifier used to match players across envs
PLAYER_PUBLIC_FIELD = "public_id"  # change to your field if different (e.g. "public_uuid")


def _field_names(model) -> set[str]:
    return {f.name for f in model._meta.get_fields() if hasattr(f, "attname")}


def _serialize_simple_fields(instance, allowed: set[str]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    names = _field_names(instance.__class__)
    for name in allowed & names:
        val = getattr(instance, name, None)
        if isinstance(val, (str, int, float, bool)) or val is None:
            payload[name] = val
        else:
            payload[name] = str(val)
    return payload


def _pt_key(pt) -> str:
    return (
        getattr(pt, "code", None)
        or getattr(pt, "slug", None)
        or getattr(pt, "name", None)
        or str(pt.pk)
    )


class Command(BaseCommand):
    help = "Export Players (and optionally PlayerAnswers) to JSON for testing/dev."

    def add_arguments(self, parser):
        parser.add_argument("--output", "-o", default="seed_players.json", help="Output path")
        parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
        parser.add_argument("--limit", type=int, default=None, help="Limit number of players")
        parser.add_argument(
            "--only-players",
            action="store_true",
            help="Export only Players (omit PlayerAnswers).",
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        path = Path(opts["output"]).resolve()
        pretty = opts["pretty"]
        limit = opts["limit"]
        only_players = opts["only_players"]

        # player type map (portable keys)
        # (Not strictly needed, but we keep consistency if you include PlayerType field)
        _ = {_pt_key(pt): pt.id for pt in PlayerType.objects.all()}

        pos_fields = _field_names(Position)
        pos_has_code = "code" in pos_fields
        pos_has_slug = "slug" in pos_fields
        pos_has_name = "name" in pos_fields

        def pos_key(p: Position) -> str:
            if pos_has_code and getattr(p, "code", None):
                return p.code
            if pos_has_slug and getattr(p, "slug", None):
                return p.slug
            if pos_has_name and getattr(p, "name", None):
                return p.name
            return f"pos{p.pk}"

        qs: QuerySet[Player] = Player.objects.all().order_by("id")
        if limit:
            qs = qs[:limit]

        players_payload: list[dict[str, Any]] = []
        answers_payload: list[dict[str, Any]] = []

        # Choose sensible, non-sensitive fields to round-trip
        player_simple_fields = {
            "first_name",
            "last_name",
            "email",
            "date_of_birth",
            "phone",
            "mobile",
            "gender",
            "address",
            "postcode",
            "city",
            "is_active",
        }

        dq_fields = _field_names(DynamicQuestion)
        dq_has_code = "code" in dq_fields
        dq_has_slug = "slug" in dq_fields
        dq_has_name = "name" in dq_fields

        def dq_key(q: DynamicQuestion) -> str:
            if dq_has_code and getattr(q, "code", None):
                return q.code
            if dq_has_slug and getattr(q, "slug", None):
                return q.slug
            if dq_has_name and getattr(q, "name", None):
                return q.name
            return f"q{q.pk}"

        for p in qs:
            public_id = getattr(p, PLAYER_PUBLIC_FIELD, None)
            if not public_id:
                continue  # skip unkeyed players

            pdata = {"public_id": str(public_id)}
            pdata.update(_serialize_simple_fields(p, player_simple_fields))

            # player type (optional)
            if hasattr(p, "player_type") and getattr(p, "player_type_id", None):
                pdata["player_type"] = _pt_key(p.player_type)

            # positions (optional M2M)
            if hasattr(p, "positions"):
                pdata["positions"] = [pos_key(pos) for pos in p.positions.all()]

            players_payload.append(pdata)

            if only_players:
                continue

            # answers
            a_qs = PlayerAnswer.objects.filter(player=p).select_related("question").order_by("id")
            for a in a_qs:
                qkey = dq_key(a.question) if getattr(a, "question_id", None) else None
                value = getattr(a, "value", None)
                answered_at = getattr(a, "answered_at", None)
                if not isinstance(value, (str, int, float, bool, list, dict)) and value is not None:
                    value = str(value)
                answers_payload.append(
                    {
                        "player_public_id": str(public_id),
                        "question": qkey,
                        "value": value,
                        "answered_at": (
                            answered_at.isoformat()
                            if hasattr(answered_at, "isoformat")
                            else answered_at
                        ),
                    }
                )

        meta_note = "Players only" if only_players else "Players + PlayerAnswers"
        payload = {"_meta": {"version": 2, "note": meta_note}, "players": players_payload}
        if not only_players:
            payload["answers"] = answers_payload

        try:
            json_text = json.dumps(
                payload, indent=2 if pretty else None, ensure_ascii=False, default=str
            )
            path.write_text(json_text)
        except Exception as e:
            raise CommandError(f"Failed to write {path}: {e}")

        msg = f"Wrote {len(players_payload)} players"
        if not only_players:
            msg += f" and {len(answers_payload)} answers"
        self.stdout.write(self.style.SUCCESS(f"{msg} → {path}"))
