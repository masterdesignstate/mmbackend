# Data migration: set is_required_for_me=True where question.is_required_for_match=True

from django.db import migrations


def set_required_for_me_from_question(apps, schema_editor):
    UserAnswer = apps.get_model("api", "UserAnswer")
    Question = apps.get_model("api", "Question")
    required_question_ids = set(
        Question.objects.filter(is_required_for_match=True).values_list("id", flat=True)
    )
    if not required_question_ids:
        return
    updated = UserAnswer.objects.filter(
        question_id__in=required_question_ids,
        is_required_for_me=False,
    ).update(is_required_for_me=True)
    # No need to print in migration; optional: pass through RunPython


def noop_reverse(apps, schema_editor):
    pass  # No reverse: we don't want to clear is_required_for_me on rollback


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0033_useranswer_is_required_for_me"),
    ]

    operations = [
        migrations.RunPython(set_required_for_me_from_question, noop_reverse),
    ]
