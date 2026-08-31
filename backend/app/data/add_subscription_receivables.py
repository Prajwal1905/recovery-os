
import random
import sys
import os
from datetime import datetime, timedelta

sys.path.append(os.getcwd())

from app.database import SessionLocal
from app.models.models import Merchant, Failure, MerchantPersona, FailureClass

random.seed(21)

SUBSCRIPTION_REASONS = [
    ("SUBSCRIPTION_ERROR", "recurring_charge_declined"),
    ("MANDATE_ERROR", "emandate_debit_failed"),
    ("SUBSCRIPTION_ERROR", "card_on_file_expired"),
]

RECEIVABLE_REASONS = [
    ("INVOICE_ERROR", "invoice_overdue"),
    ("INVOICE_ERROR", "payment_terms_exceeded"),
    ("INVOICE_ERROR", "no_response_to_invoice"),
]

PAYMENT_METHODS = ["emandate", "netbanking", "card"]

CONFIG = {
    MerchantPersona.relationship_b2b: {
        "subscription_n": 45,
        "receivable_n": 50,
        "amount_range": (5000, 120000),
    },
    MerchantPersona.neutral_midmarket: {
        "subscription_n": 25,
        "receivable_n": 20,
        "amount_range": (2000, 40000),
    },
}


def random_datetime_within_days(days_back: int) -> datetime:
    now = datetime.utcnow()
    delta = timedelta(
        days=random.randint(0, days_back),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
    )
    return now - delta


def generate_customer_id(persona: MerchantPersona, tag: str, idx: int) -> str:
    prefix = {
        MerchantPersona.relationship_b2b: f"cust_b2b_{tag}",
        MerchantPersona.neutral_midmarket: f"cust_mm_{tag}",
    }[persona]
    return f"{prefix}_{random.randint(1, 150):05d}"


def build_failures(merchant, persona, cfg, failure_class, reasons, tag, n):
    failures = []
    for i in range(n):
        code, reason = random.choice(reasons)
        amount = round(random.uniform(*cfg["amount_range"]), 2)
        # receivables/subscriptions tend to be older-dated - they linger
        attempt_count = random.randint(1, 3)

        failure = Failure(
            merchant_id=merchant.id,
            amount=amount,
            currency="INR",
            razorpay_error_code=code,
            razorpay_error_reason=reason,
            payment_method=random.choice(PAYMENT_METHODS),
            customer_id=generate_customer_id(persona, tag, i),
            attempt_count=attempt_count,
            failure_class=failure_class,
            created_at=random_datetime_within_days(45),
        )
        failures.append(failure)
    return failures


def main():
    db = SessionLocal()
    try:
        merchants = {m.persona: m for m in db.query(Merchant).all()}

        total = 0
        for persona, cfg in CONFIG.items():
            merchant = merchants.get(persona)
            if not merchant:
                print(f"Skipping {persona.value} - merchant not found")
                continue

            sub_failures = build_failures(
                merchant, persona, cfg, FailureClass.subscription_failure,
                SUBSCRIPTION_REASONS, "sub", cfg["subscription_n"]
            )
            rec_failures = build_failures(
                merchant, persona, cfg, FailureClass.overdue_receivable,
                RECEIVABLE_REASONS, "rec", cfg["receivable_n"]
            )

            db.add_all(sub_failures + rec_failures)
            db.commit()

            total += len(sub_failures) + len(rec_failures)
            print(f"Added {len(sub_failures)} subscription_failure + {len(rec_failures)} overdue_receivable for {merchant.name}")

        print(f"\nDone. Total new failures added: {total}")

    finally:
        db.close()


if __name__ == "__main__":
    main()