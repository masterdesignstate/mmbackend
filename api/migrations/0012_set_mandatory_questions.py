# Generated manually to set mandatory questions

from django.db import migrations

def set_mandatory_questions(apps, schema_editor):
    """Set is_mandatory=True for questions 1-10"""
    Question = apps.get_model('api', 'Question')
    
    # Update questions 1-10 to be mandatory
    Question.objects.filter(question_number__gte=1, question_number__lte=10).update(is_mandatory=True)
    
def reverse_mandatory_questions(apps, schema_editor):
    """Reverse the mandatory question setting"""
    Question = apps.get_model('api', 'Question')
    Question.objects.filter(question_number__gte=1, question_number__lte=10).update(is_mandatory=False)

class Migration(migrations.Migration):
    dependencies = [
        ('api', '0011_remove_question_question_type_question_is_mandatory_and_more'),
    ]

    operations = [
        migrations.RunPython(set_mandatory_questions, reverse_mandatory_questions),
    ]