from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q, Count
from django.utils import timezone
from datetime import timedelta
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
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['username', 'first_name', 'last_name', 'city', 'bio']
    ordering_fields = ['age', 'height', 'questions_answered_count', 'last_seen']
    ordering = ['-last_seen']

    def get_queryset(self):
        # Exclude banned users and current user
        return User.objects.filter(
            is_banned=False
        ).exclude(id=self.request.user.id)

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


class TagViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TagSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Tag.objects.all()


class QuestionViewSet(viewsets.ModelViewSet):
    serializer_class = QuestionSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['text']
    ordering_fields = ['created_at', 'question_type']
    ordering = ['-created_at']

    def get_queryset(self):
        queryset = Question.objects.all()
        
        # Filter by question type
        question_type = self.request.query_params.get('type', None)
        if question_type:
            queryset = queryset.filter(question_type=question_type)
        
        # Filter by tags
        tags = self.request.query_params.getlist('tags', [])
        if tags:
            queryset = queryset.filter(tags__name__in=tags).distinct()
        
        return queryset

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return DetailedQuestionSerializer
        return QuestionSerializer

    @action(detail=False, methods=['get'])
    def mandatory(self, request):
        """Get mandatory questions"""
        questions = self.get_queryset().filter(question_type='mandatory')
        serializer = self.get_serializer(questions, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def unanswered(self, request):
        """Get questions user hasn't answered"""
        answered_question_ids = request.user.answers.values_list('question_id', flat=True)
        questions = self.get_queryset().exclude(id__in=answered_question_ids)
        serializer = self.get_serializer(questions, many=True)
        return Response(serializer.data)


class UserAnswerViewSet(viewsets.ModelViewSet):
    serializer_class = UserAnswerSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']

    def get_queryset(self):
        return UserAnswer.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
        # Update user's questions answered count
        user = self.request.user
        user.questions_answered_count = user.answers.count()
        user.save()

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
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['overall_compatibility', 'compatible_with_me', 'im_compatible_with']
    ordering = ['-overall_compatibility']

    def get_queryset(self):
        return Compatibility.objects.filter(
            Q(user1=self.request.user) | Q(user2=self.request.user)
        )

    @action(detail=False, methods=['get'])
    def top_matches(self, request):
        """Get top compatibility matches"""
        limit = int(request.query_params.get('limit', 10))
        compatibilities = self.get_queryset().order_by('-overall_compatibility')[:limit]
        serializer = self.get_serializer(compatibilities, many=True)
        return Response(serializer.data)


class UserResultViewSet(viewsets.ModelViewSet):
    serializer_class = UserResultSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']

    def get_queryset(self):
        return UserResult.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

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
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']

    def get_queryset(self):
        return UserTag.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['get'])
    def by_tag(self, request):
        """Get user tags by specific tag"""
        tag = request.query_params.get('tag')
        if tag:
            user_tags = self.get_queryset().filter(tag=tag)
            serializer = self.get_serializer(user_tags, many=True)
            return Response(serializer.data)
        return Response({'error': 'tag parameter required'}, status=400)

    @action(detail=False, methods=['get'])
    def liked(self, request):
        """Get users tagged as liked/hot/approve"""
        user_tags = self.get_queryset().filter(tag__in=['liked', 'hot', 'approve'])
        serializer = self.get_serializer(user_tags, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def matches(self, request):
        """Get users tagged as matched"""
        user_tags = self.get_queryset().filter(tag='matched')
        serializer = self.get_serializer(user_tags, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def received(self, request):
        """Get tags received from other users"""
        received_tags = UserTag.objects.filter(tagged_user=self.request.user)
        serializer = self.get_serializer(received_tags, many=True)
        return Response(serializer.data)


class MessageViewSet(viewsets.ModelViewSet):
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['created_at']
    ordering = ['created_at']

    def get_queryset(self):
        return Message.objects.filter(
            Q(sender=self.request.user) | Q(receiver=self.request.user)
        )

    def perform_create(self, serializer):
        serializer.save(sender=self.request.user)

    @action(detail=False, methods=['get'])
    def conversations(self, request):
        """Get unique conversations"""
        # Get unique users the current user has messaged with
        sent_to = Message.objects.filter(sender=request.user).values_list('receiver_id', flat=True)
        received_from = Message.objects.filter(receiver=request.user).values_list('sender_id', flat=True)
        all_users = set(list(sent_to) + list(received_from))
        
        conversations = []
        for user_id in all_users:
            user = User.objects.get(id=user_id)
            last_message = Message.objects.filter(
                Q(sender=request.user, receiver=user) | 
                Q(sender=user, receiver=request.user)
            ).order_by('-created_at').first()
            
            conversations.append({
                'user': UserSerializer(user).data,
                'last_message': MessageSerializer(last_message).data if last_message else None
            })
        
        return Response(conversations)

    @action(detail=False, methods=['get'])
    def with_user(self, request):
        """Get messages with a specific user"""
        user_id = request.query_params.get('user_id')
        if user_id:
            messages = self.get_queryset().filter(
                Q(sender_id=user_id, receiver=request.user) |
                Q(sender=request.user, receiver_id=user_id)
            )
            serializer = self.get_serializer(messages, many=True)
            return Response(serializer.data)
        return Response({'error': 'user_id parameter required'}, status=400)

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Mark message as read"""
        message = self.get_object()
        if message.receiver == request.user:
            message.is_read = True
            message.save()
        return Response({'status': 'marked as read'})


class PictureModerationViewSet(viewsets.ModelViewSet):
    serializer_class = PictureModerationSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['submitted_at', 'moderated_at', 'status']
    ordering = ['-submitted_at']

    def get_queryset(self):
        if self.request.user.is_staff:
            return PictureModeration.objects.all()
        return PictureModeration.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['get'])
    def pending(self, request):
        """Get pending moderations (staff only)"""
        if not request.user.is_staff:
            return Response({'error': 'Staff only'}, status=403)
        moderations = self.get_queryset().filter(status='pending')
        serializer = self.get_serializer(moderations, many=True)
        return Response(serializer.data)


class UserReportViewSet(viewsets.ModelViewSet):
    serializer_class = UserReportSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['created_at', 'resolved_at', 'status']
    ordering = ['-created_at']

    def get_queryset(self):
        if self.request.user.is_staff:
            return UserReport.objects.all()
        return UserReport.objects.filter(reporter=self.request.user)

    def perform_create(self, serializer):
        serializer.save(reporter=self.request.user)

    @action(detail=False, methods=['get'])
    def pending(self, request):
        """Get pending reports (staff only)"""
        if not request.user.is_staff:
            return Response({'error': 'Staff only'}, status=403)
        reports = self.get_queryset().filter(status='pending')
        serializer = self.get_serializer(reports, many=True)
        return Response(serializer.data)
