from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from api.models import FeedActivity, Post


class FeedPeopleSearchTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.viewer = User.objects.create_user(username='viewer', email='viewer@test.com', password='pass123')
        self.lucy = User.objects.create_user(
            username='lucy_sky', email='lucy@test.com', password='pass123', first_name='Lucy', last_name='Hart',
        )
        self.other = User.objects.create_user(
            username='bob', email='bob@test.com', password='pass123', first_name='Bob',
        )
        Post.objects.create(author=self.lucy, body='Weekend hike photos')
        Post.objects.create(author=self.other, body='Lucy recommended this book')
        Post.objects.create(author=self.other, body='Nothing to see here')
        FeedActivity.objects.create(user=self.lucy, kind='bio_updated', payload={'snippet': 'Hi'})
        FeedActivity.objects.create(user=self.other, kind='bio_updated', payload={'snippet': 'Yo'})
        self.client = APIClient()
        self.client.force_authenticate(self.viewer)

    def _search(self, q):
        return self.client.get('/api/feed/', {'q': q}).data

    def test_name_search_returns_the_persons_posts_and_activity_and_body_matches(self):
        data = self._search('lucy')

        bodies = {item['post']['body'] for item in data['results'] if item['kind'] == 'post'}
        self.assertEqual(bodies, {'Weekend hike photos', 'Lucy recommended this book'})
        activity_users = {item['activity']['user']['id'] for item in data['results'] if item['kind'] == 'bio_updated'}
        self.assertEqual(activity_users, {str(self.lucy.id)})
        self.assertEqual([p['id'] for p in data['people']], [str(self.lucy.id)])

    def test_username_with_at_sign_and_full_name_both_match(self):
        self.assertEqual([p['id'] for p in self._search('@lucy_sky')['people']], [str(self.lucy.id)])
        self.assertEqual([p['id'] for p in self._search('Lucy Hart')['people']], [str(self.lucy.id)])

    def test_text_only_search_shows_no_activity_or_people(self):
        data = self._search('nothing')

        self.assertEqual([item['kind'] for item in data['results']], ['post'])
        self.assertEqual(data['people'], [])

    def test_viewer_is_not_listed_among_people(self):
        self.assertEqual(self._search('viewer')['people'], [])

    def test_selecting_a_person_shows_their_posts_and_updates_and_keeps_people(self):
        data = self.client.get('/api/feed/', {'q': 'lucy', 'author_id': str(self.lucy.id)}).data

        bodies = {item['post']['body'] for item in data['results'] if item['kind'] == 'post'}
        self.assertEqual(bodies, {'Weekend hike photos'})
        activity_users = {item['activity']['user']['id'] for item in data['results'] if item['kind'] == 'bio_updated'}
        self.assertEqual(activity_users, {str(self.lucy.id)})
        self.assertEqual([person['id'] for person in data['people']], [str(self.lucy.id)])

    def test_author_without_a_search_returns_posts_only(self):
        data = self.client.get('/api/feed/', {'author_id': str(self.lucy.id)}).data

        self.assertEqual([item['kind'] for item in data['results']], ['post'])
        self.assertEqual(data['people'], [])
