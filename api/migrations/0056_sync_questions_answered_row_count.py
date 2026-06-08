from django.db import migrations
from django.db.models import Count


def sync_questions_answered_row_count(apps, schema_editor):
    User = apps.get_model('api', 'User')
    UserAnswer = apps.get_model('api', 'UserAnswer')

    answer_counts = dict(
        UserAnswer.objects
        .values('user_id')
        .annotate(total=Count('id'))
        .values_list('user_id', 'total')
    )

    for user in User.objects.all().only('id', 'questions_answered_count').iterator():
        actual_count = answer_counts.get(user.id, 0)
        if user.questions_answered_count != actual_count:
            User.objects.filter(id=user.id).update(questions_answered_count=actual_count)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0055_sync_questions_answered_count'),
    ]

    operations = [
        migrations.RunPython(sync_questions_answered_row_count, noop_reverse),
    ]
