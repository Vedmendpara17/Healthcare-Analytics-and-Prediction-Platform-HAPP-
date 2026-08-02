from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
import datetime

from appointments.models import Specialization, Appointment
from doctors.models import DoctorProfile, DoctorAvailability
from patients.models import PatientProfile
from predictions.models import RiskAssessment
from predictions.services import RiskPredictor
from core.models import Notification

User = get_user_model()

class Command(BaseCommand):
    help = "Seeds initial database with medical specializations, admin, demo pre-approved doctors, demo patients, and sample assessments."

    def handle(self, *args, **options):
        self.stdout.write("Starting Healthcare Analytics System database seeding...")

        with transaction.atomic():
            # 1. Specializations
            specs = [
                {'name': 'Cardiology', 'description': 'Heart, vascular system, and blood pressure health', 'icon': 'bi-heart-pulse-fill'},
                {'name': 'Endocrinology', 'description': 'Diabetes, hormone disorders, and metabolic health', 'icon': 'bi-activity'},
                {'name': 'General Medicine', 'description': 'Comprehensive primary care and systemic illness prevention', 'icon': 'bi-hospital-fill'},
                {'name': 'Neurology', 'description': 'Brain, nerve function, and neurological diagnostics', 'icon': 'bi-cpu-fill'},
                {'name': 'Pediatrics', 'description': 'Childhood development and pediatric healthcare', 'icon': 'bi-person-hearts'},
                {'name': 'Orthopedics', 'description': 'Bone, joint, and musculoskeletal system care', 'icon': 'bi-body-text'},
            ]

            spec_objects = {}
            for s in specs:
                obj, _ = Specialization.objects.get_or_create(
                    name=s['name'],
                    defaults={'description': s['description'], 'icon': s['icon']}
                )
                spec_objects[s['name']] = obj

            # 2. Admin User
            admin_user, created = User.objects.get_or_create(
                username='admin',
                defaults={
                    'email': 'admin@healthcare.org',
                    'first_name': 'System',
                    'last_name': 'Administrator',
                    'role': User.Role.ADMIN,
                    'is_staff': True,
                    'is_superuser': True,
                    'phone': '9999999999'
                }
            )
            if created:
                admin_user.set_password('Admin@1234')
                admin_user.save()
                self.stdout.write("Created Admin user: admin / Admin@1234")

            # 3. Demo Pre-Approved Doctors
            doctors_data = [
                {
                    'username': 'dr_jenkins',
                    'email': 'jenkins@hospital.org',
                    'first_name': 'Sunita',
                    'last_name': 'Sharma',
                    'phone': '9876543210',
                    'spec': 'Cardiology',
                    'license': 'MD-CARD-8832',
                    'qualification': 'MD (Cardiology), FACC',
                    'years': 14,
                    'hospital': 'St. Jude Heart Institute',
                    'fee': 120.00,
                    'bio': 'Senior cardiologist specializing in cardiovascular risk assessment and preventative lipid management.'
                },
                {
                    'username': 'dr_chen',
                    'email': 'chen@medcenter.org',
                    'first_name': 'Rajesh',
                    'last_name': 'Patel',
                    'phone': '9876543211',
                    'spec': 'Endocrinology',
                    'license': 'MD-ENDO-5519',
                    'qualification': 'MBBS, MD (Endocrinology)',
                    'years': 10,
                    'hospital': 'Metabolic & Diabetes Center',
                    'fee': 95.00,
                    'bio': 'Endocrinologist focused on glycemic control, metabolic syndrome, and pre-diabetes risk prediction.'
                },
                {
                    'username': 'dr_williams',
                    'email': 'williams@care.org',
                    'first_name': 'Ananya',
                    'last_name': 'Iyer',
                    'phone': '9876543212',
                    'spec': 'General Medicine',
                    'license': 'MD-GEN-1029',
                    'qualification': 'MD (Internal Medicine)',
                    'years': 8,
                    'hospital': 'City Wellness Clinic',
                    'fee': 60.00,
                    'bio': 'Primary care physician providing holistic health screening and lifestyle intervention counseling.'
                },
                {
                    'username': 'dr_vance',
                    'email': 'vance@neuroinst.org',
                    'first_name': 'Vikram',
                    'last_name': 'Malhotra',
                    'phone': '9876543213',
                    'spec': 'Neurology',
                    'license': 'MD-NEURO-7741',
                    'qualification': 'MD (Neurology), DM',
                    'years': 12,
                    'hospital': 'City Neurological Institute',
                    'fee': 130.00,
                    'bio': 'Neurologist specializing in brain, nerve function, stroke prevention, and neurological diagnostics.'
                },
                {
                    'username': 'dr_foster',
                    'email': 'foster@apexortho.org',
                    'first_name': 'Meera',
                    'last_name': 'Deshmukh',
                    'phone': '9876543214',
                    'spec': 'Orthopedics',
                    'license': 'MD-ORTHO-4432',
                    'qualification': 'MS (Orthopedics), FRCS',
                    'years': 11,
                    'hospital': 'Apex Bone & Joint Hospital',
                    'fee': 110.00,
                    'bio': 'Orthopedic surgeon specializing in bone, joint, spinal health, and musculoskeletal system care.'
                },
                {
                    'username': 'dr_miller',
                    'email': 'miller@sunriseped.org',
                    'first_name': 'Suresh',
                    'last_name': 'Kulkarni',
                    'phone': '9876543215',
                    'spec': 'Pediatrics',
                    'license': 'MD-PEDI-9910',
                    'qualification': 'MD (Pediatrics), DCH',
                    'years': 9,
                    'hospital': 'Sunrise Children\'s Hospital',
                    'fee': 85.00,
                    'bio': 'Pediatrician specializing in childhood development, immunization, and pediatric healthcare.'
                }
            ]

            doc_profiles = []
            for d in doctors_data:
                u, u_created = User.objects.get_or_create(
                    username=d['username'],
                    defaults={
                        'email': d['email'],
                        'first_name': d['first_name'],
                        'last_name': d['last_name'],
                        'role': User.Role.DOCTOR,
                        'phone': d['phone']
                    }
                )
                if u_created:
                    u.set_password('Doctor@1234')
                    u.save()

                doc_prof, _ = DoctorProfile.objects.get_or_create(
                    user=u,
                    defaults={
                        'specialization': spec_objects[d['spec']],
                        'license_number': d['license'],
                        'qualification': d['qualification'],
                        'experience_years': d['years'],
                        'hospital_name': d['hospital'],
                        'consultation_fee': d['fee'],
                        'bio': d['bio'],
                        'is_approved': True  # Pre-approved demo doctor
                    }
                )
                doc_profiles.append(doc_prof)
                self.stdout.write(f"Created Doctor: {d['username']} / Doctor@1234 (Pre-approved)")

            # 4. Demo Patients
            patients_data = [
                {
                    'username': 'john_doe',
                    'email': 'john.doe@gmail.com',
                    'first_name': 'Aarav',
                    'last_name': 'Sharma',
                    'phone': '9123456789',
                    'dob': datetime.date(1978, 5, 14),
                    'gender': 'Male',
                    'blood': 'O+',
                    'height': 175.0,
                    'weight': 88.0, # BMI ~ 28.7 (Overweight)
                    'chronic': 'Hypertension'
                },
                {
                    'username': 'emily_smith',
                    'email': 'emily.smith@yahoo.com',
                    'first_name': 'Diya',
                    'last_name': 'Gupta',
                    'phone': '9123456790',
                    'dob': datetime.date(1990, 11, 22),
                    'gender': 'Female',
                    'blood': 'A+',
                    'height': 162.0,
                    'weight': 58.0, # BMI ~ 22.1 (Normal)
                    'chronic': 'None'
                },
                {
                    'username': 'michael_brown',
                    'email': 'michael.b@outlook.com',
                    'first_name': 'Rohan',
                    'last_name': 'Singh',
                    'phone': '9123456791',
                    'dob': datetime.date(1964, 3, 30),
                    'gender': 'Male',
                    'blood': 'B+',
                    'height': 170.0,
                    'weight': 95.0, # BMI ~ 32.9 (Obese)
                    'chronic': 'Type-2 Diabetes, High Cholesterol'
                }
            ]

            patient_profiles = []
            for p in patients_data:
                u, u_created = User.objects.get_or_create(
                    username=p['username'],
                    defaults={
                        'email': p['email'],
                        'first_name': p['first_name'],
                        'last_name': p['last_name'],
                        'role': User.Role.PATIENT,
                        'phone': p['phone']
                    }
                )
                if u_created:
                    u.set_password('Patient@1234')
                    u.save()

                pat_prof, _ = PatientProfile.objects.get_or_create(
                    user=u,
                    defaults={
                        'dob': p['dob'],
                        'gender': p['gender'],
                        'blood_group': p['blood'],
                        'height_cm': p['height'],
                        'weight_kg': p['weight'],
                        'chronic_conditions': p['chronic']
                    }
                )
                patient_profiles.append(pat_prof)
                self.stdout.write(f"Created Patient: {p['username']} / Patient@1234")

            # 5. Demo Appointments
            today = datetime.date.today()
            app1, _ = Appointment.objects.get_or_create(
                patient=patient_profiles[0].user,
                doctor=doc_profiles[0],
                date=today + datetime.timedelta(days=1),
                time_slot='10:00',
                defaults={'reason': 'Routine blood pressure review & cardiovascular evaluation', 'status': Appointment.Status.APPROVED}
            )

            app2, _ = Appointment.objects.get_or_create(
                patient=patient_profiles[2].user,
                doctor=doc_profiles[1],
                date=today + datetime.timedelta(days=2),
                time_slot='14:30',
                defaults={'reason': 'Fasting blood glucose assessment and diabetes screening', 'status': Appointment.Status.PENDING}
            )

            # 6. Demo Risk Assessments
            eval1 = RiskPredictor.predict({
                'age': patient_profiles[0].age,
                'gender': 'Male',
                'systolic_bp': 148,
                'diastolic_bp': 92,
                'fasting_sugar': 115,
                'postprandial_sugar': 155,
                'total_cholesterol': 230,
                'hdl_cholesterol': 42,
                'ldl_cholesterol': 150,
                'height_cm': 175,
                'weight_kg': 88,
                'smoking_status': 'former',
                'alcohol_consumption': 'occasional',
                'physical_activity': 'sedentary',
                'family_history': ['hypertension', 'heart disease'],
                'symptoms': ['fatigue', 'shortness of breath']
            })

            RiskAssessment.objects.create(
                patient=patient_profiles[0],
                doctor=doc_profiles[0],
                age=patient_profiles[0].age,
                gender='Male',
                systolic_bp=148,
                diastolic_bp=92,
                fasting_sugar=115,
                postprandial_sugar=155,
                total_cholesterol=230,
                hdl_cholesterol=42,
                ldl_cholesterol=150,
                height_cm=175,
                weight_kg=88,
                bmi=eval1['bmi'],
                smoking_status='former',
                alcohol_consumption='occasional',
                physical_activity='sedentary',
                family_history_text='hypertension, heart disease',
                symptoms_text='fatigue, shortness of breath',
                computed_score=eval1['overall_score'],
                computed_level=eval1['overall_level'],
                heart_score=eval1['heart_risk_score'],
                diabetes_score=eval1['diabetes_risk_score'],
                hypertension_score=eval1['hypertension_risk_score'],
                doctor_notes='Patient exhibits Stage 1 Hypertension and elevated LDL. Initiated daily blood pressure log.'
            )

        self.stdout.write(self.style.SUCCESS("Database seeding completed successfully!"))
