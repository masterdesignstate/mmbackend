from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q, Count, F, Exists, OuterRef
from django.utils import timezone
from datetime import timedelta
import logging
import time
from collections import defaultdict

logger = logging.getLogger(__name__)

from .models import (
    User, Tag, Question, UserAnswer, UserRequiredQuestion, Compatibility,
    UserResult, Message, PictureModeration, UserReport, UserOnlineStatus, UserTag, Controls,
    CompatibilityJob, Notification, Conversation,
)
from .services.compatibility_service import CompatibilityService
from .services.compatibility_queue import (
    enqueue_user_for_recalculation,
    should_enqueue_after_answer,
    MIN_MATCHABLE_ANSWERS,
)
from .serializers import (
    UserSerializer, TagSerializer, QuestionSerializer, UserAnswerSerializer,
    UserRequiredQuestionSerializer, CompatibilitySerializer, UserResultSerializer, MessageSerializer,
    PictureModerationSerializer, UserReportSerializer, UserOnlineStatusSerializer,
    DetailedUserSerializer, DetailedQuestionSerializer, UserTagSerializer,
    SimpleUserSerializer, ControlsSerializer, NotificationSerializer, ConversationSerializer,
)
from .permissions import IsDashboardAdmin


class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [permissions.AllowAny]  # Changed for testing
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['username', 'first_name', 'last_name', 'from_location', 'live', 'bio']
    ordering_fields = ['age', 'height', 'questions_answered_count', 'last_active']
    ordering = ['-last_active']

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

        # Update last_active timestamp (is_online is now a computed property)
        user.last_active = timezone.now()
        user.save(update_fields=['last_active'])

        # Also update the old UserOnlineStatus model if it exists (for backwards compatibility)
        online_status, created = UserOnlineStatus.objects.get_or_create(user=user)
        online_status.is_online = request.data.get('is_online', False)
        online_status.last_activity = timezone.now()
        online_status.save()

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
        _raw_scope = request.query_params.get('required_scope', 'my')
        required_scope = (_raw_scope or 'my').lower()
        if required_scope not in ('my', 'their'):
            required_scope = 'my'
        sort_by = request.query_params.get('sort', 'overall_compatibility')  # New: support sorting by required
        if required_only and required_scope == 'their' and not sort_by.startswith('required_'):
            sort_by = 'required_im_compatible_with'

        # Get age and distance filter parameters
        min_age = request.query_params.get('min_age')
        max_age = request.query_params.get('max_age')
        min_distance = request.query_params.get('min_distance')
        max_distance = request.query_params.get('max_distance')

        if min_age:
            min_age = int(min_age)
        if max_age:
            max_age = int(max_age)
        if min_distance:
            min_distance = int(min_distance)
        if max_distance:
            max_distance = int(max_distance)

        # Get tag filter parameters
        tags = request.query_params.getlist('tags')  # Get multiple tag values
        print(f"🔍 Tag filters: {tags}")

        # Get required/pending filter parameters (for server-side filtering)
        filter_required = request.query_params.get('filter_required', 'false').lower() == 'true'
        filter_pending = request.query_params.get('filter_pending', 'false').lower() == 'true'
        filter_their_required = request.query_params.get('filter_their_required', 'false').lower() == 'true'
        filter_their_pending = request.query_params.get('filter_their_pending', 'false').lower() == 'true'
        print(f"🔍 Required filters: required={filter_required}, pending={filter_pending}, their_required={filter_their_required}, their_pending={filter_their_pending}")
        print(f"🔍 Age filters: min={min_age}, max={max_age}")
        print(f"🔍 Distance filters: min={min_distance}, max={max_distance}")

        # Get search parameters
        search_term = request.query_params.get('search', '').strip()
        search_field = request.query_params.get('search_field', 'name').strip()
        print(f"🔍 Search: term='{search_term}', field='{search_field}'")

        # Get pagination parameters
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 15))
        offset = (page - 1) * page_size

        print(f"🔍 === COMPATIBLE ENDPOINT CALLED ===")
        print(f"   User: {request.user.id}")
        print(f"   RAW query required_scope={_raw_scope!r}, required_only={required_only}, required_scope={required_scope!r}, sort={request.query_params.get('sort', '')!r}")
        logger.info(f"Compatible users request for user {request.user.id}")
        logger.info(f"Filters: type={compatibility_type}, min={min_compatibility}, max={max_compatibility}, required_only={required_only}")
        logger.info(f"Pagination: page={page}, size={page_size}, offset={offset}")

        try:
            from django.db.models import Q, Case, When, FloatField, BooleanField
            from django.db import models
            from .models import Compatibility
            from .serializers import SimpleUserSerializer

            compatibility_field = {
                'overall_compatibility': 'overall_compatibility',
                'compatible_with_me': 'compatible_with_me',
                'im_compatible_with': 'im_compatible_with',
                'required_overall_compatibility': 'required_overall_compatibility',
                'required_compatible_with_me': 'required_compatible_with_me',
                'required_im_compatible_with': 'required_im_compatible_with',
            }.get(compatibility_type, 'overall_compatibility')

            apply_required_filter = required_only

            # Determine which field to use for sorting
            if sort_by.startswith('required_'):
                # Sorting by required compatibility
                if sort_by == 'required_compatible_with_me':
                    compatibility_score_expression = Case(
                        When(user1=request.user, then='required_compatible_with_me'),
                        default='required_im_compatible_with',
                        output_field=FloatField()
                    )
                elif sort_by == 'required_im_compatible_with':
                    compatibility_score_expression = Case(
                        When(user1=request.user, then='required_im_compatible_with'),
                        default='required_compatible_with_me',
                        output_field=FloatField()
                    )
                else:  # required_overall_compatibility
                    compatibility_score_expression = Case(
                        When(user1=request.user, then='required_overall_compatibility'),
                        default='required_overall_compatibility',
                        output_field=FloatField()
                    )
            else:
                # Use pre-calculated compatibilities for instant ranking of ALL users
                if compatibility_type == 'compatible_with_me':
                    compatibility_score_expression = Case(
                        When(user1=request.user, then='compatible_with_me'),
                        default='im_compatible_with',
                        output_field=FloatField()
                    )
                elif compatibility_type == 'im_compatible_with':
                    compatibility_score_expression = Case(
                        When(user1=request.user, then='im_compatible_with'),
                        default='compatible_with_me',
                        output_field=FloatField()
                    )
                else:
                    compatibility_score_expression = Case(
                        When(user1=request.user, then='overall_compatibility'),
                        default='overall_compatibility',
                        output_field=FloatField()
                    )

            # When required_scope=their, sort by "their required" score (compatibility on other user's required only)
            if apply_required_filter and required_scope == 'their':
                compatibility_score_expression = Case(
                    When(user1=request.user, then='their_required_compatibility'),
                    default='required_compatible_with_me',
                    output_field=FloatField()
                )

            # When required_only is enabled, we need to sort by completeness first, then by required compatibility
            if apply_required_filter and sort_by.startswith('required_'):
                # Completeness: for "my" = what % of MY required did THEY answer; for "their" = what % of THEIR required did I answer
                annotate_kwargs = dict(
                    other_user_id=Case(
                        When(user1=request.user, then='user2__id'),
                        default='user1__id'
                    ),
                    compatibility_score=compatibility_score_expression,
                    their_completeness=Case(
                        When(user1=request.user, then='user2_required_completeness'),
                        default='user1_required_completeness',
                        output_field=FloatField()
                    ),
                    my_completeness_toward_them=Case(
                        When(user1=request.user, then='user1_required_completeness'),
                        default='user2_required_completeness',
                        output_field=FloatField()
                    )
                )
                if required_scope == 'their':
                    compatibilities = Compatibility.objects.filter(
                        Q(user1=request.user) | Q(user2=request.user)
                    ).select_related('user1', 'user2').annotate(**annotate_kwargs).order_by('-my_completeness_toward_them', '-compatibility_score')
                else:
                    compatibilities = Compatibility.objects.filter(
                        Q(user1=request.user) | Q(user2=request.user)
                    ).select_related('user1', 'user2').annotate(**annotate_kwargs).order_by('-their_completeness', '-compatibility_score')
            else:
                compatibilities = Compatibility.objects.filter(
                    Q(user1=request.user) | Q(user2=request.user)
                ).select_related('user1', 'user2').annotate(
                    # Determine which user is the "other" user and get the right compatibility score
                    other_user_id=Case(
                        When(user1=request.user, then='user2__id'),
                        default='user1__id'
                    ),
                    compatibility_score=compatibility_score_expression,
                    # Get the completeness from the correct direction
                    # This is: what % of MY required questions did THEY answer?
                    their_completeness=Case(
                        When(user1=request.user, then='user2_required_completeness'),
                        default='user1_required_completeness',
                        output_field=FloatField()
                    )
                ).order_by('-their_completeness', '-compatibility_score')

            # Apply compatibility filters based on selected compatibility type
            if not apply_required_filter:
                if min_compatibility > 0:
                    compatibilities = compatibilities.filter(compatibility_score__gte=min_compatibility)
                if max_compatibility < 100:
                    compatibilities = compatibilities.filter(compatibility_score__lte=max_compatibility)

            # Apply tag filters (Liked, Saved, etc.). Skip when Required/Pending/Their Required/Their Pending
            # are in use: those filters only use required/pending logic, not UserResult tags.
            using_required_pending_filters = filter_required or filter_pending or filter_their_required or filter_their_pending
            if tags and not using_required_pending_filters:
                from .models import UserResult
                print(f"🔍 Applying tag filters: {tags}")
                
                # Get user IDs that match the tag criteria
                tag_filtered_user_ids = set()
                not_approved_exclude_ids = set()
                has_not_approved_tag = False
                
                for tag in tags:
                    tag_lower = tag.lower()
                    # Required/Pending/Their Required/Their Pending are filter flags, not UserResult tags - don't filter compatibilities by them
                    if tag_lower in ('required', 'pending', 'their required', 'their pending'):
                        continue
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
                        
                    elif tag_lower == 'approved me':
                        # Users who have approved me (tagged me as approve)
                        approved_me_user_ids = UserResult.objects.filter(
                            result_user=request.user,
                            tag='approve'
                        ).values_list('user_id', flat=True)
                        tag_filtered_user_ids.update(approved_me_user_ids)
                        print(f"🔍 Found {len(approved_me_user_ids)} users who approved me")
                        
                    elif tag_lower == 'liked me':
                        # Users who have liked me (tagged me as like)
                        liked_me_user_ids = UserResult.objects.filter(
                            result_user=request.user,
                            tag='like'
                        ).values_list('user_id', flat=True)
                        tag_filtered_user_ids.update(liked_me_user_ids)
                        print(f"🔍 Found {len(liked_me_user_ids)} users who liked me")
                        
                    elif tag_lower == 'not approved':
                        # Users I have NOT approved (exclude users I've tagged as approve)
                        has_not_approved_tag = True
                        approved_by_me_user_ids = UserResult.objects.filter(
                            user=request.user,
                            tag='approve'
                        ).values_list('result_user_id', flat=True)
                        not_approved_exclude_ids = set(approved_by_me_user_ids)
                        print(f"🔍 Will exclude {len(not_approved_exclude_ids)} users I have approved")
                        
                    else:
                        # Handle other tags
                        other_tag_user_ids = UserResult.objects.filter(
                            user=request.user,
                            tag=tag_lower
                        ).values_list('result_user_id', flat=True)
                        tag_filtered_user_ids.update(other_tag_user_ids)
                        print(f"🔍 Found {len(other_tag_user_ids)} users with tag '{tag_lower}'")
                
                # Handle "Not Approved" tag - exclude approved users from compatibilities
                if has_not_approved_tag and not_approved_exclude_ids:
                    compatibilities = compatibilities.exclude(
                        Q(user1=request.user, user2__id__in=not_approved_exclude_ids) |
                        Q(user2=request.user, user1__id__in=not_approved_exclude_ids)
                    )
                    print(f"🔍 After excluding approved users: {compatibilities.count()} compatibilities remain")
                
                # Filter compatibilities to only include users that match tag criteria
                special_tag_names = {'required', 'pending', 'their required', 'their pending'}
                had_non_special_tags = any(tag.lower() not in special_tag_names for tag in tags)
                if tag_filtered_user_ids:
                    print(f"🔍 Tag filtered user IDs: {list(tag_filtered_user_ids)}")
                    compatibilities = compatibilities.filter(
                        Q(user1__id__in=tag_filtered_user_ids) | Q(user2__id__in=tag_filtered_user_ids)
                    )
                    print(f"🔍 After tag filtering: {compatibilities.count()} compatibilities remain")
                elif has_not_approved_tag:
                    # If only "Not Approved" tag is selected, we've already filtered by exclusion
                    print(f"🔍 Only 'Not Approved' tag selected, using exclusion filter")
                elif had_non_special_tags:
                    # Had real tags (Liked, Saved, etc.) but no users matched
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

            # Apply age filters
            if min_age is not None or max_age is not None:
                if min_age is not None:
                    compatibilities = compatibilities.filter(
                        Q(user1=request.user, user2__age__gte=min_age) |
                        Q(user2=request.user, user1__age__gte=min_age)
                    )
                if max_age is not None:
                    compatibilities = compatibilities.filter(
                        Q(user1=request.user, user2__age__lte=max_age) |
                        Q(user2=request.user, user1__age__lte=max_age)
                    )
                print(f"🔍 Applied age filters: min={min_age}, max={max_age}")

            # Exclude hidden users unless explicitly filtering for them
            # This ensures we always return the requested number of non-hidden users per page
            is_filtering_for_hidden = tags and any(tag.lower() in ['hidden', 'hide'] for tag in tags)
            if not is_filtering_for_hidden:
                from .models import UserResult
                # Get IDs of users that the current user has hidden
                hidden_user_ids = UserResult.objects.filter(
                    user=request.user,
                    tag='hide'
                ).values_list('result_user_id', flat=True)

                if hidden_user_ids:
                    # Exclude hidden users from compatibilities
                    compatibilities = compatibilities.exclude(
                        Q(user1__id__in=hidden_user_ids) | Q(user2__id__in=hidden_user_ids)
                    )
                    print(f"🚫 Excluded {len(hidden_user_ids)} hidden users from results")

            # Apply search filters
            if search_term:
                search_lower = search_term.lower()
                if search_field == 'name':
                    # Filter by first_name (case-insensitive contains)
                    compatibilities = compatibilities.filter(
                        Q(user1=request.user, user2__first_name__icontains=search_term) |
                        Q(user2=request.user, user1__first_name__icontains=search_term)
                    )
                    print(f"🔍 Applied name search filter: '{search_term}'")
                elif search_field == 'username':
                    # Filter by username (case-insensitive contains)
                    compatibilities = compatibilities.filter(
                        Q(user1=request.user, user2__username__icontains=search_term) |
                        Q(user2=request.user, user1__username__icontains=search_term)
                    )
                    print(f"🔍 Applied username search filter: '{search_term}'")
                elif search_field == 'live':
                    # Filter by live location (case-insensitive contains)
                    compatibilities = compatibilities.filter(
                        Q(user1=request.user, user2__live__icontains=search_term) |
                        Q(user2=request.user, user1__live__icontains=search_term)
                    )
                    print(f"🔍 Applied live location search filter: '{search_term}'")
                elif search_field == 'bio':
                    # Filter by bio (case-insensitive contains)
                    compatibilities = compatibilities.filter(
                        Q(user1=request.user, user2__bio__icontains=search_term) |
                        Q(user2=request.user, user1__bio__icontains=search_term)
                    )
                    print(f"🔍 Applied bio search filter: '{search_term}'")

            if apply_required_filter:
                print(f"🔍 [required] ENTERING required_filter path: required_scope={required_scope!r}")
                compatibility_results = []

                for comp in compatibilities:
                    # Determine which user is the "other" user
                    other_user = comp.user2 if comp.user1 == request.user else comp.user1

                    # Skip banned users
                    if other_user.is_banned:
                        continue

                    compatibility_results.append({
                        'user': other_user,
                        'compatibility': {
                            'overall_compatibility': comp.overall_compatibility,
                            'compatible_with_me': comp.compatible_with_me if comp.user1 == request.user else comp.im_compatible_with,
                            'im_compatible_with': comp.im_compatible_with if comp.user1 == request.user else comp.compatible_with_me,
                            'mutual_questions_count': comp.mutual_questions_count,
                            # Include required compatibility fields
                            'required_overall_compatibility': comp.required_overall_compatibility,
                            'required_compatible_with_me': comp.required_compatible_with_me if comp.user1 == request.user else comp.required_im_compatible_with,
                            'required_im_compatible_with': comp.required_im_compatible_with if comp.user1 == request.user else comp.required_compatible_with_me,
                            'their_required_compatibility': comp.their_required_compatibility if comp.user1 == request.user else comp.required_compatible_with_me,
                            'required_mutual_questions_count': comp.required_mutual_questions_count,
                        },
                        'missing_required': False
                    })

                # Per-user required: from UserRequiredQuestion
                current_user_required_qids = set(
                    UserRequiredQuestion.objects.filter(user=request.user).values_list('question_id', flat=True)
                )

                missing_user_ids = []
                if current_user_required_qids:
                    print(f"🔍 Current user has {len(current_user_required_qids)} required questions (per-user required filter)")

                    other_user_ids = [item['user'].id for item in compatibility_results]
                    # For each other user: which of my required questions have they answered?
                    other_user_answers = UserAnswer.objects.filter(
                        user_id__in=other_user_ids,
                        question_id__in=current_user_required_qids
                    ).values_list('user_id', 'question_id')

                    user_answered_questions = defaultdict(set)
                    for user_id, question_id in other_user_answers:
                        user_answered_questions[str(user_id)].add(question_id)

                    for item in compatibility_results:
                        other_user_id = item['user'].id
                        answered_questions = user_answered_questions.get(str(other_user_id), set())
                        # missing_required = True if other user hasn't answered all questions I marked required
                        item['missing_required'] = not current_user_required_qids.issubset(answered_questions)
                        if item['missing_required']:
                            missing_user_ids.append(other_user_id)

                if missing_user_ids:
                    current_user_non_required_answers = list(
                        UserAnswer.objects.filter(
                            user=request.user
                        ).exclude(
                            question_id__in=current_user_required_qids
                        ).only(
                            'question_id',
                            'me_answer',
                            'me_open_to_all',
                            'me_importance',
                            'looking_for_answer',
                            'looking_for_open_to_all',
                            'looking_for_importance',
                        )
                    )

                    other_answers_qs = UserAnswer.objects.filter(
                        user_id__in=missing_user_ids
                    ).exclude(
                        question_id__in=current_user_required_qids
                    ).only(
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
                    for answer in other_answers_qs:
                        answers_by_user[answer.user_id].append(answer)

                    for item in compatibility_results:
                        if not item['missing_required']:
                            continue
                        other_answers = answers_by_user.get(item['user'].id, [])
                        item['compatibility_non_required'] = CompatibilityService.calculate_compatibility_between_users(
                            request.user,
                            item['user'],
                            exclude_required=True,
                            user1_answers=current_user_non_required_answers,
                            user2_answers=other_answers,
                        )

                # their_missing_required: has current user answered all questions that OTHER user marked required?
                # Normalize all IDs to string for dict keys (UUID vs str can differ across DB/ORM)
                other_user_ids = [item['user'].id for item in compatibility_results]

                # Per-user required: from UserRequiredQuestion
                other_users_required_answered = UserRequiredQuestion.objects.filter(
                    user_id__in=other_user_ids
                ).values_list('user_id', 'question_id')

                other_user_required_qids = defaultdict(set)
                for user_id, question_id in other_users_required_answered:
                    other_user_required_qids[str(user_id)].add(question_id)

                # Current user's answered question IDs (for subset check)
                current_user_answered_qids = set(
                    UserAnswer.objects.filter(user=request.user).values_list('question_id', flat=True)
                )

                their_missing_user_ids = []
                for item in compatibility_results:
                    other_user_id = item['user'].id
                    key = str(other_user_id).lower()
                    their_required_qids = other_user_required_qids.get(key, set())
                    if not their_required_qids:
                        their_required_qids = other_user_required_qids.get(str(other_user_id), set())
                    if their_required_qids:
                        # their_missing_required = True if current user hasn't answered all questions they marked required
                        item['their_missing_required'] = not their_required_qids.issubset(current_user_answered_qids)
                        if item['their_missing_required']:
                            their_missing_user_ids.append(other_user_id)
                    else:
                        # They have NO required questions: exclude from "Their Required" (only show people who have required AND I answered all)
                        item['their_missing_required'] = True

                # Calculate compatibility_non_required for Their Pending users (if not already calculated)
                if their_missing_user_ids:
                    their_pending_without_non_required = [
                        uid for uid in their_missing_user_ids
                        if uid not in missing_user_ids
                    ]

                    if their_pending_without_non_required:
                        # Reuse current_user_non_required_answers if already fetched, otherwise fetch now
                        if not missing_user_ids:
                            current_user_non_required_answers = list(
                                UserAnswer.objects.filter(
                                    user=request.user
                                ).exclude(
                                    question_id__in=current_user_required_qids
                                ).only(
                                    'question_id',
                                    'me_answer',
                                    'me_open_to_all',
                                    'me_importance',
                                    'looking_for_answer',
                                    'looking_for_open_to_all',
                                    'looking_for_importance',
                                )
                            )

                        their_pending_answers_qs = UserAnswer.objects.filter(
                            user_id__in=their_pending_without_non_required
                        ).exclude(
                            question_id__in=current_user_required_qids
                        ).only(
                            'user_id',
                            'question_id',
                            'me_answer',
                            'me_open_to_all',
                            'me_importance',
                            'looking_for_answer',
                            'looking_for_open_to_all',
                            'looking_for_importance',
                        )

                        their_pending_answers_by_user: dict[object, list[UserAnswer]] = defaultdict(list)
                        for answer in their_pending_answers_qs:
                            their_pending_answers_by_user[answer.user_id].append(answer)

                        for item in compatibility_results:
                            if not item.get('their_missing_required') or item.get('compatibility_non_required'):
                                continue  # Skip if not Their Pending or already has non-required
                            other_answers = their_pending_answers_by_user.get(item['user'].id, [])
                            item['compatibility_non_required'] = CompatibilityService.calculate_compatibility_between_users(
                                request.user,
                                item['user'],
                                exclude_required=True,
                                user1_answers=current_user_non_required_answers,
                                user2_answers=other_answers,
                            )

                # When required_scope=their, compute their_required_compatibility on the fly if missing/0 (e.g. never recalculated)
                if required_scope == 'their':
                    for item in compatibility_results:
                        trc = item['compatibility'].get('their_required_compatibility')
                        try:
                            trc_val = float(trc) if trc is not None else 0
                        except (TypeError, ValueError):
                            trc_val = 0
                        if trc_val == 0:
                            try:
                                data = CompatibilityService.calculate_compatibility_between_users(
                                    request.user, item['user']
                                )
                                item['compatibility']['their_required_compatibility'] = data.get(
                                    'their_required_compatibility', 0
                                )
                            except Exception:
                                pass

                def get_sort_score(result: dict, use_their_required: bool = False) -> float:
                    # When required_scope=their, sort by their_required_compatibility (how well I match their required)
                    if use_their_required:
                        return float(result['compatibility'].get('their_required_compatibility', 0.0) or 0.0)
                    # Use non-required compatibility for Pending or Their Pending users
                    if (result.get('missing_required') or result.get('their_missing_required')) and result.get('compatibility_non_required'):
                        return float(result['compatibility_non_required'].get(compatibility_field, 0.0) or 0.0)
                    return float(result['compatibility'].get(compatibility_field, 0.0) or 0.0)

                # Min/max compatibility filter; skip when "Their Required" tag is on so everyone who qualifies is shown
                if not filter_their_required:
                    compatibility_results = [
                        result for result in compatibility_results
                        if min_compatibility <= get_sort_score(result, use_their_required=(required_scope == 'their')) <= max_compatibility
                    ]

                # Apply Required/Pending/Their Required/Their Pending filters (server-side)
                # These filters are applied before pagination to ensure correct page counts
                if filter_required and not filter_pending:
                    # Show only users where missing_required is False (they answered all my required questions)
                    compatibility_results = [r for r in compatibility_results if not r.get('missing_required', False)]
                    print(f"🔍 Filtered to Required: {len(compatibility_results)} results")
                elif filter_pending and not filter_required:
                    # Show only users where missing_required is True (they haven't answered all my required questions)
                    compatibility_results = [r for r in compatibility_results if r.get('missing_required', False)]
                    print(f"🔍 Filtered to Pending: {len(compatibility_results)} results")
                # If both filter_required and filter_pending are True, show all (no filtering)

                if filter_their_required and not filter_their_pending:
                    # Show only users where their_missing_required is False (I answered all their required questions)
                    compatibility_results = [r for r in compatibility_results if not r.get('their_missing_required', False)]
                    their_required_usernames = [r['user'].username for r in compatibility_results]
                    print(f"🔍 Filtered to Their Required: {len(compatibility_results)} results: {their_required_usernames}")
                elif filter_their_pending and not filter_their_required:
                    # Show only users where their_missing_required is True (I haven't answered all their required questions)
                    compatibility_results = [r for r in compatibility_results if r.get('their_missing_required', False)]
                    print(f"🔍 Filtered to Their Pending: {len(compatibility_results)} results")
                # If both filter_their_required and filter_their_pending are True, show all (no filtering)

                # Sort: when required_scope=their use their_required_compatibility and their_missing_required; else use my required
                print(f"🔍 [required] BEFORE SORT: required_scope={required_scope!r}, result_count={len(compatibility_results)}")
                for i, r in enumerate(compatibility_results[:5]):
                    trc = r['compatibility'].get('their_required_compatibility')
                    rcm = r['compatibility'].get('required_compatible_with_me')
                    ric = r['compatibility'].get('required_im_compatible_with')
                    print(f"   [{i}] user={r['user'].id} their_required_compat={trc} required_cw_me={rcm} required_im_cw={ric}")
                if required_scope == 'their':
                    compatibility_results.sort(
                        key=lambda result: (
                            result.get('their_missing_required', False),
                            -get_sort_score(result, use_their_required=True),
                            str(result['user'].id)
                        )
                    )
                    print(f"🔍 [required] SORTED BY: their_missing_required, -their_required_compatibility, user_id")
                else:
                    compatibility_results.sort(
                        key=lambda result: (
                            result.get('missing_required', False),
                            -get_sort_score(result, use_their_required=False),
                            str(result['user'].id)
                        )
                    )
                    print(f"🔍 [required] SORTED BY: missing_required, -required_compat (my), user_id")
                for i, r in enumerate(compatibility_results[:5]):
                    trc = r['compatibility'].get('their_required_compatibility')
                    print(f"   AFTER SORT [{i}] user={r['user'].id} their_required_compat={trc}")
                order_ids = [str(r['user'].id) for r in compatibility_results[:10]]
                print(f"🔍 [required] FIRST 10 USER IDS IN ORDER: {order_ids}")

                total_users = len(compatibility_results)
                paginated_results = compatibility_results[offset:offset + page_size]
                page_ids = [str(r['user'].id) for r in paginated_results]
                print(f"🔍 [required] PAGE {page} (offset={offset}): returning user ids order: {page_ids}")

                response_data = []
                for result in paginated_results:
                    user_serializer = SimpleUserSerializer(result['user'])
                    response_item = {
                        'user': user_serializer.data,
                        'compatibility': result['compatibility'],
                        'missing_required': result.get('missing_required', False),
                        'their_missing_required': result.get('their_missing_required', False)
                    }
                    if result.get('compatibility_non_required'):
                        response_item['compatibility_non_required'] = result['compatibility_non_required']
                    response_data.append(response_item)

                logger.info(f"Returning {len(response_data)} compatible users with required filter applied")

                return Response({
                    'results': response_data,
                    'count': len(response_data),
                    'total_count': total_users,
                    'page': page,
                    'page_size': page_size,
                    'has_next': offset + page_size < total_users,
                    'message': f'Showing {len(response_data)} users from {total_users} total ranked by compatibility'
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
                is_user1 = comp.user1 == request.user
                response_data.append({
                    'user': user_serializer.data,
                    'compatibility': {
                        'overall_compatibility': comp.overall_compatibility,
                        'compatible_with_me': comp.compatible_with_me if is_user1 else comp.im_compatible_with,
                        'im_compatible_with': comp.im_compatible_with if is_user1 else comp.compatible_with_me,
                        'mutual_questions_count': comp.mutual_questions_count,
                        'required_overall_compatibility': comp.required_overall_compatibility,
                        'required_compatible_with_me': comp.required_compatible_with_me if is_user1 else comp.required_im_compatible_with,
                        'required_im_compatible_with': comp.required_im_compatible_with if is_user1 else comp.required_compatible_with_me,
                        'their_required_compatibility': comp.their_required_compatibility if is_user1 else comp.required_compatible_with_me,
                        'required_mutual_questions_count': comp.required_mutual_questions_count,
                        'user1_required_completeness': comp.user1_required_completeness if is_user1 else comp.user2_required_completeness,
                        'user2_required_completeness': comp.user2_required_completeness if is_user1 else comp.user1_required_completeness,
                        'required_completeness_ratio': comp.required_completeness_ratio,
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

    @action(detail=False, methods=['get'])
    def compatibility_with(self, request):
        """Get compatibility between two specific users"""
        from django.db.models import Q
        from .models import Compatibility

        user_id = request.query_params.get('user_id')
        other_user_id = request.query_params.get('other_user_id')

        if not user_id or not other_user_id:
            return Response({
                'error': 'Both user_id and other_user_id are required'
            }, status=400)

        try:
            # Find compatibility record between the two users (either direction)
            compatibility = Compatibility.objects.filter(
                Q(user1_id=user_id, user2_id=other_user_id) |
                Q(user1_id=other_user_id, user2_id=user_id)
            ).first()

            if not compatibility:
                return Response({
                    'error': 'No compatibility record found between these users'
                }, status=404)

            # Determine which user is user1/user2 to return the correct direction
            is_user1 = str(compatibility.user1_id) == str(user_id)

            # For completeness ratios (in DB):
            # - user1_required_completeness = mutual / user2_answered = "what % of user2's questions did user1 answer?"
            # - user2_required_completeness = mutual / user1_answered = "what % of user1's questions did user2 answer?"
            #
            # For display:
            # - "My Required" = "what % of MY questions did THEY answer?" (their completeness on my questions)
            # - "Their Required" = "what % of THEIR questions did I answer?" (my completeness on their questions)
            #
            # When current_user is user1: My Required = user2_completeness, Their Required = user1_completeness
            # When current_user is user2: My Required = user1_completeness, Their Required = user2_completeness

            return Response({
                'overall_compatibility': compatibility.overall_compatibility,
                'compatible_with_me': compatibility.compatible_with_me if is_user1 else compatibility.im_compatible_with,
                'im_compatible_with': compatibility.im_compatible_with if is_user1 else compatibility.compatible_with_me,
                'mutual_questions_count': compatibility.mutual_questions_count,
                'required_overall_compatibility': compatibility.required_overall_compatibility,
                'required_compatible_with_me': compatibility.required_compatible_with_me if is_user1 else compatibility.required_im_compatible_with,
                'required_im_compatible_with': compatibility.required_im_compatible_with if is_user1 else compatibility.required_compatible_with_me,
                'their_required_compatibility': compatibility.their_required_compatibility if is_user1 else compatibility.required_compatible_with_me,
                'required_mutual_questions_count': compatibility.required_mutual_questions_count,
                # "My Required" = their completeness on MY questions (how many of my Qs did they answer?)
                # "Their Required" = my completeness on THEIR questions (how many of their Qs did I answer?)
                # user1_required_completeness in DB = "of user2's Qs, what % did user1 answer"
                # user2_required_completeness in DB = "of user1's Qs, what % did user2 answer"
                # So for display: My Required = user2 (their coverage of my Qs), Their Required = user1 (my coverage of their Qs)
                'user1_required_completeness': compatibility.user2_required_completeness if is_user1 else compatibility.user1_required_completeness,
                'user2_required_completeness': compatibility.user1_required_completeness if is_user1 else compatibility.user2_required_completeness,
            })
        except Exception as e:
            logger.error(f"Error getting compatibility: {e}")
            return Response({
                'error': 'Failed to get compatibility data'
            }, status=500)

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
        # Also allow update/partial_update actions to access unapproved questions
        include_unapproved = (
            self.request.query_params.get('include_unapproved', 'false').lower() == 'true' or
            self.action in ['update', 'partial_update', 'destroy']
        )
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
            # question_number is NOT accepted from client - assigned only on approval
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
            # question_number is always None on create - assigned only on approval
            question_data = {
                'text': text,
                'question_name': question_name or text[:50],  # Use text as name if not provided
                'question_number': None,  # Always None on create - assigned only on approval
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
            
            # If question is being created as approved, assign number atomically
            if is_approved:
                from .models import QuestionNumberCounter
                question_data['question_number'] = QuestionNumberCounter.allocate_next_number()
            
            serializer = self.get_serializer(data=question_data)
            serializer.is_valid(raise_exception=True)
            question = serializer.save()
            
            # Invalidate metadata cache if question is approved (so it appears in questions list immediately)
            if question.is_approved:
                from django.core.cache import cache
                cache_key = 'questions_metadata_v2'
                cache_deleted = cache.delete(cache_key)
                logger.info(f"Question created and approved: {question.id}, question_number: {question.question_number}, cache invalidated (deleted: {cache_deleted})")
            
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
            
            # Check if this is a PATCH request with only is_approved field (simple toggle)
            if request.method == 'PATCH' and 'is_approved' in request.data and len(request.data) == 1:
                from django.core.cache import cache
                from .models import QuestionNumberCounter
                old_approved_status = question.is_approved
                new_approved_status = request.data.get('is_approved')
                
                # If transitioning to approved and question_number is NULL, assign it atomically
                if new_approved_status and not old_approved_status and question.question_number is None:
                    question.question_number = QuestionNumberCounter.allocate_next_number()
                elif not new_approved_status and old_approved_status:
                    # If unapproving, set question_number to NULL
                    question.question_number = None
                
                question.is_approved = new_approved_status
                update_fields = ['is_approved']
                if question.question_number is None or (new_approved_status and not old_approved_status):
                    update_fields.append('question_number')
                question.save(update_fields=update_fields)
                
                # Invalidate metadata cache if approval status actually changed
                if old_approved_status != question.is_approved:
                    cache.delete('questions_metadata_v2')
                    logger.info(f"Question approval toggled via PATCH: {question.id}, is_approved={question.is_approved}, question_number={question.question_number}, cache invalidated")
                else:
                    logger.info(f"Question approval unchanged via PATCH: {question.id}, is_approved={question.is_approved}")
                
                serializer = self.get_serializer(question)
                return Response(serializer.data)
            
            # Extract data from request
            text = request.data.get('text', '').strip()
            question_name = request.data.get('question_name', '').strip()
            # question_number is NOT accepted from client - assigned only on approval
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
            
            # Validate required fields (skip for PATCH with only is_approved)
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
            # question_number is NOT updated from client - only assigned on approval transition
            question_data = {
                'text': text,
                'question_name': question_name,
                # question_number is NOT updated from client - preserve existing or assign on approval
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
            
            # Check if approval status is changing
            from django.core.cache import cache
            from .models import QuestionNumberCounter
            old_approved_status = question.is_approved
            
            # If transitioning to approved and question_number is NULL, assign it atomically
            if is_approved and not old_approved_status and question.question_number is None:
                question_data['question_number'] = QuestionNumberCounter.allocate_next_number()
            elif not is_approved and old_approved_status:
                # If unapproving, set question_number to NULL
                question_data['question_number'] = None
            else:
                # Preserve existing question_number
                question_data['question_number'] = question.question_number
            
            serializer = self.get_serializer(question, data=question_data, partial=True)
            serializer.is_valid(raise_exception=True)
            updated_question = serializer.save()
            
            # Invalidate metadata cache if approval status changed
            if old_approved_status != updated_question.is_approved:
                cache.delete('questions_metadata_v2')
                logger.info(f"Question approval changed during update: {updated_question.id}, is_approved={updated_question.is_approved}, cache invalidated")
            
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
        from django.core.cache import cache
        from .models import QuestionNumberCounter
        try:
            question = self.get_object()
            
            # Assign question_number atomically if not already assigned
            if question.question_number is None:
                question.question_number = QuestionNumberCounter.allocate_next_number()
            
            question.is_approved = True
            question.save(update_fields=['is_approved', 'question_number'])

            # Invalidate metadata cache when approval status changes
            cache_key = 'questions_metadata_v2'
            cache_deleted = cache.delete(cache_key)
            logger.info(f"Question approved: {question.id}, question_number: {question.question_number}, cache invalidated (deleted: {cache_deleted})")

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
        from django.core.cache import cache
        try:
            question = self.get_object()
            question.is_approved = False
            # Set question_number to NULL when unapproving
            question.question_number = None
            question.save(update_fields=['is_approved', 'question_number'])

            # Invalidate metadata cache when approval status changes
            cache.delete('questions_metadata_v2')
            logger.info(f"Question rejected: {question.id}, question_number set to NULL, cache invalidated")

            serializer = self.get_serializer(question)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error rejecting question: {e}")
            return Response({
                'error': 'Failed to reject question'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['patch', 'post'])
    def toggle_approval(self, request, pk=None):
        """Toggle question approval status"""
        from django.core.cache import cache
        from .models import QuestionNumberCounter
        try:
            question = self.get_object()
            old_approved = question.is_approved
            new_approved = not old_approved
            
            # If transitioning to approved and question_number is NULL, assign it atomically
            if new_approved and question.question_number is None:
                question.question_number = QuestionNumberCounter.allocate_next_number()
            elif not new_approved:
                # If unapproving, set question_number to NULL
                question.question_number = None
            
            question.is_approved = new_approved
            question.save(update_fields=['is_approved', 'question_number'])

            # Invalidate metadata cache when approval status changes
            cache.delete('questions_metadata_v2')
            logger.info(f"Question approval toggled: {question.id}, is_approved={question.is_approved}, question_number={question.question_number}, cache invalidated")

            serializer = self.get_serializer(question)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error toggling approval: {e}", exc_info=True)
            return Response({
                'error': f'Failed to toggle approval: {str(e)}'
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

        # Check if client wants to bypass cache (for immediate refresh after approval)
        bypass_cache = request.query_params.get('bypass_cache', 'false').lower() == 'true'
        
        # Try to get from cache first (5 minute TTL) - unless bypass is requested
        cache_key = 'questions_metadata_v2'  # Changed version to force cache refresh
        cached_data = None if bypass_cache else cache.get(cache_key)

        if cached_data:
            logger.info(f"Returning cached question metadata (bypass_cache={bypass_cache})")
            # Log what question numbers are in cache for debugging
            cached_question_numbers = cached_data.get('distinct_question_numbers', [])
            logger.info(f"Cached metadata contains {len(cached_question_numbers)} question numbers")
            logger.info(f"Has question 18 in cache? {18 in cached_question_numbers}")
            return Response(cached_data)
        
        if bypass_cache:
            logger.info("Bypassing cache for metadata request (fresh data requested)")

        # Get distinct question numbers using database aggregation (fast with index)
        # Only include approved questions
        distinct_numbers = Question.objects.filter(is_approved=True).values('question_number').distinct().order_by('question_number')
        question_numbers = [item['question_number'] for item in distinct_numbers]
        
        # Debug logging
        logger.info(f"Fresh metadata query: Found {len(question_numbers)} distinct approved question numbers")
        logger.info(f"Question numbers: {question_numbers}")
        logger.info(f"Has question 18? {18 in question_numbers}")
        # Check if question 18 exists and is approved
        q18_exists = Question.objects.filter(question_number=18).exists()
        q18_approved = Question.objects.filter(question_number=18, is_approved=True).exists()
        logger.info(f"Question 18 exists: {q18_exists}, is_approved: {q18_approved}")

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

        # Cache for 1 minute (60 seconds) - faster updates while still maintaining performance
        cache.set(cache_key, metadata, 60)

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
            is_required_for_me = request.data.get('is_required_for_me', False)

            # Sync UserRequiredQuestion (required for me is stored there; user can require without answering)
            if is_required_for_me:
                UserRequiredQuestion.objects.get_or_create(user=user, question=question)
            else:
                UserRequiredQuestion.objects.filter(user=user, question=question).delete()

            # Create or update UserAnswer (no longer store is_required_for_me on UserAnswer)
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


class UserRequiredQuestionViewSet(viewsets.ModelViewSet):
    """List/add/remove questions a user marks as required for matching (independent of having answered)."""
    serializer_class = UserRequiredQuestionSerializer
    permission_classes = [permissions.AllowAny]
    http_method_names = ['get', 'post', 'delete', 'head', 'options']

    def get_queryset(self):
        user_id = self.request.query_params.get('user')
        if user_id:
            return UserRequiredQuestion.objects.filter(user_id=user_id).select_related('question', 'user')
        if self.request.user.is_authenticated:
            return UserRequiredQuestion.objects.filter(user=self.request.user).select_related('question', 'user')
        return UserRequiredQuestion.objects.none()

    def create(self, request, *args, **kwargs):
        question_id = request.data.get('question_id')
        if not question_id:
            return Response({'error': 'question_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        user = request.user if request.user.is_authenticated else None
        if not user:
            user_id = request.data.get('user_id')
            if not user_id:
                return Response({'error': 'user_id or authentication required'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        try:
            question = Question.objects.get(id=question_id)
        except Question.DoesNotExist:
            return Response({'error': 'Question not found'}, status=status.HTTP_404_NOT_FOUND)
        obj, created = UserRequiredQuestion.objects.get_or_create(user=user, question=question)
        serializer = self.get_serializer(obj)
        return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    def perform_destroy(self, instance):
        instance.delete()


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

            # Create notification for approve, like, or match
            notification_type = None
            if tag == 'approve':
                notification_type = 'approve'
            elif tag == 'like':
                notification_type = 'like'
                # Check if this creates a match (mutual like)
                mutual_like = UserResult.objects.filter(
                    user=result_user,
                    result_user=user,
                    tag='like'
                ).exists()

                if mutual_like:
                    # Create match notification for both users
                    Notification.objects.create(
                        recipient=user,
                        sender=result_user,
                        notification_type='match',
                        related_user_result=user_result
                    )
                    Notification.objects.create(
                        recipient=result_user,
                        sender=user,
                        notification_type='match',
                        related_user_result=user_result
                    )
                    logger.info(f"Created match notifications between {user.username} and {result_user.username}")

            # Create notification for approve or like
            if notification_type:
                Notification.objects.create(
                    recipient=result_user,
                    sender=user,
                    notification_type=notification_type,
                    related_user_result=user_result
                )
                logger.info(f"Created {notification_type} notification from {user.username} to {result_user.username}")

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

    @action(detail=False, methods=['post'])
    def send_note(self, request):
        """Send a note to another user (appears in notifications and as first message in chat)"""
        sender_id = request.data.get('sender_id')
        recipient_id = request.data.get('recipient_id')
        note = request.data.get('note')

        if not all([sender_id, recipient_id, note]):
            return Response(
                {'error': 'sender_id, recipient_id, and note are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            sender = User.objects.get(id=sender_id)
            recipient = User.objects.get(id=recipient_id)
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Create notification with note
        notification = Notification.objects.create(
            recipient=recipient,
            sender=sender,
            notification_type='note',
            note=note
        )
        logger.info(f"Created note notification from {sender.username} to {recipient.username}")

        # Get or create conversation with consistent ordering (smaller ID first)
        if str(sender.id) < str(recipient.id):
            p1_id, p2_id = sender.id, recipient.id
        else:
            p1_id, p2_id = recipient.id, sender.id

        conversation = Conversation.objects.filter(
            participant1_id=p1_id,
            participant2_id=p2_id
        ).first()

        if not conversation:
            conversation = Conversation.objects.create(
                participant1_id=p1_id,
                participant2_id=p2_id
            )

        # Create message in conversation
        message = Message.objects.create(
            conversation=conversation,
            sender=sender,
            receiver=recipient,
            content=note
        )
        logger.info(f"Created note message from {sender.username} to {recipient.username} in conversation {conversation.id}")

        return Response({
            'success': True,
            'notification_id': str(notification.id),
            'message_id': str(message.id),
            'conversation_id': str(conversation.id)
        }, status=status.HTTP_201_CREATED)


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
        # Get reporter and reported_user IDs from request data
        reporter_id = self.request.data.get('reporter')
        reported_user_id = self.request.data.get('reported_user')

        # Get the User objects
        reporter = User.objects.get(id=reporter_id)
        reported_user = User.objects.get(id=reported_user_id)

        serializer.save(reporter=reporter, reported_user=reported_user)

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
        from datetime import timedelta, datetime
        from api.models import DailyMetric

        # Check if start_date and end_date are provided
        start_date_param = request.query_params.get('start_date')
        end_date_param = request.query_params.get('end_date')

        if start_date_param and end_date_param:
            # Use specific date range
            try:
                start_date = datetime.fromisoformat(start_date_param).date()
                end_date = datetime.fromisoformat(end_date_param).date()
                days = (end_date - start_date).days + 1
            except ValueError:
                return Response({'error': 'Invalid date format'}, status=400)
        else:
            # Use period parameter (default: 30 days from today)
            period = request.query_params.get('period', '30')
            try:
                days = int(period)
            except ValueError:
                days = 30

            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=days - 1)

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


class NotificationViewSet(viewsets.ModelViewSet):
    """ViewSet for managing user notifications"""
    serializer_class = NotificationSerializer
    permission_classes = [permissions.AllowAny]  # Changed for testing
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        """Only return notifications for the current user"""
        # For detail views (retrieve, update, destroy, mark_read), return all notifications
        # so we can look up by ID
        if self.action in ['retrieve', 'update', 'partial_update', 'destroy', 'mark_read']:
            return Notification.objects.all()

        # For testing, allow user_id parameter
        user_id = self.request.query_params.get('user_id')
        if user_id:
            return Notification.objects.filter(recipient_id=user_id)

        if self.request.user.is_authenticated:
            return Notification.objects.filter(recipient=self.request.user)
        return Notification.objects.none()

    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """Get count of unread notifications"""
        user_id = request.query_params.get('user_id')
        if user_id:
            count = Notification.objects.filter(recipient_id=user_id, is_read=False).count()
        elif request.user.is_authenticated:
            count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        else:
            count = 0

        return Response({'count': count})

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Mark a notification as read"""
        notification = self.get_object()
        notification.is_read = True
        notification.save()

        serializer = self.get_serializer(notification)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        """Mark all notifications as read for the current user"""
        user_id = request.query_params.get('user_id')
        if user_id:
            Notification.objects.filter(recipient_id=user_id, is_read=False).update(is_read=True)
        elif request.user.is_authenticated:
            Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)

        return Response({'status': 'all notifications marked as read'})


class ConversationViewSet(viewsets.ModelViewSet):
    """ViewSet for managing conversations between users"""
    serializer_class = ConversationSerializer
    permission_classes = [permissions.AllowAny]  # Changed for testing
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['updated_at', 'created_at']
    ordering = ['-updated_at']

    def get_queryset(self):
        """Return conversations for the current user, only showing those with mutual likes (matches)"""
        # For detail views, return all conversations so we can look up by ID
        if self.action in ['retrieve', 'update', 'partial_update', 'destroy', 'messages', 'send_message', 'mark_messages_read']:
            return Conversation.objects.all()

        # For testing, allow user_id parameter
        user_id = self.request.query_params.get('user_id')
        current_user_id = user_id
        
        if not current_user_id and self.request.user.is_authenticated:
            current_user_id = str(self.request.user.id)
        
        if not current_user_id:
            return Conversation.objects.none()
        
        # Get conversations where the user is a participant
        conversations = Conversation.objects.filter(
            Q(participant1_id=current_user_id) | Q(participant2_id=current_user_id)
            )

        # Filter to only show conversations where there's a mutual like (match)
        # A match exists when:
        # - participant1 has liked participant2 (UserResult with user=participant1, result_user=participant2, tag='like')
        # - participant2 has liked participant1 (UserResult with user=participant2, result_user=participant1, tag='like')
        
        matched_conversations = conversations.filter(
            # Check if participant1 has liked participant2
            Exists(
                UserResult.objects.filter(
                    user_id=OuterRef('participant1_id'),
                    result_user_id=OuterRef('participant2_id'),
                    tag='like'
                )
            ),
            # Check if participant2 has liked participant1
            Exists(
                UserResult.objects.filter(
                    user_id=OuterRef('participant2_id'),
                    result_user_id=OuterRef('participant1_id'),
                    tag='like'
                )
            )
        )
        
        return matched_conversations

    def get_serializer_context(self):
        """Add user_id to serializer context"""
        context = super().get_serializer_context()
        user_id = self.request.query_params.get('user_id')
        logger.info(f"ConversationViewSet.get_serializer_context: user_id={user_id}")
        if user_id:
            context['user_id'] = user_id
        logger.info(f"ConversationViewSet.get_serializer_context: context keys={context.keys()}")
        return context

    def list(self, request, *args, **kwargs):
        """List conversations with deduplication for same user pairs"""
        queryset = self.filter_queryset(self.get_queryset())
        
        # Deduplicate conversations that represent the same pair of users
        # Group by normalized participant pair (smaller ID first)
        conversation_map = {}
        
        for conv in queryset:
            # Normalize participant order (smaller ID first)
            p1_id = str(conv.participant1.id)
            p2_id = str(conv.participant2.id)
            if p1_id > p2_id:
                p1_id, p2_id = p2_id, p1_id
            
            pair_key = f"{p1_id}_{p2_id}"
            
            # Keep the conversation with the most recent update, or if equal, the one with messages
            if pair_key not in conversation_map:
                conversation_map[pair_key] = conv
            else:
                existing = conversation_map[pair_key]
                # Prefer conversation with messages, then most recent update
                existing_has_messages = existing.messages.exists()
                conv_has_messages = conv.messages.exists()
                
                if conv_has_messages and not existing_has_messages:
                    conversation_map[pair_key] = conv
                elif existing_has_messages and not conv_has_messages:
                    pass  # Keep existing
                elif conv.updated_at > existing.updated_at:
                    conversation_map[pair_key] = conv
        
        # Convert back to queryset-like list
        deduplicated_conversations = list(conversation_map.values())
        
        # Sort by updated_at descending
        deduplicated_conversations.sort(key=lambda x: x.updated_at, reverse=True)
        
        page = self.paginate_queryset(deduplicated_conversations)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(deduplicated_conversations, many=True)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        """Create a new conversation or return existing one"""
        user_id = request.data.get('user_id') or request.query_params.get('user_id')
        other_user_id = request.data.get('other_user_id')

        if not user_id or not other_user_id:
            return Response(
                {'error': 'Both user_id and other_user_id are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Ensure consistent ordering (smaller ID first)
        if str(user_id) < str(other_user_id):
            p1_id, p2_id = user_id, other_user_id
        else:
            p1_id, p2_id = other_user_id, user_id

        # Check if conversation already exists
        conversation = Conversation.objects.filter(
            participant1_id=p1_id,
            participant2_id=p2_id
        ).first()

        if not conversation:
            # Create new conversation
            conversation = Conversation.objects.create(
                participant1_id=p1_id,
                participant2_id=p2_id
            )

        serializer = self.get_serializer(conversation, context={'user_id': user_id})
        return Response(serializer.data, status=status.HTTP_201_CREATED if not conversation else status.HTTP_200_OK)

    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        """Get messages for a conversation"""
        conversation = self.get_object()
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 50))

        messages = conversation.messages.order_by('-created_at')
        total = messages.count()

        # Paginate
        start = (page - 1) * page_size
        end = start + page_size
        messages_page = messages[start:end]

        # Reverse to get oldest first for display
        messages_page = list(reversed(messages_page))

        serializer = MessageSerializer(messages_page, many=True)

        return Response({
            'results': serializer.data,
            'count': total,
            'page': page,
            'page_size': page_size,
            'has_more': end < total
        })

    @action(detail=True, methods=['post'])
    def send_message(self, request, pk=None):
        """Send a message in this conversation"""
        conversation = self.get_object()
        sender_id = request.data.get('sender_id')
        content = request.data.get('content')

        if not sender_id or not content:
            return Response(
                {'error': 'sender_id and content are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Determine receiver
        if str(conversation.participant1_id) == str(sender_id):
            receiver = conversation.participant2
        else:
            receiver = conversation.participant1

        # Create message
        message = Message.objects.create(
            conversation=conversation,
            sender_id=sender_id,
            receiver=receiver,
            content=content
        )

        # Update conversation's updated_at
        conversation.save()  # This will update the auto_now field

        serializer = MessageSerializer(message)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def mark_messages_read(self, request, pk=None):
        """Mark all messages in conversation as read for the current user"""
        conversation = self.get_object()
        user_id = request.data.get('user_id')

        if not user_id:
            return Response(
                {'error': 'user_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Mark all unread messages where this user is the receiver as read
        updated = conversation.messages.filter(
            receiver_id=user_id,
            is_read=False
        ).update(is_read=True)

        return Response({'marked_read': updated})

    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """Get total unread message count across all conversations"""
        user_id = request.query_params.get('user_id')

        if user_id:
            count = Message.objects.filter(
                receiver_id=user_id,
                is_read=False
            ).count()
        elif request.user.is_authenticated:
            count = Message.objects.filter(
                receiver=request.user,
                is_read=False
            ).count()
        else:
            count = 0

        return Response({'count': count})
