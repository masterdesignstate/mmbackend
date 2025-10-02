#!/usr/bin/env python3
"""
Update male user profile pictures to use random girls photos
"""
import os
import sys
import random
import django

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mmbackend.settings')
django.setup()

from api.models import User

def update_male_photos():
    # Available girls photos
    GIRLS_PHOTOS = [
        '/assets/girls/IMG_0369.PNG',
        '/assets/girls/IMG_0412.JPG',
        '/assets/girls/IMG_0422.PNG',
        '/assets/girls/IMG_0426.JPG',
        '/assets/girls/IMG_0432.JPG',
        '/assets/girls/IMG_0459.JPG',
        '/assets/girls/IMG_0501.JPG',
        '/assets/girls/IMG_0533.JPG',
        '/assets/girls/IMG_0550.JPG',
        '/assets/girls/IMG_9894.JPG'
    ]

    print("=== UPDATING MALE USER PROFILE PICTURES ===")

    # Get all users
    all_users = User.objects.all()
    male_users_updated = 0

    for user in all_users:
        # Check if user is male based on gender answers
        male_answer = user.answers.filter(question__question_name='Male').first()
        female_answer = user.answers.filter(question__question_name='Female').first()

        is_male = False
        if male_answer and female_answer:
            male_score = male_answer.me_answer
            female_score = female_answer.me_answer
            # Consider someone male if they identify more as male than female
            if male_score > female_score:
                is_male = True
        elif male_answer and male_answer.me_answer >= 3:
            # If only male answer exists and it's 3 or higher
            is_male = True

        if is_male:
            # Assign random girls photo to male user
            new_photo = random.choice(GIRLS_PHOTOS)
            old_photo = user.profile_photo

            user.profile_photo = new_photo
            user.save()

            print(f"Updated {user.username} ({user.first_name} {user.last_name})")
            print(f"  Old photo: {old_photo}")
            print(f"  New photo: {new_photo}")
            print()

            male_users_updated += 1

    print(f"✅ Updated {male_users_updated} male users with girls profile pictures")
    print(f"📸 Available photos: {len(GIRLS_PHOTOS)} different images")

    # Show summary
    total_users = User.objects.count()
    print(f"\n=== SUMMARY ===")
    print(f"Total Users: {total_users}")
    print(f"Male Users Updated: {male_users_updated}")
    print(f"All users now have profile pictures!")

if __name__ == '__main__':
    update_male_photos()