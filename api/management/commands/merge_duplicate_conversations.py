from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from collections import defaultdict

from api.models import Conversation, Message


class Command(BaseCommand):
    help = 'Merge duplicate conversations that represent the same pair of users'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be merged without actually merging',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN MODE - No changes will be made'))
        
        self.stdout.write(self.style.SUCCESS('🚀 Starting duplicate conversation merge...'))
        
        # Find all conversations
        all_conversations = Conversation.objects.all().select_related('participant1', 'participant2')
        
        # Group conversations by normalized participant pair
        conversation_groups = defaultdict(list)
        
        for conv in all_conversations:
            # Normalize participant order (smaller ID first)
            p1_id = str(conv.participant1.id)
            p2_id = str(conv.participant2.id)
            if p1_id > p2_id:
                p1_id, p2_id = p2_id, p1_id
            
            pair_key = f"{p1_id}_{p2_id}"
            conversation_groups[pair_key].append(conv)
        
        # Find duplicates (groups with more than one conversation)
        duplicates_found = 0
        conversations_merged = 0
        conversations_deleted = 0
        messages_moved = 0
        
        for pair_key, conversations in conversation_groups.items():
            if len(conversations) > 1:
                duplicates_found += 1
                self.stdout.write(f'\n📦 Found {len(conversations)} conversations for pair {pair_key}:')
                
                # Determine which conversation to keep
                # Prefer conversation with messages, then most recent update
                conversations_with_messages = [c for c in conversations if c.messages.exists()]
                
                if conversations_with_messages:
                    # Keep the one with most recent update among those with messages
                    keep_conversation = max(conversations_with_messages, key=lambda x: x.updated_at)
                else:
                    # Keep the most recent one
                    keep_conversation = max(conversations, key=lambda x: x.updated_at)
                
                delete_conversations = [c for c in conversations if c.id != keep_conversation.id]
                
                self.stdout.write(f'   ✅ Keeping: {keep_conversation.id} (updated: {keep_conversation.updated_at})')
                
                for conv in delete_conversations:
                    message_count = conv.messages.count()
                    self.stdout.write(f'   🗑️  Will delete: {conv.id} (updated: {conv.updated_at}, messages: {message_count})')
                    
                    if not dry_run:
                        with transaction.atomic():
                            # Move messages to the kept conversation
                            if message_count > 0:
                                Message.objects.filter(conversation=conv).update(conversation=keep_conversation)
                                messages_moved += message_count
                                self.stdout.write(f'      📨 Moved {message_count} messages to conversation {keep_conversation.id}')
                            
                            # Delete the duplicate conversation
                            conv.delete()
                            conversations_deleted += 1
                    
                    conversations_merged += 1
        
        self.stdout.write('\n' + '─' * 50)
        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN COMPLETE - No changes were made'))
        else:
            self.stdout.write(self.style.SUCCESS('🎉 Duplicate conversation merge completed!'))
        
        self.stdout.write(f'📊 Summary:')
        self.stdout.write(f'   ├─ 🔍 Duplicate pairs found: {duplicates_found}')
        self.stdout.write(f'   ├─ 🔗 Conversations merged: {conversations_merged}')
        if not dry_run:
            self.stdout.write(f'   ├─ 🗑️  Conversations deleted: {conversations_deleted}')
            self.stdout.write(f'   └─ 📨 Messages moved: {messages_moved}')
        
        if duplicates_found == 0:
            self.stdout.write(self.style.SUCCESS('✨ No duplicate conversations found!'))

