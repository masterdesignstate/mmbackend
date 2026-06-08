from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0058_rename_hawaiian_ethnicity_to_other'),
    ]

    operations = [
        migrations.AddField(
            model_name='useranswer',
            name='excluded_answer_values',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Current user's one-way result exclusions for this question; answer values 1-5 only.",
            ),
        ),
        migrations.AddIndex(
            model_name='useranswer',
            index=models.Index(fields=['question', 'me_answer', 'user'], name='ua_question_me_user_idx'),
        ),
    ]
