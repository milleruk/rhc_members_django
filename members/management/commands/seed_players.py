from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

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


def _filter_defaults(model, defaults: dict) -> dict:
    names = _field_names(model)
    return {k: v for k, v in defaults.items() if k in names}


def _find_position(key: str) -> Position | None:
    names = _field_names(Position)
    q = Q()
    if "code" in names:
        q |= Q(code=key)
    if "slug" in names:
        q |= Q(slug=key)
    if "name" in names:
        q |= Q(name=key)
    if not q.children:
        return None
    return Position.objects.filter(q).first()


def _find_question(key: str) -> DynamicQuestion | None:
    names = _field_names(DynamicQuestion)
    q = Q()
    if "code" in names:
        q |= Q(code=key)
    if "slug" in names:
        q |= Q(slug=key)
    if "name" in names:
        q |= Q(name=key)
    if not q.children:
        return None
    return DynamicQuestion.objects.filter(q).first()


def _find_playertype(key_or_label: str) -> PlayerType | None:
    names = _field_names(PlayerType)
    q = Q()
    for f in ("code", "slug", "name", "label"):
        if f in names:
            q |= Q(**{f: key_or_label})
    if not q.children:
        return None
    return PlayerType.objects.filter(q).first()


class Command(BaseCommand):
    help = "Import Players (and optionally PlayerAnswers) from a JSON seed (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "seed_path",
            nargs="?",
            default="seed_players.json",
            help="Path to players seed JSON (default: seed_players.json)",
        )
        parser.add_argument("--dry-run", action="store_true", help="Validate only (rollback).")
        parser.add_argument(
            "--purge", action="store_true", help="Delete existing PlayerAnswers before import."
        )
        parser.add_argument(
            "--only-players",
            action="store_true",
            help="Import only Players and ignore any answers in the seed.",
        )

    def _load_json(self, path: Path) -> Dict[str, Any]:
        try:
            return json.loads(path.read_text())
        except Exception as e:
            raise CommandError(f"Failed to read/parse JSON at {path}: {e}")

    @transaction.atomic
    def handle(self, *args, **opts):
        path = Path(opts["seed_path"]).resolve()
        payload = self._load_json(path)

        dry_run = opts["dry_run"]
        purge = opts["purge"]
        only_players = opts["only_players"]

        players_data = payload.get("players", [])
        answers_data = [] if only_players else payload.get("answers", [])

        if purge and not only_players:
            PlayerAnswer.objects.all().delete()
            self.stdout.write(self.style.WARNING("Purged existing PlayerAnswers."))

        # Upsert players
        player_fields = _field_names(Player)
        created_players = updated_players = 0

        for row in players_data:
            public_id = row.get("public_id")
            if public_id:
                player = Player.objects.filter(**{PLAYER_PUBLIC_FIELD: public_id}).first()
            else:
                email = row.get("email")
                player = Player.objects.filter(email=email).first() if email else None

            # Resolve optional relations
            pt_key = row.get("player_type")
            pt_obj = _find_playertype(pt_key) if pt_key else None

            defaults = _filter_defaults(
                Player,
                {
                    "first_name": row.get("first_name"),
                    "last_name": row.get("last_name"),
                    "email": row.get("email"),
                    "date_of_birth": row.get("date_of_birth"),
                    "phone": row.get("phone") or row.get("mobile"),
                    "mobile": row.get("mobile") or row.get("phone"),
                    "gender": row.get("gender"),
                    "address": row.get("address"),
                    "postcode": row.get("postcode"),
                    "city": row.get("city"),
                    "is_active": row.get("is_active", True),
                },
            )
            if pt_obj and "player_type" in player_fields:
                defaults["player_type"] = pt_obj

            if player:
                changed = False
                for k, v in defaults.items():
                    if getattr(player, k, None) != v:
                        setattr(player, k, v)
                        changed = True
                if changed:
                    player.save()
                updated_players += 1
            else:
                create_kwargs = defaults.copy()
                if public_id and PLAYER_PUBLIC_FIELD in player_fields:
                    create_kwargs[PLAYER_PUBLIC_FIELD] = public_id
                player = Player.objects.create(**create_kwargs)
                updated_players += 0
                created_players += 1

            # Positions M2M
            if hasattr(player, "positions"):
                keys = row.get("positions", [])
                pos_objs: list[Position] = []
                for k in keys:
                    pos = _find_position(k)
                    if pos:
                        pos_objs.append(pos)
                if pos_objs:
                    player.positions.set(pos_objs)

        # Upsert answers (unless only-players)
        created_answers = updated_answers = 0
        if not only_players and answers_data:
            players_by_pub = {
                str(getattr(p, PLAYER_PUBLIC_FIELD)): p
                for p in Player.objects.exclude(**{PLAYER_PUBLIC_FIELD: None})
            }
            pa_fields = _field_names(PlayerAnswer)
            for a in answers_data:
                pub = a.get("player_public_id")
                if not pub or pub not in players_by_pub:
                    continue
                player = players_by_pub[pub]
                qkey = a.get("question")
                question = _find_question(qkey) if qkey else None

                value = a.get("value", "")
                answered_at = a.get("answered_at")

                defaults = {}
                if "value" in pa_fields:
                    defaults["value"] = value
                if "answered_at" in pa_fields and answered_at:
                    defaults["answered_at"] = answered_at

                if question and "question" in pa_fields:
                    pa, created = PlayerAnswer.objects.update_or_create(
                        player=player,
                        question=question,
                        defaults=defaults,
                    )
                else:
                    if "value" not in pa_fields:
                        continue
                    pa, created = PlayerAnswer.objects.update_or_create(
                        player=player,
                        value=value,
                        defaults=defaults,
                    )
                if created:
                    created_answers += 1
                else:
                    updated_answers += 1

        if dry_run:
            raise CommandError(
                "Dry-run complete. Transaction rolled back.\n"
                f"Players: +{created_players}, updated {updated_players}\n"
                + (
                    f"Answers: +{created_answers}, updated {updated_answers}"
                    if not only_players
                    else "Answers: skipped (--only-players)"
                )
            )

        msg = f"Import complete.\nPlayers: +{created_players}, updated {updated_players}\n" + (
            f"Answers: +{created_answers}, updated {updated_answers}"
            if not only_players
            else "Answers: skipped (--only-players)"
        )
        self.stdout.write(self.style.SUCCESS(msg))
