from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0063_user_email_verification"),
    ]

    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE users ALTER COLUMN email_verified SET DEFAULT FALSE;",
            reverse_sql="ALTER TABLE users ALTER COLUMN email_verified DROP DEFAULT;",
        ),
    ]
