from __future__ import annotations
import json
from datetime import timedelta
from typing import Any, Dict

from django.conf import settings
from django.core.management.base import BaseCommand
from django_celery_beat.models import (
    PeriodicTask, CrontabSchedule, IntervalSchedule, SolarSchedule, ClockedSchedule
)
from celery.schedules import crontab as celery_crontab

PREFIX = getattr(settings, "HOCKEYCLUB_BEAT_PREFIX", "settings:")

PERIOD_MAP = {
    "seconds": IntervalSchedule.SECONDS,
    "minutes": IntervalSchedule.MINUTES,
    "hours":   IntervalSchedule.HOURS,
    "days":    IntervalSchedule.DAYS,
}

def _json(val, default):
    try:
        return json.dumps(val if val is not None else default)
    except TypeError:
        # Fallback: stringify anything not JSONable
        return json.dumps(default)

class Command(BaseCommand):
    help = "Sync CELERY_BEAT_SCHEDULE / BEAT_FROM_SETTINGS into django-celery-beat (create/update/delete)."

    def handle(self, *args, **opts):
        # 1) Build desired tasks from BEAT_FROM_SETTINGS (simple format)
        desired: Dict[str, Dict[str, Any]] = {}
        simple = getattr(settings, "BEAT_FROM_SETTINGS", {}) or {}
        for name, spec in simple.items():
            key = f"{PREFIX}{name}"
            desired[key] = self._desired_from_simple(spec)

        # 2) Also mirror CELERY_BEAT_SCHEDULE (native Celery format)
        native = getattr(settings, "CELERY_BEAT_SCHEDULE", {}) or {}
        for name, spec in native.items():
            key = f"{PREFIX}{name}"
            desired[key] = self._desired_from_native(spec)

        # 3) Apply create/update for desired
        seen_names = set()
        for name, want in desired.items():
            pt, created = PeriodicTask.objects.get_or_create(name=name, defaults=want)
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created: {name}"))
            else:
                # update fields and clear other schedule FKs as needed
                updated = False
                for f, val in want.items():
                    if getattr(pt, f) != val:
                        setattr(pt, f, val)
                        updated = True
                # ensure only one schedule FK is set
                if want.get("interval_id") and (pt.crontab_id or pt.solar_id or pt.clocked_id):
                    pt.crontab_id = None; pt.solar_id = None; pt.clocked_id = None; updated = True
                if want.get("crontab_id") and (pt.interval_id or pt.solar_id or pt.clocked_id):
                    pt.interval_id = None; pt.solar_id = None; pt.clocked_id = None; updated = True
                if want.get("solar_id") and (pt.interval_id or pt.crontab_id or pt.clocked_id):
                    pt.interval_id = None; pt.crontab_id = None; pt.clocked_id = None; updated = True
                if want.get("clocked_id") and (pt.interval_id or pt.crontab_id or pt.solar_id):
                    pt.interval_id = None; pt.crontab_id = None; pt.solar_id = None; updated = True

                if updated:
                    pt.save()
                    self.stdout.write(self.style.SUCCESS(f"Updated: {name}"))
                else:
                    self.stdout.write(self.style.NOTICE(f"No change: {name}"))
            seen_names.add(name)

        # 4) Delete stale tasks that were previously managed via this prefix
        stale_qs = PeriodicTask.objects.filter(name__startswith=PREFIX).exclude(name__in=seen_names)
        deleted = stale_qs.count()
        if deleted:
            stale_qs.delete()
            self.stdout.write(self.style.WARNING(f"Deleted {deleted} stale task(s)."))

        # 5) Summary
        self.stdout.write(self.style.SUCCESS("Beat sync complete."))

    # ---- helpers -----------------------------------------------------------

    def _desired_from_simple(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert BEAT_FROM_SETTINGS entry to PeriodicTask fields.
        Expected keys:
          task, type: interval|crontab|solar|clocked, args?, kwargs?, enabled?, queue?
          interval: every + period
          crontab: minute hour day_of_week day_of_month month_of_year (strings)
          solar: event latitude longitude
          clocked: clocked_at (ISO 8601)
        """
        task = spec["task"]
        args = _json(spec.get("args", []), [])
        kwargs = _json(spec.get("kwargs", {}), {})
        enabled = bool(spec.get("enabled", True))
        queue = spec.get("queue") or None
        ptype = (spec.get("type") or "interval").lower()

        base = {"task": task, "args": args, "kwargs": kwargs, "enabled": enabled}
        if queue:
            base["queue"] = queue

        if ptype == "interval":
            every = int(spec.get("every", 60))
            period = PERIOD_MAP[spec.get("period", "seconds").lower()]
            interval, _ = IntervalSchedule.objects.get_or_create(every=every, period=period)
            base["interval"] = interval
            return base

        if ptype == "crontab":
            tz = getattr(settings, "CELERY_TIMEZONE", "UTC")
            cr, _ = CrontabSchedule.objects.get_or_create(
                minute=str(spec.get("minute", "*")),
                hour=str(spec.get("hour", "*")),
                day_of_week=str(spec.get("day_of_week", "*")),
                day_of_month=str(spec.get("day_of_month", "*")),
                month_of_year=str(spec.get("month_of_year", "*")),
                timezone=tz,
            )
            base["crontab"] = cr
            return base

        if ptype == "solar":
            so, _ = SolarSchedule.objects.get_or_create(
                event=spec["event"], latitude=spec["latitude"], longitude=spec["longitude"]
            )
            base["solar"] = so
            return base

        if ptype == "clocked":
            ck, _ = ClockedSchedule.objects.get_or_create(clocked_time=spec["clocked_at"])
            base["clocked"] = ck
            base["one_off"] = True
            return base

        raise ValueError(f"Unknown schedule type in BEAT_FROM_SETTINGS: {ptype}")

    def _desired_from_native(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert CELERY_BEAT_SCHEDULE entry to PeriodicTask fields.
        Supports:
          - schedule=crontab(...)
          - schedule=int/float seconds
          - schedule=timedelta(...)
        Respects 'task', 'args', 'kwargs', and 'options' ('queue', 'expires', etc.; we use 'queue').
        """
        task = spec["task"]
        args = _json(spec.get("args", []), [])
        kwargs = _json(spec.get("kwargs", {}), {})
        options = spec.get("options", {}) or {}
        queue = options.get("queue") or None

        base = {"task": task, "args": args, "kwargs": kwargs, "enabled": True}
        if queue:
            base["queue"] = queue

        schedule = spec.get("schedule")
        if isinstance(schedule, celery_crontab):
            tz = getattr(settings, "CELERY_TIMEZONE", "UTC")
            cr, _ = CrontabSchedule.objects.get_or_create(
                minute=str(schedule._orig_minute),
                hour=str(schedule._orig_hour),
                day_of_week=str(schedule._orig_day_of_week),
                day_of_month=str(schedule._orig_day_of_month),
                month_of_year=str(schedule._orig_month_of_year),
                timezone=tz,
            )
            base["crontab"] = cr
            return base

        # seconds / timedelta -> Interval (seconds)
        seconds = None
        if isinstance(schedule, (int, float)):
            seconds = int(schedule)
        elif isinstance(schedule, timedelta):
            seconds = int(schedule.total_seconds())

        if seconds is not None:
            interval, _ = IntervalSchedule.objects.get_or_create(
                every=max(1, seconds), period=IntervalSchedule.SECONDS
            )
            base["interval"] = interval
            return base

        # Unknown or not supported
        raise ValueError(f"Unsupported schedule type in CELERY_BEAT_SCHEDULE for task={task!r}: {type(schedule).__name__}")
