import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth import authenticate, login
from django.db import transaction
from django.contrib.auth.hashers import make_password
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.utils import timezone
from django.conf import settings
from django.core import signing
from datetime import datetime
from .models import User, InviteCode
from .services.email_verification import (
    apply_email_verification_restriction,
    mark_email_verified,
    read_email_verification_token,
    send_verification_email,
    set_email_verification_code,
    verify_email_code,
)
from .utils.admin_utils import ensure_dashboard_admin
from .services.password_reset import send_password_reset_email, token_generator

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
def request_password_reset(request):
    """Send a reset link without revealing whether an account exists."""
    generic_response = {
        'success': True,
        'message': 'If an account exists for that email, a reset link has been sent.',
    }
    try:
        data = json.loads(request.body)
        email = (data.get('email') or '').strip().lower()
        if not email:
            return JsonResponse({'error': 'Email is required'}, status=400)

        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if user:
            try:
                delivery = send_password_reset_email(user)
                if settings.DEBUG and delivery.get('delivery') == 'development_fallback':
                    generic_response['uid'] = delivery['uid']
                    generic_response['token'] = delivery['token']
            except Exception:
                logger.exception('Failed to send password reset email for %s', email)
        return JsonResponse(generic_response, status=200)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def confirm_password_reset(request):
    """Validate a signed one-time token and replace the user's password."""
    try:
        data = json.loads(request.body)
        uid = data.get('uid')
        token = data.get('token')
        new_password = data.get('new_password')
        if not uid or not token or not new_password:
            return JsonResponse({'error': 'Reset link and new password are required'}, status=400)

        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=user_id, is_active=True)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return JsonResponse({'error': 'This reset link is invalid or has expired'}, status=400)

        if not token_generator.check_token(user, token):
            return JsonResponse({'error': 'This reset link is invalid or has expired'}, status=400)

        try:
            password_validation.validate_password(new_password, user=user)
        except ValidationError as validation_error:
            return JsonResponse({'error': ' '.join(validation_error.messages)}, status=400)

        user.set_password(new_password)
        user.save(update_fields=['password'])
        return JsonResponse({'success': True, 'message': 'Your password has been reset.'}, status=200)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)


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
        
        # Parse request data
        data = json.loads(request.body)
        email = (data.get('email') or '').strip().lower()
        password = data.get('password')
        alpha_code = (data.get('alpha_code') or data.get('invite_code') or '').strip()

        print(f"📝 USER SIGNUP REQUEST for email: {email}")
        print(f"🎟️  Invite code provided: {bool(alpha_code)}")

        # Validate required fields
        if not email or not password:
            print("❌ Missing required fields")
            print(f"   Email present: {bool(email)}")
            return JsonResponse({
                'error': 'Email and password are required'
            }, status=400)

        if not alpha_code:
            print("❌ Missing invite code")
            return JsonResponse({
                'error': 'Invite code is required'
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
        
        # Admin/test bypass codes let signups through without consuming a real InviteCode.
        ADMIN_BYPASS_CODES = {'1234', '888888'}
        is_bypass = alpha_code in ADMIN_BYPASS_CODES

        # Create the user
        with transaction.atomic():
            print(f"🔒 Starting database transaction")

            invite = None
            if not is_bypass:
                try:
                    invite = InviteCode.objects.select_for_update().get(
                        code=alpha_code, is_used=False
                    )
                except InviteCode.DoesNotExist:
                    print(f"❌ Invalid or already used invite code: {alpha_code}")
                    return JsonResponse({
                        'error': 'Invalid or already used invite code'
                    }, status=400)
            else:
                print(f"🛠️  Admin bypass code used — skipping InviteCode validation")

            user = User.objects.create(
                username=email,  # Use email as username for now
                email=email,
                password=make_password(password),
                is_active=True,
                email_verified=not settings.EMAIL_VERIFICATION_REQUIRED,
                email_verified_at=timezone.now() if not settings.EMAIL_VERIFICATION_REQUIRED else None,
                date_joined=timezone.now()
            )
            if settings.EMAIL_VERIFICATION_REQUIRED:
                apply_email_verification_restriction(user)

            if invite is not None:
                invite.is_used = True
                invite.used_by = user
                invite.used_at = timezone.now()
                invite.save(update_fields=['is_used', 'used_by', 'used_at'])
                print(f"🎟️  Invite code {invite.code} redeemed by user {user.id}")

            print(f"✅ USER CREATED successfully!")
            print(f"   User ID: {user.id}")
            print(f"   Email: {user.email}")
            print(f"   Username: {user.username}")
            print(f"   Is Active: {user.is_active}")
            print(f"   Date Joined: {user.date_joined}")
            
            email_delivery = None
            if settings.EMAIL_VERIFICATION_REQUIRED:
                try:
                    email_delivery = send_verification_email(user)
                    print(f"📧 Verification email handled for {user.email}: {email_delivery.get('delivery')}")
                except Exception as email_error:
                    logger.error("Failed to send verification email to %s: %s", user.email, email_error)
                    print(f"⚠️ Failed to send verification email: {email_error}")
                    if not settings.DEBUG:
                        raise
                    verification_code = set_email_verification_code(user)
                    print(f"EMAIL VERIFICATION CODE for {user.email}: {verification_code}")
                    email_delivery = {
                        'sent': False,
                        'delivery': 'development_fallback',
                        'verification_code': verification_code,
                    }
            else:
                # Log the user in immediately when verification is disabled.
                login(request, user)
                print(f"🔑 User logged in successfully with session")
                print(f"   Session key: {request.session.session_key}")
                print(f"   Session data: {dict(request.session)}")
                print(f"   User in session: {request.user.id if request.user.is_authenticated else 'Not authenticated'}")
            
            response_data = {
                'success': True,
                'user_id': str(user.id),
                'email': user.email,
                'email_verification_required': settings.EMAIL_VERIFICATION_REQUIRED,
                'email_verified': user.email_verified,
                'message': 'Check your email to verify your account' if settings.EMAIL_VERIFICATION_REQUIRED else 'User account created successfully',
            }
            if email_delivery:
                response_data['email_delivery'] = email_delivery.get('delivery')
                if email_delivery.get('message_id'):
                    response_data['postmark_message_id'] = email_delivery.get('message_id')
                if settings.DEBUG and email_delivery.get('delivery') == 'development_fallback':
                    response_data['verification_code'] = email_delivery.get('verification_code')
            
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
        
        # Parse request data
        data = json.loads(request.body)
        user_id = data.get('user_id')
        
        print(f"📝 PERSONAL DETAILS REQUEST for user: {user_id}")
        
        # Get the user first so we can determine whether identity fields are locked
        try:
            user = User.objects.get(id=user_id)
            print(f"✅ User found: {user.id} - {user.email}")
        except User.DoesNotExist:
            print(f"❌ User not found with ID: {user_id}")
            return JsonResponse({
                'error': 'User not found'
            }, status=404)

        identity_already_set = bool(
            user.date_of_birth
            or user.first_name
            or user.last_name
            or (user.username and user.username != user.email)
        )
        print(f"🔒 Identity already set (locked): {identity_already_set}")

        # Validate required fields - identity fields (full_name, username, date_of_birth)
        # are required only on initial onboarding; once set, they're locked and ignored.
        required_fields = ['user_id', 'from', 'live']
        if not identity_already_set:
            required_fields += ['full_name', 'username', 'date_of_birth']
        missing_fields = [field for field in required_fields if field not in data or not data.get(field)]

        if missing_fields:
            print(f"❌ Missing required fields: {missing_fields}")
            print(f"   Available fields: {list(data.keys())}")
            return JsonResponse({
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            }, status=400)

        print(f"✅ All required fields present")

        date_of_birth = None
        age = None
        if not identity_already_set:
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
        else:
            username = user.username

        # Validate for restricted words (only check fields that can actually change)
        from api.utils.word_filter import validate_text_fields

        word_filter_kwargs = {
            'tagline': data.get('tagline'),
            'bio': data.get('bio'),
        }
        if not identity_already_set:
            word_filter_kwargs['username'] = username
            word_filter_kwargs['full_name'] = data.get('full_name')

        has_restricted, found_words = validate_text_fields(**word_filter_kwargs)

        if has_restricted:
            print(f"❌ Restricted words found: {found_words}")
            # Auto-restrict the user for TOS violation
            user.is_banned = True
            user.ban_reason = f'Restricted words detected in profile: {", ".join(found_words)}'
            user.ban_date = timezone.now()
            user.save(update_fields=['is_banned', 'ban_reason', 'ban_date'])
            return JsonResponse({
                'error': f'Your profile contains restricted words: {", ".join(found_words)}',
                'is_banned': True
            }, status=400)

        print(f"✅ No restricted words found in profile fields")

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

        if not identity_already_set:
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
        else:
            print(f"🔒 Identity fields locked - ignoring full_name / username / date_of_birth from payload")
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
        data = json.loads(request.body)
        email = (data.get('email') or '').strip().lower()
        password = data.get('password')

        if not email or not password:
            return JsonResponse({'error': 'Email and password are required'}, status=400)

        candidate = User.objects.filter(email__iexact=email).first()
        if candidate and not candidate.is_active:
            return JsonResponse({'error': 'User account is deactivated'}, status=403)

        user = authenticate(
            username=candidate.username if candidate else email,
            password=password,
        )
        if user is None:
            logger.warning('Rejected login attempt')
            return JsonResponse({'error': 'Invalid email or password'}, status=401)

        is_admin_user = ensure_dashboard_admin(user)
        if settings.EMAIL_VERIFICATION_REQUIRED and not is_admin_user and not user.email_verified:
            try:
                send_verification_email(user)
            except Exception:
                logger.exception('Failed to resend verification email for user_id=%s', user.id)
            apply_email_verification_restriction(user)

        full_name = f"{user.first_name} {user.last_name}".strip()
        login(request, user)
        logger.info('Login succeeded for user_id=%s', user.id)

        response_data = {
            'success': True,
            'user_id': str(user.id),
            'message': 'Login successful',
            'is_admin': is_admin_user,
            'email_verification_required': settings.EMAIL_VERIFICATION_REQUIRED,
            'email_verified': user.email_verified,
            'user_data': {
                'id': str(user.id),
                'username': user.username,
                'email': user.email,
                'full_name': full_name,
                'age': user.age,
                'live': user.live,
                'is_admin': is_admin_user,
                'email_verified': user.email_verified,
                'is_banned': user.is_banned,
                'restriction_type': user.restriction_type,
                'restriction_reason': user.restriction_reason,
            }
        }

        return JsonResponse(response_data, status=200)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
    except Exception:
        logger.exception('Unexpected login error')
        return JsonResponse({'error': 'Unable to log in right now'}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def verify_email(request):
    """Verify a user's email address from a 6-digit code or legacy signed token."""
    try:
        data = json.loads(request.body)
        token = data.get('token')

        if token:
            try:
                payload = read_email_verification_token(token)
            except signing.SignatureExpired:
                return JsonResponse({'error': 'Verification link has expired'}, status=400)
            except signing.BadSignature:
                return JsonResponse({'error': 'Invalid verification link'}, status=400)

            try:
                user = User.objects.get(id=payload.get('user_id'), email__iexact=payload.get('email'))
            except User.DoesNotExist:
                return JsonResponse({'error': 'Invalid verification link'}, status=400)
        else:
            email = (data.get('email') or '').strip().lower()
            code = data.get('code')
            if not email:
                return JsonResponse({'error': 'Email is required'}, status=400)

            try:
                user = User.objects.get(email__iexact=email)
            except User.DoesNotExist:
                return JsonResponse({'error': 'Invalid verification code'}, status=400)

            is_valid, error_message = verify_email_code(user, code)
            if not is_valid:
                return JsonResponse({'error': error_message}, status=400)

        mark_email_verified(user)
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')

        return JsonResponse({
            'success': True,
            'message': 'Email verified successfully',
            'user_id': str(user.id),
            'email': user.email,
            'email_verified': True,
            'is_admin': ensure_dashboard_admin(user),
        })
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
    except Exception as e:
        logger.error(f"Error in verify_email: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def resend_verification_email(request):
    """Resend an email verification code without revealing whether an email exists."""
    try:
        data = json.loads(request.body)
        email = (data.get('email') or '').strip().lower()
        if not email:
            return JsonResponse({'error': 'Email is required'}, status=400)

        user = User.objects.filter(email__iexact=email).first()
        if user and not user.email_verified:
            try:
                email_delivery = send_verification_email(user)
                response_data = {
                    'success': True,
                    'message': 'If this email needs verification, a new code has been sent.',
                    'email_delivery': email_delivery.get('delivery'),
                }
                if email_delivery.get('message_id'):
                    response_data['postmark_message_id'] = email_delivery.get('message_id')
                if settings.DEBUG and email_delivery.get('delivery') == 'development_fallback':
                    response_data['verification_code'] = email_delivery.get('verification_code')
                return JsonResponse(response_data)
            except Exception as email_error:
                logger.error("Failed to resend verification email to %s: %s", email, email_error)
                if settings.DEBUG:
                    verification_code = set_email_verification_code(user)
                    print(f"EMAIL VERIFICATION CODE for {user.email}: {verification_code}")
                    return JsonResponse({
                        'success': True,
                        'message': 'Email delivery failed locally; use the development verification code.',
                        'email_delivery': 'development_fallback',
                        'verification_code': verification_code,
                    })
                return JsonResponse({'error': 'Could not send verification email'}, status=500)

        return JsonResponse({
            'success': True,
            'message': 'If this email needs verification, a new code has been sent.',
        })
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
    except Exception as e:
        logger.error(f"Error in resend_verification_email: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


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
        
        email = request.GET.get('email')
        
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
        is_admin_user = ensure_dashboard_admin(user)
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

        # Compute which mandatory question_numbers user has already answered (distinct)
        answered_mandatory_numbers = sorted(
            UserAnswer.objects.filter(user=user, question_id__in=mandatory_question_ids)
            .values_list('question__question_number', flat=True)
            .distinct()
        )

        print(f"📊 Onboarding status:")
        print(f"   Personal details: {'✅' if has_personal_details else '❌'}")
        print(f"   Profile photo: {'✅' if has_profile_photo else '❌'}")
        print(f"   Mandatory questions: {len(answered_question_ids)}/{len(mandatory_question_ids)} answered")
        print(f"   Answered question numbers: {answered_mandatory_numbers}")
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
            step_url = '/auth/introcard'
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
            'is_admin': is_admin_user,
            'answered_mandatory_numbers': answered_mandatory_numbers
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

        data = json.loads(request.body)
        user_id = data.get('user_id')
        profile_photo_url = data.get('profile_photo_url')
        
        print(f"📸 UPDATE PROFILE PHOTO REQUEST for user: {user_id}")

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

        # Create PictureModeration record for the uploaded photo
        from .models import PictureModeration
        moderation = PictureModeration.objects.create(
            user=user,
            picture_url=profile_photo_url,
            status='pending'
        )

        print(f"📋 Created PictureModeration record: {moderation.id} (status: {moderation.status})")
        print(f"✅ PROFILE PHOTO UPDATED successfully for user: {user_id}")

        response_data = {
            'success': True,
            'message': 'Profile photo updated successfully and submitted for moderation',
            'profile_photo_url': profile_photo_url,
            'moderation_id': str(moderation.id),
            'moderation_status': moderation.status
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
        return JsonResponse(response_data, status=200)
        
    except Exception as e:
        print(f"❌ Error deleting question: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error': f'Failed to delete question: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def impostor_login(request):
    """Allow an admin to log in as another user (impostor mode)."""
    try:
        data = json.loads(request.body)
        admin_user_id = data.get('admin_user_id')
        target_user_id = data.get('target_user_id')

        if not admin_user_id or not target_user_id:
            return JsonResponse({'error': 'admin_user_id and target_user_id are required'}, status=400)

        # Verify admin
        try:
            admin_user = User.objects.get(id=admin_user_id)
        except User.DoesNotExist:
            return JsonResponse({'error': 'Admin user not found'}, status=404)

        if not admin_user.is_admin:
            return JsonResponse({'error': 'Unauthorized - admin access required'}, status=403)

        # Get target user
        try:
            target_user = User.objects.get(id=target_user_id)
        except User.DoesNotExist:
            return JsonResponse({'error': 'Target user not found'}, status=404)

        # Switch session to target user (must specify backend since we skip authenticate())
        login(request, target_user, backend='django.contrib.auth.backends.ModelBackend')

        print(f"🕵️ IMPOSTOR MODE: Admin {admin_user.email} logged in as {target_user.email}")

        return JsonResponse({
            'success': True,
            'is_impostor': True,
            'user_id': str(target_user.id),
            'admin_user_id': str(admin_user.id),
            'user_data': {
                'username': target_user.username,
                'email': target_user.email,
                'full_name': f"{target_user.first_name} {target_user.last_name}".strip(),
            }
        })

    except Exception as e:
        return JsonResponse({'error': f'Impostor login failed: {str(e)}'}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def impostor_exit(request):
    """Exit impostor mode and restore the admin session."""
    try:
        data = json.loads(request.body)
        admin_user_id = data.get('admin_user_id')

        if not admin_user_id:
            return JsonResponse({'error': 'admin_user_id is required'}, status=400)

        try:
            admin_user = User.objects.get(id=admin_user_id)
        except User.DoesNotExist:
            return JsonResponse({'error': 'Admin user not found'}, status=404)

        if not admin_user.is_admin:
            return JsonResponse({'error': 'Unauthorized - admin access required'}, status=403)

        # Restore admin session (must specify backend since we skip authenticate())
        login(request, admin_user, backend='django.contrib.auth.backends.ModelBackend')

        print(f"🕵️ IMPOSTOR MODE EXIT: Admin {admin_user.email} restored")

        return JsonResponse({
            'success': True,
            'user_id': str(admin_user.id),
            'is_admin': True,
        })

    except Exception as e:
        return JsonResponse({'error': f'Impostor exit failed: {str(e)}'}, status=500)
