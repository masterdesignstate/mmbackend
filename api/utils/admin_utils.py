from __future__ import annotations

from typing import Iterable, Set

from django.conf import settings

DEFAULT_ADMIN_EMAIL = "admin@matchmatical.com"
PROFILE_ANSWER_NAMES = {
    "male": "male",
    "female": "female",
    "friend": "friend",
    "hookup": "hookup",
    "date": "date",
    "partner": "partner",
}


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


def profile_answer_key(question) -> str | None:
    """
    Map grouped onboarding sub-questions to profile-list answer columns.

    Gender and relationship are grouped by question_number, so question_number
    alone cannot identify Male/Female/Friend/etc.
    """
    name = (getattr(question, "question_name", "") or "").strip().lower()
    if name in PROFILE_ANSWER_NAMES:
        return PROFILE_ANSWER_NAMES[name]

    text = (getattr(question, "text", "") or "").strip().lower()
    for token, key in PROFILE_ANSWER_NAMES.items():
        if token in text:
            return key

    return None
