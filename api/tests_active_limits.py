from datetime import date

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from api import mandatory_questions as mq
from api.models import Compatibility, Question, SavedResultFilter, User, UserAnswer
from api.services import active_limits
from api.services.compatibility_service import CompatibilityService


def _user(username, *, dummy=False, dob=None, age=None):
    return User.objects.create_user(
        username=username,
        email=f'{username}@test.com',
        password='pass123',
        is_dummy=dummy,
        date_of_birth=dob,
        age=age,
    )


class DummyLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.real = _user('real', dob=date(1950, 1, 1))
        self.young = _user('young', dummy=True, dob=date(2004, 1, 1))
        self.middle = _user('middle', dummy=True, dob=date(1990, 1, 1))
        self.old = _user('old', dummy=True, dob=date(1960, 1, 1))
        self.unknown = _user('unknown', dummy=True)

    def _disabled(self):
        return set(User.objects.filter(is_disabled=True).values_list('username', flat=True))

    def test_keeps_youngest_and_disables_unknown_ages_first(self):
        active_limits.apply_dummy_limit(2)
        self.assertEqual(self._disabled(), {'old', 'unknown'})

        active_limits.apply_dummy_limit(3)
        self.assertEqual(self._disabled(), {'unknown'})

    def test_real_users_are_never_disabled(self):
        active_limits.apply_dummy_limit(0)
        self.assertNotIn('real', self._disabled())
        self.assertEqual(self._disabled(), {'young', 'middle', 'old', 'unknown'})

    def test_age_is_used_when_there_is_no_birth_date(self):
        _user('aged', dummy=True, age=25)
        active_limits.apply_dummy_limit(2)
        self.assertEqual(self._disabled(), {'middle', 'old', 'unknown'})


class QuestionLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        for number in mq.MANDATORY_QUESTION_NUMBERS:
            Question.objects.create(
                question_number=number, question_name=f'M{number}', text=f'Mandatory {number}',
                is_approved=True, is_mandatory=True,
            )
        first = mq.FIRST_OPTIONAL_QUESTION_NUMBER
        for number in range(first, first + 5):
            Question.objects.create(
                question_number=number, question_name=f'O{number}', text=f'Optional {number}',
                is_approved=True,
            )
        self.first_optional = first

    def _enabled_numbers(self):
        return set(
            Question.objects.filter(is_disabled=False).values_list('question_number', flat=True)
        )

    def test_mandatory_questions_are_always_kept(self):
        active_limits.apply_question_limit(3)
        self.assertEqual(self._enabled_numbers(), set(mq.MANDATORY_QUESTION_NUMBERS))

    def test_keeps_the_lowest_numbers_and_raising_reenables(self):
        limit = len(mq.MANDATORY_QUESTION_NUMBERS) + 2
        active_limits.apply_question_limit(limit)
        expected = set(mq.MANDATORY_QUESTION_NUMBERS) | {self.first_optional, self.first_optional + 1}
        self.assertEqual(self._enabled_numbers(), expected)

        active_limits.apply_question_limit(limit + 10)
        self.assertEqual(Question.objects.filter(is_disabled=True).count(), 0)

    def test_disabled_questions_are_hidden_from_the_question_list(self):
        active_limits.apply_question_limit(len(mq.MANDATORY_QUESTION_NUMBERS))
        response = APIClient().get('/api/questions/', {'page_size': 100})
        numbers = {row['question_number'] for row in response.data['results']}
        self.assertNotIn(self.first_optional, numbers)

        admin_view = APIClient().get('/api/questions/', {'page_size': 100, 'include_disabled': 'true'})
        self.assertIn(self.first_optional, {row['question_number'] for row in admin_view.data['results']})


class DisabledScoringTests(TestCase):
    def setUp(self):
        cache.clear()
        self.a = _user('a')
        self.b = _user('b')
        self.agree = Question.objects.create(question_number=101, question_name='Agree', text='Agree', is_approved=True)
        self.clash = Question.objects.create(question_number=102, question_name='Clash', text='Clash', is_approved=True)
        for user in (self.a, self.b):
            UserAnswer.objects.create(
                user=user, question=self.agree, me_answer=3, looking_for_answer=3,
                me_importance=3, looking_for_importance=3,
            )
        UserAnswer.objects.create(
            user=self.a, question=self.clash, me_answer=1, looking_for_answer=1,
            me_importance=3, looking_for_importance=3,
        )
        UserAnswer.objects.create(
            user=self.b, question=self.clash, me_answer=5, looking_for_answer=5,
            me_importance=3, looking_for_importance=3,
        )

    def test_disabled_question_does_not_count(self):
        before = CompatibilityService.calculate_compatibility_between_users(self.a, self.b)
        self.assertEqual(before['mutual_questions_count'], 2)
        self.assertLess(before['overall_compatibility'], 100)

        Question.objects.filter(id=self.clash.id).update(is_disabled=True)
        active_limits.invalidate_question_state()

        after = CompatibilityService.calculate_compatibility_between_users(self.a, self.b)
        self.assertEqual(after['mutual_questions_count'], 1)
        self.assertEqual(after['overall_compatibility'], 100)


class DisabledUserVisibilityTests(TestCase):
    def setUp(self):
        cache.clear()
        # Seeded mandatory questions would hide these answerless accounts for another reason.
        Question.objects.update(is_mandatory=False)
        self.viewer = _user('viewer')
        self.visible = _user('visible', dummy=True)
        self.hidden = _user('hidden', dummy=True)
        for other in (self.visible, self.hidden):
            Compatibility.objects.create(user1=self.viewer, user2=other, overall_compatibility=80)
        User.objects.filter(id=self.hidden.id).update(is_disabled=True)

    def test_disabled_user_is_not_in_results(self):
        response = APIClient().get('/api/users/compatible/', {'user_id': str(self.viewer.id)})
        self.assertEqual(response.status_code, 200, response.data)
        ids = {row['user']['id'] for row in response.data['results']}
        self.assertIn(str(self.visible.id), ids)
        self.assertNotIn(str(self.hidden.id), ids)

    def test_disabled_user_cannot_log_in(self):
        response = APIClient().post(
            '/api/auth/login/', {'email': 'hidden@test.com', 'password': 'pass123'}, format='json',
        )
        self.assertEqual(response.status_code, 403)


class SavedResultFilterTests(TestCase):
    def setUp(self):
        self.user = _user('filterer')
        self.client = APIClient()
        self.base = '/api/saved-result-filters/'

    def _create(self, name, **filters):
        return self.client.post(
            self.base, {'user_id': str(self.user.id), 'name': name, 'filters': filters}, format='json',
        )

    def test_create_list_rename_and_delete(self):
        created = self._create('Close by', distance={'min': 1, 'max': 10}, tags=['Liked'])
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data['filters']['distance'], {'min': 1, 'max': 10})
        self.assertEqual(created.data['filters']['age'], {'min': 18, 'max': 80})

        listed = self.client.get(self.base, {'user_id': str(self.user.id)})
        self.assertEqual([row['name'] for row in listed.data], ['Close by'])

        pk = created.data['id']
        renamed = self.client.patch(
            f'{self.base}{pk}/?user_id={self.user.id}', {'name': 'Nearby'}, format='json',
        )
        self.assertEqual(renamed.status_code, 200, renamed.data)
        self.assertEqual(renamed.data['name'], 'Nearby')

        deleted = self.client.delete(f'{self.base}{pk}/?user_id={self.user.id}')
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(SavedResultFilter.objects.exists())

    def test_rejects_bad_payloads_and_duplicate_names(self):
        self.assertEqual(self._create('Bad', age={'min': 10, 'max': 80}).status_code, 400)
        self.assertEqual(self._create('Bad', tags=['Nope']).status_code, 400)
        self.assertEqual(self._create('Bad', compatibilityType='nope').status_code, 400)
        self.assertEqual(self._create('x' * 41).status_code, 400)
        self.assertEqual(self._create('Mine').status_code, 201)
        self.assertEqual(self._create('mine').status_code, 400)

    def test_per_user_limit(self):
        for index in range(SavedResultFilter.MAX_PER_USER):
            self.assertEqual(self._create(f'F{index}').status_code, 201)
        response = self._create('One too many')
        self.assertEqual(response.status_code, 400)

    def test_other_users_presets_are_not_visible_or_editable(self):
        pk = self._create('Mine').data['id']
        other = _user('other')
        listed = self.client.get(self.base, {'user_id': str(other.id)})
        self.assertEqual(listed.data, [])
        response = self.client.delete(f'{self.base}{pk}/?user_id={other.id}')
        self.assertEqual(response.status_code, 404)

    def test_last_applied_filters_round_trip(self):
        url = '/api/users/results_filters/'
        saved = self.client.put(
            url, {'user_id': str(self.user.id), 'filters': {'requiredOnly': True, 'requiredScope': 'their'}},
            format='json',
        )
        self.assertEqual(saved.status_code, 200, saved.data)
        loaded = self.client.get(url, {'user_id': str(self.user.id)})
        self.assertTrue(loaded.data['filters']['requiredOnly'])
        self.assertEqual(loaded.data['filters']['requiredScope'], 'their')

        bad = self.client.put(url, {'user_id': str(self.user.id), 'filters': {'tags': 'Liked'}}, format='json')
        self.assertEqual(bad.status_code, 400)
