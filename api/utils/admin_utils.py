from __future__ import annotations

from typing import Iterable, Set

from django.conf import settings

DEFAULT_ADMIN_EMAIL = "admin@matchmatical.com"


def _configured_admin_emails() -> Set[str]:
    emails: Iterable[str] = getattr(settings, "ADMIN_EMAILS", []) or []
    normalized = {
        email.strip().lower()
        for email in emails
        if isinstance(email, str) and email.strip()
    }
    normalized.add(DEFAULT_ADMIN_EMAIL)
    return {email for email in normalized if email}


def ensure_dashboard_admin(user) -> bool:
    """
    Determine whether the user should have dashboard admin access.
    If the user matches a configured admin email, their admin flags
    are persisted for future checks.
    """
    if not user:
        return False

    if getattr(user, "is_admin", False):
        return True

    normalized_email = (user.email or "").strip().lower()
    if normalized_email in _configured_admin_emails():
        fields_to_update = []
        if not getattr(user, "is_admin", False):
            user.is_admin = True
            fields_to_update.append("is_admin")
        if not getattr(user, "is_staff", False):
            user.is_staff = True
            fields_to_update.append("is_staff")
        if not getattr(user, "is_superuser", False):
            user.is_superuser = True
            fields_to_update.append("is_superuser")
        if fields_to_update:
            user.save(update_fields=fields_to_update)
        return True

    return False
