import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from api.models import FeedActivity, Question


class FeedPhotoActivityTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='photo_owner', email='photo_owner@test.com', password='pass123',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _add_picture(self, url):
        response = self.client.post(f'/api/users/{self.user.id}/pictures/', {'image_url': url}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return str(response.data['id'])

    def _feed_activities(self, kind):
        results = self.client.get(f'/api/feed/?user_id={self.user.id}').data['results']
        return [item['activity'] for item in results if item['kind'] == kind]

    def test_deleting_a_picture_removes_its_feed_activity(self):
        kept = self._add_picture('https://example.com/kept.jpg')
        removed = self._add_picture('https://example.com/removed.jpg')

        response = self.client.delete(f'/api/users/{self.user.id}/pictures/{removed}/')

        self.assertEqual(response.status_code, 204)
        remaining = [a.payload.get('picture_id') for a in FeedActivity.objects.filter(kind='photo_added')]
        self.assertEqual(remaining, [kept])

    def test_feed_hides_photo_activity_whose_picture_is_already_gone(self):
        kept = self._add_picture('https://example.com/kept.jpg')
        # Written before delete cleanup existed: the picture row is gone, the activity is not.
        FeedActivity.objects.create(
            user=self.user, kind='photo_added',
            payload={'image_url': 'https://example.com/gone.jpg', 'picture_id': str(uuid.uuid4())},
        )

        activities = self._feed_activities('photo_added')

        self.assertEqual(len(activities), 1)
        self.assertNotIn('group_count', activities[0])
        self.assertEqual(activities[0]['payload']['picture_id'], kept)

    def test_reordering_to_a_new_primary_records_one_activity(self):
        first = self._add_picture('https://example.com/first.jpg')
        second = self._add_picture('https://example.com/second.jpg')
        # Adding photos never changes an existing primary, and the first photo is photo_added news.
        self.assertFalse(FeedActivity.objects.filter(kind='primary_photo_changed').exists())

        response = self.client.post(
            f'/api/users/{self.user.id}/pictures/reorder/', {'order': [second, first]}, format='json',
        )

        self.assertEqual(response.status_code, 200)
        changes = list(FeedActivity.objects.filter(kind='primary_photo_changed'))
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].payload['picture_id'], second)
        self.assertEqual(self._feed_activities('primary_photo_changed')[0]['payload']['picture_id'], second)

    def test_feed_fills_in_question_number_for_older_answer_activity(self):
        question = Question.objects.create(
            question_number=15, group_number=1, text='How strongly do you identify as a Christian?',
            is_approved=True,
        )
        FeedActivity.objects.create(
            user=self.user, kind='question_answered',
            payload={'question_id': str(question.id), 'question_text': question.text},
        )

        activities = self._feed_activities('question_answered')

        self.assertEqual(activities[0]['payload']['question_number'], 15)
