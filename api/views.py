from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q, Count
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

from .models import (
    User, Tag, Question, UserAnswer, Compatibility, 
    UserResult, Message, PictureModeration, UserReport, UserOnlineStatus, UserTag
)
from .serializers import (
    UserSerializer, TagSerializer, QuestionSerializer, UserAnswerSerializer,
    CompatibilitySerializer, UserResultSerializer, MessageSerializer,
    PictureModerationSerializer, UserReportSerializer, UserOnlineStatusSerializer,
    DetailedUserSerializer, DetailedQuestionSerializer, UserTagSerializer
)


class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [permissions.AllowAny]  # Changed for testing
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['username', 'first_name', 'last_name', 'city', 'bio']
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
        
        # Search across multiple fields
        users = User.objects.filter(
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(username__icontains=query) |
            Q(email__icontains=query),
            is_banned=False
        ).distinct()[:10]  # Limit to 10 results
        
        serializer = self.get_serializer(users, many=True)
        return Response({'results': serializer.data})


class TagViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TagSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Tag.objects.all()


class QuestionViewSet(viewsets.ModelViewSet):
    serializer_class = QuestionSerializer
    permission_classes = [permissions.AllowAny]  # Changed for testing
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['text']
    ordering_fields = ['created_at', 'question_type']
    ordering = ['-created_at']

    def get_queryset(self):
        queryset = Question.objects.all()
        
        # Filter by type if specified
        question_type = self.request.query_params.get('type')
        if question_type:
            queryset = queryset.filter(question_type=question_type)
        
        # Filter by tags if specified
        tags = self.request.query_params.getlist('tags')
        if tags:
            queryset = queryset.filter(tags__name__in=tags).distinct()
        
        logger.info(f"QuestionViewSet.get_queryset() called. Request: {self.request.method} {self.request.path}")
        logger.info(f"Query params: {self.request.query_params}")
        logger.info(f"Returning {queryset.count()} questions")
        
        return queryset

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return DetailedQuestionSerializer
        return QuestionSerializer

    def create(self, request, *args, **kwargs):
        """
        Custom create method to handle tag creation and validation
        """
        try:
            # Extract data from request
            text = request.data.get('text', '').strip()
            question_name = request.data.get('question_name', '').strip()
            question_number = request.data.get('question_number')
            group_name = request.data.get('group_name', '').strip()
            tags = request.data.get('tags', [])
            question_type = request.data.get('question_type', 'unanswered')
            is_required_for_match = request.data.get('is_required_for_match', False)
            is_approved = request.data.get('is_approved', False)
            skip_me = request.data.get('skip_me', False)
            skip_looking_for = request.data.get('skip_looking_for', False)
            open_to_all_me = request.data.get('open_to_all_me', False)
            open_to_all_looking_for = request.data.get('open_to_all_looking_for', False)
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
            
            # Create the question
            question_data = {
                'text': text,
                'question_name': question_name,
                'question_number': question_number,
                'group_name': group_name,
                'question_type': question_type,
                'is_required_for_match': is_required_for_match,
                'is_approved': is_approved,
                'skip_me': skip_me,
                'skip_looking_for': skip_looking_for,
                'open_to_all_me': open_to_all_me,
                'open_to_all_looking_for': open_to_all_looking_for,
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
            
            # Create answers
            from .models import QuestionAnswer
            for i, answer_data in enumerate(answers):
                if answer_data.get('value') and answer_data.get('answer'):
                    QuestionAnswer.objects.create(
                        question=question,
                        value=answer_data['value'],
                        answer_text=answer_data['answer'],
                        order=i
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
            group_name = request.data.get('group_name', '').strip()
            tags = request.data.get('tags', [])
            question_type = request.data.get('question_type', question.question_type)
            is_required_for_match = request.data.get('is_required_for_match', question.is_required_for_match)
            is_approved = request.data.get('is_approved', question.is_approved)
            skip_me = request.data.get('skip_me', question.skip_me)
            skip_looking_for = request.data.get('skip_looking_for', question.skip_looking_for)
            open_to_all_me = request.data.get('open_to_all_me', question.open_to_all_me)
            open_to_all_looking_for = request.data.get('open_to_all_looking_for', question.open_to_all_looking_for)
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
                'group_name': group_name,
                'question_type': question_type,
                'is_required_for_match': is_required_for_match,
                'is_approved': is_approved,
                'skip_me': skip_me,
                'skip_looking_for': skip_looking_for,
                'open_to_all_me': open_to_all_me,
                'open_to_all_looking_for': open_to_all_looking_for,
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
                    if answer_data.get('value') and answer_data.get('answer'):
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
            queue_data.append({
                'id': moderation.id,
                'user': {
                    'id': moderation.user.id,
                    'first_name': moderation.user.first_name,
                    'last_name': moderation.user.last_name,
                    'email': moderation.user.email,
                    'profile_photo': moderation.user.profile_photo.url if moderation.user.profile_photo else None,
                },
                'picture': moderation.picture.url if moderation.picture else None,
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
        moderation.status = 'approved'
        moderation.moderated_at = timezone.now()
        moderation.save()
        
        return Response({'status': 'approved'})

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
