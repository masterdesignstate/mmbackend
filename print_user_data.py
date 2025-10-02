#!/usr/bin/env python3
"""
Print existing user data and questions/answers to understand the current structure
"""
import os
import sys
import django
import json

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mmbackend.settings')
django.setup()

from api.models import User, Question, UserAnswer, QuestionAnswer

def print_user_data():
    print("=== EXISTING USER DATA ===\n")

    users = User.objects.all()
    print(f"Total Users: {users.count()}\n")

    for user in users[:5]:  # Print first 5 users in detail
        print(f"--- USER: {user.username} ---")
        print(f"ID: {user.id}")
        print(f"Name: {user.first_name} {user.last_name}")
        print(f"Email: {user.email}")
        print(f"Age: {user.age}")
        print(f"Height: {user.height}")
        print(f"Location: {user.from_location} -> {user.live}")
        print(f"Profile Photo: {user.profile_photo}")
        print(f"Bio: {user.bio}")
        print(f"Tagline: {user.tagline}")
        print(f"Answers Count: {user.answers.count()}")
        print()

def print_questions_and_answers():
    print("=== QUESTIONS AND POSSIBLE ANSWERS ===\n")

    questions = Question.objects.filter(is_mandatory=True).order_by('question_number', 'group_number')

    for question in questions:
        print(f"--- QUESTION {question.question_number}.{question.group_number}: {question.question_name} ---")
        print(f"ID: {question.id}")
        print(f"Text: {question.text}")
        print(f"Type: {question.question_type}")
        print(f"Group: {question.group_name}")
        print(f"Skip Me: {question.skip_me}")
        print(f"Skip Looking For: {question.skip_looking_for}")
        print(f"Open to All Me: {question.open_to_all_me}")
        print(f"Open to All Looking For: {question.open_to_all_looking_for}")

        # Print possible answers
        answers = QuestionAnswer.objects.filter(question=question).order_by('order')
        print("Possible Answers:")
        for answer in answers:
            print(f"  {answer.value}: {answer.answer_text}")
        print()

def print_user_answers():
    print("=== SAMPLE USER ANSWERS ===\n")

    # Get a user with answers
    user_with_answers = User.objects.filter(answers__isnull=False).first()
    if not user_with_answers:
        print("No users with answers found!")
        return

    print(f"--- ANSWERS FOR: {user_with_answers.username} ---")
    user_answers = UserAnswer.objects.filter(user=user_with_answers).select_related('question')

    for user_answer in user_answers:
        question = user_answer.question
        print(f"Q{question.question_number}.{question.group_number}: {question.question_name}")
        print(f"  Me Answer: {user_answer.me_answer} (importance: {user_answer.me_importance}, open_to_all: {user_answer.me_open_to_all})")
        print(f"  Looking For: {user_answer.looking_for_answer} (importance: {user_answer.looking_for_importance}, open_to_all: {user_answer.looking_for_open_to_all})")
        print()

def export_data_for_generation():
    print("=== DATA FOR USER GENERATION ===\n")

    # Export questions structure
    questions = Question.objects.filter(is_mandatory=True).order_by('question_number', 'group_number')
    questions_data = []

    for question in questions:
        answers = QuestionAnswer.objects.filter(question=question).order_by('order')
        question_data = {
            'id': str(question.id),
            'question_number': question.question_number,
            'group_number': question.group_number,
            'question_name': question.question_name,
            'text': question.text,
            'question_type': question.question_type,
            'group_name': question.group_name,
            'skip_me': question.skip_me,
            'skip_looking_for': question.skip_looking_for,
            'open_to_all_me': question.open_to_all_me,
            'open_to_all_looking_for': question.open_to_all_looking_for,
            'possible_answers': [
                {'value': answer.value, 'text': answer.answer_text}
                for answer in answers
            ]
        }
        questions_data.append(question_data)

    print("QUESTIONS DATA:")
    print(json.dumps(questions_data, indent=2))
    print()

    # Export existing user patterns
    users = User.objects.all()
    user_patterns = []

    for user in users:
        user_data = {
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'age': user.age,
            'height': user.height,
            'from_location': user.from_location,
            'live': user.live,
            'bio': user.bio,
            'tagline': user.tagline,
            'has_answers': user.answers.exists()
        }
        user_patterns.append(user_data)

    print("USER PATTERNS:")
    print(json.dumps(user_patterns, indent=2))

if __name__ == '__main__':
    print_user_data()
    print_questions_and_answers()
    print_user_answers()
    export_data_for_generation()