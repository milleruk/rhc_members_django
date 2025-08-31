from django import forms
from .models import Player, PlayerType, DynamicQuestion, PlayerAnswer, Team, Position, TeamMembership
from django.db import transaction
from django.contrib import messages
from django.utils import timezone

class PlayerForm(forms.ModelForm):
    class Meta:
        model = Player
        fields = ("first_name", "last_name", "date_of_birth", "gender", "relation", "player_type")
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"})
        }
        error_messages = {
            "date_of_birth": {
                "required": "Please enter a date of birth.",
        }}

    def clean_date_of_birth(self):
        dob = self.cleaned_data.get("date_of_birth")
        if dob is None:
            return dob  # let the field’s required validator/ModelForm handle it
        if dob >= timezone.localdate():
            raise forms.ValidationError("You cannot be born in the Future.")
        return dob

    def clean(self):
        cleaned = super().clean()
        relation = cleaned.get("relation")
        ptype: PlayerType = cleaned.get("player_type")
        if relation == "child" and ptype and ptype.name.lower() != "junior":
            self.add_error("player_type", "Child players must be 'Junior'.")
        return cleaned

class DynamicAnswerForm(forms.Form):
    def __init__(self, *args, player: Player, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.player = player
        self.request = request
        self._question_field_map = {}
        self._existing = {a.question_id: a for a in PlayerAnswer.objects.filter(player=player)}

        questions = (
            DynamicQuestion.objects.filter(active=True, applies_to=player.player_type)
            .select_related("category")
            .order_by("category__display_order", "category__name", "display_order", "id")
        )

        for q in questions:
            base_name = f"q_{q.id}"
            help_txt = (getattr(q, "description", None) or getattr(q, "help_text", "") or "").strip()

            if q.question_type == "text":
                field = forms.CharField(label=q.label, help_text=help_txt, required=q.required)
                if q.id in self._existing and self._existing[q.id].text_answer:
                    field.initial = self._existing[q.id].text_answer
                self.fields[base_name] = field

            elif q.question_type == "boolean":
                field = forms.BooleanField(label=q.label, help_text=help_txt, required=False)
                if q.id in self._existing and self._existing[q.id].boolean_answer is not None:
                    field.initial = self._existing[q.id].boolean_answer
                self.fields[base_name] = field

                if q.requires_detail_if_yes:
                    dfield = forms.CharField(
                        label=f"Details for: {q.label}",
                        required=False,
                        widget=forms.Textarea(attrs={"rows": 3}),
                    )
                    if q.id in self._existing and self._existing[q.id].detail_text:
                        dfield.initial = self._existing[q.id].detail_text
                    self.fields[f"{base_name}_detail"] = dfield

            elif q.question_type == "choice":
                choices = [(opt.strip(), opt.strip())
                           for opt in (getattr(q, "choices_text", "") or "").split(",")
                           if opt.strip()]
                field = forms.ChoiceField(
                    label=q.label, help_text=help_txt, required=q.required,
                    choices=choices, widget=forms.Select(attrs={"class": "form-control"}),
                )
                if q.id in self._existing and self._existing[q.id].text_answer:
                    field.initial = self._existing[q.id].text_answer
                self.fields[base_name] = field

            elif q.question_type == "number":
                widget = forms.TextInput(attrs={"inputmode": "numeric", "pattern": r"[0-9]*"})
                field = forms.CharField(label=q.label, help_text=help_txt, required=q.required, widget=widget)
                existing = self._existing.get(q.id)
                if existing and getattr(existing, "numeric_answer", None):
                    field.initial = existing.numeric_answer
                self.fields[base_name] = field

            # 👇 IMPORTANT: keep this OUTSIDE the if/elif chain
            self._question_field_map[q.id] = q

    def save(self):
        for qid, q in self._question_field_map.items():
            base = f"q_{qid}"
            ans = self._existing.get(qid) or PlayerAnswer(player=self.player, question_id=qid)

            if q.question_type == "text":
                ans.text_answer = self.cleaned_data.get(base) or ""
                ans.boolean_answer = None
                ans.numeric_answer = None

            elif q.question_type == "boolean":
                val = self.cleaned_data.get(base)
                ans.boolean_answer = bool(val) if val is not None else None
                ans.text_answer = ""
                ans.numeric_answer = None
                ans.detail_text = (self.cleaned_data.get(f"{base}_detail", "").strip()
                                   if q.requires_detail_if_yes and val else "")

            elif q.question_type == "choice":
                ans.text_answer = self.cleaned_data.get(base) or ""
                ans.boolean_answer = None
                ans.numeric_answer = None

            elif q.question_type == "number":
                val = (self.cleaned_data.get(base) or "").strip()
                ans.numeric_answer = val or None
                ans.text_answer = ""
                ans.boolean_answer = None

            ans.save()

        if self.request:
            messages.success(self.request, "Your answers have been saved successfully.")

    def save(self):
        for qid, q in self._question_field_map.items():
            base = f"q_{qid}"
            ans = self._existing.get(qid) or PlayerAnswer(player=self.player, question_id=qid)

            if q.question_type == "text":
                ans.text_answer = self.cleaned_data.get(base) or ""
                ans.boolean_answer = None
                ans.numeric_answer = None

            elif q.question_type == "boolean":
                val = self.cleaned_data.get(base)
                ans.boolean_answer = bool(val) if val is not None else None
                ans.text_answer = ""
                ans.numeric_answer = None
                if q.requires_detail_if_yes and val:
                    ans.detail_text = self.cleaned_data.get(f"{base}_detail", "").strip()
                else:
                    ans.detail_text = ""

            elif q.question_type == "choice":
                ans.text_answer = self.cleaned_data.get(base) or ""
                ans.boolean_answer = None
                ans.numeric_answer = None

            elif q.question_type == "number":
                val = self.cleaned_data.get(base)
                ans.numeric_answer = val.strip() if val else None
                ans.text_answer = ""
                ans.boolean_answer = None

            ans.save()

        # 👇 Success message banner
        if self.request:
            messages.success(self.request, "Your answers have been saved successfully.")


class TeamAssignmentForm(forms.ModelForm):
    positions = forms.ModelMultipleChoiceField(
        queryset=Position.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Tick all positions this player can play for the selected team.",
    )

    class Meta:
        model = TeamMembership
        fields = ("team", "positions")

    def __init__(self, *args, player=None, **kwargs):
        super().__init__(*args, **kwargs)
        if player:
            # Exclude teams this player already belongs to
            existing = player.team_memberships.values_list("team_id", flat=True)
            self.fields["team"].queryset = (
                self.fields["team"].queryset.exclude(id__in=existing)
            )
        self._player = player

    def save(self, user=None, commit=True):
        obj = super().save(commit=False)
        if self._player:
            obj.player = self._player
        if user and not obj.assigned_by:
            obj.assigned_by = user
        if commit:
            obj.save()
            self.save_m2m()
        return obj

