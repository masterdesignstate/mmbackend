#!/usr/bin/env python3
"""
Quick check of created users
"""
import os
import sys
import django

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mmbackend.settings')
django.setup()

from api.models import User, UserAnswer

def check_users():
    print("=== USER SUMMARY ===")
    total_users = User.objects.count()
    users_with_answers = User.objects.filter(answers__isnull=False).distinct().count()
    total_answers = UserAnswer.objects.count()

    print(f"Total Users: {total_users}")
    print(f"Users with Answers: {users_with_answers}")
    print(f"Total User Answers: {total_answers}")
    print()

    # Show sample of diverse users
    print("=== SAMPLE DIVERSE USERS ===")
    sample_users = User.objects.order_by('?')[:10]  # Random sample

    for user in sample_users:
        gender_answers = user.answers.filter(question__group_name='Gender')
        is_male = "Unknown"
        if gender_answers.exists():
            male_answer = gender_answers.filter(question__question_name='Male').first()
            female_answer = gender_answers.filter(question__question_name='Female').first()

            male_score = male_answer.me_answer if male_answer else 1
            female_score = female_answer.me_answer if female_answer else 1

            if male_score > female_score:
                is_male = "Male"
            elif female_score > male_score:
                is_male = "Female"
            else:
                is_male = "Non-binary"

        print(f"- {user.first_name} {user.last_name} ({user.username})")
        print(f"  Age: {user.age}, Gender: {is_male}, Location: {user.live}")
        print(f"  Bio: {user.bio}")
        print(f"  Answers: {user.answers.count()}")
        print()

if __name__ == '__main__':
    check_users()