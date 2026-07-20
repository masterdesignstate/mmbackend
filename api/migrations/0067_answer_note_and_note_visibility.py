from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0066_dummy_flag_and_auto_updater_controls"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="note_visibility",
            field=models.CharField(
                choices=[
                    ("none", "None"),
                    ("all", "Everyone"),
                    ("approved", "Approved"),
                    ("liked", "Liked"),
                    ("matched", "Matched"),
                ],
                default="all",
                help_text="Who can see the free-text notes this user attaches to their Me answers.",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="useranswer",
            name="me_note",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Free-text note the user attaches to their Me answer; visibility governed by User.note_visibility.",
                max_length=280,
            ),
        ),
        migrations.AddField(
            model_name="useranswer",
            name="me_note_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
