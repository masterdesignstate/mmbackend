from unittest.mock import patch

from django.test import TestCase, override_settings

from api.models import User
from api.services.password_reset import build_password_reset_email_bodies, send_password_reset_email


@override_settings(
    FRONTEND_URL='http://testserver',
    POSTMARK_SERVER_TOKEN='',
    PASSWORD_RESET_TOKEN_MAX_AGE=3600,
    DEBUG=True,
)
class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='reset@example.com',
            email='reset@example.com',
            password='Old-password-2468',
            first_name='Taylor',
        )

    def request_reset(self, email='reset@example.com'):
        return self.client.post(
            '/api/auth/password-reset/request/',
            data={'email': email},
            content_type='application/json',
        )

    def test_request_does_not_reveal_unknown_accounts(self):
        known = self.request_reset().json()
        unknown = self.request_reset('missing@example.com').json()

        self.assertEqual(known['message'], unknown['message'])
        self.assertIn('uid', known)
        self.assertIn('token', known)
        self.assertNotIn('uid', unknown)

    def test_valid_token_changes_password_and_cannot_be_reused(self):
        reset = self.request_reset().json()
        payload = {
            'uid': reset['uid'],
            'token': reset['token'],
            'new_password': 'New-password-8642',
        }

        response = self.client.post(
            '/api/auth/password-reset/confirm/',
            data=payload,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('New-password-8642'))
        reused = self.client.post(
            '/api/auth/password-reset/confirm/',
            data=payload,
            content_type='application/json',
        )
        self.assertEqual(reused.status_code, 400)

    def test_invalid_token_and_weak_password_are_rejected(self):
        reset = self.request_reset().json()
        invalid = self.client.post(
            '/api/auth/password-reset/confirm/',
            data={'uid': reset['uid'], 'token': 'invalid', 'new_password': 'New-password-8642'},
            content_type='application/json',
        )
        self.assertEqual(invalid.status_code, 400)

        weak = self.client.post(
            '/api/auth/password-reset/confirm/',
            data={'uid': reset['uid'], 'token': reset['token'], 'new_password': 'password'},
            content_type='application/json',
        )
        self.assertEqual(weak.status_code, 400)

    def test_email_contains_branded_reset_link(self):
        text_body, html_body = build_password_reset_email_bodies(self.user)
        self.assertIn('CompatibleFirst', text_body)
        self.assertIn('/auth/reset-password?', text_body)
        self.assertIn('Reset your password', html_body)
        self.assertIn('/auth/reset-password?', html_body)

    @override_settings(
        POSTMARK_SERVER_TOKEN='postmark-test-token',
        POSTMARK_FROM_EMAIL='admin@compatiblefirst.com',
    )
    @patch('api.services.password_reset.requests.post')
    def test_postmark_password_reset_uses_compatiblefirst_sender(self, post):
        post.return_value.json.return_value = {'MessageID': 'message-id'}

        send_password_reset_email(self.user)

        self.assertEqual(post.call_args.kwargs['json']['From'], 'admin@compatiblefirst.com')
