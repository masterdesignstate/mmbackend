from rest_framework import serializers
from .models import (
    User, Tag, Question, UserAnswer, Compatibility,
    UserResult, Message, PictureModeration, UserReport, UserOnlineStatus, UserTag, QuestionAnswer, Controls
)


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['id', 'name']


class UserSerializer(serializers.ModelSerializer):
    online_status = serializers.SerializerMethodField()
    question_answers = serializers.SerializerMethodField()
    date_joined = serializers.DateTimeField(read_only=True)
    is_banned = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'profile_photo', 'age', 'date_of_birth', 'height', 'from_location', 'live', 'tagline', 'bio',
            'is_online', 'last_seen', 'questions_answered_count', 'online_status', 'question_answers',
            'date_joined', 'is_banned', 'is_admin'
        ]
        read_only_fields = [
            'id', 'is_online', 'last_seen', 'questions_answered_count',
            'date_joined', 'is_banned', 'is_admin'
        ]

    def get_online_status(self, obj):
        # Check if user is authenticated and not AnonymousUser
        if not hasattr(obj, 'online_status') or obj.is_anonymous:
            return None

        try:
            return {
                'is_online': obj.online_status.is_online,
                'last_seen': obj.online_status.last_seen,
                'last_activity': obj.online_status.last_activity
            }
        except UserOnlineStatus.DoesNotExist:
            return None

    def get_question_answers(self, obj):
        """Get answers for specific questions by question number"""
        # Get answers for questions 1-6 (Male, Female, Friend, Hookup, Date, Partner)
        answers = UserAnswer.objects.filter(
            user=obj,
            question__question_number__in=[1, 2, 3, 4, 5, 6]
        ).select_related('question').values(
            'question__question_number',
            'me_answer'
        )

        # Map to question names
        answer_map = {}
        for answer in answers:
            qnum = answer['question__question_number']
            # Map question numbers to their names
            question_names = {
                1: 'male',
                2: 'female',
                3: 'friend',
                4: 'hookup',
                5: 'date',
                6: 'partner'
            }
            if qnum in question_names:
                answer_map[question_names[qnum]] = answer['me_answer']

        return answer_map


class QuestionAnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionAnswer
        fields = ['id', 'value', 'answer_text', 'order', 'created_at', 'updated_at']


class QuestionSerializer(serializers.ModelSerializer):
    tags = TagSerializer(many=True, read_only=True)
    answers = QuestionAnswerSerializer(many=True, read_only=True)
    submitted_by = UserSerializer(read_only=True)
    is_answered = serializers.SerializerMethodField()
    is_submitted_by_me = serializers.SerializerMethodField()
    
    class Meta:
        model = Question
        fields = [
            'id', 'question_name', 'question_number', 'group_number', 'group_name', 'group_name_text', 'question_type',
            'text', 'tags', 'answers', 'is_required_for_match', 'is_mandatory', 'submitted_by', 'is_approved',
            'skip_me', 'skip_looking_for', 'open_to_all_me', 'open_to_all_looking_for', 'is_group',
            'created_at', 'updated_at', 'is_answered', 'is_submitted_by_me'
        ]
    
    def get_is_answered(self, obj):
        """Check if the current user has answered this question"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.user_answers.filter(user=request.user).exists()
        return False
    
    def get_is_submitted_by_me(self, obj):
        """Check if this question was submitted by the current user"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.submitted_by == request.user
        return False


class UserAnswerSerializer(serializers.ModelSerializer):
    question = QuestionSerializer(read_only=True)
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = UserAnswer
        fields = [
            'id', 'user', 'question', 'me_answer', 'me_open_to_all', 
            'me_importance', 'me_share', 'looking_for_answer', 
            'looking_for_open_to_all', 'looking_for_importance', 
            'looking_for_share', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']


class CompatibilitySerializer(serializers.ModelSerializer):
    user1 = UserSerializer(read_only=True)
    user2 = UserSerializer(read_only=True)
    
    class Meta:
        model = Compatibility
        fields = [
            'id', 'user1', 'user2', 'overall_compatibility', 
            'compatible_with_me', 'im_compatible_with', 
            'mutual_questions_count', 'last_calculated'
        ]
        read_only_fields = ['id', 'overall_compatibility', 'compatible_with_me', 
                           'im_compatible_with', 'mutual_questions_count', 'last_calculated']


class UserResultSerializer(serializers.ModelSerializer):
    result_user = UserSerializer(read_only=True)
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = UserResult
        fields = ['id', 'user', 'result_user', 'tag', 'created_at', 'updated_at']
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']


class MessageSerializer(serializers.ModelSerializer):
    sender = UserSerializer(read_only=True)
    receiver = UserSerializer(read_only=True)
    
    class Meta:
        model = Message
        fields = ['id', 'sender', 'receiver', 'content', 'is_read', 'created_at']
        read_only_fields = ['id', 'sender', 'is_read', 'created_at']


class PictureModerationSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    moderated_by = UserSerializer(read_only=True)
    
    class Meta:
        model = PictureModeration
        fields = [
            'id', 'user', 'picture', 'status', 'moderator_notes',
            'submitted_at', 'moderated_at', 'moderated_by'
        ]
        read_only_fields = ['id', 'user', 'status', 'moderator_notes', 
                           'submitted_at', 'moderated_at', 'moderated_by']


class UserReportSerializer(serializers.ModelSerializer):
    reporter = UserSerializer(read_only=True)
    reported_user = UserSerializer(read_only=True)
    resolved_by = UserSerializer(read_only=True)
    
    class Meta:
        model = UserReport
        fields = [
            'id', 'reporter', 'reported_user', 'reason', 'evidence',
            'status', 'moderator_notes', 'created_at', 'resolved_at', 'resolved_by'
        ]
        read_only_fields = ['id', 'reporter', 'status', 'moderator_notes', 
                           'created_at', 'resolved_at', 'resolved_by']


class UserOnlineStatusSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = UserOnlineStatus
        fields = ['id', 'user', 'is_online', 'last_seen', 'last_activity']
        read_only_fields = ['id', 'user', 'last_seen', 'last_activity']


class UserTagSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    tagged_user = UserSerializer(read_only=True)
    
    class Meta:
        model = UserTag
        fields = ['id', 'user', 'tagged_user', 'tag', 'created_at', 'updated_at']
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']


# Nested serializers for detailed views
class DetailedUserSerializer(UserSerializer):
    answers = UserAnswerSerializer(many=True, read_only=True)
    
    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ['answers']


class DetailedQuestionSerializer(QuestionSerializer):
    user_answers = UserAnswerSerializer(many=True, read_only=True)

    class Meta(QuestionSerializer.Meta):
        fields = QuestionSerializer.Meta.fields + ['user_answers']


# Lightweight serializers for compatibility endpoint (no circular references)
class SimpleUserSerializer(serializers.ModelSerializer):
    """Lightweight user serializer for compatibility lists - no nested data"""
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'profile_photo', 'age', 'date_of_birth', 'height',
            'from_location', 'live', 'tagline', 'bio', 'is_online', 'last_seen'
        ]

class CompactCompatibilityResultSerializer(serializers.Serializer):
    """Lightweight compatibility data serializer"""
    overall_compatibility = serializers.FloatField()
    compatible_with_me = serializers.FloatField()
    im_compatible_with = serializers.FloatField()
    mutual_questions_count = serializers.IntegerField()


class ControlsSerializer(serializers.ModelSerializer):
    """Serializer for Controls model"""
    class Meta:
        model = Controls
        fields = ['id', 'adjust', 'exponent', 'ota', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at'] 
