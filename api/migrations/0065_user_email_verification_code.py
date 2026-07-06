from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0064_email_verified_db_default'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='email_verification_code_attempts',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='user',
            name='email_verification_code_expires_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='user',
            name='email_verification_code_hash',
            field=models.CharField(blank=True, default='', max_length=128),
        ),
        migrations.AddField(
            model_name='user',
            name='email_verification_code_sent_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
