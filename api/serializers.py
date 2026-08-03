from rest_framework import serializers
from .models import (
    User, UserRestrictionHistory, Tag, Question, UserAnswer, UserRequiredQuestion, Compatibility,
    UserResult, Message, PictureModeration, UserReport, UserOnlineStatus, UserTag, QuestionAnswer, Controls, Notification, Conversation,
    Post, PostImage, PostHashtag, PostRevision, PostReaction, PostComment, FeedActivity,
    PromptTemplate, UserProfilePrompt, PromptPollVote, RestrictedWord,
)
from .utils.admin_utils import profile_answer_key


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['id', 'name']


class RestrictedWordSerializer(serializers.ModelSerializer):
    class Meta:
        model = RestrictedWord
        fields = ['id', 'word', 'severity', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_word(self, value):
        word = value.strip().lower()
        if not word:
            raise serializers.ValidationError('Word cannot be blank.')

        matches = RestrictedWord.objects.filter(word__iexact=word)
        if self.instance:
            matches = matches.exclude(pk=self.instance.pk)
        if matches.exists():
            raise serializers.ValidationError('This restricted word already exists.')
        return word


class UserPictureSerializer(serializers.ModelSerializer):
    class Meta:
        from .models import UserPicture
        model = UserPicture
        fields = ['id', 'image_url', 'order', 'created_at']
        read_only_fields = ['id', 'created_at']


class UserRestrictionHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = UserRestrictionHistory
        fields = [
            'id', 'restriction_type', 'duration_days', 'reason', 'reason_detail',
            'restricted_at', 'expires_at', 'ended_at', 'end_reason', 'moderator_notes',
        ]
        read_only_fields = fields


class PromptTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PromptTemplate
        fields = ['id', 'text', 'category', 'is_active', 'order', 'created_at']
        read_only_fields = ['id', 'created_at']


class PromptPollVoteSerializer(serializers.ModelSerializer):
    voter = serializers.SerializerMethodField()
    selected_option_text = serializers.SerializerMethodField()

    class Meta:
        model = PromptPollVote
        fields = [
            'id', 'prompt', 'voter', 'selected_option_index',
            'selected_option_text', 'comment', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'prompt', 'voter', 'created_at', 'updated_at']

    def get_voter(self, obj):
        return {
            'id': str(obj.voter.id),
            'username': obj.voter.username,
            'first_name': obj.voter.first_name,
            'last_name': obj.voter.last_name,
            'profile_photo': obj.voter.profile_photo,
        }

    def get_selected_option_text(self, obj):
        options = obj.prompt.poll_options or []
        if 0 <= obj.selected_option_index < len(options):
            return options[obj.selected_option_index]
        return ''


class UserProfilePromptSerializer(serializers.ModelSerializer):
    template = PromptTemplateSerializer(read_only=True)
    template_id = serializers.UUIDField(write_only=True, required=False)
    viewer_vote = serializers.SerializerMethodField()
    poll_votes = serializers.SerializerMethodField()

    class Meta:
        model = UserProfilePrompt
        fields = [
            'id', 'user', 'template', 'template_id', 'prompt_type', 'order',
            'written_answer', 'media_url', 'media_duration_seconds',
            'poll_options', 'is_active', 'viewer_vote', 'poll_votes',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']

    def get_viewer_vote(self, obj):
        viewer_id = self.context.get('viewer_id')
        if not viewer_id or obj.prompt_type != 'poll':
            return None
        vote = obj.poll_votes.filter(voter_id=viewer_id).select_related('voter', 'prompt').first()
        if not vote:
            return None
        return PromptPollVoteSerializer(vote).data

    def get_poll_votes(self, obj):
        owner_id = self.context.get('owner_id')
        viewer_id = self.context.get('viewer_id')
        include_votes = self.context.get('include_poll_votes', False)
        if (
            not include_votes
            or obj.prompt_type != 'poll'
            or str(obj.user_id) != str(owner_id)
            or str(obj.user_id) != str(viewer_id)
        ):
            return []
        votes = obj.poll_votes.select_related('voter', 'prompt').order_by('-updated_at')
        return PromptPollVoteSerializer(votes, many=True).data


class UserSerializer(serializers.ModelSerializer):
    online_status = serializers.SerializerMethodField()
    question_answers = serializers.SerializerMethodField()
    mandatory_questions_complete = serializers.SerializerMethodField()
    date_joined = serializers.DateTimeField(read_only=True)
    is_banned = serializers.BooleanField(read_only=True)
    is_online = serializers.SerializerMethodField()
    pictures = UserPictureSerializer(many=True, read_only=True)
    profile_prompts = UserProfilePromptSerializer(many=True, read_only=True)

    def validate_importance_exclusion_values(self, value):
        if value in (None, ''):
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError('Importance exclusion values must be a list.')

        normalized = []
        for raw_value in value:
            try:
                importance_value = int(raw_value)
            except (TypeError, ValueError):
                raise serializers.ValidationError('Importance exclusion values must be integers from 1 to 5.')
            if importance_value < 1 or importance_value > 5:
                raise serializers.ValidationError('Importance exclusion values must be integers from 1 to 5.')
            if importance_value not in normalized:
                normalized.append(importance_value)
        return normalized

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'profile_photo', 'age', 'date_of_birth', 'height', 'from_location', 'live', 'tagline', 'bio',
            'is_online', 'last_active', 'questions_answered_count', 'online_status', 'question_answers',
            'date_joined', 'is_banned', 'is_admin', 'email_verified', 'email_verified_at', 'mandatory_questions_complete',
            'restriction_type', 'restriction_duration', 'restriction_reason', 'restriction_reason_detail', 'restriction_date',
            'require_answers_for_likes', 'share_answers',
            'feed_visibility_bio', 'feed_visibility_photo', 'feed_visibility_question',
            'note_visibility',
            'importance_exclusion_values',
            'pictures', 'profile_prompts',
        ]
        read_only_fields = [
            'id', 'last_active', 'questions_answered_count',
            'date_joined', 'is_banned', 'is_admin', 'mandatory_questions_complete',
            'restriction_type', 'restriction_duration', 'restriction_reason', 'restriction_reason_detail', 'restriction_date',
            'username', 'first_name', 'last_name', 'date_of_birth', 'age'
        ]

    def get_is_online(self, obj):
        return obj.is_online

    def get_mandatory_questions_complete(self, obj):
        mandatory_numbers = set(
            Question.objects.filter(is_mandatory=True).values_list('question_number', flat=True)
        )
        if not mandatory_numbers:
            return True
        answered_numbers = set(
            UserAnswer.objects.filter(
                user=obj, question__is_mandatory=True
            ).values_list('question__question_number', flat=True)
        )
        return len(answered_numbers) >= len(mandatory_numbers)

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
        """Get key profile answers for grouped onboarding questions."""
        answers = UserAnswer.objects.filter(
            user=obj,
            question__question_number__in=[1, 2]
        ).select_related('question')

        answer_map = {}
        for answer in answers:
            key = profile_answer_key(answer.question)
            if key:
                answer_map[key] = answer.me_answer

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


class LightQuestionSerializer(serializers.ModelSerializer):
    """Lightweight question serializer - no nested tags, answers, or submitted_by"""
    class Meta:
        model = Question
        fields = [
            'id', 'question_name', 'question_number', 'group_number', 'group_name',
            'group_name_text', 'question_type', 'text', 'is_required_for_match',
            'is_mandatory', 'skip_me', 'skip_looking_for', 'open_to_all_me',
            'open_to_all_looking_for', 'is_group'
        ]


class UserAnswerSerializer(serializers.ModelSerializer):
    question = LightQuestionSerializer(read_only=True)
    user_id = serializers.UUIDField(source='user.id', read_only=True)
    me_note = serializers.SerializerMethodField()

    def get_me_note(self, obj):
        """Return the note text only if the requesting viewer may see it.

        Fails closed: when a caller has not wired 'note_visible_author_ids' into
        the serializer context we return '' rather than leaking the note. An
        empty string is also what an author-less note looks like, so a viewer
        cannot tell a hidden note from an absent one.
        """
        if not (obj.me_note or ''):
            return ''
        allowed = self.context.get('note_visible_author_ids')
        if allowed is None:
            return ''
        return obj.me_note if obj.user_id in allowed else ''

    def validate_excluded_answer_values(self, value):
        if value in (None, ''):
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError('Excluded answer values must be a list.')

        normalized = []
        for raw_value in value:
            try:
                answer_value = int(raw_value)
            except (TypeError, ValueError):
                raise serializers.ValidationError('Excluded answer values must be integers from 1 to 5.')
            if answer_value < 1 or answer_value > 5:
                raise serializers.ValidationError('Excluded answer values must be integers from 1 to 5.')
            if answer_value not in normalized:
                normalized.append(answer_value)
        return normalized

    class Meta:
        model = UserAnswer
        fields = [
            'id', 'user_id', 'question', 'me_answer', 'me_open_to_all',
            'me_importance', 'me_share', 'me_note', 'me_note_updated_at',
            'looking_for_answer',
            'looking_for_open_to_all', 'looking_for_importance',
            'looking_for_share', 'excluded_answer_values', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user_id', 'me_note_updated_at', 'created_at', 'updated_at']


class UserRequiredQuestionSerializer(serializers.ModelSerializer):
    question_id = serializers.UUIDField(source='question.id', read_only=True)

    class Meta:
        model = UserRequiredQuestion
        fields = ['id', 'user', 'question', 'question_id', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']


class CompatibilitySerializer(serializers.ModelSerializer):
    user1 = UserSerializer(read_only=True)
    user2 = UserSerializer(read_only=True)
    
    class Meta:
        model = Compatibility
        fields = [
            'id', 'user1', 'user2', 'overall_compatibility',
            'compatible_with_me', 'im_compatible_with',
            'mutual_questions_count',
            'required_overall_compatibility', 'required_compatible_with_me',
            'required_im_compatible_with', 'their_required_compatibility',
            'required_mutual_questions_count',
            'user1_required_completeness', 'user2_required_completeness',
            'required_completeness_ratio',  # Deprecated - use user1/user2 fields instead
            'last_calculated'
        ]
        read_only_fields = [
            'id', 'overall_compatibility', 'compatible_with_me',
            'im_compatible_with', 'mutual_questions_count',
            'required_overall_compatibility', 'required_compatible_with_me',
            'required_im_compatible_with', 'their_required_compatibility',
            'required_mutual_questions_count',
            'user1_required_completeness', 'user2_required_completeness',
            'required_completeness_ratio',
            'last_calculated'
        ]


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
        fields = ['id', 'conversation', 'sender', 'receiver', 'content', 'is_read', 'created_at']
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
            'id', 'reporter', 'reported_user', 'reason_category', 'reason', 'evidence',
            'status', 'moderator_notes', 'created_at', 'resolved_at', 'resolved_by'
        ]
        read_only_fields = ['id', 'reporter', 'status', 'moderator_notes',
                           'created_at', 'resolved_at', 'resolved_by']

    def validate(self, data):
        if data.get('reason_category') == 'other' and not data.get('reason', '').strip():
            raise serializers.ValidationError({'reason': 'Please provide details for "Other" reports.'})
        return data


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
    restriction_history = UserRestrictionHistorySerializer(many=True, read_only=True)
    
    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ['answers', 'restriction_history']


class DetailedQuestionSerializer(QuestionSerializer):
    user_answers = UserAnswerSerializer(many=True, read_only=True)

    class Meta(QuestionSerializer.Meta):
        fields = QuestionSerializer.Meta.fields + ['user_answers']


# Lightweight serializers for compatibility endpoint (no circular references)
class SimpleUserSerializer(serializers.ModelSerializer):
    """Lightweight user serializer for compatibility lists - no nested data"""
    is_online = serializers.SerializerMethodField()
    pictures = UserPictureSerializer(many=True, read_only=True)
    profile_prompts = UserProfilePromptSerializer(many=True, read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'profile_photo', 'age', 'date_of_birth', 'height',
            'from_location', 'live', 'tagline', 'bio', 'is_online', 'last_active', 'is_admin', 'email_verified',
            'require_answers_for_likes', 'share_answers', 'pictures', 'profile_prompts',
        ]

    def get_is_online(self, obj):
        return obj.is_online

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
        fields = [
            'id', 'adjust', 'exponent', 'ota',
            'auto_updater_enabled', 'auto_answer_required_enabled',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ChangeEmailSerializer(serializers.Serializer):
    """Serializer for changing user email"""
    current_password = serializers.CharField(write_only=True, required=True)
    new_email = serializers.EmailField(required=True)

    def validate_new_email(self, value):
        """Check if email is already in use"""
        user = self.context.get('request').user
        if User.objects.filter(email=value).exclude(id=user.id).exists():
            raise serializers.ValidationError("This email is already in use by another account.")
        return value

    def validate(self, data):
        """Verify current password"""
        user = self.context.get('request').user
        if not user.check_password(data['current_password']):
            raise serializers.ValidationError({"current_password": "Current password is incorrect."})
        return data


class ChangePasswordSerializer(serializers.Serializer):
    """Serializer for changing user password"""
    current_password = serializers.CharField(write_only=True, required=True)
    new_password = serializers.CharField(write_only=True, required=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, required=True)

    def validate(self, data):
        """Verify current password and confirm new password match"""
        user = self.context.get('request').user

        # Check current password
        if not user.check_password(data['current_password']):
            raise serializers.ValidationError({"current_password": "Current password is incorrect."})

        # Check new password matches confirmation
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "New passwords do not match."})

        # Check new password is different from current
        if data['current_password'] == data['new_password']:
            raise serializers.ValidationError({"new_password": "New password must be different from current password."})

        return data


class NotificationSerializer(serializers.ModelSerializer):
    sender = SimpleUserSerializer(read_only=True)
    recipient = SimpleUserSerializer(read_only=True)
    related_prompt_poll_vote = PromptPollVoteSerializer(read_only=True)

    class Meta:
        model = Notification
        fields = [
            'id', 'recipient', 'sender', 'notification_type', 'note',
            'is_read', 'created_at', 'related_user_result',
            'related_prompt_poll_vote',
        ]
        read_only_fields = ['id', 'created_at']


class ConversationSerializer(serializers.ModelSerializer):
    participant1 = SimpleUserSerializer(read_only=True)
    participant2 = SimpleUserSerializer(read_only=True)
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    other_participant = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = ['id', 'participant1', 'participant2', 'other_participant', 'last_message', 'unread_count', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_last_message(self, obj):
        last_msg = obj.messages.order_by('-created_at').first()
        if last_msg:
            return {
                'id': str(last_msg.id),
                'content': last_msg.content[:100],  # Preview
                'sender_id': str(last_msg.sender.id),
                'created_at': last_msg.created_at,
                'is_read': last_msg.is_read
            }
        return None

    def get_unread_count(self, obj):
        request = self.context.get('request')
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            return obj.messages.filter(receiver=request.user, is_read=False).count()
        # Fallback: check for user_id in context
        user_id = self.context.get('user_id')
        if user_id:
            return obj.messages.filter(receiver_id=user_id, is_read=False).count()
        return 0

    def get_other_participant(self, obj):
        request = self.context.get('request')
        user_id = self.context.get('user_id')

        current_user_id = None
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            current_user_id = request.user.id
        elif user_id:
            current_user_id = user_id

        if current_user_id:
            if str(obj.participant1.id) == str(current_user_id):
                return SimpleUserSerializer(obj.participant2).data
            else:
                return SimpleUserSerializer(obj.participant1).data
        return None


# ===== Feed: Posts, Comments, Activities =====

class PostImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostImage
        fields = ['id', 'image_url', 'order']


class PostCommentSerializer(serializers.ModelSerializer):
    author = SimpleUserSerializer(read_only=True)
    post_preview = serializers.SerializerMethodField()

    class Meta:
        model = PostComment
        fields = ['id', 'post', 'author', 'body', 'created_at', 'updated_at', 'is_deleted', 'post_preview']
        read_only_fields = ['id', 'author', 'created_at', 'updated_at', 'is_deleted']

    def get_post_preview(self, obj):
        post = obj.post
        return {
            'id': str(post.id),
            'body': post.body[:180],
            'created_at': post.created_at,
            'author': SimpleUserSerializer(post.author).data,
        }


class PostRevisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostRevision
        fields = ['id', 'body', 'edited_at']


class PostSerializer(serializers.ModelSerializer):
    author = SimpleUserSerializer(read_only=True)
    images = PostImageSerializer(many=True, read_only=True)
    hashtags = serializers.SerializerMethodField()
    reaction_summary = serializers.SerializerMethodField()
    viewer_reaction = serializers.SerializerMethodField()
    comment_count = serializers.SerializerMethodField()
    is_own = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = [
            'id', 'author', 'body', 'visibility', 'created_at', 'updated_at', 'edited_count',
            'images', 'hashtags', 'reaction_summary', 'viewer_reaction',
            'comment_count', 'is_own',
        ]
        read_only_fields = fields

    def get_hashtags(self, obj):
        return list(obj.hashtags.values_list('tag', flat=True))

    def get_reaction_summary(self, obj):
        # Return counts keyed by kind. Falls back to 0 for missing keys.
        from django.db.models import Count
        counts = dict(obj.reactions.values('kind').annotate(c=Count('id')).values_list('kind', 'c'))
        return {'like': counts.get('like', 0), 'dislike': counts.get('dislike', 0)}

    def _viewer_id(self):
        request = self.context.get('request')
        if not request:
            return None
        return self.context.get('viewer_id') or (str(request.user.id) if request.user and request.user.is_authenticated else None)

    def get_viewer_reaction(self, obj):
        viewer_id = self._viewer_id()
        if not viewer_id:
            return None
        r = obj.reactions.filter(user_id=viewer_id).first()
        return r.kind if r else None

    def get_comment_count(self, obj):
        return obj.comments.filter(is_deleted=False).count()

    def get_is_own(self, obj):
        viewer_id = self._viewer_id()
        return bool(viewer_id and str(obj.author_id) == str(viewer_id))


class FeedActivitySerializer(serializers.ModelSerializer):
    user = SimpleUserSerializer(read_only=True)

    class Meta:
        model = FeedActivity
        fields = ['id', 'user', 'kind', 'payload', 'created_at']
