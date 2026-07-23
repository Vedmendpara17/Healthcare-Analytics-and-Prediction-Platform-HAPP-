class RiskPredictor:
    """
    Transparent rule-based scoring engine for multi-condition risk prediction.
    Designed with a standard `predict(data)` interface so a trained scikit-learn / joblib 
    machine learning model can be seamlessly swapped in later.
    """

    @classmethod
    def predict(cls, data: dict) -> dict:
        age = int(data.get('age', 30))
        gender = str(data.get('gender', 'Male')).strip().title()
        sys_bp = int(data.get('systolic_bp', 120))
        dia_bp = int(data.get('diastolic_bp', 80))
        fasting_sugar = float(data.get('fasting_sugar', 90))
        pp_sugar = float(data.get('postprandial_sugar', 120))
        tot_chol = float(data.get('total_cholesterol', 180))
        hdl = float(data.get('hdl_cholesterol', 50))
        ldl = float(data.get('ldl_cholesterol', 100))
        height_cm = float(data.get('height_cm', 170))
        weight_kg = float(data.get('weight_kg', 70))
        smoking = str(data.get('smoking_status', 'never')).lower()
        alcohol = str(data.get('alcohol_consumption', 'none')).lower()
        activity = str(data.get('physical_activity', 'moderate')).lower()
        
        family_history = data.get('family_history', [])
        if isinstance(family_history, str):
            family_history = [item.strip() for item in family_history.split(',') if item.strip()]

        symptoms = data.get('symptoms', [])
        if isinstance(symptoms, str):
            symptoms = [item.strip() for item in symptoms.split(',') if item.strip()]

        # Calculate BMI
        height_m = height_cm / 100.0 if height_cm > 0 else 1.70
        bmi = round(weight_kg / (height_m * height_m), 1)

        # 1. HYPERTENSION RISK SCORE COMPUTATION (0-100)
        hyp_score = 0
        if sys_bp >= 160 or dia_bp >= 100:
            hyp_score += 55
        elif sys_bp >= 140 or dia_bp >= 90:
            hyp_score += 35
        elif sys_bp >= 130 or dia_bp >= 85:
            hyp_score += 20

        if bmi >= 30:
            hyp_score += 15
        elif bmi >= 25:
            hyp_score += 8

        if 'hypertension' in [f.lower() for f in family_history]:
            hyp_score += 15
        if activity == 'sedentary':
            hyp_score += 10
        if age > 50:
            hyp_score += 10
        hyp_score = min(100, hyp_score)

        # 2. DIABETES RISK SCORE COMPUTATION (0-100)
        diab_score = 0
        if fasting_sugar >= 126 or pp_sugar >= 200:
            diab_score += 50
        elif fasting_sugar >= 100 or pp_sugar >= 140:
            diab_score += 25

        if bmi >= 30:
            diab_score += 20
        elif bmi >= 25:
            diab_score += 10

        if 'diabetes' in [f.lower() for f in family_history]:
            diab_score += 15
        if any(s in [sym.lower() for sym in symptoms] for s in ['frequent urination', 'excessive thirst', 'blurry vision']):
            diab_score += 15
        if age > 45:
            diab_score += 10
        diab_score = min(100, diab_score)

        # 3. CARDIOVASCULAR (HEART) RISK SCORE COMPUTATION (0-100)
        heart_score = 0
        if tot_chol >= 240 or ldl >= 160:
            heart_score += 30
        elif tot_chol >= 200 or ldl >= 130:
            heart_score += 15

        if hdl < 40:
            heart_score += 15

        if sys_bp >= 140 or dia_bp >= 90:
            heart_score += 20

        if smoking == 'current':
            heart_score += 20
        elif smoking == 'former':
            heart_score += 8

        if 'chest pain' in [s.lower() for s in symptoms]:
            heart_score += 25
        if 'shortness of breath' in [s.lower() for s in symptoms]:
            heart_score += 15
        if 'heart_disease' in [f.lower() for f in family_history] or 'heart disease' in [f.lower() for f in family_history]:
            heart_score += 15

        if age > 55:
            heart_score += 10
        heart_score = min(100, heart_score)

        # 4. OVERALL COMPOSITE RISK SCORE (0-100)
        overall_score = round(0.40 * heart_score + 0.35 * diab_score + 0.25 * hyp_score)
        overall_score = min(100, max(0, overall_score))

        # Risk Level Mapping
        if overall_score >= 65:
            level = 'HIGH'
        elif overall_score >= 35:
            level = 'MEDIUM'
        else:
            level = 'LOW'

        # Generate Clinical Action Plan & Precautions
        precautions = []
        if level == 'HIGH':
            precautions.append("Immediate clinical consultation required. Schedule comprehensive diagnostics.")
            if heart_score >= 50:
                precautions.append("Perform Electrocardiogram (ECG) and lipid profile audit immediately.")
            if diab_score >= 50:
                precautions.append("Perform HbA1c test and order endocrine assessment.")
            if sys_bp >= 140:
                precautions.append("Initiate strict blood pressure monitoring and antihypertensive therapy review.")
            precautions.append("Strictly stop smoking and restrict sodium intake to under 2g/day.")
        elif level == 'MEDIUM':
            precautions.append("Moderate risk detected. Recommend lifestyle modification and 3-month follow-up.")
            precautions.append("Engage in 150 minutes of moderate aerobic physical activity per week.")
            precautions.append("Adopt a Mediterranean or DASH dietary plan low in saturated fats and refined sugars.")
            precautions.append("Monitor blood pressure and fasting glucose bi-weekly.")
        else:
            precautions.append("Patient demonstrates a favorable risk profile.")
            precautions.append("Maintain balanced nutrition, regular exercise, and annual health checkups.")

        return {
            'overall_score': overall_score,
            'overall_level': level,
            'bmi': bmi,
            'heart_risk_score': heart_score,
            'diabetes_risk_score': diab_score,
            'hypertension_risk_score': hyp_score,
            'precautions': precautions,
        }
