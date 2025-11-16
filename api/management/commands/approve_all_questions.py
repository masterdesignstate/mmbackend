from django.core.management.base import BaseCommand
from api.models import Question


class Command(BaseCommand):
    help = 'Marks all questions in the database as approved'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # Get all questions that are not approved
        unapproved_questions = Question.objects.filter(is_approved=False)
        total_unapproved = unapproved_questions.count()

        # Get total questions count
        total_questions = Question.objects.count()

        self.stdout.write(f'\n📊 Question Status:')
        self.stdout.write(f'   Total questions: {total_questions}')
        self.stdout.write(f'   Already approved: {total_questions - total_unapproved}')
        self.stdout.write(f'   Need approval: {total_unapproved}\n')

        if total_unapproved == 0:
            self.stdout.write(self.style.SUCCESS('✅ All questions are already approved!'))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING(f'\n🔍 DRY RUN MODE - No changes will be made\n'))
            self.stdout.write(f'Would approve {total_unapproved} questions:')
            for question in unapproved_questions[:10]:  # Show first 10
                self.stdout.write(f'   - Question #{question.question_number}: {question.text[:60]}...')
            if total_unapproved > 10:
                self.stdout.write(f'   ... and {total_unapproved - 10} more\n')
        else:
            self.stdout.write(f'\n🔄 Approving {total_unapproved} questions...')

            # Update all unapproved questions
            updated_count = unapproved_questions.update(is_approved=True)

            self.stdout.write(self.style.SUCCESS(f'\n✅ Successfully approved {updated_count} questions!'))

            # Verify the update
            remaining_unapproved = Question.objects.filter(is_approved=False).count()
            if remaining_unapproved == 0:
                self.stdout.write(self.style.SUCCESS('✅ All questions are now approved!\n'))
            else:
                self.stdout.write(self.style.WARNING(f'⚠️  Warning: {remaining_unapproved} questions still not approved\n'))
