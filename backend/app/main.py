
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
from app.models.models import Failure, Merchant, AuditLog, ActionTaken, FailureStatus, BatchRunHistory
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
    chase_capacity: Optional[int] = None

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

@app.get("/merchants/{merchant_id}/learning-curve")
def get_learning_curve(merchant_id: str, db: Session = Depends(get_db)):
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")
 
    history = (
        db.query(BatchRunHistory)
        .filter(BatchRunHistory.merchant_id == merchant_id)
        .order_by(BatchRunHistory.created_at)
        .all()
    )
 
    if not history:
        return {
            "merchant_id": merchant_id,
            "merchant_name": merchant.name,
            "total_batches": 0,
            "message": "No batch history yet - run some batches first.",
        }
 
   
    seen_rewards = {}  
    timeline = []
    cumulative_regret = 0.0
 
    for i, h in enumerate(history):
        
        if seen_rewards:
            best_known_arm = max(seen_rewards.keys(), key=lambda a: sum(seen_rewards[a]) / len(seen_rewards[a]))
            best_known_avg = sum(seen_rewards[best_known_arm]) / len(seen_rewards[best_known_arm])
        else:
            best_known_arm = None
            best_known_avg = h.reward  
 
        regret_this_batch = max(0.0, best_known_avg - h.reward) if best_known_arm is not None else 0.0
        cumulative_regret += regret_this_batch
 
        timeline.append({
            "batch_number": i + 1,
            "timestamp": h.created_at.isoformat(),
            "aggressiveness_used": h.aggressiveness_used,
            "reward": h.reward,
            "best_known_arm_at_the_time": best_known_arm,
            "regret_this_batch": round(regret_this_batch, 4),
            "cumulative_regret": round(cumulative_regret, 4),
            "total_batch_value": h.total_batch_value,
            "total_simulated_recovered": h.total_simulated_recovered,
            "chased_count": h.chased_count,
            "stopped_count": h.stopped_count,
        })
 
        
        seen_rewards.setdefault(h.aggressiveness_used, []).append(h.reward)
 
    midpoint = len(timeline) // 2
    if midpoint > 0:
        first_half_regret_rate = timeline[midpoint - 1]["cumulative_regret"] / midpoint
        second_half_batches = len(timeline) - midpoint
        second_half_regret_added = timeline[-1]["cumulative_regret"] - timeline[midpoint - 1]["cumulative_regret"]
        second_half_regret_rate = second_half_regret_added / second_half_batches if second_half_batches > 0 else 0
    else:
        first_half_regret_rate = None
        second_half_regret_rate = None

    arm_stats = {}
    for h in history:
        arm_stats.setdefault(h.aggressiveness_used, []).append(h.reward)
 
    arm_summary = [
        {
            "aggressiveness": arm,
            "times_used": len(rewards),
            "avg_reward": round(sum(rewards) / len(rewards), 4),
        }
        for arm, rewards in sorted(arm_stats.items())
    ]
 
    return {
        "merchant_id": merchant_id,
        "merchant_name": merchant.name,
        "total_batches": len(history),
        "timeline": timeline,
        "learning_evidence": {
            "cumulative_regret_final": round(cumulative_regret, 4),
            "regret_rate_first_half": round(first_half_regret_rate, 4) if first_half_regret_rate is not None else None,
            "regret_rate_second_half": round(second_half_regret_rate, 4) if second_half_regret_rate is not None else None,
            "is_learning": (
                second_half_regret_rate < first_half_regret_rate
                if first_half_regret_rate is not None and second_half_regret_rate is not None
                else None
            ),
            "explanation": (
                "Regret is the gap between the reward we got and the reward the best-known "
                "arm at that time would have given. A DECREASING regret rate (second half "
                "lower than first half) is honest evidence the system is learning and "
                "increasingly avoiding costly exploration mistakes - even if raw average "
                "reward per batch still varies due to intentional ongoing exploration."
            ),
        },
        "arm_summary": arm_summary,
        "current_best_aggressiveness": max(arm_summary, key=lambda a: a["avg_reward"])["aggressiveness"]
        if arm_summary else None,
    }