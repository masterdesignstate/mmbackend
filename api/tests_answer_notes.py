from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from api.models import Question, QuestionAnswer, RestrictedWord, User, UserAnswer, UserResult
from api.serializers import UserAnswerSerializer


class AnswerNoteTestBase(TestCase):
    """Shared fixtures: an author with a note, plus a second user to view it."""

    def setUp(self):
        cache.clear()  # restricted-word list is cached for 5 min
        self.client = APIClient()

        self.author = User.objects.create_user(
            username='author', email='author@example.com', password='pw'
        )
        self.viewer = User.objects.create_user(
            username='viewer', email='viewer@example.com', password='pw'
        )

        self.question = Question.objects.create(
            question_number=11,
            question_name='Test',
            group_name='Test',
            text='Test question',
            is_approved=True,
        )
        for index, value in enumerate([1, 2, 3, 4, 5]):
            QuestionAnswer.objects.create(
                question=self.question,
                value=str(value),
                answer_text=str(value),
                order=index,
            )

    def make_answer(self, user=None, note='my private note'):
        return UserAnswer.objects.create(
            user=user or self.author,
            question=self.question,
            me_answer=3,
            looking_for_answer=3,
            me_note=note,
        )

    def set_relationship(self, source, target, tag):
        UserResult.objects.create(user=source, result_user=target, tag=tag)


class MeNoteWriteTests(AnswerNoteTestBase):
    def test_create_rejects_note_over_160_chars(self):
        response = self.client.post(
            '/api/answers/',
            {
                'user_id': str(self.author.id),
                'question_id': str(self.question.id),
                'me_answer': 3,
                'looking_for_answer': 3,
                'me_note': 'x' * 161,
            },
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('160', response.data['error'])
        self.assertFalse(UserAnswer.objects.filter(user=self.author).exists())

    def test_create_accepts_note_at_exactly_160_chars(self):
        response = self.client.post(
            '/api/answers/',
            {
                'user_id': str(self.author.id),
                'question_id': str(self.question.id),
                'me_answer': 3,
                'looking_for_answer': 3,
                'me_note': 'x' * 160,
            },
            format='json',
        )
        self.assertIn(response.status_code, (200, 201))
        self.assertEqual(UserAnswer.objects.get(user=self.author).me_note, 'x' * 160)

    def test_update_rejects_note_over_160_chars(self):
        answer = self.make_answer(note='original')
        response = self.client.patch(
            f'/api/answers/{answer.id}/',
            {'me_note': 'x' * 161},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        answer.refresh_from_db()
        self.assertEqual(answer.me_note, 'original')

    def test_restricted_word_is_rejected_without_banning_the_user(self):
        RestrictedWord.objects.create(word='badword', is_active=True)
        cache.clear()

        response = self.client.post(
            '/api/answers/',
            {
                'user_id': str(self.author.id),
                'question_id': str(self.question.id),
                'me_answer': 3,
                'looking_for_answer': 3,
                'me_note': 'this is a badword note',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('badword', response.data['error'])

        self.author.refresh_from_db()
        self.assertFalse(self.author.is_banned)

    def test_resaving_without_me_note_preserves_existing_note(self):
        self.make_answer(note='keep me')

        response = self.client.post(
            '/api/answers/',
            {
                'user_id': str(self.author.id),
                'question_id': str(self.question.id),
                'me_answer': 4,
                'looking_for_answer': 2,
            },
            format='json',
        )
        self.assertIn(response.status_code, (200, 201))

        answer = UserAnswer.objects.get(user=self.author)
        self.assertEqual(answer.me_note, 'keep me')
        self.assertEqual(answer.me_answer, 4)

    def test_note_is_trimmed_and_can_be_cleared(self):
        answer = self.make_answer(note='original')

        self.client.patch(f'/api/answers/{answer.id}/', {'me_note': '  spaced  '}, format='json')
        answer.refresh_from_db()
        self.assertEqual(answer.me_note, 'spaced')
        self.assertIsNotNone(answer.me_note_updated_at)

        self.client.patch(f'/api/answers/{answer.id}/', {'me_note': ''}, format='json')
        answer.refresh_from_db()
        self.assertEqual(answer.me_note, '')


class MeNoteVisibilityTests(AnswerNoteTestBase):
    """The note text must be absent from the raw payload, not merely hidden client-side."""

    def note_from_answers_list(self, viewer_id):
        response = self.client.get(
            f'/api/answers/?user={self.author.id}&user_id={viewer_id}'
        )
        self.assertEqual(response.status_code, 200)
        results = response.data['results'] if 'results' in response.data else response.data
        return results[0]['me_note']

    def test_author_always_sees_own_note(self):
        self.make_answer()
        for visibility in ('none', 'all', 'approved', 'liked', 'matched'):
            self.author.note_visibility = visibility
            self.author.save(update_fields=['note_visibility'])
            self.assertEqual(
                self.note_from_answers_list(self.author.id),
                'my private note',
                f'author lost their own note under note_visibility={visibility}',
            )

    def test_visibility_all_shows_note_to_stranger(self):
        self.make_answer()
        self.author.note_visibility = 'all'
        self.author.save(update_fields=['note_visibility'])
        self.assertEqual(self.note_from_answers_list(self.viewer.id), 'my private note')

    def test_visibility_none_hides_note_from_everyone_else(self):
        self.make_answer()
        self.author.note_visibility = 'none'
        self.author.save(update_fields=['note_visibility'])
        self.assertEqual(self.note_from_answers_list(self.viewer.id), '')

    def test_visibility_approved_requires_author_approval_of_viewer(self):
        self.make_answer()
        self.author.note_visibility = 'approved'
        self.author.save(update_fields=['note_visibility'])

        self.assertEqual(self.note_from_answers_list(self.viewer.id), '')

        self.set_relationship(self.author, self.viewer, 'approve')
        self.assertEqual(self.note_from_answers_list(self.viewer.id), 'my private note')

    def test_visibility_liked_requires_author_like_of_viewer(self):
        self.make_answer()
        self.author.note_visibility = 'liked'
        self.author.save(update_fields=['note_visibility'])

        self.assertEqual(self.note_from_answers_list(self.viewer.id), '')

        self.set_relationship(self.author, self.viewer, 'like')
        self.assertEqual(self.note_from_answers_list(self.viewer.id), 'my private note')

    def test_visibility_matched_requires_mutual_like(self):
        self.make_answer()
        self.author.note_visibility = 'matched'
        self.author.save(update_fields=['note_visibility'])

        # One-directional like is not a match.
        self.set_relationship(self.author, self.viewer, 'like')
        self.assertEqual(self.note_from_answers_list(self.viewer.id), '')

        self.set_relationship(self.viewer, self.author, 'like')
        self.assertEqual(self.note_from_answers_list(self.viewer.id), 'my private note')

    def test_anonymous_viewer_sees_no_note(self):
        self.make_answer()
        self.author.note_visibility = 'all'
        self.author.save(update_fields=['note_visibility'])

        response = self.client.get(f'/api/answers/?user={self.author.id}')
        results = response.data['results'] if 'results' in response.data else response.data
        self.assertEqual(results[0]['me_note'], '')

    def test_serializer_without_context_fails_closed(self):
        answer = self.make_answer()
        self.author.note_visibility = 'all'
        self.author.save(update_fields=['note_visibility'])

        self.assertEqual(UserAnswerSerializer(answer).data['me_note'], '')


class MeNoteExposurePathTests(AnswerNoteTestBase):
    """Every endpoint that serializes UserAnswer must strip hidden notes."""

    def setUp(self):
        super().setUp()
        self.make_answer()
        self.author.note_visibility = 'none'
        self.author.save(update_fields=['note_visibility'])

    def assert_no_note_in(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('my private note', str(response.data))

    def test_answer_detail_strips_note(self):
        answer = UserAnswer.objects.get(user=self.author)
        self.assert_no_note_in(
            self.client.get(f'/api/answers/{answer.id}/?user_id={self.viewer.id}')
        )

    def test_by_question_strips_note(self):
        self.assert_no_note_in(
            self.client.get(
                f'/api/answers/by_question/?question_id={self.question.id}&user_id={self.viewer.id}'
            )
        )

    def test_user_detail_strips_note(self):
        self.assert_no_note_in(
            self.client.get(f'/api/users/{self.author.id}/?user_id={self.viewer.id}')
        )

    def test_question_detail_strips_note(self):
        self.assert_no_note_in(
            self.client.get(f'/api/questions/{self.question.id}/?user_id={self.viewer.id}')
        )

    def test_users_me_keeps_own_note(self):
        self.client.force_authenticate(user=self.author)
        response = self.client.get('/api/users/me/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('my private note', str(response.data))


class NoteVisibilitySettingTests(AnswerNoteTestBase):
    def test_default_is_everyone(self):
        self.assertEqual(self.author.note_visibility, 'all')

    def test_patch_persists_note_visibility(self):
        response = self.client.patch(
            f'/api/users/{self.author.id}/',
            {'note_visibility': 'matched'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.author.refresh_from_db()
        self.assertEqual(self.author.note_visibility, 'matched')
