#!/usr/bin/env python3
"""
Add database indexes for performance optimization
"""
import os
import sys
import django
from django.db import connection

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mmbackend.settings')
django.setup()

def add_performance_indexes():
    """Add database indexes for frequently queried fields"""

    with connection.cursor() as cursor:
        print("=== ADDING PERFORMANCE INDEXES ===")

        # Index on UserAnswer.user_id and question_id (most common lookup)
        try:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_useranswer_user_question
                ON api_useranswer(user_id, question_id);
            """)
            print("✅ Added index on user_id, question_id")
        except Exception as e:
            print(f"❌ Error adding user_answer index: {e}")

        # Index on Question.question_name for gender filtering queries
        try:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_question_name
                ON api_question(question_name);
            """)
            print("✅ Added index on question_name")
        except Exception as e:
            print(f"❌ Error adding question_name index: {e}")

        # Index on User.is_banned for filtering
        try:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_is_banned
                ON api_user(is_banned);
            """)
            print("✅ Added index on is_banned")
        except Exception as e:
            print(f"❌ Error adding is_banned index: {e}")

        # Index on UserAnswer.me_answer for score calculations
        try:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_useranswer_me_answer
                ON api_useranswer(me_answer);
            """)
            print("✅ Added index on me_answer")
        except Exception as e:
            print(f"❌ Error adding me_answer index: {e}")

        # Index on UserAnswer.looking_for_answer for compatibility calculations
        try:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_useranswer_looking_for_answer
                ON api_useranswer(looking_for_answer);
            """)
            print("✅ Added index on looking_for_answer")
        except Exception as e:
            print(f"❌ Error adding looking_for_answer index: {e}")

        # Composite index for Compatibility lookups
        try:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_compatibility_users
                ON api_compatibility(user1_id, user2_id);
            """)
            print("✅ Added index on compatibility user pairs")
        except Exception as e:
            print(f"❌ Error adding compatibility index: {e}")

        print("\n=== INDEXES ADDED SUCCESSFULLY ===")
        print("Database queries should now be significantly faster!")

if __name__ == '__main__':
    add_performance_indexes()