from django.db import migrations


def backfill_pictures(apps, schema_editor):
    User = apps.get_model('api', 'User')
    UserPicture = apps.get_model('api', 'UserPicture')
    to_create = []
    for user in User.objects.exclude(profile_photo__isnull=True).exclude(profile_photo=''):
        # Skip if a primary picture already exists (idempotent)
        if UserPicture.objects.filter(user=user, order=0).exists():
            continue
        to_create.append(UserPicture(user=user, image_url=user.profile_photo, order=0))
    if to_create:
        UserPicture.objects.bulk_create(to_create)


def reverse_noop(apps, schema_editor):
    # We don't unwind this — `User.profile_photo` is preserved as the canonical thumbnail anyway.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('api', '0045_userpicture'),
    ]
    operations = [
        migrations.RunPython(backfill_pictures, reverse_noop),
    ]
