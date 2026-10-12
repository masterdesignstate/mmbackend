from django.db import migrations
from django.db.models import Q

# Inlined rather than imported from api.services.dummy_activity, so this migration
# keeps working if that module changes.
DUMMY_EMAIL_DOMAIN = "dummy.matchmatical.local"


def dummies_approval_off(apps, schema_editor):
    """Simulated accounts should never gate likes behind approval. Covers banned and
    inactive dummies too, so none are left on the old default."""
    User = apps.get_model("api", "User")
    User.objects.filter(
        Q(is_dummy=True) | Q(email__iendswith=f"@{DUMMY_EMAIL_DOMAIN}")
    ).update(require_approval_for_likes=False)


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0072_user_require_approval_for_likes"),
    ]

    operations = [
        migrations.RunPython(dummies_approval_off, migrations.RunPython.noop),
    ]
