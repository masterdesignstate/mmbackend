import json
import os
import sys
import django
from datetime import datetime
from django.core.files.base import ContentFile
import requests
from io import BytesIO
from PIL import Image
import random

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mmbackend.settings')
django.setup()

from api.models import User, Question, UserAnswer, Tag
from django.contrib.auth.hashers import make_password
from django.utils import timezone

def download_random_avatar(username):
    """Download a random avatar for the user"""
    try:
        # Using DiceBear API for random avatars
        url = f"https://api.dicebear.com/7.x/avataaars/svg?seed={username}"
        response = requests.get(url)
        if response.status_code == 200:
            return ContentFile(response.content, name=f"{username}_avatar.svg")
    except Exception as e:
        print(f"Error downloading avatar for {username}: {e}")
    
    return None

def create_mandatory_questions():
    """Create the actual mandatory questions"""
    questions_data = [
        # Gender questions
        {
            "text": "How strongly do you identify as Male?",
            "tags": ["trait", "value"],
            "question_type": "mandatory"
        },
        {
            "text": "How strongly do you identify as Female?",
            "tags": ["trait", "value"],
            "question_type": "mandatory"
        },
        
        # Relationship questions
        {
            "text": "How much are you interested in Friends?",
            "tags": ["lifestyle", "value"],
            "question_type": "mandatory"
        },
        {
            "text": "How much are you interested in Hookups?",
            "tags": ["lifestyle", "value"],
            "question_type": "mandatory"
        },
        {
            "text": "How much are you interested in Dating?",
            "tags": ["lifestyle", "value"],
            "question_type": "mandatory"
        },
        {
            "text": "How much are you interested in a Partner?",
            "tags": ["lifestyle", "value"],
            "question_type": "mandatory"
        },
        
        # Religion questions
        {
            "text": "How often do you follow religious practices?",
            "tags": ["lifestyle", "value"],
            "question_type": "mandatory"
        },
        
        # Faith questions
        {
            "text": "How strongly do you identify as Christian?",
            "tags": ["value", "lifestyle"],
            "question_type": "mandatory"
        },
        {
            "text": "How strongly do you identify as Muslim?",
            "tags": ["value", "lifestyle"],
            "question_type": "mandatory"
        },
        {
            "text": "How strongly do you identify as Hindu?",
            "tags": ["value", "lifestyle"],
            "question_type": "mandatory"
        },
        {
            "text": "How strongly do you identify as Jewish?",
            "tags": ["value", "lifestyle"],
            "question_type": "mandatory"
        },
        {
            "text": "How strongly do you identify as Buddhist?",
            "tags": ["value", "lifestyle"],
            "question_type": "mandatory"
        },
        {
            "text": "How strongly do you identify as Pagan?",
            "tags": ["value", "lifestyle"],
            "question_type": "mandatory"
        },
        {
            "text": "How strongly do you identify as Other religion?",
            "tags": ["value", "lifestyle"],
            "question_type": "mandatory"
        },
        {
            "text": "How strongly do you identify as Spiritual (Nonreligious)?",
            "tags": ["value", "lifestyle"],
            "question_type": "mandatory"
        },
        {
            "text": "How strongly do you identify as Atheist?",
            "tags": ["value", "lifestyle"],
            "question_type": "mandatory"
        },
        {
            "text": "How strongly do you identify as Agnostic?",
            "tags": ["value", "lifestyle"],
            "question_type": "mandatory"
        },
        {
            "text": "How strongly do you identify as Nonspiritual?",
            "tags": ["value", "lifestyle"],
            "question_type": "mandatory"
        },
        
        # Exercise
        {
            "text": "How often do you exercise?",
            "tags": ["lifestyle", "hobby"],
            "question_type": "mandatory"
        },
        
        # Habits
        {
            "text": "How often do you consume Alcohol?",
            "tags": ["lifestyle", "hobby"],
            "question_type": "mandatory"
        },
        {
            "text": "How often do you consume Tobacco?",
            "tags": ["lifestyle", "hobby"],
            "question_type": "mandatory"
        },
        
        # Children
        {
            "text": "Do you have children?",
            "tags": ["lifestyle", "value"],
            "question_type": "mandatory"
        },
        {
            "text": "Do you want children?",
            "tags": ["lifestyle", "value"],
            "question_type": "mandatory"
        },
        
        # Education
        {
            "text": "What is your experience with Pre-High School education?",
            "tags": ["lifestyle", "value"],
            "question_type": "mandatory"
        },
        {
            "text": "What is your experience with High School education?",
            "tags": ["lifestyle", "value"],
            "question_type": "mandatory"
        },
        {
            "text": "What is your experience with Trade education?",
            "tags": ["lifestyle", "value"],
            "question_type": "mandatory"
        },
        {
            "text": "What is your experience with Undergraduate education?",
            "tags": ["lifestyle", "value"],
            "question_type": "mandatory"
        },
        {
            "text": "What is your experience with Master's education?",
            "tags": ["lifestyle", "value"],
            "question_type": "mandatory"
        },
        {
            "text": "What is your experience with Doctorate education?",
            "tags": ["lifestyle", "value"],
            "question_type": "mandatory"
        },
        
        # Diet
        {
            "text": "Do you eat meat?",
            "tags": ["lifestyle", "value"],
            "question_type": "mandatory"
        },
        {
            "text": "Do you identify as pescatarian?",
            "tags": ["lifestyle", "value"],
            "question_type": "mandatory"
        },
        {
            "text": "Do you identify as vegetarian?",
            "tags": ["lifestyle", "value"],
            "question_type": "mandatory"
        },
        {
            "text": "Do you identify as vegan?",
            "tags": ["lifestyle", "value"],
            "question_type": "mandatory"
        },
        
        # Politics
        {
            "text": "How politically engaged are you?",
            "tags": ["value", "lifestyle"],
            "question_type": "mandatory"
        },
        
        # Ideology
        {
            "text": "How strongly do you identify as Liberal?",
            "tags": ["value", "lifestyle"],
            "question_type": "mandatory"
        },
        {
            "text": "How strongly do you identify as Moderate?",
            "tags": ["value", "lifestyle"],
            "question_type": "mandatory"
        },
        {
            "text": "How strongly do you identify as Conservative?",
            "tags": ["value", "lifestyle"],
            "question_type": "mandatory"
        },
        {
            "text": "How strongly do you identify as Non-binary politically?",
            "tags": ["value", "lifestyle"],
            "question_type": "mandatory"
        },
        {
            "text": "How strongly do you identify as Anarchist?",
            "tags": ["value", "lifestyle"],
            "question_type": "mandatory"
        }
    ]
    
    created_questions = []
    
    for q_data in questions_data:
        question, created = Question.objects.get_or_create(
            text=q_data["text"],
            defaults={
                "question_type": q_data["question_type"],
                "is_required_for_match": True
            }
        )
        
        if created:
            # Add tags
            for tag_name in q_data["tags"]:
                tag, _ = Tag.objects.get_or_create(name=tag_name)
                question.tags.add(tag)
            print(f"Created question: {question.text}")
        else:
            print(f"Question already exists: {question.text}")
        
        created_questions.append(question)
    
    return created_questions

def generate_realistic_answers():
    """Generate realistic answers for the mandatory questions"""
    
    # Gender answers (most people identify strongly with one gender)
    gender_answers = [
        {"me": 5, "looking_for": 4, "open_to_all": False},  # Strong male identification
        {"me": 1, "looking_for": 4, "open_to_all": False},  # Strong female identification
    ]
    
    # Relationship preferences (varied but realistic)
    relationship_answers = [
        {"me": 3, "looking_for": 4, "open_to_all": False},  # Friends
        {"me": 2, "looking_for": 3, "open_to_all": False},  # Hookups
        {"me": 4, "looking_for": 4, "open_to_all": False},  # Dating
        {"me": 5, "looking_for": 5, "open_to_all": False},  # Partner
    ]
    
    # Religion frequency
    religion_frequency = [
        {"me": 2, "looking_for": 3, "open_to_all": False},  # Rarely
        {"me": 3, "looking_for": 3, "open_to_all": False},  # Sometimes
        {"me": 1, "looking_for": 2, "open_to_all": False},  # Never
    ]
    
    # Faith identification (most people identify with one faith strongly)
    faith_answers = [
        {"me": 5, "looking_for": 4, "open_to_all": False},  # Strong Christian
        {"me": 1, "looking_for": 3, "open_to_all": False},  # Not Christian
        {"me": 5, "looking_for": 4, "open_to_all": False},  # Strong Muslim
        {"me": 1, "looking_for": 3, "open_to_all": False},  # Not Muslim
        {"me": 5, "looking_for": 4, "open_to_all": False},  # Strong Hindu
        {"me": 1, "looking_for": 3, "open_to_all": False},  # Not Hindu
        {"me": 5, "looking_for": 4, "open_to_all": False},  # Strong Jewish
        {"me": 1, "looking_for": 3, "open_to_all": False},  # Not Jewish
        {"me": 5, "looking_for": 4, "open_to_all": False},  # Strong Buddhist
        {"me": 1, "looking_for": 3, "open_to_all": False},  # Not Buddhist
        {"me": 5, "looking_for": 4, "open_to_all": False},  # Strong Pagan
        {"me": 1, "looking_for": 3, "open_to_all": False},  # Not Pagan
        {"me": 5, "looking_for": 4, "open_to_all": False},  # Strong Other
        {"me": 1, "looking_for": 3, "open_to_all": False},  # Not Other
        {"me": 5, "looking_for": 4, "open_to_all": False},  # Strong Spiritual
        {"me": 1, "looking_for": 3, "open_to_all": False},  # Not Spiritual
        {"me": 5, "looking_for": 4, "open_to_all": False},  # Strong Atheist
        {"me": 1, "looking_for": 3, "open_to_all": False},  # Not Atheist
        {"me": 5, "looking_for": 4, "open_to_all": False},  # Strong Agnostic
        {"me": 1, "looking_for": 3, "open_to_all": False},  # Not Agnostic
        {"me": 5, "looking_for": 4, "open_to_all": False},  # Strong Nonspiritual
        {"me": 1, "looking_for": 3, "open_to_all": False},  # Not Nonspiritual
    ]
    
    # Exercise frequency
    exercise_answers = [
        {"me": 3, "looking_for": 3, "open_to_all": False},  # Sometimes
        {"me": 4, "looking_for": 4, "open_to_all": False},  # Regularly
        {"me": 2, "looking_for": 3, "open_to_all": False},  # Rarely
    ]
    
    # Habits
    alcohol_answers = [
        {"me": 3, "looking_for": 3, "open_to_all": False},  # Socially
        {"me": 2, "looking_for": 2, "open_to_all": False},  # Rarely
        {"me": 4, "looking_for": 4, "open_to_all": False},  # Regularly
    ]
    
    tobacco_answers = [
        {"me": 1, "looking_for": 1, "open_to_all": False},  # Never
        {"me": 2, "looking_for": 2, "open_to_all": False},  # Rarely
        {"me": 3, "looking_for": 3, "open_to_all": False},  # Socially
    ]
    
    # Children
    have_kids_answers = [
        {"me": 1, "looking_for": 3, "open_to_all": False},  # Don't have
        {"me": 5, "looking_for": 4, "open_to_all": False},  # Have
    ]
    
    want_kids_answers = [
        {"me": 3, "looking_for": 3, "open_to_all": False},  # Unsure
        {"me": 5, "looking_for": 4, "open_to_all": False},  # Want
        {"me": 1, "looking_for": 2, "open_to_all": False},  # Don't want
    ]
    
    # Education (most people have completed high school, some college)
    education_answers = [
        {"me": 5, "looking_for": 3, "open_to_all": False},  # Completed
        {"me": 3, "looking_for": 3, "open_to_all": False},  # Attended
        {"me": 1, "looking_for": 2, "open_to_all": False},  # Did not attend
    ]
    
    # Diet
    diet_answers = [
        {"me": 5, "looking_for": 3, "open_to_all": False},  # Yes
        {"me": 1, "looking_for": 2, "open_to_all": False},  # No
    ]
    
    # Politics
    politics_answers = [
        {"me": 3, "looking_for": 3, "open_to_all": False},  # Active
        {"me": 2, "looking_for": 2, "open_to_all": False},  # Observant
        {"me": 4, "looking_for": 4, "open_to_all": False},  # Fervent
    ]
    
    # Ideology
    ideology_answers = [
        {"me": 5, "looking_for": 4, "open_to_all": False},  # Strong Liberal
        {"me": 1, "looking_for": 3, "open_to_all": False},  # Not Liberal
        {"me": 5, "looking_for": 4, "open_to_all": False},  # Strong Moderate
        {"me": 1, "looking_for": 3, "open_to_all": False},  # Not Moderate
        {"me": 5, "looking_for": 4, "open_to_all": False},  # Strong Conservative
        {"me": 1, "looking_for": 3, "open_to_all": False},  # Not Conservative
        {"me": 5, "looking_for": 4, "open_to_all": False},  # Strong Non-binary
        {"me": 1, "looking_for": 3, "open_to_all": False},  # Not Non-binary
        {"me": 5, "looking_for": 4, "open_to_all": False},  # Strong Anarchist
        {"me": 1, "looking_for": 3, "open_to_all": False},  # Not Anarchist
    ]
    
    return {
        "gender": gender_answers,
        "relationship": relationship_answers,
        "religion_frequency": religion_frequency,
        "faith": faith_answers,
        "exercise": exercise_answers,
        "alcohol": alcohol_answers,
        "tobacco": tobacco_answers,
        "have_kids": have_kids_answers,
        "want_kids": want_kids_answers,
        "education": education_answers,
        "diet": diet_answers,
        "politics": politics_answers,
        "ideology": ideology_answers
    }

def generate_user_answers(user, questions, answer_templates):
    """Generate realistic answers for a specific user"""
    
    # Create a personality profile for this user
    personality = {
        "gender_preference": random.choice([0, 1]),  # 0 for male, 1 for female
        "religion": random.choice([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]),  # Which faith they identify with
        "political_ideology": random.choice([0, 1, 2, 3, 4]),  # Which ideology they identify with
        "has_kids": random.choice([True, False]),
        "wants_kids": random.choice([0, 1, 2]),  # 0=don't want, 1=unsure, 2=want
        "education_level": random.choice([0, 1, 2, 3, 4, 5]),  # Which education level they completed
        "diet_preference": random.choice([0, 1, 2, 3]),  # 0=omnivore, 1=pescatarian, 2=vegetarian, 3=vegan
    }
    
    answers = []
    
    for i, question in enumerate(questions):
        question_text = question.text.lower()
        
        if "male" in question_text:
            if personality["gender_preference"] == 0:
                me_answer = 5
                looking_for_answer = 4
            else:
                me_answer = 1
                looking_for_answer = 3
                
        elif "female" in question_text:
            if personality["gender_preference"] == 1:
                me_answer = 5
                looking_for_answer = 4
            else:
                me_answer = 1
                looking_for_answer = 3
                
        elif "friend" in question_text:
            template = random.choice(answer_templates["relationship"])
            me_answer = template["me"]
            looking_for_answer = template["looking_for"]
            
        elif "hookup" in question_text:
            template = random.choice(answer_templates["relationship"])
            me_answer = template["me"]
            looking_for_answer = template["looking_for"]
            
        elif "date" in question_text:
            template = random.choice(answer_templates["relationship"])
            me_answer = template["me"]
            looking_for_answer = template["looking_for"]
            
        elif "partner" in question_text:
            template = random.choice(answer_templates["relationship"])
            me_answer = template["me"]
            looking_for_answer = template["looking_for"]
            
        elif "religious practices" in question_text:
            template = random.choice(answer_templates["religion_frequency"])
            me_answer = template["me"]
            looking_for_answer = template["looking_for"]
            
        elif "christian" in question_text:
            if personality["religion"] == 0:
                me_answer = 5
                looking_for_answer = 4
            else:
                me_answer = 1
                looking_for_answer = 3
                
        elif "muslim" in question_text:
            if personality["religion"] == 1:
                me_answer = 5
                looking_for_answer = 4
            else:
                me_answer = 1
                looking_for_answer = 3
                
        elif "hindu" in question_text:
            if personality["religion"] == 2:
                me_answer = 5
                looking_for_answer = 4
            else:
                me_answer = 1
                looking_for_answer = 3
                
        elif "jewish" in question_text:
            if personality["religion"] == 3:
                me_answer = 5
                looking_for_answer = 4
            else:
                me_answer = 1
                looking_for_answer = 3
                
        elif "buddhist" in question_text:
            if personality["religion"] == 4:
                me_answer = 5
                looking_for_answer = 4
            else:
                me_answer = 1
                looking_for_answer = 3
                
        elif "pagan" in question_text:
            if personality["religion"] == 5:
                me_answer = 5
                looking_for_answer = 4
            else:
                me_answer = 1
                looking_for_answer = 3
                
        elif "other religion" in question_text:
            if personality["religion"] == 6:
                me_answer = 5
                looking_for_answer = 4
            else:
                me_answer = 1
                looking_for_answer = 3
                
        elif "spiritual" in question_text:
            if personality["religion"] == 7:
                me_answer = 5
                looking_for_answer = 4
            else:
                me_answer = 1
                looking_for_answer = 3
                
        elif "atheist" in question_text:
            if personality["religion"] == 8:
                me_answer = 5
                looking_for_answer = 4
            else:
                me_answer = 1
                looking_for_answer = 3
                
        elif "agnostic" in question_text:
            if personality["religion"] == 9:
                me_answer = 5
                looking_for_answer = 4
            else:
                me_answer = 1
                looking_for_answer = 3
                
        elif "nonspiritual" in question_text:
            if personality["religion"] == 10:
                me_answer = 5
                looking_for_answer = 4
            else:
                me_answer = 1
                looking_for_answer = 3
                
        elif "exercise" in question_text:
            template = random.choice(answer_templates["exercise"])
            me_answer = template["me"]
            looking_for_answer = template["looking_for"]
            
        elif "alcohol" in question_text:
            template = random.choice(answer_templates["alcohol"])
            me_answer = template["me"]
            looking_for_answer = template["looking_for"]
            
        elif "tobacco" in question_text:
            template = random.choice(answer_templates["tobacco"])
            me_answer = template["me"]
            looking_for_answer = template["looking_for"]
            
        elif "have children" in question_text:
            if personality["has_kids"]:
                me_answer = 5
                looking_for_answer = 4
            else:
                me_answer = 1
                looking_for_answer = 3
                
        elif "want children" in question_text:
            if personality["wants_kids"] == 0:
                me_answer = 1
                looking_for_answer = 2
            elif personality["wants_kids"] == 1:
                me_answer = 3
                looking_for_answer = 3
            else:  # wants_kids == 2
                me_answer = 5
                looking_for_answer = 4
                
        elif "pre-high school" in question_text:
            if personality["education_level"] == 0:
                me_answer = 5
                looking_for_answer = 3
            else:
                me_answer = 1
                looking_for_answer = 2
                
        elif "high school" in question_text:
            if personality["education_level"] == 1:
                me_answer = 5
                looking_for_answer = 3
            else:
                me_answer = 3
                looking_for_answer = 3
                
        elif "trade" in question_text:
            if personality["education_level"] == 2:
                me_answer = 5
                looking_for_answer = 3
            else:
                me_answer = 1
                looking_for_answer = 2
                
        elif "undergraduate" in question_text:
            if personality["education_level"] == 3:
                me_answer = 5
                looking_for_answer = 3
            else:
                me_answer = 3
                looking_for_answer = 3
                
        elif "master" in question_text:
            if personality["education_level"] == 4:
                me_answer = 5
                looking_for_answer = 3
            else:
                me_answer = 1
                looking_for_answer = 2
                
        elif "doctorate" in question_text:
            if personality["education_level"] == 5:
                me_answer = 5
                looking_for_answer = 3
            else:
                me_answer = 1
                looking_for_answer = 2
                
        elif "eat meat" in question_text:
            if personality["diet_preference"] == 0:  # omnivore
                me_answer = 5
                looking_for_answer = 3
            else:
                me_answer = 1
                looking_for_answer = 2
                
        elif "pescatarian" in question_text:
            if personality["diet_preference"] == 1:
                me_answer = 5
                looking_for_answer = 3
            else:
                me_answer = 1
                looking_for_answer = 2
                
        elif "vegetarian" in question_text:
            if personality["diet_preference"] == 2:
                me_answer = 5
                looking_for_answer = 3
            else:
                me_answer = 1
                looking_for_answer = 2
                
        elif "vegan" in question_text:
            if personality["diet_preference"] == 3:
                me_answer = 5
                looking_for_answer = 3
            else:
                me_answer = 1
                looking_for_answer = 2
                
        elif "politically engaged" in question_text:
            template = random.choice(answer_templates["politics"])
            me_answer = template["me"]
            looking_for_answer = template["looking_for"]
            
        elif "liberal" in question_text:
            if personality["political_ideology"] == 0:
                me_answer = 5
                looking_for_answer = 4
            else:
                me_answer = 1
                looking_for_answer = 3
                
        elif "moderate" in question_text:
            if personality["political_ideology"] == 1:
                me_answer = 5
                looking_for_answer = 4
            else:
                me_answer = 1
                looking_for_answer = 3
                
        elif "conservative" in question_text:
            if personality["political_ideology"] == 2:
                me_answer = 5
                looking_for_answer = 4
            else:
                me_answer = 1
                looking_for_answer = 3
                
        elif "non-binary" in question_text:
            if personality["political_ideology"] == 3:
                me_answer = 5
                looking_for_answer = 4
            else:
                me_answer = 1
                looking_for_answer = 3
                
        elif "anarchist" in question_text:
            if personality["political_ideology"] == 4:
                me_answer = 5
                looking_for_answer = 4
            else:
                me_answer = 1
                looking_for_answer = 3
                
        else:
            # Default answer
            me_answer = 3
            looking_for_answer = 3
        
        # Create the answer
        UserAnswer.objects.create(
            user=user,
            question=question,
            me_answer=me_answer,
            me_open_to_all=False,
            me_multiplier=random.choice([1, 2, 3]),
            me_share=True,
            looking_for_answer=looking_for_answer,
            looking_for_open_to_all=False,
            looking_for_multiplier=random.choice([1, 2, 3]),
            looking_for_share=True
        )

def import_users_from_json():
    """Import users from the JSON file"""
    
    # Load JSON data
    try:
        with open('dum.json', 'r', encoding='utf-8') as file:
            users_data = json.load(file)
    except FileNotFoundError:
        print("Error: dum.json file not found in the current directory")
        return
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        return
    
    print(f"Found {len(users_data)} users in JSON file")
    
    # Create mandatory questions
    print("\nCreating mandatory questions...")
    mandatory_questions = create_mandatory_questions()
    
    # Generate answer templates
    answer_templates = generate_realistic_answers()
    
    # Import users
    created_count = 0
    skipped_count = 0
    
    for user_data in users_data:
        try:
            # Extract user data
            first_name = user_data.get('First', '')
            last_name = user_data.get('Last', '')
            username = user_data.get('Username', '')
            tag_line = user_data.get('Tag Line', '')
            dob_str = user_data.get('DOB', '')
            city = user_data.get('City', '')
            bio = user_data.get('Bio', '')
            
            # Skip if username already exists
            if User.objects.filter(username=username).exists():
                print(f"Skipping {username} - already exists")
                skipped_count += 1
                continue
            
            # Parse date of birth
            date_of_birth = None
            if dob_str:
                try:
                    # Parse the date string (format: "1988-09-24T00:00:00.000")
                    date_of_birth = datetime.strptime(dob_str.split('T')[0], '%Y-%m-%d').date()
                except:
                    pass
            
            # Calculate age
            age = None
            if date_of_birth:
                today = timezone.now().date()
                age = today.year - date_of_birth.year - ((today.month, today.day) < (date_of_birth.month, date_of_birth.day))
            
            # Create user
            user = User.objects.create(
                username=username,
                first_name=first_name,
                last_name=last_name,
                email=f"{username}@example.com",  # Generate email from username
                password=make_password('password123'),  # Default password
                date_of_birth=date_of_birth,
                age=age,
                city=city,
                bio=bio,
                is_active=True,
                is_staff=False,
                is_superuser=False
            )
            
            # Download and set profile photo
            avatar = download_random_avatar(username)
            if avatar:
                user.profile_photo.save(f"{username}_avatar.svg", avatar, save=True)
            
            # Create answers for all mandatory questions
            generate_user_answers(user, mandatory_questions, answer_templates)
            
            # Update questions answered count
            user.questions_answered_count = len(mandatory_questions)
            user.save()
            
            created_count += 1
            print(f"Created user: {username} ({first_name} {last_name})")
            
        except Exception as e:
            print(f"Error creating user {username}: {e}")
            continue
    
    print(f"\nImport completed!")
    print(f"Created: {created_count} users")
    print(f"Skipped: {skipped_count} users (already existed)")
    print(f"Total mandatory questions: {len(mandatory_questions)}")

if __name__ == "__main__":
    print("Starting user import from dum.json...")
    import_users_from_json() 