from rest_framework.permissions import BasePermission

from api.utils.admin_utils import ensure_dashboard_admin


class IsDashboardAdmin(BasePermission):
    """
    Allows access only to authenticated users flagged as dashboard admins.
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return ensure_dashboard_admin(user)
