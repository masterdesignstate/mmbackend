#!/usr/bin/env python3
"""
Test script to verify the compatibility calculation algorithm
"""
import os
import sys
import django

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mmbackend.settings')
django.setup()

from api.models import User, Question, UserAnswer, Controls
from api.services.compatibility_service import CompatibilityService
import uuid

def test_compatibility_calculation():
    print("=== Testing Compatibility Calculation ===")

    # Create test users
    user1 = User.objects.create(
        id=uuid.uuid4(),
        username='testuser1',
        first_name='Alice',
        email='alice@test.com'
    )

    user2 = User.objects.create(
        id=uuid.uuid4(),
        username='testuser2',
        first_name='Bob',
        email='bob@test.com'
    )

    # Create test question
    question = Question.objects.create(
        id=uuid.uuid4(),
        text='Do you like outdoor activities?',
        question_type='basic'
    )

    # Create test answers
    # User1: Looking for someone who likes outdoor activities (answer=5, importance=5)
    # User2: Likes outdoor activities (answer=5, importance=3)
    UserAnswer.objects.create(
        user=user1,
        question=question,
        me_answer=5,
        me_importance=3,
        looking_for_answer=5,
        looking_for_importance=5
    )

    UserAnswer.objects.create(
        user=user2,
        question=question,
        me_answer=5,
        me_importance=3,
        looking_for_answer=4,
        looking_for_importance=2
    )

    # Test individual question score calculation
    print("\n--- Testing Individual Question Score ---")
    direction_a, direction_b = CompatibilityService.calculate_question_score(
        my_answer=5,           # User1 wants someone with answer 5
        my_importance=5,       # Very important to User1
        their_answer=5,        # User2 has answer 5
        their_importance=3,    # Not used for direction A
        my_open_to_all=False,
        their_open_to_all=False
    )

    print(f"Direction A (Compatible with Me): {direction_a}")
    print(f"Direction B (I'm Compatible with): {direction_b}")

    # Test full compatibility calculation
    print("\n--- Testing Full Compatibility Calculation ---")
    compatibility = CompatibilityService.calculate_compatibility_between_users(user1, user2)

    print(f"Overall Compatibility: {compatibility['overall_compatibility']}%")
    print(f"Compatible with Me: {compatibility['compatible_with_me']}%")
    print(f"I'm Compatible with: {compatibility['im_compatible_with']}%")
    print(f"Mutual Questions: {compatibility['mutual_questions_count']}")

    # Test controls
    print("\n--- Testing Controls ---")
    controls = Controls.get_current()
    print(f"Adjust: {controls.adjust}")
    print(f"Exponent: {controls.exponent}")
    print(f"OTA: {controls.ota}")

    # Test importance factor mapping
    print("\n--- Testing Importance Factor Mapping ---")
    for importance in range(1, 6):
        factor = CompatibilityService.map_importance_to_factor(importance)
        print(f"Importance {importance} -> Factor {factor}")

    # Test open to all scenarios
    print("\n--- Testing Open to All Scenarios ---")
    direction_a_ota, direction_b_ota = CompatibilityService.calculate_question_score(
        my_answer=6,           # User1 is open to all
        my_importance=3,
        their_answer=2,        # User2 has any answer
        their_importance=4,
        my_open_to_all=True,
        their_open_to_all=False
    )

    print(f"Open to All - Direction A: {direction_a_ota}")
    print(f"Open to All - Direction B: {direction_b_ota}")

    # Clean up
    user1.delete()
    user2.delete()
    question.delete()

    print("\n=== Test Completed Successfully ===")

if __name__ == '__main__':
    test_compatibility_calculation()