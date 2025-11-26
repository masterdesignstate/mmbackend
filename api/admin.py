from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    User, Tag, Question, QuestionAnswer, UserAnswer, Compatibility,
    UserResult, Message, PictureModeration, UserReport, UserOnlineStatus, UserTag, DailyMetric, RestrictedWord
)

# Custom User Admin with search functionality
@admin.register(User)
class CustomUserAdmin(UserAdmin):
    # Add search functionality
    search_fields = ['username', 'email', 'first_name', 'last_name', 'from_location', 'live']
    
    # Customize list display
    list_display = ['username', 'email', 'first_name', 'last_name', 'from_location', 'live', 'age', 'is_active', 'date_joined']

    # Add filters for easier browsing
    list_filter = ['is_active', 'is_staff', 'is_superuser', 'is_banned', 'date_joined']
    
    # Add ordering
    ordering = ['-date_joined']
    
    # Customize the form fields
    fieldsets = UserAdmin.fieldsets + (
        ('Dating Profile', {
            'fields': ('profile_photo', 'age', 'date_of_birth', 'height', 'from_location', 'live', 'bio')
        }),
        ('Status', {
            'fields': ('last_active', 'is_banned', 'ban_reason', 'ban_date', 'questions_answered_count')
        }),
    )
    
    # Add fields to the add form
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Profile Information', {
            'fields': ('email', 'first_name', 'last_name')
        }),
    )

# Custom RestrictedWord Admin
@admin.register(RestrictedWord)
class RestrictedWordAdmin(admin.ModelAdmin):
    list_display = ['word', 'severity', 'is_active', 'created_at', 'updated_at']
    list_filter = ['severity', 'is_active', 'created_at']
    search_fields = ['word']
    ordering = ['word']

    actions = ['activate_words', 'deactivate_words']

    def activate_words(self, request, queryset):
        queryset.update(is_active=True)
        self.message_user(request, f"{queryset.count()} words activated")
        # Clear cache after bulk action
        from api.utils.word_filter import clear_restricted_words_cache
        clear_restricted_words_cache()
    activate_words.short_description = "Activate selected words"

    def deactivate_words(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, f"{queryset.count()} words deactivated")
        # Clear cache after bulk action
        from api.utils.word_filter import clear_restricted_words_cache
        clear_restricted_words_cache()
    deactivate_words.short_description = "Deactivate selected words"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Clear cache when a word is saved
        from api.utils.word_filter import clear_restricted_words_cache
        clear_restricted_words_cache()

    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        # Clear cache when a word is deleted
        from api.utils.word_filter import clear_restricted_words_cache
        clear_restricted_words_cache()

# Register other models with basic admin
admin.site.register(Tag)
admin.site.register(Question)
admin.site.register(QuestionAnswer)
admin.site.register(UserAnswer)
admin.site.register(Compatibility)
admin.site.register(UserResult)
admin.site.register(UserTag)
admin.site.register(Message)
admin.site.register(PictureModeration)
admin.site.register(UserReport)
admin.site.register(UserOnlineStatus)
admin.site.register(DailyMetric) 