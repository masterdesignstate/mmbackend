from django.db import migrations
import uuid


HAWAIIAN_ETHNICITY_QUESTION_ID = uuid.UUID("2ef95f1a-3b2f-48f5-adb6-1c31d89ed904")
OTHER_ETHNICITY_QUESTION_ID = uuid.UUID("14f4f27b-0e50-4b4a-8172-5d9e6a6eb39d")
NATIVE_ETHNICITY_QUESTION_ID = uuid.UUID("473dd873-c249-4426-a1f0-7368d5604888")
HISPANIC_ETHNICITY_QUESTION_ID = uuid.UUID("ee1136e8-d7fa-4d5f-905b-09d3e85f38a7")
ASIAN_ETHNICITY_QUESTION_ID = uuid.UUID("a135b6e5-7b85-4122-9218-d0093881646c")


def rename_hawaiian_to_other(apps, schema_editor):
    Question = apps.get_model("api", "Question")
    UserAnswer = apps.get_model("api", "UserAnswer")
    UserRequiredQuestion = apps.get_model("api", "UserRequiredQuestion")

    hawaiian_question = (
        Question.objects.filter(id=HAWAIIAN_ETHNICITY_QUESTION_ID).first()
        or Question.objects.filter(question_number=3, group_name="Ethnicity", question_name="Hawaiian").first()
    )
    other_question = Question.objects.filter(id=OTHER_ETHNICITY_QUESTION_ID).first()

    if hawaiian_question:
        hawaiian_question.question_name = "Other"
        hawaiian_question.group_number = 6
        hawaiian_question.text = "How strongly do you identify as another ethnicity?"
        hawaiian_question.save(update_fields=["question_name", "group_number", "text"])

    Question.objects.filter(id=NATIVE_ETHNICITY_QUESTION_ID).update(group_number=3)
    Question.objects.filter(id=HISPANIC_ETHNICITY_QUESTION_ID).update(group_number=4)
    Question.objects.filter(id=ASIAN_ETHNICITY_QUESTION_ID).update(group_number=5)

    if hawaiian_question and other_question and hawaiian_question.id != other_question.id:
        for answer in UserAnswer.objects.filter(question=other_question):
            if UserAnswer.objects.filter(user=answer.user, question=hawaiian_question).exists():
                answer.delete()
            else:
                answer.question = hawaiian_question
                answer.save(update_fields=["question"])

        for required_question in UserRequiredQuestion.objects.filter(question=other_question):
            if UserRequiredQuestion.objects.filter(user=required_question.user, question=hawaiian_question).exists():
                required_question.delete()
            else:
                required_question.question = hawaiian_question
                required_question.save(update_fields=["question"])

        other_question.delete()


def restore_other_to_hawaiian(apps, schema_editor):
    Question = apps.get_model("api", "Question")

    Question.objects.filter(id=HAWAIIAN_ETHNICITY_QUESTION_ID).update(
        question_name="Hawaiian",
        group_number=3,
        text="How strongly do you identify as native hawaiian or other pacific islander?",
    )
    Question.objects.filter(id=NATIVE_ETHNICITY_QUESTION_ID).update(group_number=4)
    Question.objects.filter(id=HISPANIC_ETHNICITY_QUESTION_ID).update(group_number=5)
    Question.objects.filter(id=ASIAN_ETHNICITY_QUESTION_ID).update(group_number=6)


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0057_share_answers_visibility"),
    ]

    operations = [
        migrations.RunPython(rename_hawaiian_to_other, restore_other_to_hawaiian),
    ]
