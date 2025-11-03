from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
import uuid


class User(AbstractUser):
    """Extended User model for the dating app"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile_photo = models.URLField(max_length=500, null=True, blank=True)
    age = models.PositiveIntegerField(null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    height = models.PositiveIntegerField(help_text="Height in cm", null=True, blank=True)
    from_location = models.CharField(max_length=100, null=True, blank=True, help_text="Where the user is originally from")
    live = models.CharField(max_length=100, null=True, blank=True, help_text="Where the user currently lives")
    tagline = models.CharField(max_length=40, blank=True, help_text="Short tagline")
    bio = models.TextField(max_length=500, blank=True)
    is_online = models.BooleanField(default=False)
    last_seen = models.DateTimeField(default=timezone.now)
    is_banned = models.BooleanField(default=False)
    is_admin = models.BooleanField(
        default=False,
        help_text="Grants access to internal dashboard features."
    )
    ban_reason = models.TextField(blank=True)
    ban_date = models.DateTimeField(null=True, blank=True)
    questions_answered_count = models.PositiveIntegerField(default=0)
    
    class Meta:
        db_table = 'users'


class Tag(models.Model):
    """Tags for questions and user results"""
    TAG_CHOICES = [
        ('value', 'Value'),
        ('lifestyle', 'Lifestyle'),
        ('look', 'Look'),
        ('trait', 'Trait'),
        ('hobby', 'Hobby'),
        ('interest', 'Interest'),
    ]
    
    name = models.CharField(max_length=50, choices=TAG_CHOICES, unique=True)
    
    def __str__(self):
        return self.get_name_display()


class Question(models.Model):
    """Questions for the dating app"""

    QUESTION_TYPE_CHOICES = [
        ('basic', 'Basic'),
        ('four', 'Four'),
        ('grouped', 'Grouped'),
        ('double', 'Double'),
        ('triple', 'Triple'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question_name = models.CharField(max_length=200, blank=True, help_text="Short name/identifier for the question")
    question_number = models.PositiveIntegerField(null=True, blank=True, help_text="Question number for ordering")
    group_number = models.PositiveIntegerField(null=True, blank=True, help_text="Group number for organizing questions into categories")
    group_name = models.CharField(max_length=200, blank=True, help_text="Group/category name for the question")
    group_name_text = models.TextField(blank=True, help_text="Detailed description or text for the group")
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPE_CHOICES, default='basic', help_text="Type of question")
    text = models.TextField()
    tags = models.ManyToManyField(Tag, related_name='questions')
    is_required_for_match = models.BooleanField(default=False, help_text="Whether this question is required for matching")
    is_mandatory = models.BooleanField(default=False, help_text="Whether this is a mandatory question (1-10)")
    submitted_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, 
                                    related_name='submitted_questions', 
                                    help_text="User who submitted this question")
    is_approved = models.BooleanField(default=False, help_text="Whether the question is approved for use")
    skip_me = models.BooleanField(default=False, help_text="Whether to skip asking about me")
    skip_looking_for = models.BooleanField(default=False, help_text="Whether to skip asking about what I'm looking for")
    open_to_all_me = models.BooleanField(default=False, help_text="Whether I'm open to all options")
    open_to_all_looking_for = models.BooleanField(default=False, help_text="Whether I'm open to all options in a partner")
    is_group = models.BooleanField(default=False, help_text="Whether this question represents a group/category")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.text[:50]


class QuestionAnswer(models.Model):
    """Answers for questions"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='answers')
    value = models.CharField(max_length=10, help_text="Answer value (1, 2, 3, 4, 5)")
    answer_text = models.CharField(max_length=500, help_text="Answer text")
    order = models.PositiveIntegerField(default=0, help_text="Order of the answer")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['question', 'value']
        ordering = ['order']
    
    def __str__(self):
        return f"{self.question.text[:30]} - {self.value}: {self.answer_text[:30]}"


class UserAnswer(models.Model):
    """User answers to questions"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='user_answers')
    
    # Me answers (what I am)
    me_answer = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(6)],
        help_text="1-5 for specific answers, 6 for 'open to all'"
    )
    me_open_to_all = models.BooleanField(default=False)
    me_importance = models.PositiveIntegerField(default=1, help_text="Importance level for this answer")
    me_share = models.BooleanField(default=True, help_text="Whether to share this answer")
    
    # Looking for answers (what I want in a partner)
    looking_for_answer = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(6)],
        help_text="1-5 for specific answers, 6 for 'open to all'"
    )
    looking_for_open_to_all = models.BooleanField(default=False)
    looking_for_importance = models.PositiveIntegerField(default=1, help_text="Importance level for this answer")
    looking_for_share = models.BooleanField(default=True, help_text="Whether to share this preference")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['user', 'question']
    
    def __str__(self):
        return f"{self.user.username} - {self.question.text[:30]}"


class Compatibility(models.Model):
    """Compatibility scores between users"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user1 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='compatibilities_as_user1')
    user2 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='compatibilities_as_user2')
    
    overall_compatibility = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    compatible_with_me = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    im_compatible_with = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    
    mutual_questions_count = models.PositiveIntegerField(default=0)
    last_calculated = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['user1', 'user2']
        verbose_name_plural = 'compatibilities'
        indexes = [
            # Fast lookups for user1 compatibility queries
            models.Index(fields=['user1', '-overall_compatibility'], name='compatibility_user1_score'),
            # Fast lookups for user2 compatibility queries
            models.Index(fields=['user2', '-overall_compatibility'], name='compatibility_user2_score'),
            # Combined index for filtering by compatibility score ranges
            models.Index(fields=['-overall_compatibility'], name='compatibility_score_idx'),
            # Fast lookups for specific user pairs
            models.Index(fields=['user1', 'user2'], name='compatibility_pair_idx'),
            # Fast lookups for last_calculated (for cache invalidation)
            models.Index(fields=['last_calculated'], name='compatibility_calculated_idx'),
        ]
    
    def __str__(self):
        return f"{self.user1.username} & {self.user2.username}"


class UserResult(models.Model):
    """Results/tags for other users - supports multiple tags per user pair"""
    RESULT_TAG_CHOICES = [
        ('approve', 'Approve'),
        ('approved_me', 'Approved Me'),
        ('hot', 'Hot'),
        ('maybe', 'Maybe'),
        ('like', 'Like'),
        ('liked', 'Liked'),
        ('liked_me', 'Liked Me'),
        ('matched', 'Matched'),
        ('save', 'Save'),
        ('saved', 'Saved'),
        ('not_approved', 'Not Approved'),
        ('hide', 'Hide'),
        ('hidden', 'Hidden'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='my_results')
    result_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='results_from_others')
    tag = models.CharField(max_length=20, choices=RESULT_TAG_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Changed: Allow multiple tags per user pair
        unique_together = ['user', 'result_user', 'tag']
        indexes = [
            models.Index(fields=['user', 'result_user'], name='userresult_user_pair_idx'),
            models.Index(fields=['user', 'tag'], name='userresult_user_tag_idx'),
        ]

    def __str__(self):
        return f"{self.user.username} tagged {self.result_user.username} as {self.tag}"


class Message(models.Model):
    """Messages between users"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_messages')
    content = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.sender.username} -> {self.receiver.username}"


class PictureModeration(models.Model):
    """Picture moderation queue"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='picture_moderations')
    picture = models.ImageField(upload_to='moderation_queue/', null=True, blank=True)
    picture_url = models.URLField(max_length=500, null=True, blank=True, help_text="Azure Blob Storage URL for the picture")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    moderator_notes = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    moderated_at = models.DateTimeField(null=True, blank=True)
    moderated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='moderated_pictures')

    def __str__(self):
        return f"{self.user.username} - {self.status}"


class UserReport(models.Model):
    """Reported users queue"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('investigating', 'Investigating'),
        ('resolved', 'Resolved'),
        ('dismissed', 'Dismissed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reporter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reports_made')
    reported_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reports_received')
    reason = models.TextField()
    evidence = models.TextField(blank=True, help_text="Additional evidence or context")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    moderator_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_reports')
    
    def __str__(self):
        return f"{self.reporter.username} reported {self.reported_user.username}"


class UserOnlineStatus(models.Model):
    """Track user online status"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='online_status')
    is_online = models.BooleanField(default=False)
    last_seen = models.DateTimeField(default=timezone.now)
    last_activity = models.DateTimeField(default=timezone.now)
    
    def __str__(self):
        return f"{self.user.username} - {'Online' if self.is_online else 'Offline'}"


class UserTag(models.Model):
    """User tags for other users (approve, hot, maybe, liked, etc.)"""
    TAG_CHOICES = [
        ('approve', 'Approve'),
        ('approved_me', 'Approved Me'),
        ('hot', 'Hot'),
        ('maybe', 'Maybe'),
        ('liked', 'Liked'),
        ('liked_me', 'Liked Me'),
        ('matched', 'Matched'),
        ('saved', 'Saved'),
        ('not_approved', 'Not Approved'),
        ('hidden', 'Hidden'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tags_given')
    tagged_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tags_received')
    tag = models.CharField(max_length=20, choices=TAG_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['user', 'tagged_user', 'tag']
        verbose_name = 'User Tag'
        verbose_name_plural = 'User Tags'
    
    def __str__(self):
        return f"{self.user.username} tagged {self.tagged_user.username} as {self.tag}"


class Controls(models.Model):
    """App-wide control values for configuration"""
    adjust = models.FloatField(
        default=5.0,
        help_text="Adjustment factor for calculations"
    )
    exponent = models.FloatField(
        default=2.0,
        help_text="Exponent value for calculations"
    )
    ota = models.FloatField(
        default=0.5,
        help_text="OTA (Open To All) weight factor",
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Control Settings'
        verbose_name_plural = 'Control Settings'

    def __str__(self):
        return f"Controls (adjust={self.adjust}, exponent={self.exponent}, ota={self.ota})"

    @classmethod
    def get_current(cls):
        """Get the current control settings, creating default if none exists"""
        controls, created = cls.objects.get_or_create(
            id=1,  # Always use ID 1 for the single controls instance
            defaults={
                'adjust': 5.0,
                'exponent': 2.0,
                'ota': 0.5
            }
        )
        return controls


class CompatibilityJob(models.Model):
    """Queue entry for recomputing compatibility scores for a user"""

    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='compatibility_job'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True
    )
    attempts = models.PositiveIntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"CompatibilityJob(user={self.user_id}, status={self.status})"


class DailyMetric(models.Model):
    """Daily aggregated metrics for dashboard charts"""
    date = models.DateField(unique=True, db_index=True)

    # User metrics
    total_users = models.IntegerField(default=0)
    new_users = models.IntegerField(default=0)
    active_users = models.IntegerField(default=0)  # Users who logged in that day

    # Activity metrics
    total_approves = models.IntegerField(default=0)
    total_likes = models.IntegerField(default=0)
    total_matches = models.IntegerField(default=0)

    # Engagement metrics
    questions_answered = models.IntegerField(default=0)
    messages_sent = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'daily_metrics'
        ordering = ['-date']

    def __str__(self):
        return f"Metrics for {self.date}"


class RestrictedWord(models.Model):
    """Words that are not allowed in user-generated content"""
    SEVERITY_CHOICES = [
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
    ]

    word = models.CharField(max_length=100, unique=True, db_index=True, help_text="Restricted word (stored in lowercase)")
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='high', help_text="Severity level of the restriction")
    is_active = models.BooleanField(default=True, db_index=True, help_text="Whether this restriction is currently active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'restricted_words'
        ordering = ['word']
        indexes = [
            models.Index(fields=['is_active', 'word'], name='restricted_word_active_idx'),
        ]

    def save(self, *args, **kwargs):
        # Always store words in lowercase for case-insensitive matching
        self.word = self.word.lower().strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.word} ({self.severity})"
