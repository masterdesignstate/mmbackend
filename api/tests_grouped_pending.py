"""
Tests for grouped question pending behavior.

Scenario: User A marks multiple sub-questions from a grouped question as required.
User B answers one sub-question. Verify the remaining sub-questions are still pending.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from api.models import Question, UserAnswer, UserRequiredQuestion, Tag, QuestionNumberCounter


class GroupedQuestionPendingTestCase(TestCase):
    """Test that answering one sub-question of a grouped question doesn't remove others from pending."""

    def setUp(self):
        QuestionNumberCounter.objects.get_or_create(id=1, defaults={'last_number': 0})

        User = get_user_model()
        self.user_a = User.objects.create_user(
            username='user_a', email='a@test.com', password='pass123'
        )
        self.user_b = User.objects.create_user(
            username='user_b', email='b@test.com', password='pass123'
        )

        self.tag, _ = Tag.objects.get_or_create(name='lifestyle')

        # Create 3 grouped sub-questions with the same question_number (like Ethnicity or Diet)
        self.q1 = Question.objects.create(
            text='Diet - Vegetarian preferences',
            question_name='DIET_SUB1',
            question_type='grouped',
            question_number=5,
            group_number=1,
            group_name='Diet',
            group_name_text='Diet',
            is_approved=True,
        )
        self.q1.tags.add(self.tag)

        self.q2 = Question.objects.create(
            text='Diet - Vegan preferences',
            question_name='DIET_SUB2',
            question_type='grouped',
            question_number=5,
            group_number=2,
            group_name='Diet',
            group_name_text='Diet',
            is_approved=True,
        )
        self.q2.tags.add(self.tag)

        self.q3 = Question.objects.create(
            text='Diet - Keto preferences',
            question_name='DIET_SUB3',
            question_type='grouped',
            question_number=5,
            group_number=3,
            group_name='Diet',
            group_name_text='Diet',
            is_approved=True,
        )
        self.q3.tags.add(self.tag)

    def _get_pending_ids(self, required_user, answering_user):
        """Replicate the frontend pending logic: required IDs minus answered IDs."""
        required_qids = set(
            UserRequiredQuestion.objects.filter(user=required_user)
            .values_list('question_id', flat=True)
        )
        answered_qids = set(
            UserAnswer.objects.filter(user=answering_user)
            .values_list('question_id', flat=True)
        )
        return required_qids - answered_qids

    def _get_pending_group_numbers(self, pending_qids):
        """Replicate the frontend grouped deduplication: one entry per question_number."""
        questions = Question.objects.filter(id__in=pending_qids)
        seen_numbers = set()
        groups = []
        for q in questions:
            qtype = q.question_type or 'basic'
            if qtype in ('four', 'grouped', 'double', 'triple'):
                if q.question_number in seen_numbers:
                    continue
                seen_numbers.add(q.question_number)
            groups.append({
                'question_id': q.id,
                'question_number': q.question_number,
                'text': q.text,
                'type': qtype,
            })
        return groups

    def test_all_three_pending_before_any_answer(self):
        """Before User B answers anything, all 3 required sub-questions are pending."""
        UserRequiredQuestion.objects.get_or_create(user=self.user_a, question=self.q1)
        UserRequiredQuestion.objects.get_or_create(user=self.user_a, question=self.q2)
        UserRequiredQuestion.objects.get_or_create(user=self.user_a, question=self.q3)

        pending = self._get_pending_ids(self.user_a, self.user_b)
        self.assertEqual(len(pending), 3, "All 3 sub-questions should be pending")

        groups = self._get_pending_group_numbers(pending)
        self.assertEqual(len(groups), 1, "Should show as 1 pending group (deduplicated by question_number)")
        self.assertEqual(groups[0]['question_number'], 5)

    def test_answer_one_subquestion_others_remain_pending(self):
        """User B answers 1 of 3 required sub-questions — the other 2 should still be pending."""
        UserRequiredQuestion.objects.get_or_create(user=self.user_a, question=self.q1)
        UserRequiredQuestion.objects.get_or_create(user=self.user_a, question=self.q2)
        UserRequiredQuestion.objects.get_or_create(user=self.user_a, question=self.q3)

        # User B answers q1 only
        UserAnswer.objects.create(
            user=self.user_b, question=self.q1,
            me_answer=3, looking_for_answer=4,
            me_importance=3, looking_for_importance=3,
        )

        pending = self._get_pending_ids(self.user_a, self.user_b)
        self.assertEqual(len(pending), 2, "2 sub-questions should still be pending")
        self.assertNotIn(self.q1.id, pending, "q1 was answered, should not be pending")
        self.assertIn(self.q2.id, pending, "q2 should still be pending")
        self.assertIn(self.q3.id, pending, "q3 should still be pending")

        groups = self._get_pending_group_numbers(pending)
        self.assertEqual(len(groups), 1, "Group should STILL appear as 1 pending entry")
        self.assertEqual(groups[0]['question_number'], 5)

    def test_answer_two_subquestions_one_remains_pending(self):
        """User B answers 2 of 3 — the last one should still be pending."""
        UserRequiredQuestion.objects.get_or_create(user=self.user_a, question=self.q1)
        UserRequiredQuestion.objects.get_or_create(user=self.user_a, question=self.q2)
        UserRequiredQuestion.objects.get_or_create(user=self.user_a, question=self.q3)

        UserAnswer.objects.create(
            user=self.user_b, question=self.q1,
            me_answer=3, looking_for_answer=4,
            me_importance=3, looking_for_importance=3,
        )
        UserAnswer.objects.create(
            user=self.user_b, question=self.q2,
            me_answer=2, looking_for_answer=5,
            me_importance=2, looking_for_importance=4,
        )

        pending = self._get_pending_ids(self.user_a, self.user_b)
        self.assertEqual(len(pending), 1, "1 sub-question should still be pending")
        self.assertIn(self.q3.id, pending)

        groups = self._get_pending_group_numbers(pending)
        self.assertEqual(len(groups), 1, "Group should STILL appear as pending")

    def test_answer_all_subquestions_none_pending(self):
        """User B answers all 3 — the group should disappear from pending."""
        UserRequiredQuestion.objects.get_or_create(user=self.user_a, question=self.q1)
        UserRequiredQuestion.objects.get_or_create(user=self.user_a, question=self.q2)
        UserRequiredQuestion.objects.get_or_create(user=self.user_a, question=self.q3)

        for q in [self.q1, self.q2, self.q3]:
            UserAnswer.objects.create(
                user=self.user_b, question=q,
                me_answer=3, looking_for_answer=3,
                me_importance=3, looking_for_importance=3,
            )

        pending = self._get_pending_ids(self.user_a, self.user_b)
        self.assertEqual(len(pending), 0, "No sub-questions should be pending")

        groups = self._get_pending_group_numbers(pending)
        self.assertEqual(len(groups), 0, "Group should NOT appear in pending")

    def test_only_one_subquestion_required_answering_it_removes_group(self):
        """If User A only marked 1 sub-question required, answering it removes the entire group."""
        # Only q2 is required — not q1 or q3
        UserRequiredQuestion.objects.get_or_create(user=self.user_a, question=self.q2)

        pending_before = self._get_pending_ids(self.user_a, self.user_b)
        self.assertEqual(len(pending_before), 1)
        groups_before = self._get_pending_group_numbers(pending_before)
        self.assertEqual(len(groups_before), 1, "Group appears as 1 pending entry")

        # User B answers q2
        UserAnswer.objects.create(
            user=self.user_b, question=self.q2,
            me_answer=4, looking_for_answer=4,
            me_importance=3, looking_for_importance=3,
        )

        pending_after = self._get_pending_ids(self.user_a, self.user_b)
        self.assertEqual(len(pending_after), 0, "No pending — the only required sub-question was answered")
        groups_after = self._get_pending_group_numbers(pending_after)
        self.assertEqual(len(groups_after), 0, "Group should disappear — nothing pending")

    def test_frontend_optimistic_update_simulation(self):
        """
        Simulate the exact frontend flow:
        1. Load required IDs and answered IDs
        2. Answer one sub-question (optimistic add to answered set)
        3. Recalculate pending
        """
        UserRequiredQuestion.objects.get_or_create(user=self.user_a, question=self.q1)
        UserRequiredQuestion.objects.get_or_create(user=self.user_a, question=self.q2)
        UserRequiredQuestion.objects.get_or_create(user=self.user_a, question=self.q3)

        # Step 1: Initial state (frontend loads this on page open)
        profile_required_ids = set(
            str(qid) for qid in
            UserRequiredQuestion.objects.filter(user=self.user_a)
            .values_list('question_id', flat=True)
        )
        current_user_answered_ids = set(
            str(qid) for qid in
            UserAnswer.objects.filter(user=self.user_b)
            .values_list('question_id', flat=True)
        )

        my_pending = profile_required_ids - current_user_answered_ids
        self.assertEqual(len(my_pending), 3)

        # Step 2: User B answers q1 — optimistic update (frontend adds to set without refetching)
        current_user_answered_ids.add(str(self.q1.id))

        # Step 3: Recalculate pending (frontend useMemo recalculates)
        my_pending_after = profile_required_ids - current_user_answered_ids
        self.assertEqual(len(my_pending_after), 2, "Should still have 2 pending after answering 1")
        self.assertIn(str(self.q2.id), my_pending_after)
        self.assertIn(str(self.q3.id), my_pending_after)

        # Step 4: Group deduplication
        groups = self._get_pending_group_numbers(my_pending_after)
        self.assertEqual(len(groups), 1, "Group should still show as pending")
