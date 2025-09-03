# tasks/forms.py
from django import forms
from django.apps import apps
from django.contrib.auth import get_user_model

from .models import Task

User = get_user_model()

ALLOWED_SUBJECT_APPS = [
    "members",
    "memberships",
    "spond_integration",
    "resources",
    "tasks",
]


class TaskCreateForm(forms.ModelForm):
    assigned_to = forms.ModelChoiceField(
        queryset=User.objects.all(),
        required=False,
        label="Assign to",
        empty_label="",  # avoids "----------" and lets TS placeholder show
        widget=forms.Select(attrs={"style": "width:100%;"}),
    )

    # hide and force True (all manual tasks)
    allow_manual_complete = forms.BooleanField(
        required=False, initial=True, widget=forms.HiddenInput()
    )

    class Meta:
        model = Task
        fields = [
            "title",
            "description",
            "assigned_to",
            "due_at",
            "allow_manual_complete",
        ]
        widgets = {
            "due_at": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "form-control"}
            ),
        }

    def clean_due_at(self):
        return self.cleaned_data.get("due_at") or None


class TaskBulkGenerateForm(forms.Form):
    # Task fields
    title = forms.CharField(max_length=200)
    description = forms.CharField(widget=forms.Textarea, required=False)

    # 🔧 due_at → datetime-local
    due_at = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    # 🔧 complete_on → date only (since it's an event trigger date)
    complete_on = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Optional date this task auto-completes on.",
    )

    allow_manual_complete = forms.BooleanField(required=False, initial=True)

    # 🔧 Assignment behavior
    assign_to_creator = forms.BooleanField(
        required=False,
        initial=True,
        help_text="Assign each task to the player’s creator (recommended).",
    )
    fallback_assignee = forms.ModelChoiceField(
        queryset=User.objects.all(),
        required=False,
        help_text="Used only when a player has no creator.",
    )

    # Selection controls (as you already added)
    player_types = forms.ModelMultipleChoiceField(queryset=None, required=False)
    teams = forms.ModelMultipleChoiceField(queryset=None, required=False)
    season = forms.ModelChoiceField(queryset=None, required=False, empty_label="— Select season —")
    products = forms.ModelMultipleChoiceField(queryset=None, required=False)
    only_without_subscription = forms.BooleanField(required=False, initial=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        PlayerType = apps.get_model("members", "PlayerType")
        Team = apps.get_model("members", "Team")
        MembershipProduct = apps.get_model("memberships", "MembershipProduct")
        Season = apps.get_model("memberships", "Season")

        self.fields["player_types"].queryset = PlayerType.objects.order_by("name")
        self.fields["teams"].queryset = Team.objects.order_by("name")

        if Season is not None:
            season_qs = Season.objects.all().order_by("-id")
        else:
            season_qs = Season.objects.none()
        self.fields["season"].queryset = season_qs

        chosen_season_id = self.data.get("season") or self.initial.get("season") or None
        product_qs = MembershipProduct.objects.select_related("season").order_by("name")
        if chosen_season_id:
            product_qs = product_qs.filter(season_id=chosen_season_id)
        else:
            product_qs = product_qs.none()
        self.fields["products"].queryset = product_qs

    def clean(self):
        cleaned = super().clean()
        if not (cleaned.get("player_types") or cleaned.get("teams") or cleaned.get("products")):
            raise forms.ValidationError(
                "Pick at least one selection: Player Types, Teams, or Products."
            )
        return cleaned
