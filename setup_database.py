#!/usr/bin/env python
"""
Database setup script for the dating app.
Run this after setting up your Azure PostgreSQL database.
"""

import os
import sys
import django

# Add the project directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mmbackend.settings')
django.setup()

from api.models import Tag, User


def create_question_tags():
    """Create question tags"""
    tag_choices = [
        'value',
        'lifestyle', 
        'look',
        'trait',
        'hobby',
        'interest'
    ]
    
    created_tags = []
    for tag_name in tag_choices:
        tag, created = Tag.objects.get_or_create(name=tag_name)
        if created:
            created_tags.append(tag_name)
            print(f"✅ Created tag: {tag_name}")
        else:
            print(f"ℹ️  Tag already exists: {tag_name}")
    
    return created_tags


def main():
    print("🚀 Setting up database...")
    
    # Create question tags
    print("\n📝 Creating question tags...")
    create_question_tags()
    
    # Check database connection
    try:
        user_count = User.objects.count()
        print(f"\n✅ Database connection successful!")
        print(f"📊 Current user count: {user_count}")
    except Exception as e:
        print(f"\n❌ Database connection failed: {e}")
        return
    
    print("\n🎉 Database setup complete!")
    print("\nNext steps:")
    print("1. Create a superuser: python manage.py createsuperuser")
    print("2. Run the development server: python manage.py runserver")


if __name__ == "__main__":
    main() 