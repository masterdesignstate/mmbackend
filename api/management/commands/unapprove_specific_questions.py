from django.core.management.base import BaseCommand
from api.models import Question


class Command(BaseCommand):
    help = 'Unapproves specific questions by their text'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # List of question texts to unapprove
        questions_to_unapprove = [
            'How much do you like cowboys?',
            'How much do you like gingers?',
            'How much do you like cars?',
            'How much do you like horses?',
            'How much do you like rivers?',
            'Do you have a sweet tooth?',
            'Do you like living in the city?',
            'Do you like living in the US?',
            'Will you ever move to europe?',
            'How much do you like animals?',
            'How good is this website',
            'How much do you care about fitness?',
        ]

        self.stdout.write(f'\n📋 Looking for {len(questions_to_unapprove)} questions to unapprove...\n')

        # Find questions matching the text
        found_questions = []
        not_found = []

        for question_text in questions_to_unapprove:
            # Try exact match first
            question = Question.objects.filter(text=question_text).first()

            if question:
                found_questions.append(question)
                self.stdout.write(f'  ✓ Found: "{question_text}" (Q#{question.question_number}, approved={question.is_approved})')
            else:
                not_found.append(question_text)
                self.stdout.write(self.style.WARNING(f'  ✗ Not found: "{question_text}"'))

        self.stdout.write(f'\n📊 Summary:')
        self.stdout.write(f'   Found: {len(found_questions)} questions')
        self.stdout.write(f'   Not found: {len(not_found)} questions')

        if len(not_found) > 0:
            self.stdout.write(self.style.WARNING(f'\n⚠️  Could not find {len(not_found)} questions in the database'))
            self.stdout.write(self.style.WARNING(f'   They may have different text or may not exist.'))

        if len(found_questions) == 0:
            self.stdout.write(self.style.WARNING('\n⚠️  No questions found to unapprove'))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING(f'\n🔍 DRY RUN MODE - No changes will be made\n'))
            self.stdout.write(f'Would unapprove these {len(found_questions)} questions:')
            for question in found_questions:
                status = "already unapproved" if not question.is_approved else "will be unapproved"
                self.stdout.write(f'   - Q#{question.question_number}: {question.text[:60]}... ({status})')
        else:
            self.stdout.write(f'\n🔄 Unapproving {len(found_questions)} questions...')

            # Update each question
            updated_count = 0
            for question in found_questions:
                if question.is_approved:
                    question.is_approved = False
                    question.save()
                    updated_count += 1
                    self.stdout.write(f'  ✓ Unapproved: Q#{question.question_number} - {question.text[:50]}...')
                else:
                    self.stdout.write(f'  - Already unapproved: Q#{question.question_number} - {question.text[:50]}...')

            self.stdout.write(self.style.SUCCESS(f'\n✅ Successfully unapproved {updated_count} questions!'))

            if updated_count < len(found_questions):
                self.stdout.write(f'   ({len(found_questions) - updated_count} were already unapproved)')

            # Show final counts
            total_approved = Question.objects.filter(is_approved=True).count()
            total_unapproved = Question.objects.filter(is_approved=False).count()
            self.stdout.write(f'\n📊 Current status:')
            self.stdout.write(f'   Approved questions: {total_approved}')
            self.stdout.write(f'   Unapproved questions: {total_unapproved}\n')
