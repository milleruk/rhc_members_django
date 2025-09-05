# club_calendar/forms.py
from datetime import datetime

from django import forms
from django.utils import timezone

from .models import Event, EventOverride

WEEKDAYS = [
    ("MO", "Monday"),
    ("TU", "Tuesday"),
    ("WE", "Wednesday"),
    ("TH", "Thursday"),
    ("FR", "Friday"),
    ("SA", "Saturday"),
    ("SU", "Sunday"),
]


def _parse_rrule(rrule_str: str):
    out = {"FREQ": None, "INTERVAL": "1", "BYDAY": [], "UNTIL": None}
    if not rrule_str:
        return out
    for p in [x.strip() for x in rrule_str.split(";") if x.strip()]:
        if "=" not in p:
            continue
        k, v = p.split("=", 1)
        k, v = k.upper(), v.strip()
        if k == "FREQ":
            out["FREQ"] = v
        elif k == "INTERVAL":
            out["INTERVAL"] = v
        elif k == "BYDAY":
            out["BYDAY"] = [d.strip().upper() for d in v.split(",") if d.strip()]
        elif k == "UNTIL":
            try:
                if "T" in v and v[:8].isdigit():
                    out["UNTIL"] = datetime.strptime(v[:15], "%Y%m%dT%H%M%S")
                else:
                    out["UNTIL"] = datetime.fromisoformat(v)
            except Exception:
                out["UNTIL"] = None
    return out


class EventForm(forms.ModelForm):
    recurrence_pattern = forms.ChoiceField(
        required=False,
        label="Recurrence",
        choices=[
            ("", "Does not repeat"),
            ("DAILY", "Daily"),
            ("WEEKLY", "Weekly"),
            ("BIWEEKLY", "Every 2 weeks"),
            ("MONTHLY", "Monthly"),
        ],
        help_text="Choose how often this event repeats.",
    )
    recurrence_days = forms.MultipleChoiceField(
        required=False,
        label="Repeat on",
        choices=WEEKDAYS,
        widget=forms.CheckboxSelectMultiple,
        help_text="Select days for weekly patterns.",
    )

    class Meta:
        model = Event
        fields = [
            "title",
            "description",
            "start",
            "end",
            "all_day",
            "location",
            "topic",
            "visible_to_groups",
            "visible_to_teams",
            "recurrence_pattern",
            "recurrence_days",
            "recurrence_end",
        ]
        widgets = {
            "start": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "end": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "recurrence_end": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        inst = getattr(self, "instance", None)
        if inst and inst.pk and inst.rrule:
            parsed = _parse_rrule(inst.rrule)
            if parsed["FREQ"] == "DAILY":
                self.fields["recurrence_pattern"].initial = "DAILY"
            elif parsed["FREQ"] == "WEEKLY":
                self.fields["recurrence_pattern"].initial = (
                    "BIWEEKLY" if parsed["INTERVAL"] == "2" else "WEEKLY"
                )
                self.fields["recurrence_days"].initial = parsed["BYDAY"]
            elif parsed["FREQ"] == "MONTHLY":
                self.fields["recurrence_pattern"].initial = "MONTHLY"
            if parsed["UNTIL"]:
                until = parsed["UNTIL"]
                if timezone.is_aware(inst.start) and timezone.is_naive(until):
                    until = timezone.make_aware(until, timezone.get_current_timezone())
                self.fields["recurrence_end"].initial = until

    def clean(self):
        cleaned = super().clean()
        pattern = cleaned.get("recurrence_pattern") or ""
        days = cleaned.get("recurrence_days") or []
        start = cleaned.get("start")
        recurrence_end = cleaned.get("recurrence_end")

        def start_weekday_code():
            if not start:
                return "MO"
            # Mon=0..Sun=6 -> BYDAY code
            codes = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
            return codes[start.weekday()]

        rrule = ""
        if pattern == "DAILY":
            rrule = "FREQ=DAILY"
        elif pattern == "WEEKLY":
            by = days or [start_weekday_code()]
            rrule = f"FREQ=WEEKLY;BYDAY={','.join(sorted(set(by)))}"
        elif pattern == "BIWEEKLY":
            by = days or [start_weekday_code()]
            rrule = f"FREQ=WEEKLY;INTERVAL=2;BYDAY={','.join(sorted(set(by)))}"
        elif pattern == "MONTHLY":
            rrule = "FREQ=MONTHLY"

        if rrule and recurrence_end:
            until_str = recurrence_end.strftime("%Y%m%dT%H%M%S")
            rrule += f";UNTIL={until_str}"

        cleaned["is_recurring"] = bool(pattern)
        cleaned["rrule"] = rrule if pattern else ""
        return cleaned

    def save(self, commit=True):
        """
        IMPORTANT: because 'rrule' and 'is_recurring' are not in Meta.fields,
        we must push them onto the instance here so they persist.
        """
        inst = super().save(commit=False)
        inst.is_recurring = self.cleaned_data.get("is_recurring", False)
        inst.rrule = self.cleaned_data.get("rrule", "")
        # recurrence_end IS in fields, so it's already on inst via super().save(commit=False)

        if commit:
            inst.save()
            # save m2m (groups/teams, etc.)
            self.save_m2m()
        return inst


class EventOccurrenceForm(forms.ModelForm):
    class Meta:
        model = EventOverride
        fields = [
            "new_title",
            "new_start",
            "new_end",
            "new_location",
            "new_description",
            "new_topic",
        ]
        widgets = {
            "new_start": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "new_end": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }
