import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth import authenticate, login
from django.db import transaction
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from django.conf import settings
from datetime import datetime
from .models import User

logger = logging.getLogger(__name__)


ADMIN_EMAILS = {
    email.strip().lower()
    for email in getattr(settings, 'ADMIN_EMAILS', [])
    if isinstance(email, str) and email.strip()
}


@csrf_exempt
@require_http_methods(["POST"])
def user_signup(request):
    """
    Create a new user account with email and password.
    
    Request payload:
    - email: User's email address
    - password: User's password (min 8 characters)
    
    Returns:
    - success: Boolean indicating success
    - user_id: UUID of the created user
    - message: Success message
    """
    try:
        print("🚀 === USER SIGNUP ENDPOINT CALLED ===")
        print(f"📥 Request method: {request.method}")
        print(f"📥 Request headers: {dict(request.headers)}")
        print(f"📥 Request body: {request.body}")
        
        # Parse request data
        data = json.loads(request.body)
        email = data.get('email')
        password = data.get('password')
        
        print(f"📝 USER SIGNUP REQUEST for email: {email}")
        print(f"🔑 Password length: {len(password) if password else 0}")
        print(f"📊 Parsed data: {data}")
        
        # Validate required fields
        if not email or not password:
            print("❌ Missing required fields")
            print(f"   Email present: {bool(email)}")
            print(f"   Password present: {bool(password)}")
            return JsonResponse({
                'error': 'Email and password are required'
            }, status=400)
        
        # Validate email format
        if '@' not in email or '.' not in email:
            print(f"❌ Invalid email format: {email}")
            return JsonResponse({
                'error': 'Invalid email format'
            }, status=400)
        
        # Validate password length
        if len(password) < 8:
            print(f"❌ Password too short: {len(password)} characters")
            return JsonResponse({
                'error': 'Password must be at least 8 characters long'
            }, status=400)
        
        print(f"✅ Validation passed for email: {email}")
        
        # Check if user already exists
        existing_user = User.objects.filter(email=email).first()
        if existing_user:
            print(f"❌ User already exists with email: {email}")
            print(f"   Existing user ID: {existing_user.id}")
            print(f"   Existing user username: {existing_user.username}")
            return JsonResponse({
                'error': 'User with this email already exists'
            }, status=409)
        
        print(f"✅ No existing user found, proceeding with creation")
        
        # Create the user
        with transaction.atomic():
            print(f"🔒 Starting database transaction")
            user = User.objects.create(
                username=email,  # Use email as username for now
                email=email,
                password=make_password(password),
                is_active=True,
                date_joined=timezone.now()
            )
            
            print(f"✅ USER CREATED successfully!")
            print(f"   User ID: {user.id}")
            print(f"   Email: {user.email}")
            print(f"   Username: {user.username}")
            print(f"   Is Active: {user.is_active}")
            print(f"   Date Joined: {user.date_joined}")
            
            # Log the user in to create a session
            login(request, user)
            print(f"🔑 User logged in successfully with session")
            print(f"   Session key: {request.session.session_key}")
            print(f"   Session data: {dict(request.session)}")
            print(f"   User in session: {request.user.id if request.user.is_authenticated else 'Not authenticated'}")
            
            response_data = {
                'success': True,
                'user_id': str(user.id),
                'message': 'User account created successfully'
            }
            
            print(f"📤 Sending response: {response_data}")
            return JsonResponse(response_data, status=201)
            
    except json.JSONDecodeError as e:
        print(f"❌ JSON decode error: {str(e)}")
        print(f"   Raw request body: {request.body}")
        return JsonResponse({
            'error': 'Invalid JSON format'
        }, status=400)
    except Exception as e:
        print(f"❌ Unexpected error in user_signup: {str(e)}")
        import traceback
        traceback.print_exc()
        logger.error(f"Error in user_signup: {str(e)}")
        return JsonResponse({
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@transaction.atomic
def user_personal_details(request):
    """
    Update user personal details after signup.
    
    Request payload:
    - user_id: UUID of the user
    - full_name: User's full name
    - username: Desired username
    - tagline: Short tagline (max 40 chars)
    - date_of_birth: Date of birth in YYYY-MM-DD format
    - height: Height in feet and inches format (e.g., "5' 11"")
    - from: User's original location
    - live: User's current city
    - bio: User's bio (max 160 chars)
    
    Returns:
    - success: Boolean indicating success
    - message: Success message
    """
    try:
        print("🚀 === PERSONAL DETAILS ENDPOINT CALLED ===")
        print(f"📥 Request method: {request.method}")
        print(f"📥 Request headers: {dict(request.headers)}")
        print(f"📥 Request body: {request.body}")
        
        # Parse request data
        data = json.loads(request.body)
        user_id = data.get('user_id')
        
        print(f"📝 PERSONAL DETAILS REQUEST for user: {user_id}")
        print(f"📊 Parsed data: {data}")
        
        # Validate required fields
        required_fields = ['user_id', 'full_name', 'username', 'date_of_birth', 'from', 'live']
        missing_fields = [field for field in required_fields if field not in data or not data.get(field)]
        
        if missing_fields:
            print(f"❌ Missing required fields: {missing_fields}")
            print(f"   Available fields: {list(data.keys())}")
            return JsonResponse({
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            }, status=400)
        
        print(f"✅ All required fields present")
        
        # Get the user
        try:
            user = User.objects.get(id=user_id)
            print(f"✅ User found: {user.id} - {user.email}")
        except User.DoesNotExist:
            print(f"❌ User not found with ID: {user_id}")
            return JsonResponse({
                'error': 'User not found'
            }, status=404)
        
        # Parse date of birth
        try:
            date_of_birth = datetime.strptime(data.get('date_of_birth'), '%Y-%m-%d').date()
            print(f"📅 Date of birth parsed: {date_of_birth}")
        except ValueError as e:
            print(f"❌ Invalid date format: {data.get('date_of_birth')}")
            print(f"   Error: {str(e)}")
            return JsonResponse({
                'error': 'Invalid date format. Expected YYYY-MM-DD'
            }, status=400)
        
        # Calculate age
        today = timezone.now().date()
        age = today.year - date_of_birth.year - ((today.month, today.day) < (date_of_birth.month, date_of_birth.day))
        print(f"🎂 Calculated age: {age}")
        
        # Validate age (must be 18+)
        if age < 18:
            print(f"❌ User too young: {age} years old")
            return JsonResponse({
                'error': 'User must be at least 18 years old'
            }, status=400)
        
        print(f"✅ Age validation passed: {age} years old")
        
        # Check if username is already taken
        username = data.get('username')
        existing_username = User.objects.filter(username=username).exclude(id=user_id).first()
        if existing_username:
            print(f"❌ Username already taken: {username}")
            print(f"   Taken by user: {existing_username.id} - {existing_username.email}")
            return JsonResponse({
                'error': 'Username is already taken'
            }, status=409)
        
        print(f"✅ Username available: {username}")
        
        # Extract height components if provided
        height_cm = None
        height = data.get('height', '')
        print(f"📏 Height input: '{height}'")
        
        if height and "'" in height and '"' in height:
            try:
                # Parse height like "5' 11"" to get feet and inches
                height_parts = height.replace('"', '').split("'")
                feet = int(height_parts[0].strip())
                inches = int(height_parts[1].strip())
                height_cm = (feet * 12 + inches) * 2.54  # Convert to cm
                print(f"📏 Height parsed: {feet}' {inches}\" = {height_cm:.1f} cm")
            except (ValueError, IndexError) as e:
                print(f"⚠️ Could not parse height: {height}")
                print(f"   Error: {str(e)}")
        else:
            print(f"📏 No height provided or invalid format")
        
        print(f"🔒 Starting database transaction")
        
        # Update user with personal details
        old_first_name = user.first_name
        old_last_name = user.last_name
        old_username = user.username
        
        # Handle full name splitting more intelligently
        full_name = data.get('full_name', '').strip()
        if full_name:
            name_parts = full_name.split()
            if len(name_parts) == 1:
                # Single name - put it in first_name
                user.first_name = name_parts[0]
                user.last_name = ''
            else:
                # Multiple names - first goes to first_name, rest to last_name
                user.first_name = name_parts[0]
                user.last_name = ' '.join(name_parts[1:])
        else:
            user.first_name = ''
            user.last_name = ''
        user.username = username
        user.date_of_birth = date_of_birth
        user.age = age
        user.height = int(height_cm) if height_cm else None
        user.from_location = data.get('from')
        user.live = data.get('live')
        user.tagline = data.get('tagline', '')[:40]  # Limit to 40 characters
        user.bio = data.get('bio', '')[:160]  # Limit to 160 characters
        
        print(f"📝 User data updates:")
        print(f"   First name: '{old_first_name}' → '{user.first_name}'")
        print(f"   Last name: '{old_last_name}' → '{user.last_name}'")
        print(f"   Username: '{old_username}' → '{user.username}'")
        print(f"   Date of birth: {user.date_of_birth}")
        print(f"   Age: {user.age}")
        print(f"   Height: {user.height} cm")
        print(f"   From: {user.from_location}")
        print(f"   Live: {user.live}")
        print(f"   Tagline: '{user.tagline}'")
        print(f"   Bio: '{user.bio}'")
        
        # Save the user
        user.save()
        
        print(f"✅ PERSONAL DETAILS UPDATED successfully for user: {user_id}")
        
        response_data = {
            'success': True,
            'message': 'Personal details updated successfully',
            'user_data': {
                'id': str(user.id),
                'username': user.username,
                'full_name': f"{user.first_name} {user.last_name}".strip(),
                'age': user.age,
                'from': user.from_location,
                'live': user.live,
                'bio': user.bio
            }
        }
        
        print(f"📤 Sending response: {response_data}")
        return JsonResponse(response_data, status=200)
        
    except json.JSONDecodeError as e:
        print(f"❌ JSON decode error: {str(e)}")
        print(f"   Raw request body: {request.body}")
        return JsonResponse({
            'error': 'Invalid JSON format'
        }, status=400)
    except Exception as e:
        print(f"❌ Unexpected error in user_personal_details: {str(e)}")
        import traceback
        traceback.print_exc()
        logger.error(f"Error in user_personal_details: {str(e)}")
        return JsonResponse({
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def user_login(request):
    """
    Authenticate user with email and password.
    
    Request payload:
    - email: User's email address
    - password: User's password
    
    Returns:
    - success: Boolean indicating success
    - user_id: UUID of the authenticated user
    - message: Success message
    """
    try:
        print("🚀 === USER LOGIN ENDPOINT CALLED ===")
        print(f"📥 Request method: {request.method}")
        print(f"📥 Request headers: {dict(request.headers)}")
        print(f"📥 Request body: {request.body}")
        
        # Parse request data
        data = json.loads(request.body)
        email = data.get('email')
        password = data.get('password')
        
        print(f"🔐 USER LOGIN REQUEST for email: {email}")
        print(f"🔑 Password length: {len(password) if password else 0}")
        print(f"📊 Parsed data: {data}")
        
        # Validate required fields
        if not email or not password:
            print("❌ Missing required fields")
            print(f"   Email present: {bool(email)}")
            print(f"   Password present: {bool(password)}")
            return JsonResponse({
                'error': 'Email and password are required'
            }, status=400)
        
        print(f"✅ Validation passed, attempting authentication")
        
        # Check if user exists first
        try:
            user_exists = User.objects.filter(email=email).first()
            if user_exists:
                print(f"✅ User found in database: {user_exists.id} - {user_exists.email}")
                print(f"   Username: {user_exists.username}")
                print(f"   Is Active: {user_exists.is_active}")
                print(f"   Date Joined: {user_exists.date_joined}")
            else:
                print(f"❌ No user found with email: {email}")
        except Exception as e:
            print(f"⚠️ Error checking user existence: {str(e)}")
        
        # Authenticate user - try both email and username
        print(f"🔐 Attempting authentication with Django's authenticate()")
        
        # First try with email as username (how we created the user)
        user = authenticate(username=email, password=password)
        
        if user is None:
            print(f"⚠️ Authentication failed with email as username, trying alternative methods...")
            
            # Try to find the user first to debug
            try:
                found_user = User.objects.filter(email__iexact=email).first()
                if found_user:
                    print(f"🔍 Found user in database:")
                    print(f"   ID: {found_user.id}")
                    print(f"   Email: '{found_user.email}'")
                    print(f"   Username: '{found_user.username}'")
                    print(f"   Is Active: {found_user.is_active}")
                    print(f"   Has Password: {bool(found_user.password)}")
                    
                    # Try authenticating with the actual username from database
                    user = authenticate(username=found_user.username, password=password)
                    if user:
                        print(f"✅ Authentication successful with actual username!")
                    else:
                        print(f"❌ Still failed with actual username")
                        
                        # Debug: Check if password hash matches
                        from django.contrib.auth.hashers import check_password
                        password_matches = check_password(password, found_user.password)
                        print(f"🔐 Password check result: {password_matches}")
                        print(f"   Input password: '{password}'")
                        print(f"   Stored hash: {found_user.password[:20]}...")
                else:
                    print(f"❌ No user found with email: {email}")
            except Exception as e:
                print(f"⚠️ Error during debug lookup: {str(e)}")
        
        if user is None:
            print(f"❌ Authentication failed - invalid credentials")
            print(f"   This could mean:")
            print(f"   - Email doesn't exist")
            print(f"   - Password is wrong")
            print(f"   - Username field mismatch")
            print(f"   - Password hash issue")
            return JsonResponse({
                'error': 'Invalid email or password'
            }, status=401)
        
        print(f"✅ Authentication successful!")
        print(f"   Authenticated user: {user.id} - {user.email}")
        is_admin_user = (user.email or "").strip().lower() in ADMIN_EMAILS
        if is_admin_user:
            print(f"🛡️ Admin access granted for: {user.email}")

        if not user.is_active:
            print(f"❌ User account is deactivated")
            return JsonResponse({
                'error': 'User account is deactivated'
            }, status=403)
        
        print(f"✅ User account is active")
        
        # Get user data for response
        full_name = f"{user.first_name} {user.last_name}".strip()
        print(f"📝 User details:")
        print(f"   ID: {user.id}")
        print(f"   Username: {user.username}")
        print(f"   Email: {user.email}")
        print(f"   Full Name: '{full_name}'")
        print(f"   Age: {user.age}")
        print(f"   Live: {user.live}")
        print(f"   Admin: {'Yes' if is_admin_user else 'No'}")

        # Log the user in to create a session
        login(request, user)
        print(f"🔑 User logged in successfully with session")

        response_data = {
            'success': True,
            'user_id': str(user.id),
            'message': 'Login successful',
            'is_admin': is_admin_user,
            'user_data': {
                'id': str(user.id),
                'username': user.username,
                'email': user.email,
                'full_name': full_name,
                'age': user.age,
                'live': user.live,
                'is_admin': is_admin_user
            }
        }

        print(f"📤 Sending successful login response: {response_data}")
        return JsonResponse(response_data, status=200)
        
    except json.JSONDecodeError as e:
        print(f"❌ JSON decode error: {str(e)}")
        print(f"   Raw request body: {request.body}")
        return JsonResponse({
            'error': 'Invalid JSON format'
        }, status=400)
    except Exception as e:
        print(f"❌ Unexpected error in user_login: {str(e)}")
        import traceback
        traceback.print_exc()
        logger.error(f"Error in user_login: {str(e)}")
        return JsonResponse({
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def check_user_exists(request):
    """
    Check if a user with the given email already exists.
    
    Query parameters:
    - email: Email address to check
    
    Returns:
    - exists: Boolean indicating if user exists
    - message: Status message
    """
    try:
        print("🚀 === CHECK USER EXISTS ENDPOINT CALLED ===")
        print(f"📥 Request method: {request.method}")
        print(f"📥 Request headers: {dict(request.headers)}")
        print(f"📥 Query parameters: {dict(request.GET)}")
        
        email = request.GET.get('email')
        print(f"📧 Checking if user exists with email: {email}")
        
        if not email:
            print("❌ No email parameter provided")
            return JsonResponse({
                'error': 'Email parameter is required'
            }, status=400)
        
        print(f"✅ Email parameter received, checking database")
        
        # Check if user exists
        user = User.objects.filter(email=email).first()
        exists = user is not None
        
        if exists:
            print(f"✅ User found: {user.id} - {user.email}")
            print(f"   Username: {user.username}")
            print(f"   Is Active: {user.is_active}")
            print(f"   Date Joined: {user.date_joined}")
        else:
            print(f"❌ No user found with email: {email}")
        
        response_data = {
            'exists': exists,
            'message': 'User exists' if exists else 'User does not exist'
        }
        
        print(f"📤 Sending response: {response_data}")
        return JsonResponse(response_data, status=200)
        
    except Exception as e:
        print(f"❌ Unexpected error in check_user_exists: {str(e)}")
        import traceback
        traceback.print_exc()
        logger.error(f"Error in check_user_exists: {str(e)}")
        return JsonResponse({
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def check_onboarding_status(request):
    """
    Check the user's onboarding status and return which step they should be on.
    """
    try:
        print("🔍 === CHECK ONBOARDING STATUS ENDPOINT CALLED ===")
        print(f"📥 Request method: {request.method}")
        print(f"📥 Request headers: {dict(request.headers)}")
        print(f"📥 Request body: {request.body}")

        data = json.loads(request.body)
        email = data.get('email')
        
        print(f"🔍 Checking onboarding status for email: {email}")

        if not email:
            print("❌ No email provided")
            return JsonResponse({'error': 'Email is required'}, status=400)

        user = User.objects.filter(email=email).first()
        if not user:
            print(f"❌ User not found with email: {email}")
            return JsonResponse({'error': 'User not found'}, status=404)

        print(f"✅ User found: {user.username} (ID: {user.id})")
        is_admin_user = (user.email or '').strip().lower() in ADMIN_EMAILS
        if is_admin_user:
            print(f"🛡️ Admin user detected for onboarding bypass: {user.email}")
            response_data = {
                'step': 'complete',
                'step_url': '/dashboard',
                'progress': 100,
                'has_personal_details': True,
                'has_profile_photo': True,
                'has_gender_preferences': True,
                'user_id': str(user.id),
                'is_admin': True,
                'message': 'Admin users bypass onboarding requirements'
            }
            print(f"📤 Sending admin onboarding response: {response_data}")
            return JsonResponse(response_data)

        # Check onboarding progress - be more flexible with names
        has_personal_details = bool(
            (user.first_name or user.last_name) and  # At least one name field
            user.live and 
            user.bio and
            user.username != user.email  # Username was changed from email
        )
        
        has_profile_photo = bool(user.profile_photo)

        # Check if user has answered mandatory questions (questions 1-10)
        from .models import UserAnswer, Question
        mandatory_questions = Question.objects.filter(is_mandatory=True)
        mandatory_question_ids = set(mandatory_questions.values_list('id', flat=True))
        answered_question_ids = set(
            UserAnswer.objects.filter(user=user, question_id__in=mandatory_question_ids)
            .values_list('question_id', flat=True)
        )
        has_gender_preferences = len(answered_question_ids) >= min(10, len(mandatory_question_ids))
        
        print(f"📊 Onboarding status:")
        print(f"   Personal details: {'✅' if has_personal_details else '❌'}")
        print(f"   Profile photo: {'✅' if has_profile_photo else '❌'}")
        print(f"   Mandatory questions: {len(answered_question_ids)}/{len(mandatory_question_ids)} answered")
        print(f"   Questions complete: {'✅' if has_gender_preferences else '❌'}")
        
        # Determine which step user should be on
        if not has_personal_details:
            step = 'personal_details'
            step_url = '/auth/personal-details'
            progress = 10
        elif not has_profile_photo:
            step = 'add_photo'
            step_url = '/auth/add-photo'
            progress = 15
        elif not has_gender_preferences:
            step = 'gender'
            step_url = '/auth/gender'
            progress = 25
        else:
            step = 'complete'
            step_url = '/dashboard'
            progress = 100
        
        print(f"🎯 User should go to step: {step} ({step_url})")
        print(f"📈 Progress: {progress}%")
        
        response_data = {
            'step': step,
            'step_url': step_url,
            'progress': progress,
            'has_personal_details': has_personal_details,
            'has_profile_photo': has_profile_photo,
            'has_gender_preferences': has_gender_preferences,
            'user_id': str(user.id),
            'is_admin': is_admin_user
        }
        
        print(f"📤 Sending response: {response_data}")
        return JsonResponse(response_data)

    except json.JSONDecodeError as e:
        print(f"❌ JSON decode error: {str(e)}")
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
    except Exception as e:
        print(f"❌ Error in check_onboarding_status: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def update_profile_photo(request):
    """
    Update user's profile photo URL after Azure Blob upload.
    """
    try:
        print("📸 === UPDATE PROFILE PHOTO ENDPOINT CALLED ===")
        print(f"📥 Request method: {request.method}")
        print(f"📥 Request headers: {dict(request.headers)}")
        print(f"📥 Request body: {request.body}")

        data = json.loads(request.body)
        user_id = data.get('user_id')
        profile_photo_url = data.get('profile_photo_url')
        
        print(f"📸 UPDATE PROFILE PHOTO REQUEST for user: {user_id}")
        print(f"📸 Photo URL: {profile_photo_url}")

        if not user_id or not profile_photo_url:
            print("❌ Missing required fields")
            return JsonResponse({'error': 'User ID and profile photo URL are required'}, status=400)

        # Get the user
        try:
            user = User.objects.get(id=user_id)
            print(f"✅ User found: {user.id} - {user.email}")
        except User.DoesNotExist:
            print(f"❌ User not found with ID: {user_id}")
            return JsonResponse({'error': 'User not found'}, status=404)

        # Update profile photo URL
        old_photo_url = user.profile_photo
        user.profile_photo = profile_photo_url
        
        print(f"📸 Profile photo update:")
        print(f"   Old URL: {old_photo_url}")
        print(f"   New URL: {user.profile_photo}")
        
        # Save the user
        user.save()
        
        print(f"✅ PROFILE PHOTO UPDATED successfully for user: {user_id}")
        
        response_data = {
            'success': True,
            'message': 'Profile photo updated successfully',
            'profile_photo_url': profile_photo_url
        }
        
        print(f"📤 Sending response: {response_data}")
        return JsonResponse(response_data, status=200)
        
    except json.JSONDecodeError as e:
        print(f"❌ JSON decode error: {str(e)}")
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
    except Exception as e:
        print(f"❌ Error in update_profile_photo: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def test_endpoint(request):
    """
    Simple test endpoint to verify routing is working.
    """
    print("🧪 === TEST ENDPOINT CALLED ===")
    return JsonResponse({'message': 'Test endpoint working!', 'method': request.method})


@csrf_exempt
@require_http_methods(["POST"])
def upload_photo(request):
    """
    Upload photo to Azure Blob Storage via backend.
    """
    try:
        print("📸 === UPLOAD PHOTO ENDPOINT CALLED ===")
        print(f"📥 Request method: {request.method}")
        print(f"📥 Request headers: {dict(request.headers)}")
        print(f"📥 Request body length: {len(request.body)}")

        data = json.loads(request.body)
        user_id = data.get('user_id')
        file_name = data.get('file_name')
        file_type = data.get('file_type')
        file_data = data.get('file_data')  # Base64 encoded
        file_size = data.get('file_size')
        
        print(f"📸 UPLOAD PHOTO REQUEST for user: {user_id}")
        print(f"📸 File: {file_name} ({file_type}, {file_size} bytes)")

        if not all([user_id, file_name, file_type, file_data]):
            print("❌ Missing required fields")
            return JsonResponse({'error': 'Missing required fields'}, status=400)

        # Get the user
        try:
            user = User.objects.get(id=user_id)
            print(f"✅ User found: {user.id} - {user.email}")
        except User.DoesNotExist:
            print(f"❌ User not found with ID: {user_id}")
            return JsonResponse({'error': 'User not found'}, status=404)

        # Decode base64 data
        import base64
        try:
            file_bytes = base64.b64decode(file_data)
            print(f"✅ Base64 decoded successfully, size: {len(file_bytes)} bytes")
        except Exception as e:
            print(f"❌ Base64 decode failed: {str(e)}")
            return JsonResponse({'error': 'Invalid file data'}, status=400)

        # Generate unique blob name
        from datetime import datetime
        timestamp = datetime.now().isoformat().replace(':', '-').replace('.', '-')
        file_extension = file_name.split('.')[-1] if '.' in file_name else 'jpg'
        blob_name = f"profile-photos/user-{user_id}-{timestamp}.{file_extension}"
        
        print(f"📸 Generated blob name: {blob_name}")

        # Upload to Azure Blob Storage
        try:
            from azure.storage.blob import BlobServiceClient
            import os
            
            # Get Azure credentials from environment
            connection_string = os.getenv('AZURE_STORAGE_CONNECTION_STRING')
            if not connection_string:
                print("❌ Azure storage connection string not found")
                return JsonResponse({'error': 'Azure storage not configured'}, status=500)
            
            # Create blob service client
            blob_service_client = BlobServiceClient.from_connection_string(connection_string)
            container_client = blob_service_client.get_container_client("photos")
            block_blob_client = container_client.get_block_blob_client(blob_name)
            
            # Upload the file
            print(f"🚀 Starting Azure upload...")
            block_blob_client.upload_blob(file_bytes, overwrite=True, content_settings=None)
            
            # Get the public URL
            photo_url = block_blob_client.url
            print(f"✅ Azure upload successful: {photo_url}")
            
            # Update user profile with photo URL
            user.profile_photo = photo_url
            user.save()
            
            print(f"✅ User profile updated with photo URL")
            
            response_data = {
                'success': True,
                'message': 'Photo uploaded successfully',
                'photo_url': photo_url,
                'blob_name': blob_name
            }
            
            print(f"📤 Sending response: {response_data}")
            return JsonResponse(response_data, status=200)
            
        except Exception as e:
            print(f"❌ Azure upload failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return JsonResponse({'error': f'Azure upload failed: {str(e)}'}, status=500)
        
    except json.JSONDecodeError as e:
        print(f"❌ JSON decode error: {str(e)}")
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
    except Exception as e:
        print(f"❌ Error in upload_photo: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["DELETE"])
def delete_question(request, question_id):
    """
    Delete a question by ID.
    
    URL: /api/questions/{question_id}/
    Method: DELETE
    
    Returns:
    - success: Boolean indicating success
    - message: Success message
    """
    try:
        print("🗑️ === DELETE QUESTION ENDPOINT CALLED ===")
        print(f"📥 Request method: {request.method}")
        print(f"📥 Question ID: {question_id}")
        
        # Import Question model
        from .models import Question
        
        # Get the question
        try:
            question = Question.objects.get(id=question_id)
            print(f"✅ Question found: {question.id}")
            print(f"📝 Question text: {question.text}")
        except Question.DoesNotExist:
            print(f"❌ Question not found with ID: {question_id}")
            return JsonResponse({
                'error': 'Question not found'
            }, status=404)
        
        # Delete the question (this will cascade delete answers)
        question.delete()
        
        print(f"✅ Question {question_id} deleted successfully")
        
        response_data = {
            'success': True,
            'message': 'Question deleted successfully'
        }
        
        print(f"📤 Sending response: {response_data}")
        return JsonResponse(response_data, status=204)
        
    except Exception as e:
        print(f"❌ Error deleting question: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error': f'Failed to delete question: {str(e)}'
        }, status=500)
