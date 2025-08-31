# accounts/forms.py
from django import forms
from allauth.account.forms import SignupForm as AllauthBaseSignup
from allauth.account.forms import LoginForm, ResetPasswordForm, ResetPasswordKeyForm

class AllauthSignupForm(AllauthBaseSignup):
    first_name = forms.CharField(widget=forms.TextInput(attrs={
        "class": "form-control", "placeholder": "First name", "autocomplete": "given-name",
    }))
    last_name = forms.CharField(widget=forms.TextInput(attrs={
        "class": "form-control", "placeholder": "Last name", "autocomplete": "family-name",
    }))
    email = forms.EmailField(widget=forms.EmailInput(attrs={
        "class": "form-control", "placeholder": "Email address", "autocomplete": "email",
    }))
    # keep these; they'll be reinforced in __init__
    password1 = forms.CharField(widget=forms.PasswordInput(attrs={
        "class": "form-control", "placeholder": "Password", "autocomplete": "new-password",
    }))
    password2 = forms.CharField(widget=forms.PasswordInput(attrs={
        "class": "form-control", "placeholder": "Password (again)", "autocomplete": "new-password",
    }))
    agree_to_terms = forms.BooleanField(required=True, widget=forms.CheckboxInput())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ensure allauth's internal widget setup doesn't drop our classes
        def add_fc(name, placeholder=None, autocomplete=None):
            if name in self.fields:
                w = self.fields[name].widget
                w.attrs["class"] = (w.attrs.get("class", "") + " form-control").strip()
                if placeholder:  w.attrs.setdefault("placeholder", placeholder)
                if autocomplete: w.attrs.setdefault("autocomplete", autocomplete)

        add_fc("first_name", "First name", "given-name")
        add_fc("last_name", "Last name", "family-name")
        add_fc("email", "Email address", "email")
        add_fc("password1", "Password", "new-password")
        add_fc("password2", "Password (again)", "new-password")

    def save(self, request):
        user = super().save(request)
        user.first_name = self.cleaned_data["first_name"].strip()
        user.last_name  = self.cleaned_data["last_name"].strip()
        user.save(update_fields=["first_name", "last_name"])
        return user
    
class AllauthLoginForm(LoginForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["login"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Email address",
            "autocomplete": "email",
        })
        self.fields["password"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Password",
            "autocomplete": "current-password",
        })

class AllauthResetPasswordForm(ResetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Email address",
            "autocomplete": "email",
        })

class AllauthResetPasswordKeyForm(ResetPasswordKeyForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "New password",
            "autocomplete": "new-password",
        })
        self.fields["password2"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Confirm new password",
            "autocomplete": "new-password",
        })