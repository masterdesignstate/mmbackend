from django.test import TestCase, override_settings

from .models import User, UserRestrictionHistory
from .services.email_verification import build_verification_email_bodies


@override_settings(
    EMAIL_VERIFICATION_REQUIRED=True,
    FRONTEND_URL="http://testserver",
    POSTMARK_SERVER_TOKEN="",
    DEBUG=True,
)
class EmailVerificationTests(TestCase):
    def test_verification_email_uses_branded_template(self):
        user = User.objects.create_user(
            username="template@example.com",
            email="template@example.com",
            password="password123",
        )

        text_body, html_body = build_verification_email_bodies(user, "123456", 15)

        self.assertIn("Welcome to CompatibleFirst", text_body)
        self.assertIn("123456", text_body)
        self.assertIn("/auth/verify-email?", text_body)
        self.assertIn("CompatibleFirst", html_body)
        self.assertIn("Verify your email", html_body)
        self.assertIn("123456", html_body)
        self.assertNotIn("<img", html_body)
        self.assertIn("background:#672DB7", html_body)
        self.assertIn("/auth/verify-email?", html_body)

    def test_signup_requires_email_verification_before_login(self):
        signup = self.client.post(
            "/api/auth/signup/",
            data={
                "email": "new@example.com",
                "password": "password123",
                "alpha_code": "1234",
            },
            content_type="application/json",
        )

        self.assertEqual(signup.status_code, 201)
        signup_data = signup.json()
        self.assertTrue(signup_data["email_verification_required"])
        self.assertFalse(signup_data["email_verified"])
        self.assertEqual(len(signup_data["verification_code"]), 6)

        user = User.objects.get(email="new@example.com")
        self.assertFalse(user.email_verified)
        self.assertTrue(user.is_banned)
        self.assertEqual(user.restriction_reason, "email_verification")
        self.assertTrue(
            UserRestrictionHistory.objects.filter(
                user=user,
                reason="email_verification",
                ended_at__isnull=True,
            ).exists()
        )

        login = self.client.post(
            "/api/auth/login/",
            data={"email": "new@example.com", "password": "password123"},
            content_type="application/json",
        )
        self.assertEqual(login.status_code, 200)
        self.assertTrue(login.json()["email_verification_required"])
        self.assertFalse(login.json()["email_verified"])

        resend = self.client.post(
            "/api/auth/resend-verification-email/",
            data={"email": "new@example.com"},
            content_type="application/json",
        )
        self.assertEqual(resend.status_code, 200)
        verification_code = resend.json()["verification_code"]

        bad_verify = self.client.post(
            "/api/auth/verify-email/",
            data={"email": "new@example.com", "code": "000000"},
            content_type="application/json",
        )
        self.assertEqual(bad_verify.status_code, 400)

        verify = self.client.post(
            "/api/auth/verify-email/",
            data={"email": "new@example.com", "code": verification_code},
            content_type="application/json",
        )
        self.assertEqual(verify.status_code, 200)
        self.assertTrue(verify.json()["email_verified"])

        user.refresh_from_db()
        self.assertTrue(user.email_verified)
        self.assertIsNotNone(user.email_verified_at)
        self.assertFalse(user.is_banned)
        self.assertEqual(user.restriction_reason, "")
        self.assertTrue(
            UserRestrictionHistory.objects.filter(
                user=user,
                reason="email_verification",
                ended_at__isnull=False,
            ).exists()
        )

        login_after_verify = self.client.post(
            "/api/auth/login/",
            data={"email": "new@example.com", "password": "password123"},
            content_type="application/json",
        )
        self.assertEqual(login_after_verify.status_code, 200)
