import sys
import os
import pickle

sys.path.append(os.getcwd())

import pandas as pd

from app.models.models import Failure, Merchant, FailureClass

MODEL_DIR = os.path.join(os.getcwd(), "app", "ml", "artifacts")

CATEGORICAL_FEATURES = ["razorpay_error_code", "razorpay_error_reason", "payment_method", "persona"]
NUMERIC_FEATURES = ["amount", "attempt_count"]

_pipeline = None
_label_encoder = None


def _load_artifacts():
    global _pipeline, _label_encoder
    if _pipeline is None:
        with open(os.path.join(MODEL_DIR, "classifier_pipeline.pkl"), "rb") as f:
            _pipeline = pickle.load(f)
        with open(os.path.join(MODEL_DIR, "label_encoder.pkl"), "rb") as f:
            _label_encoder = pickle.load(f)
    return _pipeline, _label_encoder


def classify_failure(failure: Failure, merchant: Merchant) -> tuple:
    
    pipeline, label_encoder = _load_artifacts()

    row = pd.DataFrame([{
        "razorpay_error_code": failure.razorpay_error_code,
        "razorpay_error_reason": failure.razorpay_error_reason,
        "payment_method": failure.payment_method,
        "persona": merchant.persona.value,
        "amount": failure.amount,
        "attempt_count": failure.attempt_count,
    }])

    proba = pipeline.predict_proba(row)[0]
    pred_idx = proba.argmax()
    pred_label = label_encoder.inverse_transform([pred_idx])[0]
    confidence = float(proba[pred_idx])

    return FailureClass(pred_label), confidence


def _demo():
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        failure = db.query(Failure).filter(Failure.failure_class.is_(None)).first()
        if not failure:
            print("No unclassified failures found.")
            return
        merchant = db.query(Merchant).filter(Merchant.id == failure.merchant_id).first()

        failure_class, confidence = classify_failure(failure, merchant)
        print(f"Failure {failure.id}: predicted={failure_class.value} confidence={confidence:.3f}")

        failure.failure_class = failure_class
        failure.classifier_confidence = confidence
        db.add(failure)
        db.commit()
        print("Saved to DB.")
    finally:
        db.close()


if __name__ == "__main__":
    _demo()