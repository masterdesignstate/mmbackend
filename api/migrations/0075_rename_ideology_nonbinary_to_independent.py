from django.db import migrations
from django.db.models import Q


def rename_nonbinary_to_independent(apps, schema_editor):
    Question = apps.get_model("api", "Question")
    Question.objects.filter(group_name__iexact="Ideology").filter(
        Q(question_name__iexact="Non-binary") | Q(question_name__iexact="Nonbinary")
    ).update(
        question_name="Independent",
        text="How strongly do you identify as independent?",
    )


def restore_independent_to_nonbinary(apps, schema_editor):
    Question = apps.get_model("api", "Question")
    Question.objects.filter(
        group_name__iexact="Ideology",
        question_name="Independent",
        text="How strongly do you identify as independent?",
    ).update(
        question_name="Non-binary",
        text="How strongly do you identify as non-binary?",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0074_bio_3000_question_prompt_notifications"),
    ]

    operations = [
        migrations.RunPython(rename_nonbinary_to_independent, restore_independent_to_nonbinary),
    ]
