from django.db import migrations, models


def mark_existing_users_verified(apps, schema_editor):
    User = apps.get_model("api", "User")
    User.objects.filter(email_verified=False).update(email_verified=True)


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0062_user_importance_exclusion_values"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="email_verified",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="user",
            name="email_verified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(mark_existing_users_verified, migrations.RunPython.noop),
    ]
