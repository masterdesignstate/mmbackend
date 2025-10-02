#!/usr/bin/env python3
"""
Create 100 diverse dummy users with rotating profile pictures and varied question answers
"""
import os
import sys
import django
import random
from datetime import date, datetime, timedelta
import uuid

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mmbackend.settings')
django.setup()

from api.models import User, Question, UserAnswer

# Profile picture sets for different types
FEMALE_PHOTOS = [
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

MALE_PHOTOS = [
    '/assets/boys/boy1.jpg',
    '/assets/boys/boy2.jpg',
    '/assets/boys/boy3.jpg',
    '/assets/boys/boy4.jpg',
    '/assets/boys/boy5.jpg',
    '/assets/boys/boy6.jpg',
    '/assets/boys/boy7.jpg',
    '/assets/boys/boy8.jpg',
    '/assets/boys/boy9.jpg',
    '/assets/boys/boy10.jpg'
]

# Names for users
FEMALE_NAMES = [
    'Emma', 'Olivia', 'Ava', 'Isabella', 'Sophia', 'Charlotte', 'Mia', 'Amelia', 'Harper', 'Evelyn',
    'Abigail', 'Emily', 'Elizabeth', 'Mila', 'Ella', 'Avery', 'Sofia', 'Camila', 'Aria', 'Scarlett',
    'Victoria', 'Madison', 'Luna', 'Grace', 'Chloe', 'Penelope', 'Layla', 'Riley', 'Zoey', 'Nora',
    'Lily', 'Eleanor', 'Hannah', 'Lillian', 'Addison', 'Aubrey', 'Ellie', 'Stella', 'Natalie', 'Zoe',
    'Leah', 'Hazel', 'Violet', 'Aurora', 'Savannah', 'Audrey', 'Brooklyn', 'Bella', 'Claire', 'Skylar'
]

MALE_NAMES = [
    'Liam', 'Noah', 'William', 'James', 'Oliver', 'Benjamin', 'Elijah', 'Lucas', 'Mason', 'Logan',
    'Alexander', 'Ethan', 'Jacob', 'Michael', 'Daniel', 'Henry', 'Jackson', 'Sebastian', 'Aiden', 'Matthew',
    'Samuel', 'David', 'Joseph', 'Carter', 'Owen', 'Wyatt', 'John', 'Jack', 'Luke', 'Jayden',
    'Dylan', 'Grayson', 'Levi', 'Isaac', 'Gabriel', 'Julian', 'Mateo', 'Anthony', 'Jaxon', 'Lincoln',
    'Joshua', 'Christopher', 'Andrew', 'Theodore', 'Caleb', 'Ryan', 'Asher', 'Nathan', 'Thomas', 'Leo'
]

LAST_NAMES = [
    'Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez',
    'Hernandez', 'Lopez', 'Gonzalez', 'Wilson', 'Anderson', 'Thomas', 'Taylor', 'Moore', 'Jackson', 'Martin',
    'Lee', 'Perez', 'Thompson', 'White', 'Harris', 'Sanchez', 'Clark', 'Ramirez', 'Lewis', 'Robinson',
    'Walker', 'Young', 'Allen', 'King', 'Wright', 'Scott', 'Torres', 'Nguyen', 'Hill', 'Flores',
    'Green', 'Adams', 'Nelson', 'Baker', 'Hall', 'Rivera', 'Campbell', 'Mitchell', 'Carter', 'Roberts'
]

CITIES = [
    'Austin', 'Dallas', 'Houston', 'San Antonio', 'Fort Worth', 'El Paso', 'Arlington', 'Corpus Christi',
    'Plano', 'Lubbock', 'Laredo', 'Irving', 'Garland', 'Frisco', 'McKinney', 'Amarillo', 'Grand Prairie',
    'Brownsville', 'Pasadena', 'Mesquite', 'Killeen', 'Denton', 'Carrollton', 'Midland', 'Abilene',
    'Round Rock', 'The Woodlands', 'Richardson', 'Pearland', 'College Station', 'Waco', 'Lewisville',
    'Tyler', 'San Angelo', 'Allen', 'League City', 'Sugar Land', 'Longview', 'Beaumont', 'Odessa'
]

ORIGIN_LOCATIONS = [
    'California', 'New York', 'Florida', 'Texas', 'Illinois', 'Pennsylvania', 'Ohio', 'Georgia',
    'North Carolina', 'Michigan', 'New Jersey', 'Virginia', 'Washington', 'Arizona', 'Massachusetts',
    'Tennessee', 'Indiana', 'Maryland', 'Missouri', 'Wisconsin', 'Colorado', 'Minnesota', 'South Carolina',
    'Alabama', 'Louisiana', 'Kentucky', 'Oregon', 'Oklahoma', 'Connecticut', 'Utah', 'Iowa', 'Nevada',
    'Arkansas', 'Kansas', 'New Mexico', 'Nebraska', 'West Virginia', 'Idaho', 'Hawaii', 'New Hampshire',
    'Maine', 'Montana', 'Rhode Island', 'Delaware', 'South Dakota', 'North Dakota', 'Alaska', 'Vermont', 'Wyoming'
]

BIOS = [
    "Love adventures and trying new things!",
    "Coffee enthusiast and bookworm 📚",
    "Fitness junkie with a passion for travel",
    "Artist by day, Netflix binger by night",
    "Dog lover and hiking enthusiast 🐕",
    "Foodie always looking for the best tacos",
    "Music festival goer and concert lover",
    "Beach person who loves the outdoors",
    "Tech geek with a creative side",
    "Yoga instructor and wellness advocate",
    "Photographer capturing life's moments",
    "Chef experimenting with new recipes",
    "Runner training for my next marathon",
    "Gamer and sci-fi movie fanatic",
    "Teacher passionate about making a difference",
    "Entrepreneur building my dream",
    "Dancer who loves to move and groove",
    "Cyclist exploring new trails",
    "Wine taster and cheese lover",
    "Volunteer working with local charities",
    "Rock climber seeking new heights",
    "Gardener growing my own vegetables",
    "Surfer catching waves on weekends",
    "Writer working on my first novel",
    "Musician playing in a local band"
]

TAGLINES = [
    "Life's too short for bad coffee",
    "Adventure awaits around every corner",
    "Live laugh love",
    "Carpe diem",
    "Making memories one day at a time",
    "Always looking for the next adventure",
    "Spreading good vibes only",
    "Dream big, work hard",
    "Life is beautiful",
    "Stay curious, stay humble",
    "Find joy in the little things",
    "Be the change you wish to see",
    "Life's a journey, not a destination",
    "Embrace the chaos",
    "Create your own sunshine",
    "Live with passion",
    "Be kind, be brave, be you",
    "Chase your dreams",
    "Stay wild",
    "Love what you do"
]

def get_mandatory_questions():
    """Get all mandatory questions that need answers"""
    return Question.objects.filter(is_mandatory=True).order_by('question_number', 'group_number')

def generate_realistic_answers(question, is_male=None):
    """Generate realistic answers based on question type and user demographics"""

    # Default values
    me_answer = random.randint(1, 5)
    looking_for_answer = random.randint(1, 5)
    me_importance = random.randint(1, 5)
    looking_for_importance = random.randint(1, 5)
    me_open_to_all = False
    looking_for_open_to_all = False

    # Skip if question configuration says to skip
    if question.skip_me:
        me_answer = 1
        me_importance = 1

    if question.skip_looking_for:
        looking_for_answer = 1
        looking_for_importance = 1

    # Handle gender questions specifically
    if question.question_name == 'Male':
        if is_male:
            me_answer = random.choice([4, 5])  # Strong male identification
        else:
            me_answer = random.choice([1, 2])  # Low male identification

        # For looking for, be more open
        if question.open_to_all_looking_for and random.random() < 0.3:
            looking_for_answer = 6
            looking_for_open_to_all = True
        else:
            looking_for_answer = random.randint(1, 5)

    elif question.question_name == 'Female':
        if not is_male:
            me_answer = random.choice([4, 5])  # Strong female identification
        else:
            me_answer = random.choice([1, 2])  # Low female identification

        # For looking for, be more open
        if question.open_to_all_looking_for and random.random() < 0.3:
            looking_for_answer = 6
            looking_for_open_to_all = True
        else:
            looking_for_answer = random.randint(1, 5)

    # Handle relationship questions
    elif question.group_name == 'Relationship':
        # Make relationship preferences more varied but realistic
        me_answer = random.choice([1, 2, 3, 4, 5])
        me_importance = random.choice([2, 3, 4, 5])  # Usually important

        # Looking for answers often differ from me answers
        looking_for_answer = random.choice([1, 2, 3, 4, 5])
        looking_for_importance = random.choice([1, 2, 3])  # Usually less important

    # Handle ethnicity questions
    elif question.group_name == 'Ethnicity':
        # Most people identify strongly with one ethnicity
        ethnicity_chance = random.random()
        if ethnicity_chance < 0.15:  # 15% chance of strong identification
            me_answer = 5
        elif ethnicity_chance < 0.25:  # 10% moderate identification
            me_answer = random.choice([3, 4])
        else:  # 75% low identification
            me_answer = random.choice([1, 2])

        # For looking for, often open to all
        if question.open_to_all_looking_for and random.random() < 0.6:
            looking_for_answer = 6
            looking_for_open_to_all = True

    # Handle education questions
    elif question.group_name == 'Education':
        # Most people complete some level, distribute realistically
        education_level = random.choice([
            'pre_high', 'high_school', 'trade', 'undergraduate', 'masters', 'doctorate'
        ])

        if question.question_name.lower().replace(' ', '_') == education_level:
            me_answer = random.choice([4, 5])
        else:
            me_answer = random.choice([1, 2])

    # Handle diet questions
    elif question.group_name == 'Diet':
        # Most people are omnivores
        if question.question_name == 'Omnivore':
            me_answer = random.choice([4, 5]) if random.random() < 0.7 else random.choice([1, 2])
        else:
            me_answer = random.choice([1, 2]) if random.random() < 0.8 else random.choice([3, 4, 5])

    # Handle exercise
    elif question.question_name == 'Exercise':
        me_answer = random.choice([2, 3, 4])  # Most people exercise sometimes to regularly
        me_importance = random.choice([3, 4, 5])  # Usually important

    # Handle habits (alcohol, smoking, vaping)
    elif question.group_name == 'Habits':
        if question.question_name == 'Alcohol':
            me_answer = random.choice([1, 2, 3])  # Most people drink never to sometimes
        else:  # Cigarettes, Vape
            me_answer = random.choice([1, 1, 1, 2, 3])  # Most people don't smoke

    # Handle religion
    elif question.question_name == 'Religion':
        me_answer = random.choice([1, 2, 3])  # Most people practice never to sometimes

    # Handle politics
    elif question.question_name == 'Politics':
        me_answer = random.choice([1, 2, 3, 4])  # Varied political involvement

    # Handle kids questions
    elif question.group_name in ['Children', 'Kids']:
        if question.question_name == 'Have':
            me_answer = random.choice([1, 1, 1, 5])  # Most don't have kids yet
        elif question.question_name == 'Want':
            # More varied on wanting kids
            if random.random() < 0.2:  # 20% open to all
                me_answer = 6
                me_open_to_all = True
            else:
                me_answer = random.choice([1, 2, 3, 4, 5])

    # Add some randomness to open_to_all for questions that allow it
    if question.open_to_all_me and random.random() < 0.1:  # 10% chance
        me_answer = 6
        me_open_to_all = True

    if question.open_to_all_looking_for and random.random() < 0.2:  # 20% chance
        looking_for_answer = 6
        looking_for_open_to_all = True

    return {
        'me_answer': me_answer,
        'me_importance': me_importance,
        'me_open_to_all': me_open_to_all,
        'looking_for_answer': looking_for_answer,
        'looking_for_importance': looking_for_importance,
        'looking_for_open_to_all': looking_for_open_to_all
    }

def create_dummy_users(count=100):
    """Create diverse dummy users with realistic data"""

    questions = get_mandatory_questions()
    print(f"Found {questions.count()} mandatory questions to answer")

    created_users = []

    for i in range(count):
        # Determine gender (roughly 50/50 split)
        is_male = random.random() < 0.5

        # Select names and photos based on gender
        if is_male:
            first_name = random.choice(MALE_NAMES)
            photos = MALE_PHOTOS
        else:
            first_name = random.choice(FEMALE_NAMES)
            photos = FEMALE_PHOTOS

        last_name = random.choice(LAST_NAMES)

        # Generate username (lowercase first name + last initial + random number)
        username = f"{first_name.lower()}{last_name[0].lower()}{random.randint(10, 99)}"

        # Ensure unique username
        while User.objects.filter(username=username).exists():
            username = f"{first_name.lower()}{last_name[0].lower()}{random.randint(100, 999)}"

        # Generate other user data
        age = random.randint(18, 45)
        height = random.randint(150, 200) if is_male else random.randint(145, 185)

        # Calculate birth date from age
        today = date.today()
        birth_year = today.year - age
        birth_date = date(birth_year, random.randint(1, 12), random.randint(1, 28))

        email = f"{username}@example.com"
        from_location = random.choice(ORIGIN_LOCATIONS)
        live = random.choice(CITIES)
        bio = random.choice(BIOS)
        tagline = random.choice(TAGLINES)

        # Rotate through photos
        profile_photo = photos[i % len(photos)]

        # Create user
        user = User.objects.create(
            id=uuid.uuid4(),
            username=username,
            first_name=first_name,
            last_name=last_name,
            email=email,
            age=age,
            date_of_birth=birth_date,
            height=height,
            from_location=from_location,
            live=live,
            bio=bio,
            tagline=tagline,
            profile_photo=profile_photo,
            is_online=random.choice([True, False]),
            last_seen=datetime.now() - timedelta(hours=random.randint(0, 72))
        )

        # Create answers for all mandatory questions
        answers_created = 0
        for question in questions:
            answer_data = generate_realistic_answers(question, is_male)

            UserAnswer.objects.create(
                user=user,
                question=question,
                me_answer=answer_data['me_answer'],
                me_importance=answer_data['me_importance'],
                me_open_to_all=answer_data['me_open_to_all'],
                me_share=True,
                looking_for_answer=answer_data['looking_for_answer'],
                looking_for_importance=answer_data['looking_for_importance'],
                looking_for_open_to_all=answer_data['looking_for_open_to_all'],
                looking_for_share=True
            )
            answers_created += 1

        created_users.append(user)
        print(f"Created user {i+1}/{count}: {username} ({first_name} {last_name}) - {answers_created} answers")

    print(f"\n✅ Successfully created {len(created_users)} users with complete answer sets!")
    return created_users

if __name__ == '__main__':
    print("=== Creating 100 Diverse Dummy Users ===\n")
    users = create_dummy_users(100)

    print(f"\n=== Summary ===")
    print(f"Total users in database: {User.objects.count()}")
    print(f"Users with answers: {User.objects.filter(answers__isnull=False).distinct().count()}")
    print(f"Total user answers: {UserAnswer.objects.count()}")

    # Sample a few users to show variety
    print(f"\n=== Sample Created Users ===")
    for user in users[:5]:
        answer_count = user.answers.count()
        print(f"- {user.username}: {user.first_name} {user.last_name}, {user.age}, {user.live} ({answer_count} answers)")