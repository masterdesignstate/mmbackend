"""
Split the Gender, Habits and Kids questions into standalone questions.

Questions 2 (Male/Female), 7 (Alcohol/Cigarettes/Vape) and 10 (Have/Want kids) each packed
several sub-questions behind one ``question_number``, which is what forced the onboarding
page to label every slider row. This command gives each sub-question its own number, so the
mandatory block becomes 1..14 and everything optional shifts up by four.

``UserAnswer`` rows point at ``Question.id``, so no answer is touched or lost — only the
ordering numbers change.

    python manage.py split_mandatory_questions --dry-run
    python manage.py split_mandatory_questions
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F, Max

from api import mandatory_questions as mq
from api.models import Question, QuestionNumberCounter

SHIFT = 4
OLD_LAST_MANDATORY = 10
# The block as this split left it. Frozen rather than read from `mq`: Faith and Ideology
# joined the mandatory block afterwards, and a re-run must still recognise a split database.
SPLIT_LAST_MANDATORY = OLD_LAST_MANDATORY + SHIFT

# (old question_number, old group_number) -> new number. group_number None means the
# question was already standalone.
RENUMBER = {
    (1, None): mq.RELATIONSHIP,      # Relationship keeps its four grouped sub-questions
    (2, 2): mq.FEMALE,
    (2, 1): mq.MALE,
    (3, None): mq.ETHNICITY,
    (4, None): mq.EDUCATION,
    (5, None): mq.DIET,
    (6, None): mq.EXERCISE,
    (7, 1): mq.ALCOHOL,
    (7, 2): mq.CIGARETTES,
    (7, 3): mq.VAPE,
    (8, None): mq.RELIGION,
    (9, None): mq.POLITICS,
    (10, 2): mq.WANT_KIDS,
    (10, 1): mq.HAVE_KIDS,
}

# The split questions stop being grouped: they lose their group_number and take a
# group_name of their own so the onboarding title reads "8. Alcohol". Their
# group_name_text is cleared too -- it held the old group-level prompt ("What are your
# thoughts on kids?"), which surfaces as the subtitle and no longer describes one
# question. Standalone questions like Exercise already carry an empty one.
SPLIT = {
    mq.FEMALE: ('Female', 'Female'),
    mq.MALE: ('Male', 'Male'),
    mq.ALCOHOL: ('Alcohol', 'Alcohol'),
    mq.CIGARETTES: ('Cigarettes', 'Cigarettes'),
    mq.VAPE: ('Vape', 'Vape'),
    mq.WANT_KIDS: ('Want Kids', 'Want Kids'),
    mq.HAVE_KIDS: ('Have Kids', 'Have Kids'),
}


class Command(BaseCommand):
    help = 'Split questions 2/7/10 into standalone questions and renumber 1..14 + optional +4'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report what would change without writing anything.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        distinct_mandatory = (
            Question.objects.filter(is_mandatory=True)
            .values('question_number')
            .distinct()
            .count()
        )
        if distinct_mandatory >= SPLIT_LAST_MANDATORY:
            self.stdout.write(self.style.WARNING(
                'Already split: mandatory questions occupy '
                f'{distinct_mandatory} distinct numbers. Nothing to do.'
            ))
            return
        if distinct_mandatory != OLD_LAST_MANDATORY:
            raise CommandError(
                f'Expected {OLD_LAST_MANDATORY} distinct mandatory numbers before the split, '
                f'found {distinct_mandatory}. Refusing to renumber a database in an '
                'unexpected shape.'
            )

        stray = Question.objects.filter(is_mandatory=False, question_number__lte=OLD_LAST_MANDATORY)
        if stray.exists():
            raise CommandError(
                f'{stray.count()} optional question(s) sit at number <= {OLD_LAST_MANDATORY}. '
                'They would collide with the new mandatory block; fix them first.'
            )

        # Resolve every mandatory question to its new number before writing, so a bad
        # mapping fails loudly instead of half-renumbering the table.
        planned = []
        for question in Question.objects.filter(is_mandatory=True).order_by('question_number', 'group_number'):
            key = (question.question_number, question.group_number)
            new_number = RENUMBER.get(key, RENUMBER.get((question.question_number, None)))
            if new_number is None:
                raise CommandError(
                    f'No mapping for mandatory question {question.question_number}'
                    f'/{question.group_number} ({question.question_name!r}).'
                )
            planned.append((question, new_number))

        to_shift = Question.objects.filter(question_number__gt=OLD_LAST_MANDATORY).count()

        self.stdout.write(f'Mandatory questions to renumber: {len(planned)}')
        self.stdout.write(f'Optional questions to shift by +{SHIFT}: {to_shift}')
        for question, new_number in planned:
            split_note = ' (split off)' if new_number in SPLIT else ''
            self.stdout.write(
                f'  {question.question_number}/{question.group_number} '
                f'{question.question_name!r} -> {new_number}{split_note}'
            )

        if dry_run:
            self.stdout.write(self.style.WARNING('Dry run: nothing written.'))
            return

        with transaction.atomic():
            # Park the mandatory rows above every optional number so neither pass can
            # collide with the other while both are mid-flight.
            # Max(), not order_by('-question_number').first(): Postgres sorts NULLs first
            # on a DESC ordering, so questions awaiting approval (question_number NULL)
            # would make the offset 0 and the shift below would skip most of the table.
            highest = Question.objects.aggregate(highest=Max('question_number'))['highest'] or 0
            parking_offset = highest + SHIFT + 100
            for question, new_number in planned:
                Question.objects.filter(pk=question.pk).update(
                    question_number=parking_offset + new_number
                )

            Question.objects.filter(
                question_number__gt=OLD_LAST_MANDATORY,
                question_number__lt=parking_offset,
            ).update(question_number=F('question_number') + SHIFT)

            for question, new_number in planned:
                fields = {'question_number': new_number}
                if new_number in SPLIT:
                    question_name, group_name = SPLIT[new_number]
                    fields.update(
                        question_name=question_name,
                        group_name=group_name,
                        group_name_text='',
                        group_number=None,
                        question_type='basic',
                    )
                Question.objects.filter(pk=question.pk).update(**fields)

            counter = QuestionNumberCounter.get_or_create_counter()
            QuestionNumberCounter.objects.filter(pk=counter.pk).update(
                last_number=F('last_number') + SHIFT
            )

        self.stdout.write(self.style.SUCCESS(
            f'Split complete: mandatory questions now 1..{SPLIT_LAST_MANDATORY}, '
            f'{to_shift} optional questions shifted to {SPLIT_LAST_MANDATORY + 1}+.'
        ))
