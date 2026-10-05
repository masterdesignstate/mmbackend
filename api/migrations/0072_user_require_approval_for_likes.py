from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0071_feedactivity_primary_photo_changed"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="require_approval_for_likes",
            field=models.BooleanField(
                default=True,
                db_default=True,
                help_text="If true, other users can only like this user after this user has approved (or liked) them",
            ),
        ),
    ]
