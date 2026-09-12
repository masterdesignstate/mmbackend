from django.db import migrations, models


class Migration(migrations.Migration):
    """Adds the primary_photo_changed feed activity kind. Choices only — no schema change."""

    dependencies = [
        ("api", "0070_enable_optional_them_ota"),
    ]

    operations = [
        migrations.AlterField(
            model_name="feedactivity",
            name="kind",
            field=models.CharField(
                choices=[
                    ("bio_updated", "Bio updated"),
                    ("photo_added", "Photo added"),
                    ("primary_photo_changed", "Primary photo changed"),
                    ("question_answered", "Question answered"),
                ],
                max_length=32,
            ),
        ),
    ]
