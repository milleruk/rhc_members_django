from django.conf import settings
from datetime import date
from django.urls import resolve, reverse
from django.utils.text import capfirst

def portal_meta(request):
    return {
        "current_year": date.today().year,
        "portal_version": getattr(settings, "PORTAL_VERSION", None),
        "portal_build": getattr(settings, "PORTAL_BUILD", None),
    }

def portal_breadcrumbs(request):
    """
    Build a simple breadcrumb trail based on the URL resolver.
    """
    breadcrumbs = []
    try:
        match = resolve(request.path_info)
        # Always start with Home
        breadcrumbs.append({"title": "Home", "url": reverse("dashboard")})

        # Split path parts
        parts = request.path.strip("/").split("/")
        url_accum = ""
        for part in parts:
            url_accum += "/" + part
            # Skip numeric IDs, UUIDs, etc.
            if part.isnumeric() or len(part) > 16:
                continue
            breadcrumbs.append({
                "title": capfirst(part.replace("-", " ")),
                "url": url_accum + "/",
            })

        # If there's a named view with kwargs, show "active" without URL
        if match.url_name:
            breadcrumbs[-1]["active"] = True

    except Exception:
        # fallback: only Home
        breadcrumbs = [{"title": "Home", "url": reverse("dashboard"), "active": True}]

    return {"auto_breadcrumbs": breadcrumbs}