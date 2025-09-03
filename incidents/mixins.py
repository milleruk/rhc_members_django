from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin


class AppAccessRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Require 'incidents.access_app' to enter any incidents pages."""

    def test_func(self):
        return self.request.user.has_perm("incidents.access_app")


class CanSeeListMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.has_perm("incidents.view_list")
