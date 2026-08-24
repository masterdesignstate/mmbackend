from django.db import migrations

OLD_ADMIN_EMAIL = "admin@matchmatical.com"
NEW_ADMIN_EMAIL = "admin@compatiblefirst.com"


def _swap(apps, from_email, to_email):
    User = apps.get_model("api", "User")

    old_user = User.objects.filter(email__iexact=from_email).first()
    if not old_user:
        return

    if User.objects.filter(email__iexact=to_email).exists():
        # Target admin already exists; retire admin access on the stale account.
        fields_to_update = []
        for flag in ("is_admin", "is_staff", "is_superuser"):
            if getattr(old_user, flag, False):
                setattr(old_user, flag, False)
                fields_to_update.append(flag)
        if fields_to_update:
            old_user.save(update_fields=fields_to_update)
        return

    old_user.email = to_email
    old_user.save(update_fields=["email"])


def rename_admin_email(apps, schema_editor):
    _swap(apps, OLD_ADMIN_EMAIL, NEW_ADMIN_EMAIL)


def revert_admin_email(apps, schema_editor):
    _swap(apps, NEW_ADMIN_EMAIL, OLD_ADMIN_EMAIL)


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0068_text_length_limits"),
    ]

    operations = [
        migrations.RunPython(rename_admin_email, revert_admin_email),
    ]
