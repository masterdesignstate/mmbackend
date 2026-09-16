"""
Tests for clearing answers through POST /api/answers/undo_question/.

A mandatory grouped question (Ethnicity, Education, Ideology, ...) is satisfied by any one
answered option, so a single option may be cleared while another stays answered.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from api.models import Question, UserAnswer, UserRequiredQuestion

URL = '/api/answers/undo_question/'


class UndoQuestionTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(username='u', email='u@test.com', password='pass123')

        def option(name, number, group_number, mandatory):
            return Question.objects.create(
                text=name, question_name=name, question_type='grouped', question_number=number,
                group_number=group_number, group_name='Group', is_approved=True, is_mandatory=mandatory,
            )

        self.white = option('White', 4, 1, True)
        self.black = option('Black', 4, 2, True)
        self.optional_a = option('A', 40, 1, False)
        self.basic = Question.objects.create(
            text='Basic', question_name='Basic', question_type='basic', question_number=41, is_approved=True,
        )

    def answer(self, question, required=False):
        UserAnswer.objects.create(user=self.user, question=question, me_answer=3, looking_for_answer=3)
        if required:
            UserRequiredQuestion.objects.create(user=self.user, question=question)

    def post(self, **data):
        return self.client.post(URL, {'user_id': str(self.user.id), **data}, format='json')

    def test_clears_one_mandatory_option_when_another_stays_answered(self):
        self.answer(self.white, required=True)
        self.answer(self.black, required=True)

        response = self.post(question_id=str(self.black.id))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['deleted_count'], 1)
        self.assertFalse(UserAnswer.objects.filter(user=self.user, question=self.black).exists())
        self.assertTrue(UserAnswer.objects.filter(user=self.user, question=self.white).exists())
        self.assertFalse(UserRequiredQuestion.objects.filter(user=self.user, question=self.black).exists())
        self.assertTrue(UserRequiredQuestion.objects.filter(user=self.user, question=self.white).exists())
        self.user.refresh_from_db()
        self.assertEqual(self.user.questions_answered_count, 1)

    def test_refuses_last_answered_mandatory_option(self):
        self.answer(self.white)

        response = self.post(question_id=str(self.white.id))

        self.assertEqual(response.status_code, 400)
        self.assertTrue(UserAnswer.objects.filter(user=self.user, question=self.white).exists())

    def test_clears_last_optional_grouped_option(self):
        self.answer(self.optional_a)

        response = self.post(question_id=str(self.optional_a.id))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(UserAnswer.objects.filter(user=self.user).exists())

    def test_refuses_single_non_grouped_question_by_id(self):
        self.answer(self.basic)

        response = self.post(question_id=str(self.basic.id))

        self.assertEqual(response.status_code, 400)
        self.assertTrue(UserAnswer.objects.filter(user=self.user, question=self.basic).exists())

    def test_unanswered_option_is_not_found(self):
        self.answer(self.white)

        response = self.post(question_id=str(self.black.id))

        self.assertEqual(response.status_code, 404)

    def test_question_number_still_refuses_mandatory(self):
        self.answer(self.white)
        self.answer(self.black)

        response = self.post(question_number=4)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(UserAnswer.objects.filter(user=self.user).count(), 2)

    def test_question_number_clears_optional_question(self):
        self.answer(self.basic, required=True)

        response = self.post(question_number=41)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(UserAnswer.objects.filter(user=self.user).exists())
        self.assertFalse(UserRequiredQuestion.objects.filter(user=self.user).exists())
