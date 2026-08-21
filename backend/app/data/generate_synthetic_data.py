"""
Synthetic data generator for Recovery OS.

Generates:
- 3 merchants (one per persona)
- 1200 payment failures distributed across personas with realistic,
  persona-correlated patterns using real Razorpay error/reason codes.

Run from backend/ with:
    python -m app.data.generate_synthetic_data
"""

import random
import sys
import os
from datetime import datetime, timedelta

sys.path.append(os.getcwd())

from app.database import SessionLocal, engine, Base
from app.models.models import Merchant, Failure, MerchantPersona, FailureClass

random.seed(42)  
ERROR_CODE_MAP = {
    FailureClass.insufficient_funds: [
        ("BAD_REQUEST_ERROR", "insufficient_funds"),
        ("GATEWAY_ERROR", "insufficient_balance_in_account"),
    ],
    FailureClass.expired_card: [
        ("BAD_REQUEST_ERROR", "card_expired"),
        ("GATEWAY_ERROR", "expired_card"),
    ],
    FailureClass.bank_timeout: [
        ("GATEWAY_ERROR", "gateway_timeout"),
        ("SERVER_ERROR", "issuer_timeout"),
        ("GATEWAY_ERROR", "bank_server_down"),
    ],
    FailureClass.risk_decline: [
        ("BAD_REQUEST_ERROR", "payment_declined_by_risk_engine"),
        ("GATEWAY_ERROR", "fraud_suspected"),
        ("BAD_REQUEST_ERROR", "issuer_declined_transaction"),
    ],
    FailureClass.mandate_failure: [
        ("BAD_REQUEST_ERROR", "mandate_not_active"),
        ("GATEWAY_ERROR", "emandate_registration_failed"),
        ("BAD_REQUEST_ERROR", "mandate_amount_exceeded"),
    ],
}

AMBIGUOUS_REASONS = [
    ("GATEWAY_ERROR", "payment_failed"),
    ("SERVER_ERROR", "unknown_error"),
    ("GATEWAY_ERROR", "transaction_declined"),
    ("BAD_REQUEST_ERROR", "authentication_failed"),
]


AMBIGUOUS_REASON_RATE = 0.18

PAYMENT_METHODS_BY_CLASS = {
    FailureClass.insufficient_funds: ["upi", "card", "netbanking"],
    FailureClass.expired_card: ["card"],
    FailureClass.bank_timeout: ["netbanking", "upi"],
    FailureClass.risk_decline: ["card", "upi"],
    FailureClass.mandate_failure: ["emandate"],
}

PERSONA_CONFIG = {
    MerchantPersona.aggressive_d2c: {
        "name": "UrbanCart D2C",
        "n_failures": 550,
        "class_weights": {
            FailureClass.insufficient_funds: 0.40,
            FailureClass.expired_card: 0.20,
            FailureClass.risk_decline: 0.20,
            FailureClass.bank_timeout: 0.15,
            FailureClass.mandate_failure: 0.05,
        },
        "amount_range": (299, 4500),       # small-ticket D2C orders
        "attempt_count_range": (1, 4),
    },
    MerchantPersona.relationship_b2b: {
        "name": "LedgerFlow B2B SaaS",
        "n_failures": 350,
        "class_weights": {
            FailureClass.mandate_failure: 0.35,
            FailureClass.bank_timeout: 0.30,
            FailureClass.insufficient_funds: 0.15,
            FailureClass.risk_decline: 0.10,
            FailureClass.expired_card: 0.10,
        },
        "amount_range": (8000, 150000),    # large B2B invoices/subscriptions
        "attempt_count_range": (1, 2),     # fewer retries, more relationship handling
    },
    MerchantPersona.neutral_midmarket: {
        "name": "Kirana Konnect Marketplace",
        "n_failures": 300,
        "class_weights": {
            FailureClass.insufficient_funds: 0.25,
            FailureClass.expired_card: 0.20,
            FailureClass.bank_timeout: 0.20,
            FailureClass.risk_decline: 0.20,
            FailureClass.mandate_failure: 0.15,
        },
        "amount_range": (500, 25000),
        "attempt_count_range": (1, 3),
    },
}


def weighted_choice(weights: dict):
    classes = list(weights.keys())
    probs = list(weights.values())
    return random.choices(classes, weights=probs, k=1)[0]


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
        MerchantPersona.aggressive_d2c: "cust_d2c",
        MerchantPersona.relationship_b2b: "cust_b2b",
        MerchantPersona.neutral_midmarket: "cust_mm",
    }[persona]
    
    pool_size = max(10, idx // 3)
    return f"{prefix}_{random.randint(1, pool_size):05d}"


def create_merchants(db):
    merchants = {}
    for persona, cfg in PERSONA_CONFIG.items():
        merchant = Merchant(
            name=cfg["name"],
            persona=persona,
            stopping_aggressiveness={
                MerchantPersona.aggressive_d2c: 0.8,
                MerchantPersona.relationship_b2b: 0.25,
                MerchantPersona.neutral_midmarket: 0.5,
            }[persona],
        )
        db.add(merchant)
        merchants[persona] = merchant
    db.commit()
    for m in merchants.values():
        db.refresh(m)
    return merchants


def generate_failures_for_merchant(db, merchant: Merchant, persona: MerchantPersona, cfg: dict):
    failures = []
    for i in range(cfg["n_failures"]):
        failure_class = weighted_choice(cfg["class_weights"])

        if random.random() < AMBIGUOUS_REASON_RATE:
            code, reason = random.choice(AMBIGUOUS_REASONS)
        else:
            code, reason = random.choice(ERROR_CODE_MAP[failure_class])

        payment_method = random.choice(PAYMENT_METHODS_BY_CLASS[failure_class])
        amount = round(random.uniform(*cfg["amount_range"]), 2)
        attempt_count = random.randint(*cfg["attempt_count_range"])

        failure = Failure(
            merchant_id=merchant.id,
            amount=amount,
            currency="INR",
            razorpay_error_code=code,
            razorpay_error_reason=reason,
            payment_method=payment_method,
            customer_id=generate_customer_id(persona, i),
            attempt_count=attempt_count,
            failure_class=failure_class,  # ground truth label for classifier training
            created_at=random_datetime_within_days(60),
        )
        failures.append(failure)

    db.add_all(failures)
    db.commit()
    return failures


def main():
    print("Creating tables if not exist...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        print("Seeding merchants...")
        merchants = create_merchants(db)
        for persona, m in merchants.items():
            print(f"  - {m.name} ({persona.value}) -> id={m.id}")

        total = 0
        for persona, cfg in PERSONA_CONFIG.items():
            print(f"Generating {cfg['n_failures']} failures for {cfg['name']}...")
            failures = generate_failures_for_merchant(db, merchants[persona], persona, cfg)
            total += len(failures)

        print(f"\nDone. Total failures generated: {total}")

        print("\nClass distribution per persona:")
        for persona, cfg in PERSONA_CONFIG.items():
            merchant = merchants[persona]
            rows = db.query(Failure).filter(Failure.merchant_id == merchant.id).all()
            counts = {}
            for r in rows:
                counts[r.failure_class.value] = counts.get(r.failure_class.value, 0) + 1
            print(f"  {merchant.name}: {counts}")

    finally:
        db.close()


if __name__ == "__main__":
    main()