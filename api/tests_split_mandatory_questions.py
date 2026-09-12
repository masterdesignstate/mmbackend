from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from api import mandatory_questions as mq
from api.management.commands.split_mandatory_questions import SPLIT_LAST_MANDATORY
from api.models import Question, QuestionNumberCounter, User, UserAnswer


class SplitMandatoryQuestionsTests(TestCase):
    """The one-off renumber that turned questions 2/7/10 into standalone questions."""

    def make_question(self, number, group_number=None, name='Q', mandatory=True, qtype='basic',
                      group_name_text=''):
        return Question.objects.create(
            question_number=number,
            group_number=group_number,
            question_name=name,
            question_type=qtype,
            group_name_text=group_name_text,
            text=f'{name}?',
            is_mandatory=mandatory,
            is_approved=True,
        )

    def setUp(self):
        # A migration seeds the singleton counter, so update rather than create it.
        QuestionNumberCounter.objects.update_or_create(id=1, defaults={'last_number': 12})

        # The pre-split shape: 10 mandatory numbers, three of them grouped.
        for group, name in [(1, 'Friend'), (2, 'Hookup'), (3, 'Date'), (4, 'Partner')]:
            self.make_question(1, group, name, qtype='four')
        self.male = self.make_question(2, 1, 'Male', qtype='double')
        self.female = self.make_question(2, 2, 'Female', qtype='double')
        for group, name in [(1, 'White'), (2, 'Black')]:
            self.make_question(3, group, name, qtype='grouped')
        self.make_question(4, 1, 'High School', qtype='grouped')
        self.make_question(5, 1, 'Omnivore', qtype='grouped')
        self.exercise = self.make_question(6, None, 'Exercise')
        self.alcohol = self.make_question(7, 1, 'Alcohol', qtype='triple')
        self.cigarettes = self.make_question(7, 2, 'Cigarettes', qtype='triple')
        self.vape = self.make_question(7, 3, 'Vape', qtype='triple')
        self.religion = self.make_question(8, None, 'Religion')
        self.politics = self.make_question(9, None, 'Politics')
        self.have_kids = self.make_question(
            10, 1, 'Have', qtype='double', group_name_text='What are your thoughts on kids?'
        )
        self.want_kids = self.make_question(
            10, 2, 'Want', qtype='double', group_name_text='What are your thoughts on kids?'
        )

        self.faith = self.make_question(11, 1, 'Christian', mandatory=False, qtype='grouped')
        self.bonus = self.make_question(12, None, 'Horses', mandatory=False)

        self.user = User.objects.create_user(username='u', email='u@example.com', password='pw')
        self.answer = UserAnswer.objects.create(
            user=self.user, question=self.female, me_answer=5, looking_for_answer=3
        )

    def test_renumbers_mandatory_block_and_shifts_optional(self):
        call_command('split_mandatory_questions')

        self.male.refresh_from_db()
        self.female.refresh_from_db()
        self.alcohol.refresh_from_db()
        self.cigarettes.refresh_from_db()
        self.vape.refresh_from_db()
        self.have_kids.refresh_from_db()
        self.want_kids.refresh_from_db()
        self.exercise.refresh_from_db()
        self.religion.refresh_from_db()
        self.politics.refresh_from_db()
        self.faith.refresh_from_db()
        self.bonus.refresh_from_db()

        self.assertEqual(self.female.question_number, mq.FEMALE)
        self.assertEqual(self.male.question_number, mq.MALE)
        self.assertEqual(self.exercise.question_number, mq.EXERCISE)
        self.assertEqual(self.alcohol.question_number, mq.ALCOHOL)
        self.assertEqual(self.cigarettes.question_number, mq.CIGARETTES)
        self.assertEqual(self.vape.question_number, mq.VAPE)
        self.assertEqual(self.religion.question_number, mq.RELIGION)
        self.assertEqual(self.politics.question_number, mq.POLITICS)
        self.assertEqual(self.want_kids.question_number, mq.WANT_KIDS)
        self.assertEqual(self.have_kids.question_number, mq.HAVE_KIDS)

        self.assertEqual(self.faith.question_number, mq.FAITH)
        self.assertEqual(self.bonus.question_number, mq.IDEOLOGY)

        self.assertEqual(
            Question.objects.filter(is_mandatory=True).values('question_number').distinct().count(),
            SPLIT_LAST_MANDATORY,
        )

    def test_split_questions_stop_being_grouped(self):
        call_command('split_mandatory_questions')

        for question in (self.male, self.female, self.alcohol, self.vape, self.have_kids):
            question.refresh_from_db()
            self.assertIsNone(question.group_number)
            self.assertEqual(question.question_type, 'basic')

        self.have_kids.refresh_from_db()
        self.want_kids.refresh_from_db()
        self.assertEqual(self.have_kids.question_name, 'Have Kids')
        self.assertEqual(self.want_kids.question_name, 'Want Kids')

        # The group-level prompt described all the rows at once, so it must not survive as
        # a standalone question's subtitle.
        self.assertEqual(self.have_kids.group_name_text, '')
        self.assertEqual(self.want_kids.group_name_text, '')

    def test_no_number_collides_and_answers_survive(self):
        call_command('split_mandatory_questions')

        numbers = list(
            Question.objects.exclude(question_number__isnull=True)
            .values_list('question_number', 'group_number')
        )
        self.assertEqual(len(numbers), len(set(numbers)), 'a number/group pair was duplicated')

        self.answer.refresh_from_db()
        self.assertEqual(self.answer.question_id, self.female.id)
        self.assertEqual(self.answer.me_answer, 5)

    def test_counter_leaves_room_for_the_shifted_numbers(self):
        call_command('split_mandatory_questions')

        counter = QuestionNumberCounter.objects.get(pk=1)
        self.assertEqual(counter.last_number, 16)
        self.assertGreaterEqual(
            counter.last_number,
            Question.objects.order_by('-question_number').values_list('question_number', flat=True).first(),
        )

    def test_running_twice_is_a_no_op(self):
        call_command('split_mandatory_questions')
        call_command('split_mandatory_questions')

        self.female.refresh_from_db()
        self.faith.refresh_from_db()
        self.assertEqual(self.female.question_number, mq.FEMALE)
        self.assertEqual(self.faith.question_number, mq.FAITH)

    def test_dry_run_writes_nothing(self):
        call_command('split_mandatory_questions', '--dry-run')

        self.female.refresh_from_db()
        self.faith.refresh_from_db()
        self.assertEqual(self.female.question_number, 2)
        self.assertEqual(self.female.group_number, 2)
        self.assertEqual(self.faith.question_number, 11)

    def test_shifts_every_optional_question_even_with_unnumbered_questions(self):
        """A question awaiting approval has question_number NULL. Postgres sorts NULLs
        first on a DESC ordering, so deriving the parking offset that way once produced 0
        and left most of the table unshifted."""
        self.make_question(None, None, 'Awaiting approval', mandatory=False)
        high = self.make_question(400, None, 'High', mandatory=False)

        call_command('split_mandatory_questions')

        self.faith.refresh_from_db()
        self.bonus.refresh_from_db()
        high.refresh_from_db()
        self.assertEqual(self.faith.question_number, mq.FAITH)
        self.assertEqual(self.bonus.question_number, mq.IDEOLOGY)
        self.assertEqual(high.question_number, 404)

        numbers = list(
            Question.objects.exclude(question_number__isnull=True)
            .values_list('question_number', 'group_number')
        )
        self.assertEqual(len(numbers), len(set(numbers)), 'a number/group pair was duplicated')

    def test_refuses_when_an_optional_question_sits_in_the_mandatory_block(self):
        self.make_question(9, None, 'Stray', mandatory=False)

        with self.assertRaises(CommandError):
            call_command('split_mandatory_questions')
