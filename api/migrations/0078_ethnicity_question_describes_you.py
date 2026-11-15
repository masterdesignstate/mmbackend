from django.db import migrations

from api.mandatory_questions import ETHNICITY

# The option name is already shown beside the slider. Naming it again
# ("How well does white describe you?") reads as grading that ethnicity.
NEW_TEXT = "What ethnicity best describes you?"
OLD_TEXT = "How strongly do you identify as "


def forwards(apps, schema_editor):
    Question = apps.get_model("api", "Question")
    Question.objects.filter(question_number=ETHNICITY).update(text=NEW_TEXT)


def backwards(apps, schema_editor):
    Question = apps.get_model("api", "Question")
    for question in Question.objects.filter(question_number=ETHNICITY):
        name = (question.question_name or "this ethnicity").strip()
        question.text = f"{OLD_TEXT}{name}?"
        question.save(update_fields=["text"])


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0077_disabled_flags_and_saved_filters"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
