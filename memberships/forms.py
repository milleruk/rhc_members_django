# memberships/forms.py
from django import forms


class ConfirmSubscriptionForm(forms.Form):
    accept_terms = forms.BooleanField(
        required=True,
        label="I agree to the club’s Membership Terms & Conditions",
        error_messages={"required": "You must agree to the club’s Membership Terms & Conditions."},
        widget=forms.CheckboxInput(
            attrs={
                "class": "form-check-input",
                "required": "required",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Remove trailing colon in labels for cleaner UI (optional)
        self.label_suffix = ""
