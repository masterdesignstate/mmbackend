"""
Management command to populate initial restricted words.
"""
from django.core.management.base import BaseCommand
from api.models import RestrictedWord


class Command(BaseCommand):
    help = 'Populate initial restricted words for content filtering'

    def handle(self, *args, **options):
        # Sample restricted words (keeping it minimal for demonstration)
        # In production, you'd want a comprehensive list
        initial_words = [
            # Common profanity (high severity)
            ('fuck', 'high'),
            ('shit', 'high'),
            ('damn', 'medium'),
            ('hell', 'low'),
            ('ass', 'medium'),
            ('bitch', 'high'),
            ('bastard', 'medium'),

            # Slurs and offensive terms (high severity)
            ('nazi', 'high'),
            ('terrorist', 'high'),

            # Sexual/explicit terms (high severity)
            ('porn', 'high'),
            ('xxx', 'high'),
            ('nsfw', 'high'),

            # Contact info patterns (medium severity)
            ('instagram', 'low'),
            ('snapchat', 'low'),
            ('whatsapp', 'low'),
            ('telegram', 'low'),

            # Scam-related (high severity)
            ('bitcoin', 'medium'),
            ('crypto', 'medium'),
            ('cashapp', 'medium'),
            ('venmo', 'medium'),
            ('paypal', 'medium'),
        ]

        created_count = 0
        skipped_count = 0

        for word, severity in initial_words:
            word_obj, created = RestrictedWord.objects.get_or_create(
                word=word.lower(),
                defaults={
                    'severity': severity,
                    'is_active': True
                }
            )

            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'✅ Created: {word} ({severity})')
                )
            else:
                skipped_count += 1
                self.stdout.write(
                    self.style.WARNING(f'⏭️  Skipped (already exists): {word}')
                )

        # Clear cache to ensure new words are loaded
        from api.utils.word_filter import clear_restricted_words_cache
        clear_restricted_words_cache()

        self.stdout.write(
            self.style.SUCCESS(
                f'\n📊 Summary:\n'
                f'  - Created: {created_count} words\n'
                f'  - Skipped: {skipped_count} words\n'
                f'  - Total: {RestrictedWord.objects.filter(is_active=True).count()} active restricted words\n'
            )
        )
