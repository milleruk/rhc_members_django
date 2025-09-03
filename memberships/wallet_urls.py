# memberships/wallet_urls.py
from django.urls import path

from .views_wallet import apple_wallet_pkpass, apple_wallet_preview

app_name = "wallet"
urlpatterns = [
    path("apple/<uuid:public_id>/preview/", apple_wallet_preview, name="apple_preview"),
    path("apple/<uuid:public_id>/pkpass/", apple_wallet_pkpass, name="apple"),
    path("apple/<uuid:public_id>/", apple_wallet_pkpass, name="wallet_apple"),
]
