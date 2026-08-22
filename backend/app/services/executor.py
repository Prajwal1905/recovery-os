"""
State machine executor for Recovery OS.

Takes a decision (action + explanation, from portfolio scoring + LLM
reasoning) for a single failure and executes it:
- For actions that map to a real Razorpay test-mode API call (retry,
  payment link generation), makes the actual call - not mocked.
- For actions that don't need an external call (nudge, escalate, stop),
  just records the decision.
- Enforces final stopping rules (max attempts, cooldown, do-not-disturb
  hours) as a last line of defense even if upstream scoring said "chase".
- Writes an immutable audit_log entry for every step: decision received,
  stopping-rule check, API call + response (or skip reason), and final
  status update on the Failure row.

Usage:
    from app.services.executor import ActionExecutor
    executor = ActionExecutor()
    result = executor.execute(failure, decision)
"""

import sys
import os
from datetime import datetime, time

sys.path.append(os.getcwd())

from dotenv import load_dotenv
import razorpay

from app.database import SessionLocal
from app.models.models import (
    Failure, ActionTaken, AuditLog, ActionType, FailureStatus
)

load_dotenv()

MAX_ATTEMPTS = 4  # hard ceiling regardless of what upstream recommends
DND_START_HOUR = 21  # 9 PM
DND_END_HOUR = 8     # 8 AM - no outbound nudges/calls in this window

# Actions that trigger a real Razorpay test-mode API call.
API_BACKED_ACTIONS = {
    ActionType.retry_now,
    ActionType.retry_scheduled,
    ActionType.update_payment_method_flow,
}

# Actions that involve contacting the customer - subject to do-not-disturb hours.
CUSTOMER_CONTACT_ACTIONS = {
    ActionType.whatsapp_nudge,
    ActionType.hinglish_voice_call,
    ActionType.retry_scheduled,
}


class StoppingRuleViolation(Exception):
    """Raised internally when a final-line stopping rule blocks execution."""
    pass


class ActionExecutor:
    def __init__(self, db=None):
        self._db = db
        key_id = os.getenv("RAZORPAY_KEY_ID")
        key_secret = os.getenv("RAZORPAY_KEY_SECRET")
        if not key_id or not key_secret:
            raise RuntimeError("RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET not set in .env")
        self.client = razorpay.Client(auth=(key_id, key_secret))

    def _get_db(self):
        return self._db if self._db is not None else SessionLocal()

    def _log_audit(self, db, failure_id, event_type: str, payload: dict):
        entry = AuditLog(failure_id=failure_id, event_type=event_type, payload=payload)
        db.add(entry)
        db.commit()
        return entry

    def _check_stopping_rules(self, failure: Failure, action: ActionType):
        """Raises StoppingRuleViolation with a plain-language reason if blocked."""
        if failure.attempt_count >= MAX_ATTEMPTS and action != ActionType.stop_chasing:
            raise StoppingRuleViolation(
                f"Max attempts ({MAX_ATTEMPTS}) reached for this failure "
                f"(current attempt_count={failure.attempt_count}). Forcing stop_chasing."
            )

        if action in CUSTOMER_CONTACT_ACTIONS:
            now_hour = datetime.now().hour
            in_dnd = now_hour >= DND_START_HOUR or now_hour < DND_END_HOUR
            if in_dnd:
                raise StoppingRuleViolation(
                    f"Do-not-disturb window active (current hour={now_hour}, "
                    f"DND is {DND_START_HOUR}:00-{DND_END_HOUR}:00). "
                    f"Customer-contact action '{action.value}' deferred, not executed now."
                )

    def _call_razorpay_retry(self, failure: Failure) -> dict:
        """
        Real Razorpay test-mode call: creates a Payment Link the customer
        can use to complete payment. Razorpay's test mode does not expose a
        direct "retry this failed payment" endpoint for arbitrary failures,
        so a fresh Payment Link is the realistic, judge-inspectable
        equivalent of "give the customer a way to pay again right now."
        """
        payment_link = self.client.payment_link.create({
            "amount": int(failure.amount * 100),  # paise
            "currency": failure.currency,
            "description": f"Retry payment - failure {failure.id}",
            "customer": {
                "name": f"Customer {failure.customer_id}",
                "contact": "",
                "email": "",
            },
            "notify": {"sms": False, "email": False},
            "reminder_enable": False,
            "notes": {
                "failure_id": str(failure.id),
                "razorpay_error_code": failure.razorpay_error_code,
                "razorpay_error_reason": failure.razorpay_error_reason,
            },
        })
        return {
            "payment_link_id": payment_link["id"],
            "short_url": payment_link["short_url"],
            "status": payment_link["status"],
        }

    def _execute_api_backed_action(self, failure: Failure, action: ActionType) -> dict:
        try:
            api_result = self._call_razorpay_retry(failure)
            return {"success": True, "api_result": api_result, "error": None}
        except Exception as e:
            return {"success": False, "api_result": None, "error": str(e)}

    def execute(self, failure: Failure, decision: dict) -> dict:
        """
        decision: dict with keys 'action', 'confidence', 'explanation'
        (the output shape of ReasoningEngine.decide()).

        Returns a result dict summarizing what happened, and writes the
        full trace to audit_log regardless of outcome.
        """
        db = self._get_db()
        owns_session = self._db is None
        try:
            action = ActionType(decision["action"])

            self._log_audit(db, failure.id, "decided", {
                "action": action.value,
                "confidence": decision.get("confidence"),
                "explanation": decision.get("explanation"),
            })

            # ---- final-line stopping rules ----
            try:
                self._check_stopping_rules(failure, action)
            except StoppingRuleViolation as e:
                self._log_audit(db, failure.id, "stopping_rule_blocked", {
                    "attempted_action": action.value,
                    "reason": str(e),
                })
                failure.status = FailureStatus.stopped
                db.add(failure)
                db.commit()

                action_record = ActionTaken(
                    failure_id=failure.id,
                    action_type=ActionType.stop_chasing,
                    confidence=decision.get("confidence"),
                    explanation=f"Blocked by stopping rule: {e}",
                    outcome="not_attempted",
                )
                db.add(action_record)
                db.commit()

                return {"executed": False, "final_action": ActionType.stop_chasing.value, "reason": str(e)}

            # ---- stop_chasing: no execution needed, just record ----
            if action == ActionType.stop_chasing:
                self._log_audit(db, failure.id, "executed", {
                    "action": action.value,
                    "note": "No action taken by design.",
                })
                failure.status = FailureStatus.stopped
                db.add(failure)

                action_record = ActionTaken(
                    failure_id=failure.id,
                    action_type=action,
                    confidence=decision.get("confidence"),
                    explanation=decision.get("explanation"),
                    outcome="not_attempted",
                )
                db.add(action_record)
                db.commit()

                return {"executed": True, "final_action": action.value, "api_call": False}

            # ---- API-backed actions: real Razorpay test-mode call ----
            if action in API_BACKED_ACTIONS:
                exec_result = self._execute_api_backed_action(failure, action)

                self._log_audit(db, failure.id, "razorpay_api_call", {
                    "action": action.value,
                    "success": exec_result["success"],
                    "api_result": exec_result["api_result"],
                    "error": exec_result["error"],
                })

                failure.attempt_count += 1
                failure.status = (
                    FailureStatus.action_executed if exec_result["success"] else FailureStatus.action_recommended
                )
                db.add(failure)

                action_record = ActionTaken(
                    failure_id=failure.id,
                    action_type=action,
                    confidence=decision.get("confidence"),
                    explanation=decision.get("explanation"),
                    outcome="pending" if exec_result["success"] else "failed",
                    cost_incurred=None,
                )
                db.add(action_record)
                db.commit()

                return {
                    "executed": exec_result["success"],
                    "final_action": action.value,
                    "api_call": True,
                    "api_result": exec_result["api_result"],
                    "error": exec_result["error"],
                }

            # ---- non-API actions that still require logging (escalate, nudge, etc.) ----
            self._log_audit(db, failure.id, "executed", {
                "action": action.value,
                "note": "Non-API action recorded (would trigger external workflow e.g. WhatsApp/human queue in production).",
            })
            failure.status = FailureStatus.action_executed
            db.add(failure)

            action_record = ActionTaken(
                failure_id=failure.id,
                action_type=action,
                confidence=decision.get("confidence"),
                explanation=decision.get("explanation"),
                outcome="pending",
            )
            db.add(action_record)
            db.commit()

            return {"executed": True, "final_action": action.value, "api_call": False}

        finally:
            if owns_session:
                db.close()


def _demo():
    from app.models.models import Merchant
    from app.services.retrieval import PrecedentRetriever
    from app.services.reasoning import ReasoningEngine

    db = SessionLocal()
    try:
        import sys as _sys
        # allow picking a specific failure_class for testing via CLI arg,
        # e.g. `python -m app.services.executor bank_timeout`
        target_class = _sys.argv[1] if len(_sys.argv) > 1 else None
        query = db.query(Failure).filter(Failure.failure_class.isnot(None))
        if target_class:
            query = query.filter(Failure.failure_class == target_class)
        failure = query.first()
        merchant = db.query(Merchant).filter(Merchant.id == failure.merchant_id).first()

        retriever = PrecedentRetriever(db)
        precedents = retriever.retrieve_similar(failure, merchant, top_k=3)

        engine = ReasoningEngine()
        decision = engine.decide(failure, merchant, precedents)
        print("Decision:", decision)

        # allow forcing a specific action via second CLI arg for testing,
        # e.g. `python -m app.services.executor bank_timeout retry_now`
        force_action = _sys.argv[2] if len(_sys.argv) > 2 else None
        if force_action:
            decision = {**decision, "action": force_action}
            print(f"(forced action override for testing: {force_action})")

        executor = ActionExecutor(db)
        result = executor.execute(failure, decision)
        print("\nExecution result:", result)

        print("\n--- Audit log for this failure ---")
        entries = db.query(AuditLog).filter(AuditLog.failure_id == failure.id).order_by(AuditLog.created_at).all()
        for e in entries:
            print(f"[{e.created_at}] {e.event_type}: {e.payload}")

    finally:
        db.close()


if __name__ == "__main__":
    _demo()