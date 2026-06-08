from django.db import migrations, models


def migrate_share_answers_to_visibility(apps, schema_editor):
    User = apps.get_model('api', 'User')
    for user in User.objects.all().only('id', 'share_answers').iterator():
        User.objects.filter(id=user.id).update(
            answer_visibility='all' if user.share_answers else 'none'
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0056_sync_questions_answered_row_count'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='answer_visibility',
            field=models.CharField(
                choices=[
                    ('none', 'None'),
                    ('all', 'Everyone'),
                    ('approved', 'Approved'),
                    ('liked', 'Liked'),
                    ('matched', 'Matched'),
                ],
                default='none',
                help_text="Who can see this user's looking-for answers on answers they share.",
                max_length=16,
            ),
        ),
        migrations.RunPython(migrate_share_answers_to_visibility, noop_reverse),
        migrations.RemoveField(
            model_name='user',
            name='share_answers',
        ),
        migrations.RenameField(
            model_name='user',
            old_name='answer_visibility',
            new_name='share_answers',
        ),
    ]
