
import sys
import os
import json

sys.path.append(os.getcwd())

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from app.database import SessionLocal, get_db
from app.models.models import Failure, Merchant, AuditLog, ActionTaken, FailureStatus
from app.services.batch_runner import BatchRunner

app = FastAPI(title="Recovery OS API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class MerchantOut(BaseModel):
    id: str
    name: str
    persona: str
    stopping_aggressiveness: float

    class Config:
        from_attributes = True


class FailureOut(BaseModel):
    id: str
    merchant_id: str
    amount: float
    currency: str
    razorpay_error_code: str
    razorpay_error_reason: str
    payment_method: str
    customer_id: str
    attempt_count: int
    failure_class: Optional[str]
    status: str

    class Config:
        from_attributes = True


class BatchRunRequest(BaseModel):
    merchant_persona: Optional[str] = None
    batch_limit: int = 30
    chase_capacity: int = 15


@app.get("/")
def root():
    return {"status": "ok", "service": "Recovery OS API"}


@app.get("/merchants", response_model=list[MerchantOut])
def list_merchants(db: Session = Depends(get_db)):
    merchants = db.query(Merchant).all()
    return [
        MerchantOut(
            id=str(m.id), name=m.name, persona=m.persona.value,
            stopping_aggressiveness=m.stopping_aggressiveness,
        )
        for m in merchants
    ]


@app.get("/failures", response_model=list[FailureOut])
def list_failures(
    merchant_persona: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, le=1000),
    db: Session = Depends(get_db),
):
    query = db.query(Failure)

    if merchant_persona:
        merchant_ids = [m.id for m in db.query(Merchant).filter(Merchant.persona == merchant_persona).all()]
        query = query.filter(Failure.merchant_id.in_(merchant_ids))

    if status:
        query = query.filter(Failure.status == status)

    failures = query.limit(limit).all()

    return [
        FailureOut(
            id=str(f.id), merchant_id=str(f.merchant_id), amount=f.amount,
            currency=f.currency, razorpay_error_code=f.razorpay_error_code,
            razorpay_error_reason=f.razorpay_error_reason, payment_method=f.payment_method,
            customer_id=f.customer_id, attempt_count=f.attempt_count,
            failure_class=f.failure_class.value if f.failure_class else None,
            status=f.status.value,
        )
        for f in failures
    ]


@app.get("/failures/{failure_id}/audit")
def get_failure_audit(failure_id: str, db: Session = Depends(get_db)):
    failure = db.query(Failure).filter(Failure.id == failure_id).first()
    if not failure:
        raise HTTPException(status_code=404, detail="Failure not found")

    entries = (
        db.query(AuditLog)
        .filter(AuditLog.failure_id == failure_id)
        .order_by(AuditLog.created_at)
        .all()
    )
    actions = (
        db.query(ActionTaken)
        .filter(ActionTaken.failure_id == failure_id)
        .order_by(ActionTaken.executed_at)
        .all()
    )

    return {
        "failure_id": failure_id,
        "current_status": failure.status.value,
        "audit_trail": [
            {"timestamp": e.created_at.isoformat(), "event_type": e.event_type, "payload": e.payload}
            for e in entries
        ],
        "actions_taken": [
            {
                "action_type": a.action_type.value,
                "confidence": a.confidence,
                "explanation": a.explanation,
                "outcome": a.outcome,
                "recovered_amount": a.recovered_amount,
                "executed_at": a.executed_at.isoformat(),
            }
            for a in actions
        ],
    }


@app.post("/batch/run")
def run_batch(req: BatchRunRequest, db: Session = Depends(get_db)):
    merchant_lookup = {m.id: m for m in db.query(Merchant).all()}

    query = db.query(Failure).filter(Failure.failure_class.isnot(None))
    if req.merchant_persona:
        merchant_ids = [m.id for m in merchant_lookup.values() if m.persona.value == req.merchant_persona]
        query = query.filter(Failure.merchant_id.in_(merchant_ids))

    failures = query.limit(req.batch_limit).all()
    if not failures:
        raise HTTPException(status_code=404, detail="No failures found matching the given filters")

    runner = BatchRunner(db)
    output = runner.run_batch(failures, merchant_lookup, chase_capacity=req.chase_capacity)

    return output


@app.get("/metrics/classifier")
def get_classifier_metrics():
    metrics_path = os.path.join(os.getcwd(), "app", "ml", "artifacts", "metrics.json")
    if not os.path.exists(metrics_path):
        raise HTTPException(status_code=404, detail="Classifier metrics not found - run training first")

    with open(metrics_path) as f:
        return json.load(f)