from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta, date

from appointments.models import Appointment, EmailLog
from appointments.emails import send_appointment_email

class Command(BaseCommand):
    help = "Automated background job to send 24-hour and same-day appointment email reminders to patients."

    def handle(self, *args, **options):
        today = date.today()
        tomorrow = today + timedelta(days=1)

        self.stdout.write("Starting automated appointment reminder email scan...")

        # 1. 24-Hour Reminders (Tomorrow's appointments)
        reminders_24h = Appointment.objects.filter(
            status__in=[Appointment.Status.APPROVED, Appointment.Status.RESCHEDULED],
            date=tomorrow,
            reminder_24h_sent=False
        ).select_related('patient', 'doctor__user', 'doctor__specialization')

        count_24h = 0
        for app in reminders_24h:
            success = send_appointment_email(
                EmailLog.EmailType.REMINDER,
                app,
                extra_context={'reminder_timeframe': '24-Hour Notice'}
            )
            if success:
                app.reminder_24h_sent = True
                app.save(update_fields=['reminder_24h_sent'])
                count_24h += 1
                self.stdout.write(f"Sent 24-hour reminder to {app.patient.email} for Appointment #{app.id}")

        # 2. Same-Day / 1-Hour Reminders (Today's appointments)
        reminders_1h = Appointment.objects.filter(
            status__in=[Appointment.Status.APPROVED, Appointment.Status.RESCHEDULED],
            date=today,
            reminder_1h_sent=False
        ).select_related('patient', 'doctor__user', 'doctor__specialization')

        count_1h = 0
        for app in reminders_1h:
            success = send_appointment_email(
                EmailLog.EmailType.REMINDER,
                app,
                extra_context={'reminder_timeframe': 'Same-Day Notice'}
            )
            if success:
                app.reminder_1h_sent = True
                app.save(update_fields=['reminder_1h_sent'])
                count_1h += 1
                self.stdout.write(f"Sent same-day reminder to {app.patient.email} for Appointment #{app.id}")

        self.stdout.write(
            self.style.SUCCESS(f"Finished appointment reminders execution! 24h sent: {count_24h}, Same-day sent: {count_1h}")
        )
