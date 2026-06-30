import logging
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.core import signing
from django.utils import timezone

from api.models import UserRestrictionHistory


logger = logging.getLogger(__name__)

EMAIL_VERIFICATION_SALT = "api.email-verification"
EMAIL_VERIFICATION_RESTRICTION_REASON = "email_verification"


def make_email_verification_token(user):
    return signing.dumps(
        {"user_id": str(user.id), "email": user.email},
        salt=EMAIL_VERIFICATION_SALT,
    )


def read_email_verification_token(token):
    return signing.loads(
        token,
        salt=EMAIL_VERIFICATION_SALT,
        max_age=settings.EMAIL_VERIFICATION_TOKEN_MAX_AGE_SECONDS,
    )


def make_email_verification_url(user):
    query = urlencode({"token": make_email_verification_token(user)})
    return f"{settings.FRONTEND_URL.rstrip('/')}/auth/verify-email?{query}"


def send_verification_email(user):
    verification_url = make_email_verification_url(user)
    from_email = settings.DEFAULT_FROM_EMAIL
    postmark_token = getattr(settings, "POSTMARK_SERVER_TOKEN", "")

    if not postmark_token:
        logger.warning("POSTMARK_SERVER_TOKEN is not configured; verification link for %s: %s", user.email, verification_url)
        print(f"EMAIL VERIFICATION LINK for {user.email}: {verification_url}")
        return {
            "sent": False,
            "delivery": "development_fallback",
            "verification_url": verification_url,
        }

    response = requests.post(
        "https://api.postmarkapp.com/email",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Postmark-Server-Token": postmark_token,
        },
        json={
            "From": from_email,
            "To": user.email,
            "Subject": "Verify your email",
            "TextBody": (
                "Welcome to Matchmatical.\n\n"
                f"Verify your email by opening this link:\n{verification_url}\n\n"
                "If you did not create this account, you can ignore this email."
            ),
            "HtmlBody": (
                "<p>Welcome to Matchmatical.</p>"
                f'<p><a href="{verification_url}">Verify your email</a></p>'
                "<p>If you did not create this account, you can ignore this email.</p>"
            ),
            "MessageStream": getattr(settings, "POSTMARK_MESSAGE_STREAM", "outbound"),
        },
        timeout=10,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError:
        logger.error(
            "Postmark verification email rejected for %s: status=%s body=%s",
            user.email,
            response.status_code,
            response.text[:1000],
        )
        print(f"⚠️ Postmark rejected verification email for {user.email}: {response.status_code} {response.text[:500]}")
        raise

    response_data = response.json()
    message_id = response_data.get("MessageID")
    submitted_at = response_data.get("SubmittedAt")
    logger.info("Postmark verification email accepted for %s: message_id=%s submitted_at=%s", user.email, message_id, submitted_at)
    print(f"📧 Postmark accepted verification email for {user.email}: MessageID={message_id}")
    return {
        "sent": True,
        "delivery": "postmark",
        "verification_url": verification_url,
        "message_id": message_id,
        "submitted_at": submitted_at,
    }


def mark_email_verified(user):
    if not user.email_verified:
        user.email_verified = True
        user.email_verified_at = timezone.now()
        user.save(update_fields=["email_verified", "email_verified_at"])
    clear_email_verification_restriction(user)
    return user


def apply_email_verification_restriction(user):
    if user.email_verified:
        return

    # Do not replace a real moderation restriction.
    if user.is_banned and user.restriction_reason != EMAIL_VERIFICATION_RESTRICTION_REASON:
        return

    now = timezone.now()
    user.is_banned = True
    user.restriction_type = "temporary"
    user.restriction_duration = None
    user.restriction_reason = EMAIL_VERIFICATION_RESTRICTION_REASON
    user.restriction_reason_detail = "Email address has not been verified."
    user.restriction_date = now
    user.save(update_fields=[
        "is_banned",
        "restriction_type",
        "restriction_duration",
        "restriction_reason",
        "restriction_reason_detail",
        "restriction_date",
    ])

    UserRestrictionHistory.objects.get_or_create(
        user=user,
        ended_at__isnull=True,
        defaults={
            "restriction_type": "temporary",
            "duration_days": None,
            "reason": EMAIL_VERIFICATION_RESTRICTION_REASON,
            "reason_detail": "Email address has not been verified.",
            "restricted_at": now,
            "expires_at": None,
        },
    )


def clear_email_verification_restriction(user):
    if user.restriction_reason != EMAIL_VERIFICATION_RESTRICTION_REASON:
        return

    now = timezone.now()
    UserRestrictionHistory.objects.filter(
        user=user,
        ended_at__isnull=True,
        reason=EMAIL_VERIFICATION_RESTRICTION_REASON,
    ).update(ended_at=now, end_reason="removed", moderator_notes="Email verified")

    user.is_banned = False
    user.restriction_type = None
    user.restriction_duration = None
    user.restriction_reason = ""
    user.restriction_reason_detail = ""
    user.restriction_date = None
    user.save(update_fields=[
        "is_banned",
        "restriction_type",
        "restriction_duration",
        "restriction_reason",
        "restriction_reason_detail",
        "restriction_date",
    ])
