from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
import uuid


class User(AbstractUser):
    """Extended User model for the dating app"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile_photo = models.ImageField(upload_to='profile_photos/', null=True, blank=True)
    age = models.PositiveIntegerField(null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    height = models.PositiveIntegerField(help_text="Height in cm", null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    bio = models.TextField(max_length=500, blank=True)
    is_online = models.BooleanField(default=False)
    last_seen = models.DateTimeField(default=timezone.now)
    is_banned = models.BooleanField(default=False)
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
        ('mandatory', 'Mandatory'),
        ('answered', 'Answered'),
        ('unanswered', 'Unanswered'),
        ('required', 'Required'),
        ('submitted', 'Submitted'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    text = models.TextField()
    tags = models.ManyToManyField(Tag, related_name='questions')
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPE_CHOICES, default='unanswered')
    is_required_for_match = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.text[:50]


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
    me_multiplier = models.PositiveIntegerField(default=1, help_text="Weight multiplier for this answer")
    me_share = models.BooleanField(default=True, help_text="Whether to share this answer")
    
    # Looking for answers (what I want in a partner)
    looking_for_answer = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(6)],
        help_text="1-5 for specific answers, 6 for 'open to all'"
    )
    looking_for_open_to_all = models.BooleanField(default=False)
    looking_for_multiplier = models.PositiveIntegerField(default=1, help_text="Weight multiplier for this answer")
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
    
    def __str__(self):
        return f"{self.user1.username} & {self.user2.username}"


class UserResult(models.Model):
    """Results/tags for other users"""
    RESULT_TAG_CHOICES = [
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
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='my_results')
    result_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='results_from_others')
    tag = models.CharField(max_length=20, choices=RESULT_TAG_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['user', 'result_user']
    
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
    picture = models.ImageField(upload_to='moderation_queue/')
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
