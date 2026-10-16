from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from api.models import Notification, Question, QuestionAnswer, UserAnswer, UserResult


class QuestionPromptTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.sender = User.objects.create_user(username='sender', email='s@test.com', password='pass123', first_name='Sam')
        self.recipient = User.objects.create_user(username='recipient', email='r@test.com', password='pass123')
        self.question = Question.objects.create(
            question_number=40, question_name='Coffee', group_name='Coffee', text='Do you drink coffee?',
            is_approved=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.sender)

    def _prompt(self, **overrides):
        payload = {'recipient_id': str(self.recipient.id), 'question_number': 40, **overrides}
        return self.client.post('/api/notifications/prompt_question/', payload, format='json')

    def test_prompt_notifies_recipient_with_the_question(self):
        response = self._prompt()

        self.assertEqual(response.status_code, 200, response.data)
        notification = Notification.objects.get(recipient=self.recipient)
        self.assertEqual(notification.notification_type, 'question_prompt')
        self.assertEqual(notification.sender, self.sender)
        self.assertEqual(notification.related_question, self.question)

        listed = self.client.get('/api/notifications/', {'user_id': str(self.recipient.id)}).data
        rows = listed['results'] if isinstance(listed, dict) else listed
        self.assertEqual(rows[0]['related_question']['question_number'], 40)

    def test_repeat_prompt_while_unread_does_not_stack(self):
        self._prompt()
        response = self._prompt()

        self.assertTrue(response.data['already_prompted'])
        self.assertEqual(Notification.objects.filter(recipient=self.recipient).count(), 1)

    def test_cannot_prompt_for_an_answered_question(self):
        QuestionAnswer.objects.create(question=self.question, value='1', answer_text='Never', order=0)
        UserAnswer.objects.create(user=self.recipient, question=self.question, me_answer=1, looking_for_answer=1)

        response = self._prompt()

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Notification.objects.exists())

    def test_cannot_prompt_yourself(self):
        response = self._prompt(recipient_id=str(self.sender.id))
        self.assertEqual(response.status_code, 400)

    def test_recipient_who_hid_the_sender_gets_nothing(self):
        UserResult.objects.create(user=self.recipient, result_user=self.sender, tag='hide')

        response = self._prompt()

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Notification.objects.exists())


class AnswerExclusionsEndpointTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='u', email='u@test.com', password='pass123')
        self.question = Question.objects.create(
            question_number=41, question_name='Tea', group_name='Tea', text='Tea?', is_approved=True,
        )
        for value, text in [(1, 'Never'), (3, 'Sometimes'), (5, 'Daily')]:
            QuestionAnswer.objects.create(question=self.question, value=str(value), answer_text=text, order=value)
        self.client = APIClient()

    def test_lists_only_answers_with_exclusions_and_their_allowed_values(self):
        UserAnswer.objects.create(
            user=self.user, question=self.question, me_answer=3, looking_for_answer=3, excluded_answer_values=[1, 5],
        )
        other = Question.objects.create(question_number=42, question_name='X', group_name='X', text='X?', is_approved=True)
        UserAnswer.objects.create(user=self.user, question=other, me_answer=2, looking_for_answer=2)

        rows = self.client.get('/api/answers/exclusions/', {'user': str(self.user.id)}).data

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['excluded_answer_values'], [1, 5])
        self.assertEqual(rows[0]['allowed_values'], [1, 3, 5])
        self.assertEqual(rows[0]['blocked_values'], [3])
        self.assertEqual(rows[0]['value_labels']['5'], 'Daily')

    def test_all_lists_every_answer_that_can_be_excluded_on(self):
        UserAnswer.objects.create(
            user=self.user, question=self.question, me_answer=3, looking_for_answer=3, excluded_answer_values=[1],
        )
        other = Question.objects.create(question_number=42, question_name='X', group_name='X', text='X?', is_approved=True)
        UserAnswer.objects.create(user=self.user, question=other, me_answer=2, looking_for_answer=2)

        rows = self.client.get('/api/answers/exclusions/', {'user': str(self.user.id), 'all': '1'}).data

        self.assertEqual([row['question']['question_number'] for row in rows], [41, 42])
        self.assertEqual(rows[1]['excluded_answer_values'], [])


class BioLengthTests(TestCase):
    def test_edit_profile_keeps_a_3000_character_about_me(self):
        User = get_user_model()
        user = User.objects.create_user(username='writer', email='w@test.com', password='pass123', first_name='Wren')
        about_me = 'word ' * 600

        response = APIClient().post(
            '/api/auth/personal-details/',
            {'user_id': str(user.id), 'from': 'Austin', 'live': 'Austin', 'bio': about_me},
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.content)
        user.refresh_from_db()
        self.assertEqual(len(user.bio), User.MAX_BIO_LENGTH)
