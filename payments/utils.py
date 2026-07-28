import datetime
import random
import string

def generate_payment_id():
    year = datetime.date.today().year
    random_digits = ''.join(random.choices(string.digits, k=6))
    return f"PAY-{year}-{random_digits}"

def generate_transaction_id():
    year = datetime.date.today().year
    random_digits = ''.join(random.choices(string.digits, k=6))
    return f"TXN-{year}-{random_digits}"

def generate_invoice_number():
    year = datetime.date.today().year
    random_digits = ''.join(random.choices(string.digits, k=6))
    return f"INV-{year}-{random_digits}"

def generate_refund_id():
    year = datetime.date.today().year
    random_digits = ''.join(random.choices(string.digits, k=6))
    return f"RFD-{year}-{random_digits}"
