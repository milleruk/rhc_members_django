from django import forms
from .models import Incident

class IncidentForm(forms.ModelForm):
    class Meta:
        model = Incident
        fields = [
            "incident_datetime", "location", "activity_type", "team",
            "primary_player", "role_involved", "age_under_18",
            "summary", "description", "suspected_concussion", "injury_types",
            "treatment_level", "first_aider_name", "first_aider_contact",
            "attachments",
            "is_sensitive",
            "status_notes",
        ]

        widgets = {
            "incident_datetime": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-control"}),
            "status_notes": forms.Textarea(attrs={"rows": 3}),
            "description": forms.Textarea(attrs={"rows": 4}),
        }

class IncidentActionForm(forms.ModelForm):
    class Meta:
        model = Incident
        fields = [
            "status_notes",
            "safeguarding_notified", "safeguarding_notes",
            "submitted_to_eh", "eh_submission_datetime",
        ]
        widgets = {
            "eh_submission_datetime": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-control"}),
            "status_notes": forms.Textarea(attrs={"rows": 3}),
            "safeguarding_notes": forms.Textarea(attrs={"rows": 3}),
        }
