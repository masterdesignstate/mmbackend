# Their Required compatibility: score using ONLY the other user's required questions

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0037_remove_useranswer_is_required_for_me"),
    ]

    operations = [
        migrations.AddField(
            model_name="compatibility",
            name="their_required_compatibility",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Compatibility calculated only on user2's required questions (their required from user1's perspective)",
                max_digits=5,
            ),
        ),
    ]
