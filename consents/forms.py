from django import forms


class ConsentForm(forms.Form):
    accept_terms = forms.BooleanField(required=True, label="I agree to the Terms of Service")
    accept_club = forms.BooleanField(
        required=True,
        label="I consent to Redditch HC processing my data for club administration",
    )
    accept_marketing = forms.BooleanField(
        required=False, label="Send me occasional product updates"
    )
    accept_eh_data = forms.BooleanField(
        required=True, label="I understand sharing with England Hockey as needed"
    )
    recaptcha_token = forms.CharField(widget=forms.HiddenInput(), required=False)

    # If you want to verify reCAPTCHA server-side, do it here.
    # def clean(self):
    #     cleaned = super().clean()
    #     token = cleaned.get("recaptcha_token")
    #     # verify token...
    #     return cleaned
