from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from api.models import Question, User, UserAnswer, UserRestrictionHistory


class RestrictionDashboardTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='restricted@example.com',
            email='restricted@example.com',
            password='testpass123',
            first_name='Restricted',
            last_name='User',
        )

    def test_restricted_endpoint_expires_temporary_restrictions(self):
        restricted_at = timezone.now() - timedelta(days=3)
        self.user.is_banned = True
        self.user.restriction_type = 'temporary'
        self.user.restriction_duration = 1
        self.user.restriction_reason = 'admin_restriction'
        self.user.restriction_date = restricted_at
        self.user.save()

        response = self.client.get('/api/users/restricted/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_banned)
        self.assertIsNone(self.user.restriction_type)
        self.assertEqual(self.user.restriction_reason, '')

        history = UserRestrictionHistory.objects.get(user=self.user)
        self.assertEqual(history.end_reason, 'expired')
        self.assertEqual(history.ended_at, restricted_at + timedelta(days=1))

    def test_restrict_action_creates_history_visible_on_detail(self):
        response = self.client.post(
            f'/api/users/{self.user.id}/restrict/',
            {
                'restriction_type': 'temporary',
                'duration': 14,
                'reason': 'harassment',
                'reason_detail': 'Repeated unwanted messages',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)

        detail = self.client.get(f'/api/users/{self.user.id}/')
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(detail.data['is_banned'])
        self.assertEqual(detail.data['restriction_type'], 'temporary')
        self.assertEqual(len(detail.data['restriction_history']), 1)

        history = detail.data['restriction_history'][0]
        self.assertEqual(history['duration_days'], 14)
        self.assertEqual(history['reason'], 'harassment')
        self.assertEqual(history['reason_detail'], 'Repeated unwanted messages')
        self.assertEqual(history['end_reason'], 'active')

    def test_admin_profiles_includes_real_gender_answers(self):
        question_friend = Question.objects.create(
            question_number=1,
            question_name='Friend',
            group_name='Relationship',
            text='How strongly are you looking for friendship?',
            is_approved=True,
        )
        question_male = Question.objects.create(
            question_number=2,
            question_name='Male',
            group_name='Gender',
            text='How strongly do you identify as male?',
            is_approved=True,
        )
        question_female = Question.objects.create(
            question_number=2,
            question_name='Female',
            group_name='Gender',
            text='How strongly do you identify as female?',
            is_approved=True,
        )
        UserAnswer.objects.create(
            user=self.user,
            question=question_friend,
            me_answer=5,
            looking_for_answer=3,
        )
        UserAnswer.objects.create(
            user=self.user,
            question=question_male,
            me_answer=4,
            looking_for_answer=3,
        )
        UserAnswer.objects.create(
            user=self.user,
            question=question_female,
            me_answer=2,
            looking_for_answer=3,
        )
        unanswered_user = User.objects.create_user(
            username='unanswered@example.com',
            email='unanswered@example.com',
            password='testpass123',
        )
        User.objects.filter(id=self.user.id).update(questions_answered_count=0)

        response = self.client.get('/api/users/admin_profiles/')

        self.assertEqual(response.status_code, 200)
        by_id = {str(row['id']): row for row in response.data}
        self.assertEqual(by_id[str(self.user.id)]['question_answers']['male'], 4)
        self.assertEqual(by_id[str(self.user.id)]['question_answers']['female'], 2)
        self.assertEqual(by_id[str(self.user.id)]['question_answers']['friend'], 5)
        self.assertEqual(by_id[str(self.user.id)]['questions_answered_count'], 3)
        self.assertNotIn('male', by_id[str(unanswered_user.id)]['question_answers'])

    def test_detail_closes_orphan_active_expired_history(self):
        restricted_at = timezone.now() - timedelta(days=30)
        expires_at = restricted_at + timedelta(days=14)
        UserRestrictionHistory.objects.create(
            user=self.user,
            restriction_type='temporary',
            duration_days=14,
            reason='admin_restriction',
            restricted_at=restricted_at,
            expires_at=expires_at,
        )

        response = self.client.get(f'/api/users/{self.user.id}/')

        self.assertEqual(response.status_code, 200)
        history = UserRestrictionHistory.objects.get(user=self.user)
        self.assertEqual(history.end_reason, 'expired')
        self.assertEqual(history.ended_at, expires_at)
        self.assertEqual(response.data['restriction_history'][0]['end_reason'], 'expired')

    def test_restricted_endpoint_creates_history_for_legacy_banned_user(self):
        legacy_user = User.objects.create_user(
            username='legacy@example.com',
            email='legacy@example.com',
            password='testpass123',
        )
        legacy_user.is_banned = True
        legacy_user.ban_reason = 'Legacy moderation action'
        legacy_user.ban_date = timezone.now()
        legacy_user.save()

        response = self.client.get('/api/users/restricted/')

        self.assertEqual(response.status_code, 200)
        history = UserRestrictionHistory.objects.get(user=legacy_user)
        self.assertEqual(history.restriction_type, 'temporary')
        self.assertEqual(history.reason, 'Legacy moderation action')
        self.assertIsNone(history.ended_at)
