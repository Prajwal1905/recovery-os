
import random
import sys
import os
from datetime import datetime, timedelta

sys.path.append(os.getcwd())

from app.database import SessionLocal
from app.models.models import Merchant, Failure, MerchantPersona, FailureClass

random.seed(99)

ABANDONMENT_REASONS = [
    ("USER_CANCELLED", "checkout_abandoned_by_user"),
    ("SESSION_TIMEOUT", "checkout_session_expired"),
    ("USER_CANCELLED", "payment_page_exited"),
    ("SESSION_TIMEOUT", "otp_entry_abandoned"),
]

PAYMENT_METHODS = ["upi", "card", "netbanking"]

ABANDONMENT_CONFIG = {
    MerchantPersona.aggressive_d2c: {"n_failures": 80, "amount_range": (299, 4500)},
    MerchantPersona.relationship_b2b: {"n_failures": 40, "amount_range": (8000, 150000)},
    MerchantPersona.neutral_midmarket: {"n_failures": 60, "amount_range": (500, 25000)},
}


def random_datetime_within_days(days_back: int) -> datetime:
    now = datetime.utcnow()
    delta = timedelta(
        days=random.randint(0, days_back),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
    )
    return now - delta


def generate_customer_id(persona: MerchantPersona, idx: int) -> str:
    prefix = {
        MerchantPersona.aggressive_d2c: "cust_d2c_abandon",
        MerchantPersona.relationship_b2b: "cust_b2b_abandon",
        MerchantPersona.neutral_midmarket: "cust_mm_abandon",
    }[persona]
    return f"{prefix}_{random.randint(1, 200):05d}"


def main():
    db = SessionLocal()
    try:
        merchants = {m.persona: m for m in db.query(Merchant).all()}

        total = 0
        for persona, cfg in ABANDONMENT_CONFIG.items():
            merchant = merchants.get(persona)
            if not merchant:
                print(f"Skipping {persona.value} - merchant not found")
                continue

            failures = []
            for i in range(cfg["n_failures"]):
                code, reason = random.choice(ABANDONMENT_REASONS)
                amount = round(random.uniform(*cfg["amount_range"]), 2)

                failure = Failure(
                    merchant_id=merchant.id,
                    amount=amount,
                    currency="INR",
                    razorpay_error_code=code,
                    razorpay_error_reason=reason,
                    payment_method=random.choice(PAYMENT_METHODS),
                    customer_id=generate_customer_id(persona, i),
                    attempt_count=1,
                    failure_class=FailureClass.checkout_abandonment,
                    created_at=random_datetime_within_days(30),
                )
                failures.append(failure)

            db.add_all(failures)
            db.commit()
            total += len(failures)
            print(f"Added {len(failures)} checkout_abandonment records for {merchant.name}")

        print(f"\nDone. Total checkout_abandonment failures added: {total}")

    finally:
        db.close()


if __name__ == "__main__":
    main()