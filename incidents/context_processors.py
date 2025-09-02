from .models import Incident

def incident_badge(request):
    if not request.user.is_authenticated:
        return {}
    count = Incident.objects.filter(
        assigned_to=request.user,
        status__in=[Incident.Status.ASSIGNED, Incident.Status.ACTION_REQUIRED],
    ).count()
    return {"INCIDENTS_ASSIGNED_OPEN_COUNT": count}
