from django.db import migrations


def enable_rets_them_ota(apps, schema_editor):
    Question = apps.get_model("api", "Question")
    Question.objects.filter(question_number=13).update(open_to_all_looking_for=True)


def disable_rets_them_ota(apps, schema_editor):
    Question = apps.get_model("api", "Question")
    Question.objects.filter(question_number=13).update(open_to_all_looking_for=False)


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0060_disable_optional_ota_me"),
    ]

    operations = [
        migrations.RunPython(enable_rets_them_ota, disable_rets_them_ota),
    ]
