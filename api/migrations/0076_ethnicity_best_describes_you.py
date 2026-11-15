from django.db import migrations

from api.mandatory_questions import ETHNICITY

NEW_PROMPT = "What ethnicity best describes you?"
OLD_PROMPT = "What ethnicity do you identify with?"


def forwards(apps, schema_editor):
    Question = apps.get_model("api", "Question")
    Question.objects.filter(question_number=ETHNICITY).update(group_name_text=NEW_PROMPT)


def backwards(apps, schema_editor):
    Question = apps.get_model("api", "Question")
    Question.objects.filter(question_number=ETHNICITY).update(group_name_text=OLD_PROMPT)


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0075_rename_ideology_nonbinary_to_independent"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
