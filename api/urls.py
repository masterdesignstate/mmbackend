from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    UserViewSet, TagViewSet, QuestionViewSet, UserAnswerViewSet,
    UserRequiredQuestionViewSet, CompatibilityViewSet, UserResultViewSet, MessageViewSet,
    PictureModerationViewSet, UserReportViewSet, UserTagViewSet, StatsViewSet, ControlsViewSet, NotificationViewSet, ConversationViewSet,
    PostViewSet, PostCommentViewSet, FeedView,
    PromptTemplateViewSet, UserProfilePromptViewSet,
)
from .function_views import (
    user_signup, user_personal_details, user_login, check_user_exists, check_onboarding_status, update_profile_photo, upload_photo, test_endpoint, delete_question,
    impostor_login, impostor_exit, verify_email, resend_verification_email
)

router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'tags', TagViewSet, basename='tag')
router.register(r'questions', QuestionViewSet, basename='question')
router.register(r'answers', UserAnswerViewSet, basename='answer')
router.register(r'user-required-questions', UserRequiredQuestionViewSet, basename='userrequiredquestion')
router.register(r'compatibility', CompatibilityViewSet, basename='compatibility')
router.register(r'results', UserResultViewSet, basename='result')
router.register(r'user-tags', UserTagViewSet, basename='user-tag')
router.register(r'messages', MessageViewSet, basename='message')
router.register(r'picture-moderation', PictureModerationViewSet, basename='picture-moderation')
router.register(r'reports', UserReportViewSet, basename='report')
router.register(r'stats', StatsViewSet, basename='stats')
router.register(r'controls', ControlsViewSet, basename='controls')
router.register(r'notifications', NotificationViewSet, basename='notification')
router.register(r'conversations', ConversationViewSet, basename='conversation')
router.register(r'posts', PostViewSet, basename='post')
router.register(r'comments', PostCommentViewSet, basename='comment')
router.register(r'feed', FeedView, basename='feed')
router.register(r'prompt-templates', PromptTemplateViewSet, basename='prompt-template')
router.register(r'profile-prompts', UserProfilePromptViewSet, basename='profile-prompt')

urlpatterns = [
    path('', include(router.urls)),
    
    # Functional views for user authentication
    path('auth/signup/', user_signup, name='user_signup'),
    path('auth/personal-details/', user_personal_details, name='user_personal_details'),
    path('auth/login/', user_login, name='user_login'),
    path('auth/verify-email/', verify_email, name='verify_email'),
    path('auth/resend-verification-email/', resend_verification_email, name='resend_verification_email'),
    path('auth/check-user/', check_user_exists, name='check_user_exists'),
    path('auth/onboarding-status/', check_onboarding_status, name='check_onboarding_status'),
    path('auth/update-profile-photo/', update_profile_photo, name='update_profile_photo'),
    path('auth/upload-photo/', upload_photo, name='upload_photo'),
    path('auth/upload-photo', upload_photo, name='upload_photo_no_slash'),
    path('test/', test_endpoint, name='test_endpoint'),
    path('questions/<str:question_id>/delete/', delete_question, name='delete_question'),
    path('auth/impostor-login/', impostor_login, name='impostor_login'),
    path('auth/impostor-exit/', impostor_exit, name='impostor_exit'),
] 
