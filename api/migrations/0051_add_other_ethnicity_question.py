from django.db import migrations
import uuid


OTHER_ETHNICITY_QUESTION_ID = uuid.UUID("14f4f27b-0e50-4b4a-8172-5d9e6a6eb39d")


def add_other_ethnicity_question(apps, schema_editor):
    Question = apps.get_model("api", "Question")
    QuestionAnswer = apps.get_model("api", "QuestionAnswer")
    Tag = apps.get_model("api", "Tag")

    question, _ = Question.objects.update_or_create(
        id=OTHER_ETHNICITY_QUESTION_ID,
        defaults={
            "question_name": "Other",
            "question_number": 3,
            "group_number": 7,
            "group_name": "Ethnicity",
            "text": "How strongly do you identify as another ethnicity?",
            "question_type": "grouped",
            "is_required_for_match": False,
            "is_mandatory": True,
            "is_approved": True,
            "skip_me": False,
            "skip_looking_for": False,
            "open_to_all_me": False,
            "open_to_all_looking_for": True,
            "is_group": False,
        },
    )

    value_tag, _ = Tag.objects.get_or_create(name="value")
    question.tags.add(value_tag)

    answers = [
        ("1", "Less", 0),
        ("2", "", 1),
        ("3", "", 2),
        ("4", "", 3),
        ("5", "More", 4),
    ]
    for value, answer_text, order in answers:
        QuestionAnswer.objects.update_or_create(
            question=question,
            value=value,
            defaults={
                "answer_text": answer_text,
                "order": order,
            },
        )


def remove_other_ethnicity_question(apps, schema_editor):
    Question = apps.get_model("api", "Question")
    Question.objects.filter(id=OTHER_ETHNICITY_QUESTION_ID).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0050_user_share_answers"),
    ]

    operations = [
        migrations.RunPython(add_other_ethnicity_question, remove_other_ethnicity_question),
    ]
