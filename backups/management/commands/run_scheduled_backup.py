from django.core.management.base import BaseCommand
from django.utils import timezone
from backups.models import BackupScheduleConfig, BackupType
from backups.services import create_backup_archive, purge_expired_backups

class Command(BaseCommand):
    help = "Executes automated daily/weekly backup based on BackupScheduleConfig and purges expired backups."

    def handle(self, *args, **options):
        self.stdout.write("Checking automated backup schedule configuration...")
        config, _ = BackupScheduleConfig.objects.get_or_create(id=1)

        if not config.is_enabled:
            self.stdout.write(self.style.WARNING("Automated backups are currently disabled in settings."))
            return

        self.stdout.write(f"Executing automated system backup ({config.get_frequency_display()})...")
        try:
            record = create_backup_archive(backup_type=BackupType.FULL, notes="Automated scheduled backup.")
            config.last_run = timezone.now()
            config.save(update_fields=['last_run'])
            self.stdout.write(self.style.SUCCESS(f"Automated backup '{record.backup_name}' generated successfully ({record.get_formatted_file_size()})."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Automated backup failed: {str(e)}"))

        self.stdout.write("Running retention policy purge for expired backups...")
        purged_count = purge_expired_backups()
        self.stdout.write(self.style.SUCCESS(f"Purged {purged_count} expired backup records exceeding {config.retention_days} days retention limit."))
