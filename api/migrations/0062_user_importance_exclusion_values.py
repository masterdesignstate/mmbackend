from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0061_enable_rets_them_ota"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="importance_exclusion_values",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Exclude results where this user's Them importance is 5 and the other user's Them importance is in these values.",
            ),
        ),
    ]
