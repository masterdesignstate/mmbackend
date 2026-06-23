from django.test import TestCase

from api.models import Compatibility, Question, QuestionAnswer, User, UserAnswer
from api.views import (
    _apply_importance_exclusions,
    _allowed_excluded_answer_values_for_question,
    _normalize_importance_exclusion_values,
    _normalize_question_answer_value,
    _normalize_excluded_answer_values,
)


class ExcludedAnswerValuesTests(TestCase):
    def make_question(self, question_number, group_number=None, question_name='Question', values=None):
        question = Question.objects.create(
            question_number=question_number,
            group_number=group_number,
            question_name=question_name,
            group_name='Test',
            text='Test question',
            is_approved=True,
        )
        for index, value in enumerate(values or [1, 2, 3, 4, 5]):
            QuestionAnswer.objects.create(
                question=question,
                value=str(value),
                answer_text=str(value),
                order=index,
            )
        return question

    def test_relationship_exclusions_allow_full_scale(self):
        question = self.make_question(1, question_name='Date')

        self.assertEqual(
            _allowed_excluded_answer_values_for_question(question),
            {1, 2, 3, 4, 5},
        )
        self.assertEqual(_normalize_excluded_answer_values([1, 3, 5], question), [1, 3, 5])

    def test_mandatory_endpoint_only_exclusions(self):
        for question_number in [2, 3, 5, 7]:
            question = self.make_question(question_number)
            self.assertEqual(_allowed_excluded_answer_values_for_question(question), {1, 5})
            self.assertEqual(_normalize_excluded_answer_values([1, 5], question), [1, 5])
            with self.assertRaises(ValueError):
                _normalize_excluded_answer_values([2], question)

    def test_education_exclusions_only_allow_three_points(self):
        question = self.make_question(4, values=[1, 3, 5])
        self.assertEqual(_allowed_excluded_answer_values_for_question(question), {1, 3, 5})
        self.assertEqual(_normalize_excluded_answer_values([5, 1, 3], question), [5, 1, 3])
        with self.assertRaises(ValueError):
            _normalize_excluded_answer_values([2], question)

    def test_kids_have_and_want_have_different_exclusion_shapes(self):
        kids_have = self.make_question(10, group_number=1, question_name='Have', values=[1, 5])
        kids_want = self.make_question(10, group_number=2, question_name='Want')

        self.assertEqual(_allowed_excluded_answer_values_for_question(kids_have), {1, 5})
        self.assertEqual(
            _allowed_excluded_answer_values_for_question(kids_want),
            {1, 2, 3, 4, 5},
        )
        with self.assertRaises(ValueError):
            _normalize_excluded_answer_values([3], kids_have)
        self.assertEqual(_normalize_excluded_answer_values([1, 2, 3, 4, 5], kids_want), [1, 2, 3, 4, 5])

    def test_apply_path_can_drop_stale_unsupported_values(self):
        question = self.make_question(3)

        self.assertEqual(
            _normalize_excluded_answer_values([1, 2, 5], question, drop_unsupported=True),
            [1, 5],
        )

    def test_answer_values_must_match_question_answer_rows(self):
        education = self.make_question(4, values=[1, 3, 5])
        kids_have = self.make_question(10, group_number=1, question_name='Have', values=[1, 5])

        self.assertEqual(_normalize_question_answer_value(5, education), 5)
        self.assertEqual(_normalize_question_answer_value(3, education), 3)
        self.assertEqual(_normalize_question_answer_value(5, kids_have), 5)
        self.assertEqual(_normalize_question_answer_value(3, kids_have, open_to_all=True), 6)

        with self.assertRaises(ValueError):
            _normalize_question_answer_value(4, education)
        with self.assertRaises(ValueError):
            _normalize_question_answer_value(3, kids_have)


class ImportanceExclusionTests(TestCase):
    def make_question(self):
        question = Question.objects.create(
            question_number=11,
            question_name='Test',
            group_name='Test',
            text='Importance test question',
            is_approved=True,
        )
        for index, value in enumerate([1, 2, 3, 4, 5]):
            QuestionAnswer.objects.create(
                question=question,
                value=str(value),
                answer_text=str(value),
                order=index,
            )
        return question

    def make_answer(self, user, question, looking_for_importance, me_importance=3):
        return UserAnswer.objects.create(
            user=user,
            question=question,
            me_answer=3,
            me_importance=me_importance,
            looking_for_answer=3,
            looking_for_importance=looking_for_importance,
        )

    def make_pair(self, current_user, other_user):
        return Compatibility.objects.create(
            user1=current_user,
            user2=other_user,
            overall_compatibility=80,
            compatible_with_me=80,
            im_compatible_with=80,
            mutual_questions_count=1,
        )

    def test_importance_exclusion_values_normalize(self):
        self.assertEqual(_normalize_importance_exclusion_values([2, '1', 2, 5]), [2, 1, 5])
        self.assertEqual(_normalize_importance_exclusion_values(None), [])
        with self.assertRaises(ValueError):
            _normalize_importance_exclusion_values('1')
        with self.assertRaises(ValueError):
            _normalize_importance_exclusion_values([0])

    def test_excludes_candidates_by_them_importance_for_questions_i_mark_five(self):
        question = self.make_question()
        current_user = User.objects.create_user(
            username='current',
            email='current@example.com',
            password='password',
            importance_exclusion_values=[1, 2],
        )
        low_importance_user = User.objects.create_user(username='low', email='low@example.com', password='password')
        ok_importance_user = User.objects.create_user(username='ok', email='ok@example.com', password='password')
        self.make_answer(current_user, question, looking_for_importance=5)
        self.make_answer(low_importance_user, question, looking_for_importance=2)
        self.make_answer(ok_importance_user, question, looking_for_importance=3)
        hidden_pair = self.make_pair(current_user, low_importance_user)
        visible_pair = self.make_pair(current_user, ok_importance_user)

        filtered_ids = set(
            _apply_importance_exclusions(Compatibility.objects.all(), current_user)
            .values_list('id', flat=True)
        )

        self.assertNotIn(hidden_pair.id, filtered_ids)
        self.assertIn(visible_pair.id, filtered_ids)

    def test_does_not_apply_when_my_them_importance_is_not_five(self):
        question = self.make_question()
        current_user = User.objects.create_user(
            username='current',
            email='current@example.com',
            password='password',
            importance_exclusion_values=[1, 2],
        )
        other_user = User.objects.create_user(username='other', email='other@example.com', password='password')
        self.make_answer(current_user, question, looking_for_importance=4)
        self.make_answer(other_user, question, looking_for_importance=1)
        pair = self.make_pair(current_user, other_user)

        filtered_ids = set(
            _apply_importance_exclusions(Compatibility.objects.all(), current_user)
            .values_list('id', flat=True)
        )

        self.assertIn(pair.id, filtered_ids)

    def test_uses_candidate_them_importance_not_me_importance(self):
        question = self.make_question()
        current_user = User.objects.create_user(
            username='current',
            email='current@example.com',
            password='password',
            importance_exclusion_values=[1],
        )
        other_user = User.objects.create_user(username='other', email='other@example.com', password='password')
        self.make_answer(current_user, question, looking_for_importance=5)
        self.make_answer(other_user, question, looking_for_importance=3, me_importance=1)
        pair = self.make_pair(current_user, other_user)

        filtered_ids = set(
            _apply_importance_exclusions(Compatibility.objects.all(), current_user)
            .values_list('id', flat=True)
        )

        self.assertIn(pair.id, filtered_ids)
