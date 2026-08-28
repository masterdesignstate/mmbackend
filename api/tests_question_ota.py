from django.test import TestCase

from .models import Question


class OptionalQuestionOpenToAllTests(TestCase):
    def test_optional_question_always_enables_them_ota_only(self):
        question = Question.objects.create(
            question_name="Optional OTA",
            text="Optional OTA question",
            is_mandatory=False,
            open_to_all_me=True,
            open_to_all_looking_for=False,
        )

        self.assertFalse(question.open_to_all_me)
        self.assertTrue(question.open_to_all_looking_for)

    def test_mandatory_question_preserves_configured_ota(self):
        question = Question.objects.create(
            question_name="Mandatory OTA",
            text="Mandatory OTA question",
            is_mandatory=True,
            open_to_all_me=True,
            open_to_all_looking_for=False,
        )

        self.assertTrue(question.open_to_all_me)
        self.assertFalse(question.open_to_all_looking_for)
