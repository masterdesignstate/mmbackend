from django.db import migrations


def enable_optional_them_ota(apps, schema_editor):
    Question = apps.get_model("api", "Question")
    Question.objects.filter(is_mandatory=False).update(
        open_to_all_me=False,
        open_to_all_looking_for=True,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0069_rename_admin_email"),
    ]

    operations = [
        migrations.RunPython(enable_optional_them_ota, migrations.RunPython.noop),
    ]
