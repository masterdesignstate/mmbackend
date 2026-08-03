from django.core.cache import cache
from django.test import TestCase

from api.models import RestrictedWord, User


class RestrictedWordApiTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='restricted-admin@example.com',
            email='restricted-admin@example.com',
            password='Admin-password-2468',
            is_admin=True,
        )
        self.member = User.objects.create_user(
            username='restricted-member@example.com',
            email='restricted-member@example.com',
            password='Member-password-2468',
        )

    def test_admin_is_required(self):
        anonymous = self.client.get('/api/restricted-words/')
        member = self.client.get(f'/api/restricted-words/?user_id={self.member.id}')
        self.assertEqual(anonymous.status_code, 403)
        self.assertEqual(member.status_code, 403)

    def test_admin_can_create_update_list_and_delete(self):
        cache.set('restricted_words_set', {'stale'}, 300)
        created = self.client.post(
            '/api/restricted-words/',
            data={
                'user_id': str(self.admin.id),
                'word': '  ExampleBlockedPhrase  ',
                'severity': 'medium',
                'is_active': True,
            },
            content_type='application/json',
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()['word'], 'exampleblockedphrase')
        self.assertIsNone(cache.get('restricted_words_set'))

        word_id = created.json()['id']
        listed = self.client.get(f'/api/restricted-words/?user_id={self.admin.id}')
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()['count'], 1)

        cache.set('restricted_words_set', {'stale'}, 300)
        updated = self.client.patch(
            f'/api/restricted-words/{word_id}/',
            data={'user_id': str(self.admin.id), 'is_active': False},
            content_type='application/json',
        )
        self.assertEqual(updated.status_code, 200)
        self.assertFalse(updated.json()['is_active'])
        self.assertIsNone(cache.get('restricted_words_set'))

        cache.set('restricted_words_set', {'stale'}, 300)
        deleted = self.client.delete(
            f'/api/restricted-words/{word_id}/?user_id={self.admin.id}'
        )
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(RestrictedWord.objects.filter(pk=word_id).exists())
        self.assertIsNone(cache.get('restricted_words_set'))

    def test_duplicate_is_case_insensitive(self):
        RestrictedWord.objects.create(word='duplicate', severity='high')
        duplicate = self.client.post(
            '/api/restricted-words/',
            data={
                'user_id': str(self.admin.id),
                'word': 'DUPLICATE',
                'severity': 'low',
                'is_active': True,
            },
            content_type='application/json',
        )
        self.assertEqual(duplicate.status_code, 400)
