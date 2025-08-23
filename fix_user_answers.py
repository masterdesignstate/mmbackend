#!/usr/bin/env python
"""
Fix user answers to ensure all users have answered all mandatory questions.
This script adds missing answers for users who don't have complete question sets.
"""

import os
import sys
import django
import random

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mmbackend.settings')
django.setup()

from api.models import User, Question, UserAnswer

def fix_user_answers():
    print("=== FIXING USER ANSWERS ===")
    
    # Get all mandatory questions
    all_questions = Question.objects.filter(question_type='mandatory')
    print(f"Total mandatory questions: {all_questions.count()}")
    
    # Get all users
    users = User.objects.all()
    print(f"Total users: {users.count()}")
    
    total_added = 0
    
    for user in users:
        print(f"\nProcessing user: {user.first_name} {user.last_name} ({user.username})")
        
        # Get existing answers for this user
        existing_answers = UserAnswer.objects.filter(user=user)
        answered_question_ids = set(existing_answers.values_list('question_id', flat=True))
        print(f"  Current answers: {len(answered_question_ids)}")
        
        # Find missing questions
        missing_questions = all_questions.exclude(id__in=answered_question_ids)
        print(f"  Missing questions: {missing_questions.count()}")
        
        # Add missing answers
        for question in missing_questions:
            # Generate random answers (1-6 scale)
            me_answer = random.randint(1, 6)
            looking_for_answer = random.randint(1, 6)
            me_multiplier = random.randint(1, 3)
            looking_for_multiplier = random.randint(1, 3)
            
            UserAnswer.objects.create(
                user=user,
                question=question,
                me_answer=me_answer,
                looking_for_answer=looking_for_answer,
                me_multiplier=me_multiplier,
                looking_for_multiplier=looking_for_multiplier
            )
            total_added += 1
        
        # Verify the user now has all answers
        final_count = UserAnswer.objects.filter(user=user).count()
        print(f"  Final answer count: {final_count}")
    
    print(f"\n=== SUMMARY ===")
    print(f"Total answers added: {total_added}")
    
    # Verify all users now have complete answer sets
    print("\n=== VERIFICATION ===")
    for user in users[:5]:  # Check first 5 users
        answer_count = UserAnswer.objects.filter(user=user).count()
        print(f"{user.first_name} {user.last_name}: {answer_count}/{all_questions.count()} questions")

if __name__ == '__main__':
    fix_user_answers()
    print("\n✅ User answer fixing complete!") 