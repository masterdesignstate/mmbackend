import os
import sys
import django
import random
from django.contrib.auth.hashers import make_password
from django.utils import timezone

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mmbackend.settings')
django.setup()

from api.models import User, Question, UserAnswer, Tag

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

def generate_user_answers(user, questions):
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
    
    # Delete existing answers for this user
    UserAnswer.objects.filter(user=user).delete()
    
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
            me_answer = random.choice([3, 4, 5])
            looking_for_answer = random.choice([3, 4, 5])
            
        elif "hookup" in question_text:
            me_answer = random.choice([1, 2, 3])
            looking_for_answer = random.choice([2, 3, 4])
            
        elif "date" in question_text:
            me_answer = random.choice([3, 4, 5])
            looking_for_answer = random.choice([3, 4, 5])
            
        elif "partner" in question_text:
            me_answer = random.choice([4, 5])
            looking_for_answer = random.choice([4, 5])
            
        elif "religious practices" in question_text:
            me_answer = random.choice([1, 2, 3])
            looking_for_answer = random.choice([2, 3, 4])
            
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
            me_answer = random.choice([2, 3, 4])
            looking_for_answer = random.choice([2, 3, 4])
            
        elif "alcohol" in question_text:
            me_answer = random.choice([1, 2, 3, 4])
            looking_for_answer = random.choice([1, 2, 3, 4])
            
        elif "tobacco" in question_text:
            me_answer = random.choice([1, 2, 3])
            looking_for_answer = random.choice([1, 2, 3])
            
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
            me_answer = random.choice([2, 3, 4])
            looking_for_answer = random.choice([2, 3, 4])
            
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

def update_all_users():
    """Update all existing users with correct mandatory questions and answers"""
    
    print("Creating mandatory questions...")
    mandatory_questions = create_mandatory_questions()
    
    print(f"Found {len(mandatory_questions)} mandatory questions")
    
    # Get all users
    users = User.objects.all()
    print(f"Found {users.count()} users to update")
    
    updated_count = 0
    
    for user in users:
        try:
            print(f"Updating answers for user: {user.username}")
            generate_user_answers(user, mandatory_questions)
            
            # Update questions answered count
            user.questions_answered_count = len(mandatory_questions)
            user.save()
            
            updated_count += 1
            
        except Exception as e:
            print(f"Error updating user {user.username}: {e}")
            continue
    
    print(f"\nUpdate completed!")
    print(f"Updated: {updated_count} users")
    print(f"Total mandatory questions: {len(mandatory_questions)}")

if __name__ == "__main__":
    print("Starting user answer updates...")
    update_all_users() 