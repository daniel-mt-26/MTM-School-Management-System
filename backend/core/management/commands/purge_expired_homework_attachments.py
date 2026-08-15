from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import HomeworkAttachment


class Command(BaseCommand):
    help = "Delete expired Homework attachment files and their database records."

    def handle(self, *args, **options):
        deleted = 0
        for attachment in HomeworkAttachment.objects.filter(expires_at__lte=timezone.now()).iterator():
            attachment.file.delete(save=False)
            attachment.delete()
            deleted += 1
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} expired homework attachment(s)."))
