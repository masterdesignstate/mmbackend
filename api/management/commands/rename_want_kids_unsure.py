"""Set the middle Want Kids answer (value 3) to "Open".

The frontend renders this caption from `WANT_KIDS_ANSWER_LABELS`. The stored
`QuestionAnswer.answer_text` is what the admin question editor reads, so it has to match or
the two disagree — it previously read "Unsure".

Idempotent: rows already reading "Open" are left alone, so a second run does nothing.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from api.mandatory_questions import WANT_KIDS
from api.models import QuestionAnswer

NEW_TEXT = 'Open'
ANSWER_VALUE = '3'


class Command(BaseCommand):
    help = 'Rename the Want Kids answer to "Open".'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report what would change without writing.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        rows = QuestionAnswer.objects.filter(
            question__question_number=WANT_KIDS,
            value=ANSWER_VALUE,
        ).select_related('question')

        if not rows:
            self.stdout.write(self.style.WARNING(
                f'No answer rows found for question {WANT_KIDS}, value {ANSWER_VALUE}.'
            ))
            return

        to_change = []
        for row in rows:
            state = 'already renamed' if row.answer_text == NEW_TEXT else 'will change'
            if row.answer_text != NEW_TEXT:
                to_change.append(row)
            self.stdout.write(
                f'  question {row.question.question_number} '
                f'({row.question.question_name or row.question.text[:40]!r}) '
                f'value {row.value}: {row.answer_text!r} -- {state}'
            )

        if not to_change:
            self.stdout.write(self.style.SUCCESS('Nothing to do; already up to date.'))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'Dry run: {len(to_change)} row(s) would become {NEW_TEXT!r}.'
            ))
            return

        with transaction.atomic():
            updated = 0
            for row in to_change:
                row.answer_text = NEW_TEXT
                row.save(update_fields=['answer_text', 'updated_at'])
                updated += 1

        self.stdout.write(self.style.SUCCESS(
            f'Updated {updated} row(s) to {NEW_TEXT!r}.'
        ))
