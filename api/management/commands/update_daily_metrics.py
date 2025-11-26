from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Count, Q
from datetime import datetime, timedelta
from api.models import User, UserResult, UserAnswer, Message, DailyMetric


class Command(BaseCommand):
    help = 'Calculate and update daily metrics for dashboard charts'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=90,
            help='Number of days to calculate metrics for (default: 90)'
        )
        parser.add_argument(
            '--date',
            type=str,
            help='Specific date to calculate (YYYY-MM-DD format)'
        )

    def handle(self, *args, **options):
        if options['date']:
            # Calculate for specific date
            target_date = datetime.strptime(options['date'], '%Y-%m-%d').date()
            self.calculate_metrics_for_date(target_date)
        else:
            # Calculate for the last N days
            days = options['days']
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=days)

            self.stdout.write(f"Calculating metrics from {start_date} to {end_date}...")

            current_date = start_date
            while current_date <= end_date:
                self.calculate_metrics_for_date(current_date)
                current_date += timedelta(days=1)

            self.stdout.write(self.style.SUCCESS(f'Successfully calculated metrics for {days} days'))

    def calculate_metrics_for_date(self, target_date):
        """Calculate metrics for a specific date"""
        next_date = target_date + timedelta(days=1)

        # User metrics
        total_users = User.objects.filter(date_joined__date__lte=target_date).count()
        new_users = User.objects.filter(date_joined__date=target_date).count()
        active_users = User.objects.filter(
            last_active__date=target_date
        ).count()

        # Activity metrics (created on this day)
        approves = UserResult.objects.filter(
            tag='approve',
            created_at__date=target_date
        ).count()

        likes = UserResult.objects.filter(
            tag='like',
            created_at__date=target_date
        ).count()

        matches = UserResult.objects.filter(
            tag='matched',
            created_at__date=target_date
        ).count()

        # Engagement metrics
        questions_answered = UserAnswer.objects.filter(
            created_at__date=target_date
        ).count()

        messages_sent = Message.objects.filter(
            created_at__date=target_date
        ).count()

        # Create or update the daily metric
        metric, created = DailyMetric.objects.update_or_create(
            date=target_date,
            defaults={
                'total_users': total_users,
                'new_users': new_users,
                'active_users': active_users,
                'total_approves': approves,
                'total_likes': likes,
                'total_matches': matches,
                'questions_answered': questions_answered,
                'messages_sent': messages_sent,
            }
        )

        action = "Created" if created else "Updated"
        self.stdout.write(
            f"{action} metrics for {target_date}: "
            f"Users={total_users}, New={new_users}, Active={active_users}, "
            f"Approves={approves}, Likes={likes}, Matches={matches}"
        )
