from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    # Enforce a unique, required email on the user account
    email = models.EmailField(unique=True)

    REQUIRED_FIELDS = ["email"]

    def __str__(self):
        return self.get_full_name() or self.username
