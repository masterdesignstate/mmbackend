from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    UserViewSet, TagViewSet, QuestionViewSet, UserAnswerViewSet,
    CompatibilityViewSet, UserResultViewSet, MessageViewSet,
    PictureModerationViewSet, UserReportViewSet, UserTagViewSet
)

router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'tags', TagViewSet, basename='tag')
router.register(r'questions', QuestionViewSet, basename='question')
router.register(r'answers', UserAnswerViewSet, basename='answer')
router.register(r'compatibility', CompatibilityViewSet, basename='compatibility')
router.register(r'results', UserResultViewSet, basename='result')
router.register(r'user-tags', UserTagViewSet, basename='user-tag')
router.register(r'messages', MessageViewSet, basename='message')
router.register(r'picture-moderation', PictureModerationViewSet, basename='picture-moderation')
router.register(r'reports', UserReportViewSet, basename='report')

urlpatterns = [
    path('', include(router.urls)),
] 