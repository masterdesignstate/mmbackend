import logging
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core import signing
from django.utils import timezone

from api.models import UserRestrictionHistory


logger = logging.getLogger(__name__)

EMAIL_VERIFICATION_SALT = "api.email-verification"
EMAIL_VERIFICATION_RESTRICTION_REASON = "email_verification"
EMAIL_VERIFICATION_CODE_LENGTH = 6
EMAIL_VERIFICATION_MAX_CODE_ATTEMPTS = 5


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


def make_email_verification_code():
    return f"{secrets.randbelow(10 ** EMAIL_VERIFICATION_CODE_LENGTH):0{EMAIL_VERIFICATION_CODE_LENGTH}d}"


def build_verification_email_bodies(user, verification_code, expiry_minutes):
    verification_url = make_email_verification_url(user)
    text_body = (
        "Welcome to Matchmatical.\n\n"
        f"Your verification code is: {verification_code}\n\n"
        f"Or verify your email here: {verification_url}\n\n"
        f"This code expires in {expiry_minutes} minutes.\n\n"
        "If you did not create this account, you can ignore this email."
    )
    html_body = f"""
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f6f3fb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#1f2937;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f6f3fb;margin:0;padding:32px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;background:#ffffff;border:1px solid #e7e2f2;border-radius:20px;overflow:hidden;box-shadow:0 16px 40px rgba(103,45,183,0.12);">
            <tr>
              <td style="padding:28px 32px 18px 32px;text-align:center;background:#ffffff;">
                <div style="font-size:14px;font-weight:800;letter-spacing:0.12em;text-transform:uppercase;color:#672DB7;">Matchmatical</div>
                <h1 style="margin:12px 0 8px 0;font-size:28px;line-height:1.2;font-weight:800;color:#111827;">Verify your email</h1>
                <p style="margin:0 auto;max-width:420px;font-size:15px;line-height:1.6;color:#6b7280;">Enter this code in the app to finish setting up your account.</p>
              </td>
            </tr>
            <tr>
              <td style="padding:8px 32px 6px 32px;text-align:center;">
                <div style="display:inline-block;padding:18px 24px;border-radius:16px;background:#f4effc;border:1px solid #ded2f1;color:#2f1558;font-size:34px;line-height:1;font-weight:800;letter-spacing:0.22em;">{verification_code}</div>
              </td>
            </tr>
            <tr>
              <td style="padding:18px 32px 8px 32px;text-align:center;">
                <a href="{verification_url}" style="display:inline-block;background:#672DB7;color:#ffffff;text-decoration:none;border-radius:12px;padding:14px 22px;font-size:15px;font-weight:700;">Verify email</a>
              </td>
            </tr>
            <tr>
              <td style="padding:12px 32px 30px 32px;text-align:center;">
                <p style="margin:0;font-size:13px;line-height:1.6;color:#6b7280;">This code expires in {expiry_minutes} minutes.</p>
                <p style="margin:10px 0 0 0;font-size:12px;line-height:1.6;color:#9ca3af;">If you did not create this account, you can safely ignore this email.</p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
""".strip()
    return text_body, html_body


def set_email_verification_code(user):
    code = make_email_verification_code()
    now = timezone.now()
    user.email_verification_code_hash = make_password(code)
    user.email_verification_code_sent_at = now
    user.email_verification_code_expires_at = now + timedelta(
        seconds=settings.EMAIL_VERIFICATION_CODE_MAX_AGE_SECONDS
    )
    user.email_verification_code_attempts = 0
    user.save(update_fields=[
        "email_verification_code_hash",
        "email_verification_code_sent_at",
        "email_verification_code_expires_at",
        "email_verification_code_attempts",
    ])
    return code


def verify_email_code(user, code):
    normalized_code = "".join(ch for ch in str(code or "") if ch.isdigit())
    if len(normalized_code) != EMAIL_VERIFICATION_CODE_LENGTH:
        return False, "Enter the 6-digit verification code."

    if user.email_verified:
        return False, "Email is already verified."

    if not user.email_verification_code_hash:
        return False, "Verification code has expired. Request a new code."

    if (
        user.email_verification_code_expires_at
        and timezone.now() > user.email_verification_code_expires_at
    ):
        return False, "Verification code has expired. Request a new code."

    if user.email_verification_code_attempts >= EMAIL_VERIFICATION_MAX_CODE_ATTEMPTS:
        return False, "Too many attempts. Request a new code."

    if not check_password(normalized_code, user.email_verification_code_hash):
        user.email_verification_code_attempts += 1
        user.save(update_fields=["email_verification_code_attempts"])
        return False, "Invalid verification code."

    return True, ""


def send_verification_email(user):
    verification_code = set_email_verification_code(user)
    from_email = settings.DEFAULT_FROM_EMAIL
    postmark_token = getattr(settings, "POSTMARK_SERVER_TOKEN", "")
    expiry_minutes = max(settings.EMAIL_VERIFICATION_CODE_MAX_AGE_SECONDS // 60, 1)
    text_body, html_body = build_verification_email_bodies(user, verification_code, expiry_minutes)

    if not postmark_token:
        logger.warning("POSTMARK_SERVER_TOKEN is not configured; verification code for %s: %s", user.email, verification_code)
        print(f"EMAIL VERIFICATION CODE for {user.email}: {verification_code}")
        return {
            "sent": False,
            "delivery": "development_fallback",
            "verification_code": verification_code,
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
            "Subject": "Verify your Matchmatical email",
            "TextBody": text_body,
            "HtmlBody": html_body,
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
        "message_id": message_id,
        "submitted_at": submitted_at,
    }


def mark_email_verified(user):
    update_fields = [
        "email_verification_code_hash",
        "email_verification_code_sent_at",
        "email_verification_code_expires_at",
        "email_verification_code_attempts",
    ]
    user.email_verification_code_hash = ""
    user.email_verification_code_sent_at = None
    user.email_verification_code_expires_at = None
    user.email_verification_code_attempts = 0
    if not user.email_verified:
        user.email_verified = True
        user.email_verified_at = timezone.now()
        update_fields.extend(["email_verified", "email_verified_at"])
    user.save(update_fields=update_fields)
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
