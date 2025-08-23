from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    User, Tag, Question, QuestionAnswer, UserAnswer, Compatibility, 
    UserResult, Message, PictureModeration, UserReport, UserOnlineStatus, UserTag
)

# Custom User Admin with search functionality
@admin.register(User)
class CustomUserAdmin(UserAdmin):
    # Add search functionality
    search_fields = ['username', 'email', 'first_name', 'last_name', 'city']
    
    # Customize list display
    list_display = ['username', 'email', 'first_name', 'last_name', 'city', 'age', 'is_online', 'is_active', 'date_joined']
    
    # Add filters for easier browsing
    list_filter = ['is_active', 'is_staff', 'is_superuser', 'is_online', 'is_banned', 'date_joined']
    
    # Add ordering
    ordering = ['-date_joined']
    
    # Customize the form fields
    fieldsets = UserAdmin.fieldsets + (
        ('Dating Profile', {
            'fields': ('profile_photo', 'age', 'date_of_birth', 'height', 'city', 'bio')
        }),
        ('Status', {
            'fields': ('is_online', 'last_seen', 'is_banned', 'ban_reason', 'ban_date', 'questions_answered_count')
        }),
    )
    
    # Add fields to the add form
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Profile Information', {
            'fields': ('email', 'first_name', 'last_name')
        }),
    )

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