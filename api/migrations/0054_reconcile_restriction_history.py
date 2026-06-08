import datetime

from django.db import migrations
from django.utils import timezone


def _expires_at(restriction_type, restricted_at, duration_days):
    if restriction_type != 'temporary' or not restricted_at or duration_days is None:
        return None
    try:
        duration = int(duration_days)
    except (TypeError, ValueError):
        return None
    return restricted_at + datetime.timedelta(days=duration)


def reconcile_restriction_history(apps, schema_editor):
    User = apps.get_model('api', 'User')
    UserRestrictionHistory = apps.get_model('api', 'UserRestrictionHistory')
    now = timezone.now()

    for user in User.objects.all():
        active_history = UserRestrictionHistory.objects.filter(
            user_id=user.id,
            ended_at__isnull=True,
        ).order_by('-restricted_at').first()

        if active_history:
            if not user.is_banned:
                if (
                    active_history.restriction_type == 'temporary'
                    and active_history.expires_at
                    and active_history.expires_at <= now
                ):
                    active_history.ended_at = active_history.expires_at
                    active_history.end_reason = 'expired'
                else:
                    active_history.ended_at = now
                    active_history.end_reason = 'removed'
                active_history.save(update_fields=['ended_at', 'end_reason'])
                continue

            if (
                active_history.restriction_type == 'temporary'
                and active_history.expires_at
                and active_history.expires_at <= now
            ):
                active_history.ended_at = active_history.expires_at
                active_history.end_reason = 'expired'
                active_history.save(update_fields=['ended_at', 'end_reason'])

                user.is_banned = False
                user.restriction_type = None
                user.restriction_duration = None
                user.restriction_reason = ''
                user.restriction_reason_detail = ''
                user.restriction_date = None
                user.save(update_fields=[
                    'is_banned', 'restriction_type', 'restriction_duration',
                    'restriction_reason', 'restriction_reason_detail', 'restriction_date',
                ])
            continue

        if not user.is_banned:
            continue

        restriction_type = user.restriction_type or (
            'permanent' if user.restriction_duration == 0 else 'temporary'
        )
        duration_days = user.restriction_duration
        restricted_at = user.restriction_date or user.ban_date or user.date_joined or now
        expires_at = _expires_at(restriction_type, restricted_at, duration_days)
        reason = user.restriction_reason or user.ban_reason or 'admin_restriction'

        history = UserRestrictionHistory.objects.create(
            user_id=user.id,
            restriction_type=restriction_type,
            duration_days=duration_days,
            reason=reason,
            reason_detail=user.restriction_reason_detail or '',
            restricted_at=restricted_at,
            expires_at=expires_at,
        )

        if restriction_type == 'temporary' and expires_at and expires_at <= now:
            history.ended_at = expires_at
            history.end_reason = 'expired'
            history.save(update_fields=['ended_at', 'end_reason'])

            user.is_banned = False
            user.restriction_type = None
            user.restriction_duration = None
            user.restriction_reason = ''
            user.restriction_reason_detail = ''
            user.restriction_date = None
            user.save(update_fields=[
                'is_banned', 'restriction_type', 'restriction_duration',
                'restriction_reason', 'restriction_reason_detail', 'restriction_date',
            ])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0053_userrestrictionhistory'),
    ]

    operations = [
        migrations.RunPython(reconcile_restriction_history, noop_reverse),
    ]
