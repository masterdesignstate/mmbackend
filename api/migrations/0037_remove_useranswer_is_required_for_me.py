# Remove is_required_for_me from UserAnswer; required state is now in UserRequiredQuestion

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0036_migrate_required_to_userrequiredquestion"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="useranswer",
            name="is_required_for_me",
        ),
    ]
