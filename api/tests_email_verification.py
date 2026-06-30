from urllib.parse import parse_qs, urlparse

from django.test import TestCase, override_settings

from .models import User, UserRestrictionHistory


@override_settings(
    EMAIL_VERIFICATION_REQUIRED=True,
    FRONTEND_URL="http://testserver",
    POSTMARK_SERVER_TOKEN="",
    DEBUG=True,
)
class EmailVerificationTests(TestCase):
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

        token = parse_qs(urlparse(signup_data["verification_url"]).query)["token"][0]
        verify = self.client.post(
            "/api/auth/verify-email/",
            data={"token": token},
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
