import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Text, Enum
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

import enum

from app.database import Base


class MerchantPersona(str, enum.Enum):
    aggressive_d2c = "aggressive_d2c"
    relationship_b2b = "relationship_b2b"
    neutral_midmarket = "neutral_midmarket"


class FailureClass(str, enum.Enum):
    insufficient_funds = "insufficient_funds"
    expired_card = "expired_card"
    bank_timeout = "bank_timeout"
    risk_decline = "risk_decline"
    mandate_failure = "mandate_failure"
    checkout_abandonment = "checkout_abandonment"

class ActionType(str, enum.Enum):
    retry_now = "retry_now"
    retry_scheduled = "retry_scheduled"
    update_payment_method_flow = "update_payment_method_flow"
    mandate_reauth = "mandate_reauth"
    whatsapp_nudge = "whatsapp_nudge"
    hinglish_voice_call = "hinglish_voice_call"
    escalate_human = "escalate_human"
    stop_chasing = "stop_chasing"


class FailureStatus(str, enum.Enum):
    pending = "pending"
    scored = "scored"
    action_recommended = "action_recommended"
    action_executed = "action_executed"
    recovered = "recovered"
    stopped = "stopped"
    exhausted = "exhausted"


class Merchant(Base):
    __tablename__ = "merchants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    persona = Column(Enum(MerchantPersona), nullable=False)
    # risk appetite / stopping-rule aggressiveness, learned over time (0 = very conservative, 1 = very aggressive)
    stopping_aggressiveness = Column(Float, default=0.5)
    created_at = Column(DateTime, default=datetime.utcnow)

    failures = relationship("Failure", back_populates="merchant")
    api_key_hash = Column(String, nullable=True, unique=True)

class Failure(Base):
    __tablename__ = "failures"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False)

    # raw transaction context
    amount = Column(Float, nullable=False)
    currency = Column(String, default="INR")
    razorpay_error_code = Column(String, nullable=False)
    razorpay_error_reason = Column(String, nullable=False)
    payment_method = Column(String, nullable=False)  
    customer_id = Column(String, nullable=False)
    attempt_count = Column(Integer, default=1)

    # classifier output
    failure_class = Column(Enum(FailureClass), nullable=True)
    classifier_confidence = Column(Float, nullable=True)

    # portfolio scoring output
    expected_recovery_value = Column(Float, nullable=True)
    probability_of_success = Column(Float, nullable=True)
    annoyance_cost = Column(Float, nullable=True)
    priority_score = Column(Float, nullable=True)

    status = Column(Enum(FailureStatus), default=FailureStatus.pending)
    promised_payment_date = Column(DateTime, nullable=True)
    promise_status = Column(String, nullable=True) 
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    merchant = relationship("Merchant", back_populates="failures")
    actions = relationship("ActionTaken", back_populates="failure")
    audit_entries = relationship("AuditLog", back_populates="failure")


class ActionTaken(Base):
    __tablename__ = "actions_taken"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    failure_id = Column(UUID(as_uuid=True), ForeignKey("failures.id"), nullable=False)

    action_type = Column(Enum(ActionType), nullable=False)
    confidence = Column(Float, nullable=True)
    explanation = Column(Text, nullable=True)  

    outcome = Column(String, nullable=True)  
    recovered_amount = Column(Float, nullable=True)
    cost_incurred = Column(Float, nullable=True)

    executed_at = Column(DateTime, default=datetime.utcnow)
    outcome_captured_at = Column(DateTime, nullable=True)

    failure = relationship("Failure", back_populates="actions")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    failure_id = Column(UUID(as_uuid=True), ForeignKey("failures.id"), nullable=False)

    event_type = Column(String, nullable=False)  
    payload = Column(JSONB, nullable=True)  
    created_at = Column(DateTime, default=datetime.utcnow)

    failure = relationship("Failure", back_populates="audit_entries")


class Precedent(Base):
    
    __tablename__ = "precedents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_persona = Column(Enum(MerchantPersona), nullable=False)
    failure_class = Column(Enum(FailureClass), nullable=False)

    case_summary = Column(Text, nullable=False)  
    embedding = Column(JSONB, nullable=False)

    action_taken = Column(Enum(ActionType), nullable=False)
    outcome = Column(String, nullable=False) 
    recovered_amount = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

class MerchantBanditState(Base):
    
    __tablename__ = "merchant_bandit_state"
 
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False, unique=True)
 
    
    arms = Column(JSONB, nullable=False, default=lambda: [0.1, 0.3, 0.5, 0.7, 0.9])
 
    a_matrices = Column(JSONB, nullable=False)
    b_vectors = Column(JSONB, nullable=False)
 
    
    total_batches_run = Column(Integer, default=0)
    current_best_arm_index = Column(Integer, default=2)  
 
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
 
    merchant = relationship("Merchant")
 
 
class BatchRunHistory(Base):
    
    __tablename__ = "batch_run_history"
 
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False)
 
    batch_size = Column(Integer, nullable=False)
    chase_capacity = Column(Integer, nullable=True)
 
    
    aggressiveness_used = Column(Float, nullable=False)
    arm_index_used = Column(Integer, nullable=False)
 
    context_features = Column(JSONB, nullable=True)
 
    total_batch_value = Column(Float, nullable=False)
    total_expected_recovery = Column(Float, nullable=False)
    total_simulated_recovered = Column(Float, nullable=False)
    total_annoyance_cost = Column(Float, nullable=False)
    reward = Column(Float, nullable=False)  # normalized ROI used to update the bandit
 
    chased_count = Column(Integer, nullable=False)
    stopped_count = Column(Integer, nullable=False)
 
    created_at = Column(DateTime, default=datetime.utcnow)
 
    merchant = relationship("Merchant")
 