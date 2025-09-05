# club_calendar/views.py
from datetime import timedelta

from dateutil.rrule import rrulestr
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import (
    HttpResponseBadRequest,
    HttpResponseForbidden,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.dateparse import parse_datetime
from django.utils.timezone import get_current_timezone, is_aware, is_naive, make_aware
from django.views import View
from django.views.generic import CreateView, DeleteView, UpdateView

from .forms import EventForm, EventOccurrenceForm
from .models import Event, EventCancellation, EventOverride, Topic
from .permissions import filter_events_for_user


class CalendarPageView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "club_calendar.view_event"

    def get(self, request):
        topics = Topic.objects.filter(active=True).order_by("name")
        # NOTE: template path matches your current structure (templates/calendar/index.html)
        return render(request, "calendar/index.html", {"topics": topics})


def _normalize_for_event_window(ev_start, win_start, win_end):
    """
    Make the window datetimes match the awareness (naive/aware) of ev_start.
    - If event.start is aware, make window aware in the same tz.
    - If event.start is naive, make window naive.
    """
    tz = ev_start.tzinfo or get_current_timezone()

    def to_match(dt):
        if dt is None:
            return None
        if is_aware(ev_start) and is_naive(dt):
            return make_aware(dt, tz)
        if is_naive(ev_start) and is_aware(dt):
            # drop tzinfo to compare in naive local time
            return dt.replace(tzinfo=None)
        return dt

    return to_match(win_start), to_match(win_end)


# --- API feed ----------------------------------------------------------------
@login_required
@permission_required("club_calendar.view_event", raise_exception=True)
def events_feed(request):
    """
    FullCalendar feed — expands recurring events within [start, end] window.
    Handles tz/naive mismatches, cancellations, and per-occurrence overrides.
    """
    start = request.GET.get("start")
    end = request.GET.get("end")
    if not start or not end:
        return JsonResponse([], safe=False)

    window_start = parse_datetime(start)
    window_end = parse_datetime(end)
    if window_start is None or window_end is None:
        return JsonResponse([], safe=False)

    qs = filter_events_for_user(Event.objects.all(), request.user)
    data = []

    for ev in qs:
        # Align the window with this event's datetime kind (aware/naive)
        win_start, win_end = _normalize_for_event_window(ev.start, window_start, window_end)

        if not ev.is_recurring:
            ev_start = ev.start
            ev_end = ev.end or ev.start
            if (ev_end >= win_start) and (ev_start <= win_end):
                data.append(ev.as_fullcalendar_dict())
            continue

        rule_str = (ev.rrule or "").strip()
        if not rule_str:
            continue

        # If model has recurrence_end but rule lacks UNTIL, append it
        rrule_source = rule_str
        if ev.recurrence_end and "UNTIL=" not in rule_str.upper():
            rrule_source = f"{rrule_source};UNTIL={ev.recurrence_end.isoformat()}"

        try:
            rule = rrulestr(rrule_source, dtstart=ev.start)
        except Exception:
            # malformed rule; skip
            continue

        # Expand with a small pad to catch edges
        try:
            occ_starts = rule.between(
                win_start - timedelta(days=1),
                win_end + timedelta(days=1),
                inc=True,
            )
        except Exception:
            # dateutil may still complain if types clash; skip safely
            continue

        delta = (ev.end - ev.start) if ev.end else None
        cancelled = set(ev.cancellations.values_list("occurrence_start", flat=True))

        for occ_start in occ_starts:
            occ_end = (occ_start + delta) if delta else None
            if occ_end and occ_end < win_start:
                continue
            if occ_start > win_end:
                continue

            # Normalize for cancellation/override lookups
            cmp_start = occ_start
            if is_aware(ev.start) and is_naive(cmp_start):
                cmp_start = make_aware(cmp_start, ev.start.tzinfo)

            # Skip cancelled single occurrence
            if cmp_start in cancelled:
                continue

            # Apply per-occurrence override (time/title/location/description/topic)
            override = ev.overrides.filter(occurrence_start__exact=cmp_start).first()
            if override:
                payload = ev.as_fullcalendar_dict(
                    occurrence_start=override.new_start or occ_start,
                    occurrence_end=override.new_end or occ_end,
                )
                if override.new_title:
                    payload["title"] = override.new_title
                if override.new_location:
                    payload["extendedProps"]["location"] = override.new_location
                if override.new_description:
                    payload["extendedProps"]["description"] = override.new_description[:500]
                topic = override.new_topic or ev.topic
                if topic:
                    payload["extendedProps"]["topic"] = topic.name
                    if getattr(topic, "color", None):
                        payload["color"] = topic.color
                data.append(payload)
                continue

            data.append(ev.as_fullcalendar_dict(occurrence_start=occ_start, occurrence_end=occ_end))

    return JsonResponse(data, safe=False)


# --- CRUD views ---------------------------------------------------------------
class EventCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = "club_calendar.add_event"
    model = Event
    form_class = EventForm
    template_name = "calendar/create.html"
    success_url = reverse_lazy("club_calendar:index")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, "Event created.")
        return super().form_valid(form)


class EventUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = "club_calendar.change_event"
    model = Event
    form_class = EventForm
    template_name = "calendar/update.html"
    success_url = reverse_lazy("club_calendar:index")

    def dispatch(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj not in filter_events_for_user(Event.objects.filter(pk=obj.pk), request.user):
            messages.error(request, "You do not have access to this event.")
            return redirect("club_calendar:index")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, "Event updated.")
        return super().form_valid(form)


class EventDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    permission_required = "club_calendar.delete_event"
    model = Event
    template_name = "calendar/confirm_delete.html"
    success_url = reverse_lazy("club_calendar:index")

    def dispatch(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj not in filter_events_for_user(Event.objects.filter(pk=obj.pk), request.user):
            messages.error(request, "You do not have access to this event.")
            return redirect("club_calendar:index")
        return super().dispatch(request, *args, **kwargs)


# --- single-occurrence actions ------------------------------------------------
@login_required
@permission_required("club_calendar.delete_event", raise_exception=True)
def cancel_occurrence(request, pk):
    """
    Cancel a single occurrence of a recurring series.
    POST body must include 'occurrence_start' (ISO 8601).
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    ev = get_object_or_404(Event, pk=pk)
    if ev not in filter_events_for_user(Event.objects.filter(pk=ev.pk), request.user):
        return HttpResponseForbidden("No access")

    if not ev.is_recurring:
        return HttpResponseBadRequest("Event is not recurring")

    occ_str = request.POST.get("occurrence_start")
    if not occ_str:
        return HttpResponseBadRequest("occurrence_start required")

    occ_dt = parse_datetime(occ_str)
    if occ_dt is None:
        return HttpResponseBadRequest("Invalid occurrence_start")

    if is_aware(ev.start) and is_naive(occ_dt):
        occ_dt = make_aware(occ_dt, ev.start.tzinfo)

    EventCancellation.objects.get_or_create(event=ev, occurrence_start=occ_dt)
    return JsonResponse({"status": "ok"})


@login_required
@permission_required("club_calendar.change_event", raise_exception=True)
def edit_occurrence(request, pk):
    """
    Create/update an override for a single occurrence of a recurring series.
    Requires ?occurrence_start=<ISO> or POST with same.
    """
    ev = get_object_or_404(Event, pk=pk)
    if ev not in filter_events_for_user(Event.objects.filter(pk=ev.pk), request.user):
        return HttpResponseForbidden("No access")

    if not ev.is_recurring:
        messages.error(request, "This event is not recurring.")
        return redirect("club_calendar:index")

    occ_str = request.GET.get("occurrence_start") or request.POST.get("occurrence_start")
    if not occ_str:
        return HttpResponseBadRequest("occurrence_start required")

    occ_dt = parse_datetime(occ_str)
    if occ_dt is None:
        return HttpResponseBadRequest("Invalid occurrence_start")

    if is_aware(ev.start) and is_naive(occ_dt):
        occ_dt = make_aware(occ_dt, ev.start.tzinfo)

    override, _ = EventOverride.objects.get_or_create(event=ev, occurrence_start=occ_dt)

    if request.method == "POST":
        form = EventOccurrenceForm(request.POST, instance=override)
        if form.is_valid():
            form.save()
            messages.success(request, "Occurrence updated.")
            return redirect("club_calendar:index")
    else:
        form = EventOccurrenceForm(instance=override)

    return render(
        request,
        "calendar/edit_occurrence.html",
        {"event": ev, "form": form, "occurrence_start": occ_dt},
    )
