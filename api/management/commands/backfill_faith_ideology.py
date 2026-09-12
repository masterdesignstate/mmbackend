"""
Make Faith (15) and Ideology (16) mandatory, filling them in for every account first.

A missing mandatory answer filters an account out of Results. Faith and Ideology were optional
until now, so flipping the flag on its own would have hidden nearly every account. In one
transaction this command:

1. creates generated answers (see ``api/services/faith_ideology_answers.py``) for each account
   that has not answered a question — an account that answered any of its options keeps its own;
2. marks every Faith/Ideology answer required for its owner, as saving a mandatory answer does;
3. refreshes ``questions_answered_count`` on every account it touched;
4. sets ``is_mandatory`` and ``is_required_for_match`` on both questions.

Afterwards it queues compatibility recalculation for the touched accounts, which
``calculate_missing_compatibilities`` works through. Re-running finds nothing left to do.

    python manage.py backfill_faith_ideology            # dry run, writes nothing
    python manage.py backfill_faith_ideology --commit
"""

import contextlib
import io
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce

from api.models import Question, User, UserAnswer, UserRequiredQuestion
from api.services.faith_ideology_answers import GENERATED_QUESTION_NUMBERS, plan_generated_answers

DEFAULT_SEED = 20260911
BATCH_SIZE = 1000
# Matches what import_dummy_users writes for mandatory answers.
DEFAULT_IMPORTANCE = 3


class Command(BaseCommand):
    help = 'Backfill Faith/Ideology answers for every account, then make both questions mandatory.'

    def add_arguments(self, parser):
        parser.add_argument('--commit', action='store_true', help='Write the changes. Without it nothing is written.')
        parser.add_argument('--seed', type=int, default=DEFAULT_SEED)
        parser.add_argument(
            '--skip-recalculation', action='store_true',
            help='Do not queue compatibility recalculation for the accounts that changed.',
        )

    def handle(self, *args, **options):
        seed = options['seed']

        questions_by_number = defaultdict(list)
        for question in Question.objects.filter(question_number__in=GENERATED_QUESTION_NUMBERS):
            questions_by_number[question.question_number].append(question)
        missing = [number for number in GENERATED_QUESTION_NUMBERS if not questions_by_number[number]]
        if missing:
            raise CommandError(f'No questions found for number(s) {missing}; refusing to continue.')

        answered_numbers = defaultdict(set)
        existing_answers = UserAnswer.objects.filter(question__question_number__in=GENERATED_QUESTION_NUMBERS)
        for user_id, number in existing_answers.values_list('user_id', 'question__question_number').distinct():
            answered_numbers[user_id].add(number)

        accounts = list(User.objects.order_by('date_joined').values_list('id', 'is_dummy'))
        planned = []
        touched = set()
        real_touched = set()
        to_fill = Counter()
        primary_mix = defaultdict(Counter)
        strength_mix = Counter()
        for user_id, is_dummy in accounts:
            for number in GENERATED_QUESTION_NUMBERS:
                if number in answered_numbers[user_id]:
                    continue
                plan = plan_generated_answers(str(user_id), number, questions_by_number[number], seed)
                planned.extend((user_id, answer) for answer in plan)
                to_fill[number] += 1
                touched.add(user_id)
                if not is_dummy:
                    real_touched.add(user_id)
                primary = next(answer for answer in plan if answer.is_primary)
                primary_mix[number][primary.question.question_name] += 1
                strength_mix[primary.me_answer] += 1

        required_pairs = set(existing_answers.values_list('user_id', 'question_id'))
        required_pairs.update((user_id, answer.question.pk) for user_id, answer in planned)
        already_required = set(
            UserRequiredQuestion.objects.filter(question__question_number__in=GENERATED_QUESTION_NUMBERS)
            .values_list('user_id', 'question_id')
        )
        new_required = required_pairs - already_required

        question_rows = Question.objects.filter(question_number__in=GENERATED_QUESTION_NUMBERS)
        rows_to_flag = question_rows.filter(Q(is_mandatory=False) | Q(is_required_for_match=False)).count()

        dummy_count = sum(1 for _, is_dummy in accounts if is_dummy)
        self.stdout.write(f'Faith/Ideology backfill plan (seed {seed})')
        self.stdout.write(f'  Accounts: {len(accounts)} ({dummy_count} dummy, {len(accounts) - dummy_count} real)')
        for number in GENERATED_QUESTION_NUMBERS:
            name = questions_by_number[number][0].group_name or f'Question {number}'
            self.stdout.write(
                f'  {name} ({number}): {to_fill[number]} accounts to fill, '
                f'{len(accounts) - to_fill[number]} already answered, '
                f'{len(questions_by_number[number])} options each'
            )
        self.stdout.write(f'  Accounts touched: {len(touched)} ({len(real_touched)} real)')
        self.stdout.write(f'  Answers to create: {len(planned)}')
        self.stdout.write(f'  Required-question rows to add: {len(new_required)}')
        self.stdout.write(f'  Question rows to mark mandatory: {rows_to_flag} of {question_rows.count()}')
        for number in GENERATED_QUESTION_NUMBERS:
            mix = ', '.join(f'{name} {count}' for name, count in primary_mix[number].most_common())
            self.stdout.write(f'  Primary picks for {number}: {mix or "none"}')
        if strength_mix:
            self.stdout.write(
                '  Primary strengths: ' + ', '.join(f'{value}: {strength_mix[value]}' for value in sorted(strength_mix))
            )

        if not options['commit']:
            self.stdout.write(self.style.WARNING('Dry run: nothing written. Re-run with --commit to apply.'))
            return

        with transaction.atomic():
            UserAnswer.objects.bulk_create(
                [
                    UserAnswer(
                        user_id=user_id,
                        question=answer.question,
                        me_answer=answer.me_answer,
                        me_open_to_all=False,
                        me_importance=DEFAULT_IMPORTANCE,
                        me_share=True,
                        looking_for_answer=answer.looking_for_answer,
                        looking_for_open_to_all=answer.looking_for_open_to_all,
                        looking_for_importance=DEFAULT_IMPORTANCE,
                        looking_for_share=True,
                        excluded_answer_values=[],
                    )
                    for user_id, answer in planned
                ],
                batch_size=BATCH_SIZE,
            )
            UserRequiredQuestion.objects.bulk_create(
                [UserRequiredQuestion(user_id=user_id, question_id=question_id) for user_id, question_id in new_required],
                batch_size=BATCH_SIZE,
                ignore_conflicts=True,
            )
            if touched:
                answer_count = (
                    UserAnswer.objects.filter(user=OuterRef('pk'))
                    .values('user').annotate(total=Count('id')).values('total')
                )
                User.objects.filter(id__in=touched).update(
                    questions_answered_count=Coalesce(Subquery(answer_count), Value(0))
                )
            question_rows.update(is_mandatory=True, is_required_for_match=True)

        self.stdout.write(self.style.SUCCESS(
            f'Created {len(planned)} answers for {len(touched)} accounts, added {len(new_required)} '
            f'required-question rows, and marked Faith and Ideology mandatory.'
        ))

        if options['skip_recalculation'] or not touched:
            return

        from api.services.compatibility_queue import enqueue_user_for_recalculation

        queued = 0
        # enqueue_user_for_recalculation prints a line per account; keep this command's output readable.
        with contextlib.redirect_stdout(io.StringIO()):
            for user in User.objects.filter(id__in=touched, is_banned=False).iterator():
                if not enqueue_user_for_recalculation(user).skipped:
                    queued += 1
        self.stdout.write(
            f'Queued compatibility recalculation for {queued} accounts '
            '(processed by calculate_missing_compatibilities).'
        )
