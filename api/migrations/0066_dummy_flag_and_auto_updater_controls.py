from django.db import migrations, models


DUMMY_EMAIL_DOMAIN = "dummy.matchmatical.local"


def backfill_is_dummy(apps, schema_editor):
    """Every account that exists at this point is seeded/simulated data -- there
    are no real signups yet. Mark them all as dummy so the activity simulator,
    which from here on only acts on non-dummy users, does not touch them.

    Accounts created after this migration default to is_dummy=False, so real
    signups are correctly treated as real.
    """
    User = apps.get_model("api", "User")
    User.objects.all().update(is_dummy=True)


def unbackfill_is_dummy(apps, schema_editor):
    """Reverse leaves only the email-domain-derived dummies flagged, which is the
    closest recoverable approximation of the pre-migration world.
    """
    User = apps.get_model("api", "User")
    User.objects.exclude(email__iendswith=f"@{DUMMY_EMAIL_DOMAIN}").update(is_dummy=False)


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0065_user_email_verification_code"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="is_dummy",
            field=models.BooleanField(
                default=False,
                db_index=True,
                help_text=(
                    "Seeded/simulated account rather than a real signup. Authoritative "
                    "source of truth for dummy-ness -- do not infer it from the email "
                    "domain. The background activity simulator uses this to decide which "
                    "accounts it may act on."
                ),
            ),
        ),
        migrations.AddField(
            model_name="controls",
            name="auto_updater_enabled",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Master switch for the background activity simulator. When off, "
                    "the simulator does nothing at all."
                ),
            ),
        ),
        migrations.AddField(
            model_name="controls",
            name="auto_answer_required_enabled",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Switch for the simulator's required-question catch-up. When off, "
                    "feed activity is still simulated but no required questions are "
                    "auto-answered."
                ),
            ),
        ),
        migrations.RunPython(backfill_is_dummy, unbackfill_is_dummy),
    ]
