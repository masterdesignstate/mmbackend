import html
import logging
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


logger = logging.getLogger(__name__)
token_generator = PasswordResetTokenGenerator()


def make_password_reset_values(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = token_generator.make_token(user)
    return uid, token


def make_password_reset_url(user):
    uid, token = make_password_reset_values(user)
    query = urlencode({'uid': uid, 'token': token})
    return f"{settings.FRONTEND_URL.rstrip('/')}/auth/reset-password?{query}"


def build_password_reset_email_bodies(user):
    reset_url = make_password_reset_url(user)
    display_name = html.escape(user.first_name or 'there')
    expiry_minutes = max(settings.PASSWORD_RESET_TOKEN_MAX_AGE // 60, 1)
    text_body = (
        f"Hi {user.first_name or 'there'},\n\n"
        "We received a request to reset your CompatibleFirst password.\n\n"
        f"Reset your password: {reset_url}\n\n"
        f"This link expires in {expiry_minutes} minutes. "
        "If you did not request it, you can ignore this email."
    )
    html_body = f"""
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f6f3fb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#1f2937;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f6f3fb;padding:32px 16px;">
      <tr><td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;background:#fff;border:1px solid #e7e2f2;border-radius:20px;overflow:hidden;">
          <tr><td style="padding:30px 32px;text-align:center;">
            <div style="font-size:14px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:#672DB7;">CompatibleFirst</div>
            <h1 style="margin:14px 0 10px;font-size:28px;color:#111827;">Reset your password</h1>
            <p style="margin:0 0 22px;color:#6b7280;line-height:1.6;">Hi {display_name}, use the button below to choose a new password.</p>
            <a href="{reset_url}" style="display:inline-block;background:#672DB7;color:#fff;text-decoration:none;border-radius:12px;padding:14px 22px;font-weight:700;">Reset password</a>
            <p style="margin:22px 0 0;font-size:13px;color:#6b7280;line-height:1.6;">This link expires in {expiry_minutes} minutes. If you did not request it, you can safely ignore this email.</p>
          </td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>
""".strip()
    return text_body, html_body


def send_password_reset_email(user):
    text_body, html_body = build_password_reset_email_bodies(user)
    postmark_token = getattr(settings, 'POSTMARK_SERVER_TOKEN', '')
    uid, token = make_password_reset_values(user)

    if not postmark_token:
        logger.warning('POSTMARK_SERVER_TOKEN is not configured; password reset requested for %s', user.email)
        return {
            'sent': False,
            'delivery': 'development_fallback',
            'uid': uid,
            'token': token,
        }

    response = requests.post(
        'https://api.postmarkapp.com/email',
        headers={
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'X-Postmark-Server-Token': postmark_token,
        },
        json={
            'From': settings.POSTMARK_FROM_EMAIL,
            'To': user.email,
            'Subject': 'Reset your CompatibleFirst password',
            'TextBody': text_body,
            'HtmlBody': html_body,
            'MessageStream': getattr(settings, 'POSTMARK_MESSAGE_STREAM', 'outbound'),
        },
        timeout=10,
    )
    response.raise_for_status()
    response_data = response.json()
    return {
        'sent': True,
        'delivery': 'postmark',
        'message_id': response_data.get('MessageID'),
    }
