from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q, Count, F
from django.utils import timezone
from datetime import timedelta
import logging
import time
from collections import defaultdict

logger = logging.getLogger(__name__)

from .models import (
    User, Tag, Question, UserAnswer, Compatibility,
    UserResult, Message, PictureModeration, UserReport, UserOnlineStatus, UserTag, Controls,
    CompatibilityJob,
)
from .services.compatibility_service import CompatibilityService
from .services.compatibility_queue import (
    enqueue_user_for_recalculation,
    should_enqueue_after_answer,
    MIN_MATCHABLE_ANSWERS,
)
from .serializers import (
    UserSerializer, TagSerializer, QuestionSerializer, UserAnswerSerializer,
    CompatibilitySerializer, UserResultSerializer, MessageSerializer,
    PictureModerationSerializer, UserReportSerializer, UserOnlineStatusSerializer,
    DetailedUserSerializer, DetailedQuestionSerializer, UserTagSerializer,
    SimpleUserSerializer, ControlsSerializer,
)
from .permissions import IsDashboardAdmin


class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [permissions.AllowAny]  # Changed for testing
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['username', 'first_name', 'last_name', 'from_location', 'live', 'bio']
    ordering_fields = ['age', 'height', 'questions_answered_count', 'last_seen']
    ordering = ['-last_seen']

    def get_queryset(self):
        # Exclude banned users and current user
        queryset = User.objects.filter(
            is_banned=False
        ).exclude(id=self.request.user.id)
        
        logger.info(f"UserViewSet.get_queryset() called. Request: {self.request.method} {self.request.path}")
        logger.info(f"Query params: {self.request.query_params}")
        logger.info(f"Returning {queryset.count()} users")
        
        return queryset

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return DetailedUserSerializer
        return UserSerializer

    @action(detail=False, methods=['get'])
    def me(self, request):
        """Get current user's profile"""
        print(f"🔍 /users/me/ called")
        print(f"   User authenticated: {request.user.is_authenticated}")
        print(f"   User: {request.user}")
        print(f"   Session key: {request.session.session_key}")
        print(f"   Session data: {dict(request.session)}")
        
        if not request.user.is_authenticated:
            print(f"❌ User not authenticated")
            return Response({'error': 'Authentication required'}, status=401)
        
        print(f"✅ User authenticated: {request.user.id}")
        serializer = DetailedUserSerializer(request.user)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def online(self, request):
        """Get online users"""
        online_users = self.get_queryset().filter(is_online=True)
        serializer = self.get_serializer(online_users, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def update_online_status(self, request, pk=None):
        """Update user's online status"""
        user = self.get_object()
        is_online = request.data.get('is_online', False)
        
        online_status, created = UserOnlineStatus.objects.get_or_create(user=user)
        online_status.is_online = is_online
        online_status.last_activity = timezone.now()
        if is_online:
            online_status.last_seen = timezone.now()
        online_status.save()
        
        user.is_online = is_online
        user.last_seen = timezone.now()
        user.save()
        
        return Response({'status': 'updated'})

    @action(detail=False, methods=['get'])
    def restricted(self, request):
        """Get restricted users (admin only)"""
        # Removed staff requirement for testing
        # if not request.user.is_staff:
        #     return Response({'error': 'Staff only'}, status=403)
        
        # Get users with restrictions (you can add restriction logic here)
        restricted_users = User.objects.filter(is_banned=True)
        serializer = self.get_serializer(restricted_users, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def reported(self, request):
        """Get reported users (admin only)"""
        # Removed staff requirement for testing
        # if not request.user.is_staff:
        #     return Response({'error': 'Staff only'}, status=403)
        
        # Get users who have been reported
        reported_users = User.objects.filter(
            reports_received__isnull=False
        ).distinct()
        serializer = self.get_serializer(reported_users, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def restrict(self, request, pk=None):
        """Restrict a user (admin only)"""
        # Removed staff requirement for testing
        # if not request.user.is_staff:
        #     return Response({'error': 'Staff only'}, status=403)
        
        user = self.get_object()
        restriction_type = request.data.get('restriction_type', 'temporary')
        duration = request.data.get('duration', 30)
        reason = request.data.get('reason', '')
        
        user.is_banned = True
        user.restriction_type = restriction_type
        user.restriction_duration = duration
        user.restriction_reason = reason
        user.restriction_date = timezone.now()
        user.save()
        
        return Response({'status': 'user restricted'})

    @action(detail=True, methods=['post'])
    def remove_restriction(self, request, pk=None):
        """Remove restriction from a user (admin only)"""
        # Removed staff requirement for testing
        # if not request.user.is_staff:
        #     return Response({'error': 'Staff only'}, status=403)
        
        user = self.get_object()
        user.is_banned = False
        user.restriction_type = None
        user.restriction_duration = None
        user.restriction_reason = None
        user.restriction_date = None
        user.save()
        
        return Response({'status': 'restriction removed'})

    @action(detail=False, methods=['get'])
    def search(self, request):
        """Search users by name, username, or email"""
        query = request.query_params.get('q', '').strip()

        if not query or len(query) < 2:
            return Response({'results': []})

        # Optional result limit
        try:
            limit = int(request.query_params.get('limit', 10))
        except ValueError:
            limit = 10
        limit = max(1, min(limit, 25))

        # Search across multiple fields
        users = User.objects.filter(
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(username__icontains=query) |
            Q(email__icontains=query),
            is_banned=False
        ).distinct()[:limit]

        serializer = self.get_serializer(users, many=True)
        return Response({'results': serializer.data})

    @action(detail=False, methods=['get'])
    def compatible(self, request):
        """Get users compatible with the current user"""
        # Allow user_id parameter for frontend compatibility
        user_id_param = request.query_params.get('user_id')
        if user_id_param:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            try:
                request.user = User.objects.get(id=user_id_param)
                print(f"Using provided user ID: {request.user.username} (ID: {request.user.id})")
            except User.DoesNotExist:
                return Response({'error': 'User not found'}, status=404)
        elif not request.user.is_authenticated:
            return Response({'error': 'Authentication required'}, status=401)

        # Get filter parameters
        compatibility_type = request.query_params.get('compatibility_type', 'overall_compatibility')
        min_compatibility = float(request.query_params.get('min_compatibility', 0))
        max_compatibility = float(request.query_params.get('max_compatibility', 100))
        required_only = request.query_params.get('required_only', 'false').lower() == 'true'
        
        # Get tag filter parameters
        tags = request.query_params.getlist('tags')  # Get multiple tag values
        print(f"🔍 Tag filters: {tags}")

        # Get pagination parameters
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 15))
        offset = (page - 1) * page_size

        print(f"🔍 === COMPATIBLE ENDPOINT CALLED ===")
        print(f"   User: {request.user.id}")
        print(f"   required_only={required_only}")
        logger.info(f"Compatible users request for user {request.user.id}")
        logger.info(f"Filters: type={compatibility_type}, min={min_compatibility}, max={max_compatibility}, required_only={required_only}")
        logger.info(f"Pagination: page={page}, size={page_size}, offset={offset}")

        try:
            from django.db.models import Q, Case, When, FloatField
            from .models import Compatibility
            from .serializers import SimpleUserSerializer

            compatibility_field = {
                'overall_compatibility': 'overall_compatibility',
                'compatible_with_me': 'compatible_with_me',
                'im_compatible_with': 'im_compatible_with',
            }.get(compatibility_type, 'overall_compatibility')

            if required_only:
                logger.info("Using real-time calculation for required-only filter")
                from .services.compatibility_service import CompatibilityService

                start_time = time.monotonic()
                max_candidates = 60

                compat_candidates = Compatibility.objects.filter(
                    Q(user1=request.user) | Q(user2=request.user)
                ).select_related('user1', 'user2').order_by('-overall_compatibility')[:max_candidates * 3]

                candidate_users: list[User] = []
                seen_candidate_ids = set()

                for comp in compat_candidates:
                    other_user = comp.user2 if comp.user1 == request.user else comp.user1
                    if other_user.is_banned or other_user.id == request.user.id:
                        continue
                    if other_user.id in seen_candidate_ids:
                        continue
                    candidate_users.append(other_user)
                    seen_candidate_ids.add(other_user.id)
                    if len(candidate_users) >= max_candidates:
                        break

                if not candidate_users:
                    candidate_users = list(
                        User.objects.exclude(id=request.user.id)
                        .exclude(is_banned=True)
                        .filter(answers__isnull=False)
                        .distinct()[:max_candidates]
                    )

                candidate_ids = [user.id for user in candidate_users]

                answer_qs = UserAnswer.objects.filter(
                    Q(user=request.user) | Q(user__in=candidate_ids)
                ).filter(question__is_required_for_match=True).only(
                    'user_id',
                    'question_id',
                    'me_answer',
                    'me_open_to_all',
                    'me_importance',
                    'looking_for_answer',
                    'looking_for_open_to_all',
                    'looking_for_importance',
                )

                answers_by_user: dict[object, list[UserAnswer]] = defaultdict(list)
                for answer in answer_qs:
                    answers_by_user[answer.user_id].append(answer)

                current_user_answers = answers_by_user.get(request.user.id, [])

                if not current_user_answers:
                    logger.info("Required-only: current user has no required-question answers; returning empty result set")
                    return Response({
                        'results': [],
                        'count': 0,
                        'total_count': 0,
                        'page': page,
                        'page_size': page_size,
                        'has_next': False,
                        'message': 'No required-question matches available'
                    })

                compatibility_results = []
                for other_user in candidate_users:
                    other_answers = answers_by_user.get(other_user.id, [])
                    if not other_answers or not current_user_answers:
                        continue
                    compatibility_data = CompatibilityService.calculate_compatibility_between_users(
                        request.user,
                        other_user,
                        required_only=True,
                        user1_answers=current_user_answers,
                        user2_answers=other_answers,
                    )
                    score = compatibility_data.get(compatibility_field, 0.0)
                    if score < min_compatibility or score > max_compatibility:
                        continue
                    compatibility_results.append({
                        'user': other_user,
                        'compatibility': compatibility_data
                    })

                compatibility_results.sort(
                    key=lambda x: x['compatibility'].get(compatibility_field, 0.0),
                    reverse=True
                )

                total_users = len(compatibility_results)
                paginated_results = compatibility_results[offset:offset + page_size]

                response_data = []
                for result in paginated_results:
                    user_serializer = SimpleUserSerializer(result['user'])
                    response_data.append({
                        'user': user_serializer.data,
                        'compatibility': result['compatibility']
                    })

                duration = time.monotonic() - start_time
                logger.info(
                    "Required-only calculation returned %s users (checked %s candidates) in %.2fs",
                    len(response_data),
                    len(candidate_users),
                    duration,
                )

                return Response({
                    'results': response_data,
                    'count': len(response_data),
                    'total_count': total_users,
                    'page': page,
                    'page_size': page_size,
                    'has_next': offset + page_size < total_users,
                    'message': f"Showing {len(response_data)} users from {total_users} total ranked by compatibility (real-time)"
                })

            # Use pre-calculated compatibilities for instant ranking of ALL users
            compatibilities = Compatibility.objects.filter(
                Q(user1=request.user) | Q(user2=request.user)
            ).select_related('user1', 'user2').annotate(
                # Determine which user is the "other" user and get the right compatibility score
                other_user_id=Case(
                    When(user1=request.user, then='user2__id'),
                    default='user1__id'
                ),
                compatibility_score=Case(
                    When(user1=request.user, then='overall_compatibility'),
                    default='overall_compatibility'
                )
            ).order_by('-compatibility_score')

            # Apply compatibility filters
            if min_compatibility > 0:
                compatibilities = compatibilities.filter(overall_compatibility__gte=min_compatibility)
            if max_compatibility < 100:
                compatibilities = compatibilities.filter(overall_compatibility__lte=max_compatibility)

            # Apply tag filters
            if tags:
                from .models import UserResult
                print(f"🔍 Applying tag filters: {tags}")
                
                # Get user IDs that match the tag criteria
                tag_filtered_user_ids = set()
                
                for tag in tags:
                    tag_lower = tag.lower()
                    print(f"🔍 Processing tag: {tag_lower}")
                    
                    if tag_lower == 'liked':
                        # Users I have liked
                        liked_user_ids = UserResult.objects.filter(
                            user=request.user,
                            tag='like'
                        ).values_list('result_user_id', flat=True)
                        tag_filtered_user_ids.update(liked_user_ids)
                        print(f"🔍 Found {len(liked_user_ids)} liked users")
                        
                    elif tag_lower == 'approved':
                        # Users I have approved
                        approved_user_ids = UserResult.objects.filter(
                            user=request.user,
                            tag='approve'
                        ).values_list('result_user_id', flat=True)
                        tag_filtered_user_ids.update(approved_user_ids)
                        print(f"🔍 Found {len(approved_user_ids)} approved users")
                        
                    elif tag_lower == 'matched':
                        # Users I have liked AND who have liked me (mutual likes)
                        my_liked_users = set(UserResult.objects.filter(
                            user=request.user,
                            tag='like'
                        ).values_list('result_user_id', flat=True))
                        
                        users_who_liked_me = set(UserResult.objects.filter(
                            result_user=request.user,
                            tag='like'
                        ).values_list('user_id', flat=True))
                        
                        matched_user_ids = my_liked_users.intersection(users_who_liked_me)
                        tag_filtered_user_ids.update(matched_user_ids)
                        print(f"🔍 Found {len(matched_user_ids)} matched users")
                        
                    elif tag_lower == 'saved':
                        # Users I have saved
                        saved_user_ids = UserResult.objects.filter(
                            user=request.user,
                            tag='save'
                        ).values_list('result_user_id', flat=True)
                        tag_filtered_user_ids.update(saved_user_ids)
                        print(f"🔍 Found {len(saved_user_ids)} saved users")
                        
                    elif tag_lower == 'hidden':
                        # Users I have hidden
                        hidden_user_ids = UserResult.objects.filter(
                            user=request.user,
                            tag='hide'
                        ).values_list('result_user_id', flat=True)
                        tag_filtered_user_ids.update(hidden_user_ids)
                        print(f"🔍 Found {len(hidden_user_ids)} hidden users")
                        
                    else:
                        # Handle other tags
                        other_tag_user_ids = UserResult.objects.filter(
                            user=request.user,
                            tag=tag_lower
                        ).values_list('result_user_id', flat=True)
                        tag_filtered_user_ids.update(other_tag_user_ids)
                        print(f"🔍 Found {len(other_tag_user_ids)} users with tag '{tag_lower}'")
                
                # Filter compatibilities to only include users that match tag criteria
                if tag_filtered_user_ids:
                    print(f"🔍 Tag filtered user IDs: {list(tag_filtered_user_ids)}")
                    compatibilities = compatibilities.filter(
                        Q(user1__id__in=tag_filtered_user_ids) | Q(user2__id__in=tag_filtered_user_ids)
                    )
                    print(f"🔍 After tag filtering: {compatibilities.count()} compatibilities remain")
                else:
                    print(f"🔍 No users match tag criteria, returning empty result")
                    return Response({
                        'results': [],
                        'count': 0,
                        'total_count': 0,
                        'page': page,
                        'page_size': page_size,
                        'has_next': False,
                        'message': 'No users match the selected tag filters'
                    })

            # Check if we have sufficient pre-calculated data
            total_compatibilities = compatibilities.count()

            # Use pre-calculated results
            paginated_compatibilities = compatibilities[offset:offset + page_size]

            # Build response with pre-calculated data
            response_data = []
            for comp in paginated_compatibilities:
                # Determine which user is the "other" user
                other_user = comp.user2 if comp.user1 == request.user else comp.user1

                # Skip banned users
                if other_user.is_banned:
                    continue

                user_serializer = SimpleUserSerializer(other_user)
                response_data.append({
                    'user': user_serializer.data,
                    'compatibility': {
                        'overall_compatibility': comp.overall_compatibility,
                        'compatible_with_me': comp.compatible_with_me if comp.user1 == request.user else comp.im_compatible_with,
                        'im_compatible_with': comp.im_compatible_with if comp.user1 == request.user else comp.compatible_with_me,
                        'mutual_questions_count': comp.mutual_questions_count
                    }
                })

            logger.info(f"Returning {len(response_data)} compatible users from pre-calculated data")

            return Response({
                'results': response_data,
                'count': len(response_data),
                'total_count': total_compatibilities,  # ALL users ranked by compatibility
                'page': page,
                'page_size': page_size,
                'has_next': offset + page_size < total_compatibilities,
                'message': f'Showing {len(response_data)} users from {total_compatibilities} total ranked by compatibility'
            })

        except Exception as e:
            logger.error(f"Error getting compatible users: {e}")
            return Response({
                'error': 'Failed to get compatible users'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'])
    def change_email(self, request):
        """Change user's email address (requires current password and current email)"""
        current_email = request.data.get('current_email')
        current_password = request.data.get('current_password')
        new_email = request.data.get('new_email')

        if not current_email or not current_password or not new_email:
            return Response({
                'error': 'Current email, current password, and new email are required'
            }, status=400)

        # Find user by current email
        try:
            user = User.objects.get(email=current_email)
        except User.DoesNotExist:
            return Response({'error': 'Invalid credentials'}, status=400)

        # Verify password
        if not user.check_password(current_password):
            return Response({'current_password': ['Current password is incorrect.']}, status=400)

        # Check if new email is already in use by another user
        if User.objects.filter(email=new_email).exclude(id=user.id).exists():
            return Response({'new_email': ['This email is already in use by another account.']}, status=400)

        # Update email and username (since we use email as username)
        user.email = new_email
        user.username = new_email
        user.save()

        logger.info(f"User {user.id} changed email from {current_email} to {new_email}")
        return Response({
            'success': True,
            'message': 'Email updated successfully',
            'email': new_email
        })

    @action(detail=False, methods=['post'])
    def change_password(self, request):
        """Change user's password (requires current email and password)"""
        current_email = request.data.get('current_email')
        current_password = request.data.get('current_password')
        new_password = request.data.get('new_password')
        confirm_password = request.data.get('confirm_password')

        if not current_email or not current_password or not new_password or not confirm_password:
            return Response({
                'error': 'Current email, current password, new password, and confirm password are required'
            }, status=400)

        # Find user by email
        try:
            user = User.objects.get(email=current_email)
        except User.DoesNotExist:
            return Response({'error': 'Invalid credentials'}, status=400)

        # Verify current password
        if not user.check_password(current_password):
            return Response({'current_password': ['Current password is incorrect.']}, status=400)

        # Check new password matches confirmation
        if new_password != confirm_password:
            return Response({'confirm_password': ['New passwords do not match.']}, status=400)

        # Check password length
        if len(new_password) < 8:
            return Response({'new_password': ['Password must be at least 8 characters long.']}, status=400)

        # Check new password is different from current
        if current_password == new_password:
            return Response({'new_password': ['New password must be different from current password.']}, status=400)

        # Set new password
        user.set_password(new_password)
        user.save()

        logger.info(f"User {user.id} changed password")
        return Response({
            'success': True,
            'message': 'Password updated successfully'
        })


class TagViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TagSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Tag.objects.all()


class QuestionViewSet(viewsets.ModelViewSet):
    serializer_class = QuestionSerializer
    permission_classes = [permissions.AllowAny]  # Changed for testing
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['text']
    ordering_fields = ['created_at', 'question_number']
    ordering = ['question_number', 'group_number']

    def get_queryset(self):
        # Use prefetch_related to optimize queries for tags and related objects
        queryset = Question.objects.all().prefetch_related('tags', 'answers').select_related('submitted_by')
        
        # For retrieve action, conditionally prefetch user_answers only if needed
        if self.action == 'retrieve':
            skip_user_answers = self.request.query_params.get('skip_user_answers', 'false').lower() == 'true'
            if not skip_user_answers:
                # Only prefetch user_answers if we're actually going to serialize them
                queryset = queryset.prefetch_related('user_answers__user', 'user_answers__question')

        # Filter by is_approved=True by default (hide unapproved questions from public)
        # Allow override via query param for admin endpoints
        include_unapproved = self.request.query_params.get('include_unapproved', 'false').lower() == 'true'
        if not include_unapproved:
            queryset = queryset.filter(is_approved=True)

        # Filter by is_mandatory if specified
        is_mandatory = self.request.query_params.get('is_mandatory')
        if is_mandatory is not None:
            queryset = queryset.filter(is_mandatory=is_mandatory.lower() == 'true')

        # Filter by is_required_for_match if specified
        is_required = self.request.query_params.get('is_required_for_match')
        if is_required is not None:
            queryset = queryset.filter(is_required_for_match=is_required.lower() == 'true')

        # Filter by submitted_by if specified
        submitted_by = self.request.query_params.get('submitted_by')
        if submitted_by:
            queryset = queryset.filter(submitted_by__id=submitted_by)

        # Filter by question_number if specified (supports multiple values and gt/lt)
        question_numbers = self.request.query_params.getlist('question_number')
        if question_numbers:
            queryset = queryset.filter(question_number__in=question_numbers)

        # Support question_number__gt for pagination
        question_number_gt = self.request.query_params.get('question_number__gt')
        if question_number_gt:
            queryset = queryset.filter(question_number__gt=int(question_number_gt))

        # Filter by tags if specified
        tags = self.request.query_params.getlist('tags')
        if tags:
            queryset = queryset.filter(tags__name__in=tags).distinct()

        # Filter by whether user has answered (requires authenticated user)
        has_answer = self.request.query_params.get('has_answer')
        if has_answer is not None and self.request.user.is_authenticated:
            if has_answer.lower() == 'true':
                queryset = queryset.filter(user_answers__user=self.request.user).distinct()
            else:
                queryset = queryset.exclude(user_answers__user=self.request.user)

        logger.info(f"QuestionViewSet.get_queryset() called. Request: {self.request.method} {self.request.path}")
        logger.info(f"Query params: {self.request.query_params}")
        logger.info(f"Returning {queryset.count()} questions")

        return queryset

    def get_serializer_class(self):
        if self.action == 'retrieve':
            # For edit operations, skip user_answers to improve performance
            skip_user_answers = self.request.query_params.get('skip_user_answers', 'false').lower() == 'true'
            if skip_user_answers:
                return QuestionSerializer
            return DetailedQuestionSerializer
        return QuestionSerializer
    
    def get_serializer_context(self):
        """Ensure request context is passed to serializer"""
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    def create(self, request, *args, **kwargs):
        """
        Custom create method to handle tag creation and validation
        """
        try:
            # Extract data from request
            text = request.data.get('text', '').strip()
            user_id = request.data.get('user_id')  # Get user_id from frontend
            question_name = request.data.get('question_name', '').strip()
            question_number = request.data.get('question_number')
            group_number = request.data.get('group_number')
            group_name = request.data.get('group_name', '').strip()
            group_name_text = request.data.get('group_name_text', '').strip()
            question_type = request.data.get('question_type', 'basic')
            tags = request.data.get('tags', [])
            is_required_for_match = request.data.get('is_required_for_match', False)
            is_mandatory = request.data.get('is_mandatory', False)
            is_approved = request.data.get('is_approved', False)  # User-submitted questions need approval
            skip_me = request.data.get('skip_me', False)
            skip_looking_for = request.data.get('skip_looking_for', False)
            open_to_all_me = request.data.get('open_to_all_me', False)
            open_to_all_looking_for = request.data.get('open_to_all_looking_for', False)
            is_group = request.data.get('is_group', False)
            value_label_1 = request.data.get('value_label_1', '').strip()
            value_label_5 = request.data.get('value_label_5', '').strip()
            
            # Validate required fields
            if not text:
                return Response({
                    'error': 'Question text is required'
                }, status=status.HTTP_400_BAD_REQUEST)

            if len(text) > 100:  # Updated to match frontend limit
                return Response({
                    'error': 'Question text must be less than 100 characters'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Validate for restricted words
            from api.utils.word_filter import validate_text_fields

            has_restricted, found_words = validate_text_fields(
                text=text,
                question_name=question_name
            )

            if has_restricted:
                return Response({
                    'error': f'Your question contains restricted words: {", ".join(found_words)}'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if not tags:
                return Response({
                    'error': 'At least one tag is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if len(tags) > 3:
                return Response({
                    'error': 'Maximum 3 tags allowed'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if not value_label_1:
                return Response({
                    'error': 'Value label 1 is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if not value_label_5:
                return Response({
                    'error': 'Value label 5 is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Get the user object if user_id is provided
            submitted_by_user = None
            if user_id:
                try:
                    from django.contrib.auth import get_user_model
                    User = get_user_model()
                    submitted_by_user = User.objects.get(id=user_id)
                    logger.info(f"Found user for question submission: {submitted_by_user.username}")
                except User.DoesNotExist:
                    logger.warning(f"User ID {user_id} not found, question will have no submitter")
            elif request.user.is_authenticated:
                submitted_by_user = request.user
            
            # Create the question
            question_data = {
                'text': text,
                'question_name': question_name or text[:50],  # Use text as name if not provided
                'question_number': question_number,
                'group_number': group_number,
                'group_name': group_name,
                'group_name_text': group_name_text,
                'question_type': question_type,
                'is_required_for_match': is_required_for_match,
                'is_mandatory': is_mandatory,
                'submitted_by': submitted_by_user,
                'is_approved': is_approved,
                'skip_me': skip_me,
                'skip_looking_for': skip_looking_for,
                'open_to_all_me': open_to_all_me,
                'open_to_all_looking_for': open_to_all_looking_for,
                'is_group': is_group,
            }
            
            serializer = self.get_serializer(data=question_data)
            serializer.is_valid(raise_exception=True)
            question = serializer.save()
            
            # Add tags
            for tag_name in tags:
                tag, created = Tag.objects.get_or_create(name=tag_name.lower())
                question.tags.add(tag)
                if created:
                    logger.info(f"Created new tag: {tag_name}")
                else:
                    logger.info(f"Added existing tag: {tag_name}")
            
            # Create answers for positions 1 and 5, with empty answers for positions 2, 3, 4
            from .models import QuestionAnswer
            
            # Create all 5 answer options
            answer_values = [
                {'value': '1', 'answer_text': value_label_1, 'order': 0},
                {'value': '2', 'answer_text': '', 'order': 1},
                {'value': '3', 'answer_text': '', 'order': 2},
                {'value': '4', 'answer_text': '', 'order': 3},
                {'value': '5', 'answer_text': value_label_5, 'order': 4},
            ]
            
            for answer_data in answer_values:
                QuestionAnswer.objects.create(
                    question=question,
                    value=answer_data['value'],
                    answer_text=answer_data['answer_text'],
                    order=answer_data['order']
                )
            
            logger.info(f"Question created successfully: {question.id}")
            
            # Return the created question
            return Response(serializer.data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Error creating question: {e}")
            return Response({
                'error': 'Failed to create question'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def update(self, request, *args, **kwargs):
        """
        Custom update method to handle tag updates and validation
        """
        try:
            question = self.get_object()
            
            # Extract data from request
            text = request.data.get('text', '').strip()
            question_name = request.data.get('question_name', '').strip()
            question_number = request.data.get('question_number')
            group_number = request.data.get('group_number')
            group_name = request.data.get('group_name', '').strip()
            group_name_text = request.data.get('group_name_text', '').strip()
            question_type = request.data.get('question_type', 'basic')
            tags = request.data.get('tags', [])
            question_type = request.data.get('question_type', question.question_type)
            is_required_for_match = request.data.get('is_required_for_match', question.is_required_for_match)
            is_approved = request.data.get('is_approved', question.is_approved)
            skip_me = request.data.get('skip_me', question.skip_me)
            skip_looking_for = request.data.get('skip_looking_for', question.skip_looking_for)
            open_to_all_me = request.data.get('open_to_all_me', question.open_to_all_me)
            open_to_all_looking_for = request.data.get('open_to_all_looking_for', question.open_to_all_looking_for)
            is_group = request.data.get('is_group', question.is_group)
            answers = request.data.get('answers', [])
            
            # Validate required fields
            if not text:
                return Response({
                    'error': 'Question text is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if len(text) > 1000:
                return Response({
                    'error': 'Question text must be less than 1000 characters'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if not tags:
                return Response({
                    'error': 'At least one tag is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Update the question
            question_data = {
                'text': text,
                'question_name': question_name,
                'question_number': question_number,
                'group_number': group_number,
                'group_name': group_name,
                'group_name_text': group_name_text,
                'question_type': question_type,
                'question_type': question_type,
                'is_required_for_match': is_required_for_match,
                'is_approved': is_approved,
                'skip_me': skip_me,
                'skip_looking_for': skip_looking_for,
                'open_to_all_me': open_to_all_me,
                'open_to_all_looking_for': open_to_all_looking_for,
                'is_group': is_group,
            }
            
            serializer = self.get_serializer(question, data=question_data, partial=True)
            serializer.is_valid(raise_exception=True)
            updated_question = serializer.save()
            
            # Clear existing tags and add new ones
            updated_question.tags.clear()
            for tag_name in tags:
                tag, created = Tag.objects.get_or_create(name=tag_name.lower())
                updated_question.tags.add(tag)
                if created:
                    logger.info(f"Created new tag: {tag_name}")
                else:
                    logger.info(f"Added existing tag: {tag_name}")
            
            # Update answers if provided
            if answers:
                from .models import QuestionAnswer
                # Clear existing answers
                QuestionAnswer.objects.filter(question=updated_question).delete()
                # Create new answers
                for i, answer_data in enumerate(answers):
                    if answer_data.get('value'):
                        QuestionAnswer.objects.create(
                            question=updated_question,
                            value=answer_data['value'],
                            answer_text=answer_data['answer'],
                            order=i
                        )
            
            logger.info(f"Question updated successfully: {updated_question.id}")
            
            # Return the updated question
            return Response(serializer.data)
            
        except Exception as e:
            logger.error(f"Error updating question: {e}")
            return Response({
                'error': 'Failed to update question'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a question (admin only)"""
        try:
            question = self.get_object()
            question.is_approved = True
            question.save()

            logger.info(f"Question approved: {question.id}")

            serializer = self.get_serializer(question)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error approving question: {e}")
            return Response({
                'error': 'Failed to approve question'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject a question (admin only)"""
        try:
            question = self.get_object()
            question.is_approved = False
            question.save()

            logger.info(f"Question rejected: {question.id}")

            serializer = self.get_serializer(question)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error rejecting question: {e}")
            return Response({
                'error': 'Failed to reject question'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def mandatory(self, request):
        """Get mandatory questions"""
        questions = self.get_queryset().filter(question_type='mandatory')
        serializer = self.get_serializer(questions, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def unanswered(self, request):
        """Get questions user hasn't answered"""
        if request.user.is_authenticated:
            answered_question_ids = request.user.answers.values_list('question_id', flat=True)
            questions = self.get_queryset().exclude(id__in=answered_question_ids)
        else:
            # If not authenticated, return all questions
            questions = self.get_queryset()
        serializer = self.get_serializer(questions, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def restricted_text(self, request):
        """Get restricted text questions (admin only)"""
        # Removed staff requirement for testing
        # if not request.user.is_staff:
        #     return Response({'error': 'Staff only'}, status=403)

        # Get questions related to restricted text
        restricted_questions = Question.objects.filter(
            question_type='restricted_text'
        )
        serializer = self.get_serializer(restricted_questions, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def metadata(self, request):
        """
        Get question metadata in a single optimized query.
        Returns: distinct question numbers, total count, and answer counts.
        This replaces multiple paginated requests on the frontend.
        """
        from django.core.cache import cache
        from django.db.models import Count

        # Try to get from cache first (5 minute TTL)
        cache_key = 'questions_metadata_v2'  # Changed version to force cache refresh
        cached_data = cache.get(cache_key)

        if cached_data:
            logger.info("Returning cached question metadata")
            return Response(cached_data)

        # Get distinct question numbers using database aggregation (fast with index)
        # Only include approved questions
        distinct_numbers = Question.objects.filter(is_approved=True).values('question_number').distinct().order_by('question_number')
        question_numbers = [item['question_number'] for item in distinct_numbers]

        # Calculate answer counts efficiently using aggregation
        answer_counts = {}

        # Group questions by question_number (only approved questions)
        questions_by_number = {}
        questions = Question.objects.filter(is_approved=True).prefetch_related('user_answers')

        for question in questions:
            if question.question_number not in questions_by_number:
                questions_by_number[question.question_number] = []
            questions_by_number[question.question_number].append(question)

        # Calculate counts per question group
        for question_number, question_group in questions_by_number.items():
            if not question_group:
                continue

            # Check if grouped question
            is_grouped = len(question_group) > 1 or question_group[0].question_type in ['grouped', 'four', 'triple', 'double']

            if is_grouped:
                # For grouped: count unique users who answered ANY question in group
                user_ids = set()
                for question in question_group:
                    user_ids.update(UserAnswer.objects.filter(question=question).values_list('user_id', flat=True))
                answer_counts[question_number] = len(user_ids)
            else:
                # For individual: count users who answered this specific question
                answer_counts[question_number] = UserAnswer.objects.filter(question=question_group[0]).values('user').distinct().count()

        # Prepare response data
        metadata = {
            'distinct_question_numbers': question_numbers,
            'total_question_groups': len(question_numbers),
            'answer_counts': answer_counts
        }

        # Cache for 5 minutes
        cache.set(cache_key, metadata, 300)

        logger.info(f"Generated question metadata: {len(question_numbers)} question groups")
        return Response(metadata)

    @action(detail=False, methods=['get'])
    def answer_counts(self, request):
        """Get answer counts for questions"""
        # Get all questions grouped by question_number
        questions = Question.objects.all().order_by('question_number', 'group_number')

        # Create a dictionary to store answer counts by question_number
        answer_counts = {}

        # Group questions by question_number
        questions_by_number = {}
        for question in questions:
            if question.question_number not in questions_by_number:
                questions_by_number[question.question_number] = []
            questions_by_number[question.question_number].append(question)

        # Calculate answer counts for each question group
        for question_number, question_group in questions_by_number.items():
            if not question_group:
                continue

            # Check if this is a grouped question (multiple questions with same question_number)
            is_grouped = len(question_group) > 1 or question_group[0].question_type in ['grouped', 'four', 'triple', 'double']

            if is_grouped:
                # For grouped questions: count users who answered ANY question in the group
                user_ids_with_answers = set()
                for question in question_group:
                    question_user_ids = UserAnswer.objects.filter(question=question).values_list('user_id', flat=True)
                    user_ids_with_answers.update(question_user_ids)
                answer_counts[question_number] = len(user_ids_with_answers)
            else:
                # For individual questions: count users who answered this specific question
                question = question_group[0]
                count = UserAnswer.objects.filter(question=question).values('user').distinct().count()
                answer_counts[question_number] = count

        return Response(answer_counts)


class UserAnswerViewSet(viewsets.ModelViewSet):
    serializer_class = UserAnswerSerializer
    permission_classes = [permissions.AllowAny]  # Changed for testing
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']

    def get_queryset(self):
        queryset = UserAnswer.objects.all()
        
        # Filter by user if user parameter is provided
        user_id = self.request.query_params.get('user')
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        print(f"UserAnswerViewSet.get_queryset() called. Request: {self.request.method} {self.request.path}")
        print(f"Query params: {self.request.query_params}")
        print(f"User filter: {user_id}")
        print(f"Returning {queryset.count()} answers")
        
        return queryset

    def create(self, request, *args, **kwargs):
        """
        Custom create method to handle user_id and question_id
        """
        try:
            # Extract user_id and question_id from request data
            user_id = request.data.get('user_id')
            question_id = request.data.get('question_id')
            
            if not user_id:
                return Response({
                    'error': 'user_id is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if not question_id:
                return Response({
                    'error': 'question_id is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Get user and question objects
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return Response({
                    'error': 'User not found'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            try:
                question = Question.objects.get(id=question_id)
            except Question.DoesNotExist:
                return Response({
                    'error': 'Question not found'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Extract other fields
            me_answer = request.data.get('me_answer', 1)
            me_open_to_all = request.data.get('me_open_to_all', False)
            me_importance = request.data.get('me_importance', 1)
            me_share = request.data.get('me_share', True)
            looking_for_answer = request.data.get('looking_for_answer', 1)
            looking_for_open_to_all = request.data.get('looking_for_open_to_all', False)
            looking_for_importance = request.data.get('looking_for_importance', 1)
            looking_for_share = request.data.get('looking_for_share', True)
            
            # Create or update UserAnswer
            user_answer, created = UserAnswer.objects.update_or_create(
                user=user,
                question=question,
                defaults={
                    'me_answer': me_answer,
                    'me_open_to_all': me_open_to_all,
                    'me_importance': me_importance,
                    'me_share': me_share,
                    'looking_for_answer': looking_for_answer,
                    'looking_for_open_to_all': looking_for_open_to_all,
                    'looking_for_importance': looking_for_importance,
                    'looking_for_share': looking_for_share,
                }
            )

            # Maintain answered count and determine whether to enqueue a compatibility job
            if created:
                User.objects.filter(id=user.id).update(
                    questions_answered_count=F('questions_answered_count') + 1
                )
                user.refresh_from_db(fields=['questions_answered_count'])
            elif user.questions_answered_count == 0:
                actual_count = UserAnswer.objects.filter(user=user).count()
                if actual_count != user.questions_answered_count:
                    User.objects.filter(id=user.id).update(
                        questions_answered_count=actual_count
                    )
                    user.questions_answered_count = actual_count

            match_ready = (user.questions_answered_count or 0) >= MIN_MATCHABLE_ANSWERS
            has_existing_compat = Compatibility.objects.filter(
                Q(user1=user) | Q(user2=user)
            ).exists()

            should_enqueue, force_enqueue = should_enqueue_after_answer(
                question_id=str(question.id),
                user=user,
                created=created,
            )

            if match_ready and not has_existing_compat:
                should_enqueue = True
                force_enqueue = True

            if should_enqueue:
                enqueue_user_for_recalculation(user, force=force_enqueue)

            if should_enqueue and force_enqueue:
                try:
                    print(f"⚡ Inline compatibility recompute starting for user {user.id}", flush=True)
                    CompatibilityService.recalculate_all_compatibilities(user, use_full_reset=False)
                    job = getattr(user, 'compatibility_job', None)
                    if job:
                        job.attempts = (job.attempts or 0) + 1
                        job.status = CompatibilityJob.STATUS_COMPLETED
                        job.error_message = ''
                        job.last_attempt_at = timezone.now()
                        job.save(update_fields=['attempts', 'status', 'error_message', 'last_attempt_at', 'updated_at'])
                    print(f"✅ Inline compatibility recompute finished for user {user.id}", flush=True)
                except Exception as exc:
                    print(f"❌ Inline compatibility recompute failed for user {user.id}: {exc}", flush=True)
                    logger.exception(
                        "Immediate compatibility recompute failed for user %s: %s",
                        user.id,
                        exc,
                    )
                    # Leave the job pending for the scheduled worker to pick up
                    if should_enqueue:
                        enqueue_user_for_recalculation(user, force=force_enqueue)
            
            serializer = self.get_serializer(user_answer)
            status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
            return Response(serializer.data, status=status_code)
            
        except Exception as e:
            return Response({
                'error': f'Failed to create user answer: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def perform_create(self, serializer):
        serializer.save()

    @action(detail=False, methods=['get'])
    def by_question(self, request):
        """Get answers for a specific question"""
        question_id = request.query_params.get('question_id')
        if question_id:
            answers = self.get_queryset().filter(question_id=question_id)
            serializer = self.get_serializer(answers, many=True)
            return Response(serializer.data)
        return Response({'error': 'question_id parameter required'}, status=400)


class CompatibilityViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CompatibilitySerializer
    permission_classes = [permissions.AllowAny]  # Changed for testing
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['overall_compatibility', 'compatible_with_me', 'im_compatible_with']
    ordering = ['-overall_compatibility']

    def get_queryset(self):
        return Compatibility.objects.all()

    @action(detail=False, methods=['get'])
    def top_matches(self, request):
        """Get top compatibility matches"""
        limit = int(request.query_params.get('limit', 10))
        compatibilities = self.get_queryset().order_by('-overall_compatibility')[:limit]
        serializer = self.get_serializer(compatibilities, many=True)
        return Response(serializer.data)


class UserResultViewSet(viewsets.ModelViewSet):
    serializer_class = UserResultSerializer
    permission_classes = [permissions.AllowAny]  # Changed for testing
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']

    def get_queryset(self):
        return UserResult.objects.all()

    def perform_create(self, serializer):
        serializer.save()

    @action(detail=False, methods=['get'])
    def by_tag(self, request):
        """Get results by tag"""
        tag = request.query_params.get('tag')
        if tag:
            results = self.get_queryset().filter(tag=tag)
            serializer = self.get_serializer(results, many=True)
            return Response(serializer.data)
        return Response({'error': 'tag parameter required'}, status=400)

    @action(detail=False, methods=['get'])
    def liked(self, request):
        """Get liked users"""
        results = self.get_queryset().filter(tag__in=['liked', 'hot', 'approve'])
        serializer = self.get_serializer(results, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def matches(self, request):
        """Get matched users"""
        results = self.get_queryset().filter(tag='matched')
        serializer = self.get_serializer(results, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def toggle_tag(self, request):
        """Toggle a tag for a user - add if doesn't exist, remove if exists"""
        user_id = request.data.get('user_id')
        result_user_id = request.data.get('result_user_id')
        tag = request.data.get('tag')
        

        if not all([user_id, result_user_id, tag]):
            return Response(
                {'error': 'user_id, result_user_id, and tag are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Normalize tag to lowercase
        tag = tag.lower()

        try:
            user = User.objects.get(id=user_id)
            result_user = User.objects.get(id=result_user_id)
        except User.DoesNotExist as e:
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check if tag exists
        user_result = UserResult.objects.filter(
            user=user,
            result_user=result_user,
            tag=tag
        ).first()
        

        if user_result:
            # Tag exists, remove it
            user_result.delete()
            return Response({
                'action': 'removed',
                'tag': tag,
                'user_id': str(user_id),
                'result_user_id': str(result_user_id)
            })
        else:
            # Tag doesn't exist, add it
            user_result = UserResult.objects.create(
                user=user,
                result_user=result_user,
                tag=tag
            )
            serializer = self.get_serializer(user_result)
            return Response({
                'action': 'added',
                'tag': tag,
                'user_id': str(user_id),
                'result_user_id': str(result_user_id),
                'data': serializer.data
            }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'])
    def user_tags(self, request):
        """Get all tags for a specific user pair"""
        user_id = request.query_params.get('user_id')
        result_user_id = request.query_params.get('result_user_id')
        

        if not user_id or not result_user_id:
            return Response(
                {'error': 'user_id and result_user_id are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        tags = UserResult.objects.filter(
            user_id=user_id,
            result_user_id=result_user_id
        ).values_list('tag', flat=True)
        
        tags_list = list(tags)

        return Response({'tags': tags_list})


class UserTagViewSet(viewsets.ModelViewSet):
    serializer_class = UserTagSerializer
    permission_classes = [permissions.AllowAny]  # Changed for testing
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']

    def get_queryset(self):
        return UserTag.objects.all()

    def perform_create(self, serializer):
        serializer.save()

    @action(detail=False, methods=['get'])
    def by_tag(self, request):
        """Get tags by type"""
        tag = request.query_params.get('tag')
        if tag:
            tags = self.get_queryset().filter(tag=tag)
            serializer = self.get_serializer(tags, many=True)
            return Response(serializer.data)
        return Response({'error': 'tag parameter required'}, status=400)

    @action(detail=False, methods=['get'])
    def liked(self, request):
        """Get liked users"""
        tags = self.get_queryset().filter(tag__in=['liked', 'hot', 'approve'])
        serializer = self.get_serializer(tags, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def matches(self, request):
        """Get matched users"""
        tags = self.get_queryset().filter(tag='matched')
        serializer = self.get_serializer(tags, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def received(self, request):
        """Get all tags received by users"""
        tags = self.get_queryset()
        serializer = self.get_serializer(tags, many=True)
        return Response(serializer.data)


class MessageViewSet(viewsets.ModelViewSet):
    serializer_class = MessageSerializer
    permission_classes = [permissions.AllowAny]  # Changed for testing
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['created_at']
    ordering = ['created_at']

    def get_queryset(self):
        return Message.objects.all()

    def perform_create(self, serializer):
        serializer.save()

    @action(detail=False, methods=['get'])
    def conversations(self, request):
        """Get all conversations"""
        messages = self.get_queryset()
        serializer = self.get_serializer(messages, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def with_user(self, request):
        """Get messages with a specific user"""
        user_id = request.query_params.get('user_id')
        if user_id:
            messages = self.get_queryset().filter(
                Q(sender_id=user_id) | Q(receiver_id=user_id)
            )
            serializer = self.get_serializer(messages, many=True)
            return Response(serializer.data)
        return Response({'error': 'user_id parameter required'}, status=400)

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Mark a message as read"""
        message = self.get_object()
        message.is_read = True
        message.save()
        return Response({'status': 'marked as read'})


class PictureModerationViewSet(viewsets.ModelViewSet):
    serializer_class = PictureModerationSerializer
    permission_classes = [permissions.AllowAny]  # Changed for testing
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['submitted_at', 'moderated_at', 'status']
    ordering = ['-submitted_at']

    def get_queryset(self):
        if self.request.user.is_staff:
            return PictureModeration.objects.all()
        return PictureModeration.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save()

    @action(detail=False, methods=['get'])
    def pending(self, request):
        """Get pending picture moderations (admin only)"""
        # Removed staff requirement for testing
        # if not request.user.is_staff:
        #     return Response({'error': 'Staff only'}, status=403)
        
        pending_moderations = PictureModeration.objects.filter(status='pending')
        serializer = self.get_serializer(pending_moderations, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def queue(self, request):
        """Get picture moderation queue (admin only)"""
        # Removed staff requirement for testing
        # if not request.user.is_staff:
        #     return Response({'error': 'Staff only'}, status=403)
        
        # Get pending moderations with user details
        moderations = PictureModeration.objects.filter(status='pending').select_related('user')
        
        # Format data for frontend
        queue_data = []
        for moderation in moderations:
            # Use picture_url if available, otherwise fall back to picture.url
            picture_url = moderation.picture_url
            if not picture_url and moderation.picture:
                picture_url = moderation.picture.url

            queue_data.append({
                'id': moderation.id,
                'user': {
                    'id': moderation.user.id,
                    'first_name': moderation.user.first_name,
                    'last_name': moderation.user.last_name,
                    'email': moderation.user.email,
                    'profile_photo': moderation.user.profile_photo,
                },
                'picture': picture_url,
                'submitted_date': moderation.submitted_at,
                'status': moderation.status,
                'moderation_reason': moderation.moderator_notes,
                'previous_rejections': 0,  # You can implement this logic
            })
        
        return Response(queue_data)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a picture (admin only)"""
        # Removed staff requirement for testing
        # if not request.user.is_staff:
        #     return Response({'error': 'Staff only'}, status=403)

        moderation = self.get_object()

        # Update user's profile photo with the approved picture URL
        if moderation.picture_url:
            user = moderation.user
            user.profile_photo = moderation.picture_url
            user.save()
            print(f"✅ Updated user {user.id} profile_photo to: {moderation.picture_url}")

        moderation.status = 'approved'
        moderation.moderated_at = timezone.now()
        moderation.save()

        return Response({
            'status': 'approved',
            'user_id': str(moderation.user.id),
            'picture_url': moderation.picture_url
        })

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject a picture (admin only)"""
        # Removed staff requirement for testing
        # if not request.user.is_staff:
        #     return Response({'error': 'Staff only'}, status=403)
        
        moderation = self.get_object()
        reason = request.data.get('reason', '')
        
        moderation.status = 'rejected'
        moderation.rejection_reason = reason
        moderation.moderated_at = timezone.now()
        moderation.save()
        
        return Response({'status': 'rejected'})


class UserReportViewSet(viewsets.ModelViewSet):
    serializer_class = UserReportSerializer
    permission_classes = [permissions.AllowAny]  # Changed for testing
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['created_at', 'resolved_at', 'status']
    ordering = ['-created_at']

    def get_queryset(self):
        if self.request.user.is_staff:
            return UserReport.objects.all()
        return UserReport.objects.filter(reporter=self.request.user)

    def perform_create(self, serializer):
        serializer.save()

    @action(detail=False, methods=['get'])
    def pending(self, request):
        """Get pending reports (admin only)"""
        # Removed staff requirement for testing
        # if not request.user.is_staff:
        #     return Response({'error': 'Staff only'}, status=403)
        
        pending_reports = UserReport.objects.filter(status='pending')
        serializer = self.get_serializer(pending_reports, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def reported_users(self, request):
        """Get reported users with details (admin only)"""
        # Removed staff requirement for testing
        # if not request.user.is_staff:
        #     return Response({'error': 'Staff only'}, status=403)
        
        # Get all reports with user details
        reports = UserReport.objects.select_related('reported_user', 'reporter').all()
        
        # Group by reported user and aggregate data
        reported_users_data = {}
        for report in reports:
            user_id = report.reported_user.id
            if user_id not in reported_users_data:
                reported_users_data[user_id] = {
                    'user': {
                        'id': report.reported_user.id,
                        'first_name': report.reported_user.first_name,
                        'last_name': report.reported_user.last_name,
                        'email': report.reported_user.email,
                        'profile_photo': report.reported_user.profile_photo.url if report.reported_user.profile_photo else None,
                    },
                    'report_reason': report.reason,
                    'report_date': report.created_at,
                    'report_count': 1,
                    'status': report.status,
                    'severity': 'Medium',  # You can implement severity logic
                    'reporter_count': 1,
                    'last_reported': report.created_at,
                    'current_restriction': report.reported_user.is_banned,
                }
            else:
                # Aggregate data for multiple reports
                reported_users_data[user_id]['report_count'] += 1
                reported_users_data[user_id]['reporter_count'] += 1
                if report.created_at > reported_users_data[user_id]['last_reported']:
                    reported_users_data[user_id]['last_reported'] = report.created_at
                    reported_users_data[user_id]['report_reason'] = report.reason
        
        return Response(list(reported_users_data.values()))

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """Resolve a report (admin only)"""
        # Removed staff requirement for testing
        # if not request.user.is_staff:
        #     return Response({'error': 'Staff only'}, status=403)
        
        report = self.get_object()
        action = request.data.get('action', 'dismiss')
        
        if action == 'dismiss':
            report.status = 'dismissed'
            report.resolved_at = timezone.now()
            report.save()
            return Response({'status': 'dismissed'})
        
        elif action == 'restrict':
            # Apply temporary restriction to reported user
            reported_user = report.reported_user
            reported_user.is_banned = True
            reported_user.restriction_reason = f'Reported: {report.reason}'
            reported_user.restriction_date = timezone.now()
            reported_user.restriction_type = 'temporary'
            reported_user.restriction_duration = 30  # 30 days
            reported_user.save()
            
            report.status = 'resolved'
            report.resolved_at = timezone.now()
            report.save()
            
            return Response({'status': 'restricted'})
        
        elif action == 'permanent':
            # Apply permanent restriction to reported user
            reported_user = report.reported_user
            reported_user.is_banned = True
            reported_user.restriction_reason = f'Permanently banned due to report: {report.reason}'
            reported_user.restriction_date = timezone.now()
            reported_user.restriction_type = 'permanent'
            reported_user.restriction_duration = 0
            reported_user.save()
            
            report.status = 'resolved'
            report.resolved_at = timezone.now()
            report.save()
            
            return Response({'status': 'permanently_banned'})

        return Response({'error': 'Invalid action'}, status=400)


class StatsViewSet(viewsets.ViewSet):
    """Dashboard statistics endpoint"""
    permission_classes = [permissions.AllowAny]

    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        """Get dashboard statistics"""
        from datetime import timedelta

        now = timezone.now()
        day_ago = now - timedelta(days=1)
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)
        year_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

        active_users = User.objects.filter(is_banned=False)

        total_users = active_users.count()
        daily_active = active_users.filter(last_login__gte=day_ago).count()
        weekly_active = active_users.filter(last_login__gte=week_ago).count()
        monthly_active = active_users.filter(last_login__gte=month_ago).count()
        new_users_this_year = active_users.filter(date_joined__gte=year_start).count()

        total_matches = UserResult.objects.filter(tag='matched').count()
        total_likes = UserResult.objects.filter(tag='like').count()
        total_approves = UserResult.objects.filter(tag='approve').count()

        return Response({
            'total_users': total_users,
            'daily_active_users': daily_active,
            'weekly_active_users': weekly_active,
            'monthly_active_users': monthly_active,
            'new_users_this_year': new_users_this_year,
            'total_matches': total_matches,
            'total_likes': total_likes,
            'total_approves': total_approves
        })

    @action(detail=False, methods=['get'])
    def timeseries(self, request):
        """Get time-series data for charts"""
        from datetime import timedelta
        from api.models import DailyMetric

        # Get period parameter (default: 30 days)
        period = request.query_params.get('period', '30')
        try:
            days = int(period)
        except ValueError:
            days = 30

        # Get metrics for the specified period
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)

        metrics = DailyMetric.objects.filter(
            date__gte=start_date,
            date__lte=end_date
        ).order_by('date')

        # Format data for frontend
        data = []
        for metric in metrics:
            data.append({
                'date': metric.date.isoformat(),
                'users': metric.active_users,
                'approves': metric.total_approves,
                'likes': metric.total_likes,
                'matches': metric.total_matches,
                'new_users': metric.new_users,
            })

        return Response({
            'period': days,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'data': data
        })


class ControlsViewSet(viewsets.ModelViewSet):
    """ViewSet for managing Controls (app-wide configuration)"""
    serializer_class = ControlsSerializer
    permission_classes = [permissions.AllowAny]  # Changed for testing

    def get_queryset(self):
        return Controls.objects.all()

    @action(detail=False, methods=['get'])
    def current(self, request):
        """Get the current/active controls (creates default if none exists)"""
        controls = Controls.get_current()
        serializer = self.get_serializer(controls)
        return Response(serializer.data)

    def update(self, request, *args, **kwargs):
        """Update controls values"""
        # Get the current controls or the one being updated
        if kwargs.get('pk'):
            instance = self.get_object()
        else:
            instance = Controls.get_current()

        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data)
