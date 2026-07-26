from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from doctors.models import DoctorProfile
from appointments.models import Specialization

User = get_user_model()

class DoctorProfilePhotoTests(TestCase):
    def setUp(self):
        self.spec = Specialization.objects.create(name="Dermatology")
        self.doctor_user = User.objects.create_user(
            username='dr_photo_test',
            email='dr_photo@example.com',
            password='Password123!',
            role=User.Role.DOCTOR,
            phone='9876543219'
        )
        self.doctor = DoctorProfile.objects.create(
            user=self.doctor_user,
            specialization=self.spec,
            license_number='LIC-PHOTO-99',
            qualification='MD Dermatology',
            hospital_name='Skin Clinic',
            consultation_fee=75.00,
            is_approved=True
        )
        self.client = Client()
        self.client.login(username='dr_photo_test', password='Password123!')

    def test_upload_profile_photo_success(self):
        # 1x1 GIF image bytes
        image_content = b'GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'
        uploaded_file = SimpleUploadedFile("avatar.jpg", image_content, content_type="image/jpeg")

        response = self.client.post('/doctors/profile/edit/', {
            'qualification': 'MD Dermatology & Cosmetology',
            'experience_years': 8,
            'hospital_name': 'Metro Skin Hospital',
            'consultation_fee': 100.00,
            'bio': 'Specialist in clinical dermatology',
            'profile_photo': uploaded_file
        })

        self.assertEqual(response.status_code, 302)
        self.doctor.refresh_from_db()
        self.assertTrue(bool(self.doctor.profile_photo))
        self.assertIn("avatar", self.doctor.profile_photo.name)

        # GET profile page - verify photo URL is rendered
        get_res = self.client.get('/doctors/profile/edit/')
        self.assertEqual(get_res.status_code, 200)
        self.assertContains(get_res, self.doctor.profile_photo.url)

    def test_invalid_file_extension_rejected(self):
        invalid_file = SimpleUploadedFile("document.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        response = self.client.post('/doctors/profile/edit/', {
            'qualification': 'MD Dermatology',
            'experience_years': 5,
            'hospital_name': 'Clinic',
            'consultation_fee': 50.00,
            'profile_photo': invalid_file
        })
        self.doctor.refresh_from_db()
        self.assertFalse(bool(self.doctor.profile_photo))
