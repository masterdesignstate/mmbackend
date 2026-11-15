from django.db import migrations

from api.mandatory_questions import ETHNICITY

# The phrase that fills "Does {phrase} best describe you?"
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
        question.text = f"Does {phrase} best describe you?"
        question.save(update_fields=["text"])


def backwards(apps, schema_editor):
    Question = apps.get_model("api", "Question")
    Question.objects.filter(question_number=ETHNICITY).update(
        text="What ethnicity best describes you?"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0079_ethnicity_question_this_ethnicity"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
