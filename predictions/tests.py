from django.test import TestCase
from predictions.services import RiskPredictor

class RiskPredictorEngineTests(TestCase):
    def test_healthy_vitals_yield_low_risk(self):
        healthy_data = {
            'age': 25,
            'gender': 'Female',
            'systolic_bp': 115,
            'diastolic_bp': 75,
            'fasting_sugar': 85,
            'postprandial_sugar': 110,
            'total_cholesterol': 170,
            'hdl_cholesterol': 60,
            'ldl_cholesterol': 90,
            'height_cm': 165,
            'weight_kg': 58,
            'smoking_status': 'never',
            'alcohol_consumption': 'none',
            'physical_activity': 'active',
            'family_history': [],
            'symptoms': []
        }
        res = RiskPredictor.predict(healthy_data)
        self.assertEqual(res['overall_level'], 'LOW')
        self.assertLess(res['overall_score'], 35)

    def test_severe_vitals_yield_high_risk(self):
        high_risk_data = {
            'age': 62,
            'gender': 'Male',
            'systolic_bp': 165,
            'diastolic_bp': 105,
            'fasting_sugar': 145,
            'postprandial_sugar': 220,
            'total_cholesterol': 260,
            'hdl_cholesterol': 35,
            'ldl_cholesterol': 175,
            'height_cm': 170,
            'weight_kg': 95,
            'smoking_status': 'current',
            'alcohol_consumption': 'regular',
            'physical_activity': 'sedentary',
            'family_history': ['diabetes', 'heart disease'],
            'symptoms': ['chest pain', 'shortness of breath']
        }
        res = RiskPredictor.predict(high_risk_data)
        self.assertEqual(res['overall_level'], 'HIGH')
        self.assertGreaterEqual(res['overall_score'], 65)

    def test_bmi_calculation(self):
        data = {
            'height_cm': 180,
            'weight_kg': 81
        }
        res = RiskPredictor.predict(data)
        self.assertEqual(res['bmi'], 25.0)
