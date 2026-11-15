from django.db import migrations

from api.mandatory_questions import ETHNICITY

# The phrase that fills "To what extent does {phrase} describe you?"
PHRASES = {
    "White": "white",
    "Black": "Black or African descent",
    "Native": "Native American",
    "Hispanic": "Hispanic/Latino",
    "Asian": "Asian",
    "Other": "another ethnicity",
    "Hawaiian": "another ethnicity",
}


def forwards(apps, schema_editor):
    Question = apps.get_model("api", "Question")
    for question in Question.objects.filter(question_number=ETHNICITY):
        phrase = PHRASES.get((question.question_name or "").strip())
        if not phrase:
            continue
        question.text = f"To what extent does {phrase} describe you?"
        question.save(update_fields=["text"])


def backwards(apps, schema_editor):
    Question = apps.get_model("api", "Question")
    for question in Question.objects.filter(question_number=ETHNICITY):
        phrase = PHRASES.get((question.question_name or "").strip())
        if not phrase:
            continue
        question.text = f"Does {phrase} best describe you?"
        question.save(update_fields=["text"])


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0080_ethnicity_option_best_describes"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
