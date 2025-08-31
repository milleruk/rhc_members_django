from allauth.account.adapter import DefaultAccountAdapter

class RHCAccountAdapter(DefaultAccountAdapter):
    def save_user(self, request, user, form, commit=True):
        user = super().save_user(request, user, form, commit=False)
        # force username to be the email
        user.username = user.email
        if commit:
            user.save()
        return user