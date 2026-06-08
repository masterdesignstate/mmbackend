from django.db import migrations


def sync_questions_answered_count(apps, schema_editor):
    User = apps.get_model('api', 'User')
    UserAnswer = apps.get_model('api', 'UserAnswer')

    for user in User.objects.all().only('id', 'questions_answered_count').iterator():
        actual_count = (
            UserAnswer.objects
            .filter(user_id=user.id, question__question_number__isnull=False)
            .values('question__question_number')
            .distinct()
            .count()
        )
        if user.questions_answered_count != actual_count:
            User.objects.filter(id=user.id).update(questions_answered_count=actual_count)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0054_reconcile_restriction_history'),
    ]

    operations = [
        migrations.RunPython(sync_questions_answered_count, noop_reverse),
    ]
