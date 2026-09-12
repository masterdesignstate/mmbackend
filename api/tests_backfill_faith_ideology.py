from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from api import mandatory_questions as mq
from api.models import Question, QuestionAnswer, User, UserAnswer, UserRequiredQuestion
from api.services.faith_ideology_answers import OPEN_TO_ALL_ANSWER, plan_generated_answers


class BackfillFaithIdeologyTests(TestCase):
    def make_grouped(self, number, group_name, names):
        rows = []
        for group_number, name in enumerate(names, start=1):
            question = Question.objects.create(
                question_number=number, group_number=group_number, question_name=name,
                group_name=group_name, question_type='grouped', text=f'{name}?', is_approved=True,
            )
            for value in (1, 5):
                QuestionAnswer.objects.create(question=question, value=str(value), answer_text=str(value))
            rows.append(question)
        return rows

    def setUp(self):
        self.faith = self.make_grouped(mq.FAITH, 'Faith', ['Christian', 'Atheist', 'Hindu'])
        self.ideology = self.make_grouped(mq.IDEOLOGY, 'Ideology', ['Left', 'Right'])
        self.fresh = User.objects.create_user(username='fresh', email='fresh@test.com', password='pw', is_dummy=True)
        self.partial = User.objects.create_user(username='partial', email='partial@test.com', password='pw', is_dummy=True)
        self.real = User.objects.create_user(username='real', email='real@test.com', password='pw', is_dummy=False)
        self.kept = UserAnswer.objects.create(user=self.partial, question=self.faith[1], me_answer=4, looking_for_answer=2)

    def run_command(self, *args):
        out = StringIO()
        call_command('backfill_faith_ideology', *args, '--skip-recalculation', stdout=out)
        return out.getvalue()

    def answers(self, user, number):
        return list(UserAnswer.objects.filter(user=user, question__question_number=number))

    def test_dry_run_writes_nothing(self):
        output = self.run_command()

        self.assertIn('Dry run', output)
        # fresh and real: 3 Faith + 2 Ideology each; partial keeps its Faith answer, gets 2 Ideology.
        self.assertIn('Answers to create: 12', output)
        self.assertEqual(UserAnswer.objects.count(), 1)
        self.assertFalse(UserRequiredQuestion.objects.exists())
        self.assertFalse(Question.objects.filter(is_mandatory=True).exists())

    def test_commit_fills_every_account_and_makes_both_questions_mandatory(self):
        self.run_command('--commit')

        for user in (self.fresh, self.real):
            for number, rows in ((mq.FAITH, self.faith), (mq.IDEOLOGY, self.ideology)):
                answers = self.answers(user, number)
                self.assertEqual(len(answers), len(rows))
                primaries = [a for a in answers if a.me_answer != 1]
                self.assertEqual(len(primaries), 1)
                self.assertIn(primaries[0].me_answer, (3, 4, 5))
                for answer in answers:
                    self.assertEqual(answer.looking_for_answer, OPEN_TO_ALL_ANSWER)
                    self.assertTrue(answer.looking_for_open_to_all)

        # An account that answered any Faith option keeps exactly what it gave.
        partial_faith = self.answers(self.partial, mq.FAITH)
        self.assertEqual([(a.pk, a.me_answer) for a in partial_faith], [(self.kept.pk, 4)])
        self.assertEqual(len(self.answers(self.partial, mq.IDEOLOGY)), len(self.ideology))

        for answer in UserAnswer.objects.all():
            self.assertTrue(UserRequiredQuestion.objects.filter(user=answer.user, question=answer.question).exists())
        self.assertFalse(Question.objects.filter(is_mandatory=False).exists())
        self.assertFalse(Question.objects.filter(is_required_for_match=False).exists())

        self.fresh.refresh_from_db()
        self.partial.refresh_from_db()
        self.assertEqual(self.fresh.questions_answered_count, 5)
        self.assertEqual(self.partial.questions_answered_count, 3)

    def test_rerun_finds_nothing_to_do(self):
        self.run_command('--commit')
        answer_count = UserAnswer.objects.count()

        output = self.run_command('--commit')

        self.assertIn('Answers to create: 0', output)
        self.assertEqual(UserAnswer.objects.count(), answer_count)

    def test_queues_recalculation_without_failing(self):
        out = StringIO()
        call_command('backfill_faith_ideology', '--commit', stdout=out)
        self.assertIn('Queued compatibility recalculation', out.getvalue())

    def test_plan_is_stable_for_an_account(self):
        first = plan_generated_answers('account-1', mq.FAITH, self.faith, seed=7)
        second = plan_generated_answers('account-1', mq.FAITH, list(reversed(self.faith)), seed=7)
        self.assertEqual(
            [(a.question.pk, a.me_answer) for a in first],
            [(a.question.pk, a.me_answer) for a in second],
        )
