def user_groups(request):
    if not request.user.is_authenticated:
        return {}
    return {
        "user_groups": set(request.user.groups.values_list("name", flat=True))
    }
