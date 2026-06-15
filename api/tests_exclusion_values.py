from django.test import TestCase

from api.models import Question, QuestionAnswer
from api.views import (
    _allowed_excluded_answer_values_for_question,
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
