from django.db import migrations


def disable_optional_ota_me(apps, schema_editor):
    Question = apps.get_model("api", "Question")
    Question.objects.filter(is_mandatory=False, open_to_all_me=True).update(
        open_to_all_me=False
    )


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0059_useranswer_excluded_answer_values_and_index"),
    ]

    operations = [
        migrations.RunPython(disable_optional_ota_me, migrations.RunPython.noop),
    ]
