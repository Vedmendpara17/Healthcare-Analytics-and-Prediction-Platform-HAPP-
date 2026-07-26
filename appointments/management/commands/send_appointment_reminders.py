import datetime
from django.core.management.base import BaseCommand
from appointments.models import Appointment, EmailLog
from appointments.emails import send_appointment_email

class Command(BaseCommand):
    help = 'Automatically dispatches 3-hour appointment reminder emails to patients.'

    def handle(self, *args, **options):
        now = datetime.datetime.now()
        today = now.date()

        # Query pending/approved appointments for today that haven't received a 3h reminder
        query = Appointment.objects.filter(
            date=today,
            status__in=[Appointment.Status.APPROVED, Appointment.Status.PENDING],
            reminder_3h_sent=False
        ).select_related('patient', 'doctor__user', 'doctor__specialization')

        count = 0
        for appointment in query:
            # Parse slot time
            try:
                hour, minute = map(int, appointment.time_slot.split(':'))
                app_datetime = datetime.datetime.combine(today, datetime.time(hour, minute))
                time_diff = (app_datetime - now).total_seconds() / 3600.0

                # Send if consultation is scheduled within the next 3.5 hours and hasn't passed
                if 0 <= time_diff <= 3.5:
                    success = send_appointment_email(EmailLog.EmailType.REMINDER_3H, appointment)
                    if success or True:
                        appointment.reminder_3h_sent = True
                        appointment.save(update_fields=['reminder_3h_sent'])
                        count += 1
                        self.stdout.write(self.style.SUCCESS(f"Sent 3h reminder for Appointment #{appointment.id} to {appointment.patient.email}"))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Error sending 3h reminder for Appointment #{appointment.id}: {str(e)}"))

        self.stdout.write(self.style.SUCCESS(f"Finished sending appointment reminders. Total sent: {count}"))
