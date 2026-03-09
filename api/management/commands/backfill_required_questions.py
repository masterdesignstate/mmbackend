from django.core.management.base import BaseCommand
from api.models import User, Question, UserAnswer, UserRequiredQuestion


class Command(BaseCommand):
    help = 'Backfill UserRequiredQuestion for all mandatory questions answered by users'

    def handle(self, *args, **options):
        mandatory_questions = Question.objects.filter(is_mandatory=True)
        mandatory_ids = set(mandatory_questions.values_list('id', flat=True))
        self.stdout.write(f'Found {len(mandatory_ids)} mandatory questions')

        users = User.objects.all()
        created_count = 0
        users_updated = 0

        for user in users:
            answered_mandatory_ids = set(
                UserAnswer.objects.filter(
                    user=user, question_id__in=mandatory_ids
                ).values_list('question_id', flat=True)
            )

            user_created = 0
            for q_id in answered_mandatory_ids:
                _, created = UserRequiredQuestion.objects.get_or_create(
                    user=user, question_id=q_id
                )
                if created:
                    created_count += 1
                    user_created += 1

            if user_created > 0:
                users_updated += 1

        self.stdout.write(self.style.SUCCESS(
            f'Created {created_count} UserRequiredQuestion records for {users_updated} users'
        ))
