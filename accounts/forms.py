# accounts/forms.py
from allauth.account.adapter import get_adapter
from allauth.account.forms import LoginForm, ResetPasswordForm, ResetPasswordKeyForm
from allauth.account.forms import SignupForm as AllauthBaseSignup
from django import forms
from django.contrib.auth import get_user_model

User = get_user_model()


class AllauthSignupForm(AllauthBaseSignup):
    first_name = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "First name",
                "autocomplete": "given-name",
            }
        )
    )
    last_name = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Last name",
                "autocomplete": "family-name",
            }
        )
    )
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "name@example.com",
                "autocomplete": "email",
            }
        )
    )
    password1 = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Password",
                "autocomplete": "new-password",
            }
        )
    )
    password2 = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Password (again)",
                "autocomplete": "new-password",
            }
        )
    )
    agree_to_terms = forms.BooleanField(required=True, widget=forms.CheckboxInput())

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip()
        email = get_adapter().clean_email(email)
        email = email.lower()
        get_adapter().validate_unique_email(email)  # raises ValidationError if taken
        return email

    def save(self, request):
        user = super().save(request)  # Allauth will create the user
        user.first_name = self.cleaned_data["first_name"].strip()
        user.last_name = self.cleaned_data["last_name"].strip()
        # Belt & braces: ensure email is lowercased and set as username if your adapter expects that
        if user.email:
            user.email = user.email.strip().lower()
        user.save(update_fields=["first_name", "last_name", "email"])
        return user


class AllauthLoginForm(LoginForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["login"].widget.attrs.update(
            {
                "class": "form-control",
                "placeholder": "Email address",
                "autocomplete": "email",
            }
        )
        self.fields["password"].widget.attrs.update(
            {
                "class": "form-control",
                "placeholder": "Password",
                "autocomplete": "current-password",
            }
        )


class AllauthResetPasswordForm(ResetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].widget.attrs.update(
            {
                "class": "form-control",
                "placeholder": "name@example.com",
                "autocomplete": "email",
            }
        )


class AllauthResetPasswordKeyForm(ResetPasswordKeyForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].widget.attrs.update(
            {
                "class": "form-control",
                "placeholder": "New password",
                "autocomplete": "new-password",
            }
        )
        self.fields["password2"].widget.attrs.update(
            {
                "class": "form-control",
                "placeholder": "Confirm new password",
                "autocomplete": "new-password",
            }
        )


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]
        widgets = {
            "first_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "First name"}
            ),
            "last_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Last name"}
            ),
            "email": forms.EmailInput(
                attrs={"class": "form-control", "placeholder": "name@example.com"}
            ),
        }
