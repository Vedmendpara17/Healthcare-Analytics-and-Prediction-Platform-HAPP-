from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

User = get_user_model()

class AccountLockoutPolicyTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='patient_lockout',
            email='patient_lock@test.com',
            password='SecurePassword123!',
            role='PATIENT',
            first_name='Rahul',
            last_name='Sharma'
        )

    def test_failed_attempts_warnings_and_5th_attempt_lockout(self):
        # Attempt 1 -> 4 attempts remaining
        resp1 = self.client.post('/auth/login/', {'username': 'patient_lock@test.com', 'password': 'WrongPassword1'}, follow=True)
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 1)
        self.assertContains(resp1, "4 login attempts remaining")

        # Attempt 2 -> 3 attempts remaining
        resp2 = self.client.post('/auth/login/', {'username': 'patient_lock@test.com', 'password': 'WrongPassword2'}, follow=True)
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 2)
        self.assertContains(resp2, "3 login attempts remaining")

        # Attempt 3 -> 2 attempts remaining
        resp3 = self.client.post('/auth/login/', {'username': 'patient_lock@test.com', 'password': 'WrongPassword3'}, follow=True)
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 3)
        self.assertContains(resp3, "2 login attempts remaining")

        # Attempt 4 -> Account will be locked on the next failed attempt
        resp4 = self.client.post('/auth/login/', {'username': 'patient_lock@test.com', 'password': 'WrongPassword4'}, follow=True)
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 4)
        self.assertContains(resp4, "Account will be locked on the next failed attempt")

        # Attempt 5 -> Lockout for 15 minutes
        resp5 = self.client.post('/auth/login/', {'username': 'patient_lock@test.com', 'password': 'WrongPassword5'}, follow=True)
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 5)
        self.assertTrue(self.user.account_locked)
        self.assertTrue(self.user.is_account_locked())
        self.assertContains(resp5, "temporarily locked due to multiple failed login attempts")

        # Attempt login with correct password while locked -> Denied
        resp_correct = self.client.post('/auth/login/', {'username': 'patient_lock@test.com', 'password': 'SecurePassword123!'}, follow=True)
        self.assertContains(resp_correct, "currently locked")

    def test_automatic_unlock_after_15_minutes(self):
        # Trigger 5 failed attempts
        for i in range(5):
            self.client.post('/auth/login/', {'username': 'patient_lock@test.com', 'password': f'WrongPass{i}'})

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_account_locked())

        # Fast forward time by 15 minutes
        self.user.account_locked_until = timezone.now() - timedelta(seconds=1)
        self.user.lock_until = self.user.account_locked_until
        self.user.save()

        # Account auto unlocks
        self.assertFalse(self.user.is_account_locked())

    def test_password_reset_unlocks_account(self):
        # Trigger lock
        for i in range(5):
            self.client.post('/auth/login/', {'username': 'patient_lock@test.com', 'password': f'WrongPass{i}'})

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_account_locked())

        # Unlock via reset_password
        self.user.unlock_account()
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 0)
        self.assertFalse(self.user.account_locked)
        self.assertFalse(self.user.is_account_locked())
