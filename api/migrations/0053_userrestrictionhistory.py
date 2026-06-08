import datetime
import uuid

from django.db import migrations, models
import django.db.models.deletion


def backfill_restriction_history(apps, schema_editor):
    User = apps.get_model('api', 'User')
    UserRestrictionHistory = apps.get_model('api', 'UserRestrictionHistory')

    for user in User.objects.filter(
        restriction_date__isnull=False,
        restriction_type__isnull=False,
    ):
        duration_days = user.restriction_duration
        expires_at = None
        if user.restriction_type == 'temporary' and duration_days:
            expires_at = user.restriction_date + datetime.timedelta(days=duration_days)

        UserRestrictionHistory.objects.get_or_create(
            user_id=user.id,
            restricted_at=user.restriction_date,
            defaults={
                'restriction_type': user.restriction_type,
                'duration_days': duration_days,
                'reason': user.restriction_reason or '',
                'reason_detail': user.restriction_reason_detail or '',
                'expires_at': expires_at,
                'end_reason': 'active',
            },
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0052_add_profile_prompts'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserRestrictionHistory',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('restriction_type', models.CharField(help_text='temporary or permanent', max_length=20)),
                ('duration_days', models.PositiveIntegerField(blank=True, null=True)),
                ('reason', models.TextField(blank=True)),
                ('reason_detail', models.TextField(blank=True, default='')),
                ('restricted_at', models.DateTimeField()),
                ('expires_at', models.DateTimeField(blank=True, null=True)),
                ('ended_at', models.DateTimeField(blank=True, null=True)),
                ('end_reason', models.CharField(choices=[('active', 'Active'), ('expired', 'Expired'), ('removed', 'Removed'), ('replaced', 'Replaced')], default='active', max_length=20)),
                ('moderator_notes', models.TextField(blank=True, default='')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='restriction_history', to='api.user')),
            ],
            options={
                'db_table': 'user_restriction_history',
                'ordering': ['-restricted_at'],
            },
        ),
        migrations.AddIndex(
            model_name='userrestrictionhistory',
            index=models.Index(fields=['user', '-restricted_at'], name='restriction_hist_user_date'),
        ),
        migrations.AddIndex(
            model_name='userrestrictionhistory',
            index=models.Index(fields=['user', 'ended_at'], name='restriction_hist_active'),
        ),
        migrations.RunPython(backfill_restriction_history, noop_reverse),
    ]
