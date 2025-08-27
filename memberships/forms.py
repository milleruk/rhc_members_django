from django import forms

class ConfirmSubscriptionForm(forms.Form):
    accept_terms = forms.BooleanField(
        label="I agree to the club’s Membership Terms & Conditions",
        required=True
    )
    notes = forms.CharField(
        label="Optional note to membership secretary",
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
    )
