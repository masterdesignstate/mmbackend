from django.db import migrations

from api.mandatory_questions import ETHNICITY

NEW_TEXT = "What ethnicity best describes you?"


def forwards(apps, schema_editor):
    Question = apps.get_model("api", "Question")
    Question.objects.filter(question_number=ETHNICITY).update(text=NEW_TEXT)


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0078_ethnicity_question_describes_you"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
