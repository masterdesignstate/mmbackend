# Data migration: copy UserAnswer.is_required_for_me=True to UserRequiredQuestion

from django.db import migrations


def migrate_required_to_userrequiredquestion(apps, schema_editor):
    UserAnswer = apps.get_model("api", "UserAnswer")
    UserRequiredQuestion = apps.get_model("api", "UserRequiredQuestion")
    rows = UserAnswer.objects.filter(is_required_for_me=True).values_list("user_id", "question_id")
    created = 0
    for user_id, question_id in rows:
        _, created_this = UserRequiredQuestion.objects.get_or_create(
            user_id=user_id,
            question_id=question_id,
        )
        if created_this:
            created += 1


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0035_userrequiredquestion"),
    ]

    operations = [
        migrations.RunPython(migrate_required_to_userrequiredquestion, noop_reverse),
    ]
