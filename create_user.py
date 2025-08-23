#!/usr/bin/env python
"""
Script to create a user for testing
"""

import os
import sys
import django

# Add the project directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mmbackend.settings')
django.setup()

from api.models import User

def create_test_user():
    """Create a test user"""
    try:
        # Check if user already exists
        user, created = User.objects.get_or_create(
            email='atomsable@gmail.com',
            defaults={
                'username': 'atomsable',
                'first_name': 'Test',
                'last_name': 'User',
                'is_active': True,
            }
        )
        
        if created:
            # Set password for new user
            user.set_password('12345678')
            user.save()
            print("✅ User created successfully!")
            print(f"Email: {user.email}")
            print(f"Username: {user.username}")
            print(f"Password: 12345678")
        else:
            # Update password for existing user
            user.set_password('12345678')
            user.save()
            print("✅ User password updated!")
            print(f"Email: {user.email}")
            print(f"Username: {user.username}")
            print(f"Password: 12345678")
            
    except Exception as e:
        print(f"❌ Error creating user: {e}")

if __name__ == "__main__":
    create_test_user() 