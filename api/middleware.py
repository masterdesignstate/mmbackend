from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin
from datetime import timedelta


class UpdateLastActiveMiddleware(MiddlewareMixin):
    """
    Middleware to update user's last_active timestamp on each request.
    This allows us to track when users were last active for the activity status feature.
    """

    def process_request(self, request):
        """Update last_active for authenticated users on each request"""
        user_id = None

        # Check if user is authenticated via session
        if request.user.is_authenticated:
            user_id = request.user.pk
        # Otherwise check for user_id in query params (for API requests)
        elif 'user_id' in request.GET:
            user_id = request.GET.get('user_id')

        if user_id:
            try:
                from api.models import User

                # Get the user object to check last_active
                user = User.objects.filter(pk=user_id).first()
                if user:
                    now = timezone.now()
                    # Only update if last_active is None or older than 1 minute
                    should_update = (
                        user.last_active is None or
                        (now - user.last_active) > timedelta(minutes=1)
                    )

                    if should_update:
                        # Use update() to avoid triggering model save signals
                        User.objects.filter(pk=user_id).update(last_active=now)
            except Exception as e:
                # Silently fail - don't break the request if activity update fails
                pass
        return None
