from django import forms
from .models import Player, PlayerType, DynamicQuestion, PlayerAnswer, Team, Position, TeamMembership

class PlayerForm(forms.ModelForm):
    class Meta:
        model = Player
        fields = ("first_name", "last_name", "date_of_birth", "gender", "relation", "player_type")
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"})
        }



    def clean(self):
        cleaned = super().clean()
        relation = cleaned.get("relation")
        ptype: PlayerType = cleaned.get("player_type")
        if relation == "child" and ptype and ptype.name.lower() != "junior":
            self.add_error("player_type", "Child players must be 'Junior'.")
        return cleaned

class DynamicAnswerForm(forms.Form):
    """Dynamically generated at runtime from DynamicQuestion for a specific player."""

    def __init__(self, *args, player: Player, **kwargs):
        super().__init__(*args, **kwargs)
        self.player = player
        self._question_field_map = {}
        questions = (
            DynamicQuestion.objects.filter(active=True, applies_to=player.player_type)
            .select_related("category")
            .order_by("category__display_order", "category__name", "display_order", "id")
        )
        existing = {a.question_id: a for a in PlayerAnswer.objects.filter(player=player)}

        for q in questions:
            base_name = f"q_{q.id}"

            if q.question_type == "text":
                field = forms.CharField(
                    label=q.label,
                    help_text=q.help_text,
                    required=q.required,
                )
                if q.id in existing and existing[q.id].text_answer:
                    field.initial = existing[q.id].text_answer
                self.fields[base_name] = field

            elif q.question_type == "boolean":
                field = forms.BooleanField(
                    label=q.label,
                    help_text=q.help_text,
                    required=False,
                )
                if q.id in existing and existing[q.id].boolean_answer is not None:
                    field.initial = existing[q.id].boolean_answer
                self.fields[base_name] = field

                if q.requires_detail_if_yes:
                    dfield = forms.CharField(
                        label=f"Details for: {q.label}",
                        required=False,
                        widget=forms.Textarea(attrs={"rows": 3}),
                    )
                    if q.id in existing and existing[q.id].detail_text:
                        dfield.initial = existing[q.id].detail_text
                    self.fields[f"{base_name}_detail"] = dfield

            elif q.question_type == "choice":
                # Split comma-separated options
                choices = [
                    (opt.strip(), opt.strip())
                    for opt in (q.choices_text or "").split(",")
                    if opt.strip()
                ]
                field = forms.ChoiceField(
                    label=q.label,
                    help_text=q.help_text,
                    required=q.required,
                    choices=choices,
                    widget=forms.Select(attrs={"class": "form-control"}),
                )
                if q.id in existing and existing[q.id].text_answer:
                    field.initial = existing[q.id].text_answer
                self.fields[base_name] = field

            self._question_field_map[q.id] = q

    def clean(self):
        cleaned = super().clean()
        for qid, q in self._question_field_map.items():
            # If a boolean question is required but left unticked
            if q.question_type == "boolean" and q.required:
                if not cleaned.get(f"q_{qid}"):
                    self.add_error(f"q_{qid}", "This field is required.")

            # If boolean requires details
            if q.question_type == "boolean" and q.requires_detail_if_yes:
                v = cleaned.get(f"q_{qid}")
                if v is True and not cleaned.get(f"q_{qid}_detail"):
                    self.add_error(f"q_{qid}_detail", "Please provide details.")
        return cleaned


    def save(self):
        for qid, q in self._question_field_map.items():
            ans, _ = PlayerAnswer.objects.get_or_create(player=self.player, question=q)

            if q.question_type == "text":
                ans.text_answer = self.cleaned_data.get(f"q_{qid}", "")
                ans.boolean_answer = None
                ans.detail_text = ""

            elif q.question_type == "boolean":
                ans.boolean_answer = bool(self.cleaned_data.get(f"q_{qid}") or False)
                if q.requires_detail_if_yes and ans.boolean_answer:
                    ans.detail_text = self.cleaned_data.get(f"q_{qid}_detail", "")
                else:
                    ans.detail_text = ""
                ans.text_answer = ""

            elif q.question_type == "choice":
                ans.text_answer = self.cleaned_data.get(f"q_{qid}", "")
                ans.boolean_answer = None
                ans.detail_text = ""

            ans.save()


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

