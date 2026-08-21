

import sys
import os
import random

sys.path.append(os.getcwd())

from sentence_transformers import SentenceTransformer

from app.database import SessionLocal
from app.models.models import Failure, Merchant, Precedent, ActionType, FailureClass, MerchantPersona

random.seed(7)

N_PRECEDENTS = 400  

EMBED_MODEL_NAME = "all-MiniLM-L6-v2"

ACTIONS_BY_CLASS = {
    FailureClass.insufficient_funds: [ActionType.retry_scheduled, ActionType.whatsapp_nudge, ActionType.stop_chasing],
    FailureClass.expired_card: [ActionType.update_payment_method_flow, ActionType.whatsapp_nudge],
    FailureClass.bank_timeout: [ActionType.retry_now, ActionType.retry_scheduled],
    FailureClass.risk_decline: [ActionType.escalate_human, ActionType.stop_chasing],
    FailureClass.mandate_failure: [ActionType.mandate_reauth, ActionType.escalate_human],
}

ACTION_SUCCESS_BASE_RATE = {
    ActionType.retry_now: 0.55,
    ActionType.retry_scheduled: 0.65,
    ActionType.update_payment_method_flow: 0.60,
    ActionType.mandate_reauth: 0.50,
    ActionType.whatsapp_nudge: 0.40,
    ActionType.escalate_human: 0.70,
    ActionType.stop_chasing: 0.0,  
}

PERSONA_MODIFIER = {
    MerchantPersona.aggressive_d2c: {"retry_bonus": 0.05, "escalate_bonus": -0.05},
    MerchantPersona.relationship_b2b: {"retry_bonus": -0.05, "escalate_bonus": 0.15},
    MerchantPersona.neutral_midmarket: {"retry_bonus": 0.0, "escalate_bonus": 0.0},
}


def pick_action(failure_class: FailureClass) -> ActionType:
    return random.choice(ACTIONS_BY_CLASS[failure_class])


def simulate_outcome(action: ActionType, persona: MerchantPersona, amount: float):
    if action == ActionType.stop_chasing:
        return "not_attempted", None

    base_rate = ACTION_SUCCESS_BASE_RATE[action]
    modifier = PERSONA_MODIFIER[persona]

    if action in (ActionType.retry_now, ActionType.retry_scheduled):
        base_rate += modifier["retry_bonus"]
    elif action == ActionType.escalate_human:
        base_rate += modifier["escalate_bonus"]

    
    if amount > 20000:
        base_rate -= 0.08

    base_rate = max(0.05, min(0.95, base_rate))

    success = random.random() < base_rate
    if success:
        return "recovered", round(amount * random.uniform(0.95, 1.0), 2)
    else:
        return random.choice(["failed", "no_response"]), None


def build_case_summary(failure: Failure, merchant: Merchant, action: ActionType, outcome: str) -> str:
    return (
        f"Merchant persona: {merchant.persona.value}. "
        f"Failure class: {failure.failure_class.value}. "
        f"Payment method: {failure.payment_method}. "
        f"Error: {failure.razorpay_error_code} / {failure.razorpay_error_reason}. "
        f"Amount: INR {failure.amount:.2f}. Attempt count: {failure.attempt_count}. "
        f"Action taken: {action.value}. Outcome: {outcome}."
    )


def main():
    print("Loading embedding model (all-MiniLM-L6-v2)...")
    model = SentenceTransformer(EMBED_MODEL_NAME)

    db = SessionLocal()
    try:
        merchants = {m.id: m for m in db.query(Merchant).all()}

        all_failures = db.query(Failure).all()
        sample = random.sample(all_failures, min(N_PRECEDENTS, len(all_failures)))

        print(f"Seeding {len(sample)} precedents from sampled failures...")

        summaries = []
        meta = []
        for failure in sample:
            merchant = merchants[failure.merchant_id]
            action = pick_action(failure.failure_class)
            outcome, recovered_amount = simulate_outcome(action, merchant.persona, failure.amount)
            summary = build_case_summary(failure, merchant, action, outcome)

            summaries.append(summary)
            meta.append({
                "merchant_persona": merchant.persona,
                "failure_class": failure.failure_class,
                "action_taken": action,
                "outcome": outcome,
                "recovered_amount": recovered_amount,
                "case_summary": summary,
            })

        print("Computing embeddings...")
        embeddings = model.encode(summaries, show_progress_bar=True, convert_to_numpy=True)

        precedents = []
        for m, emb in zip(meta, embeddings):
            precedents.append(Precedent(
                merchant_persona=m["merchant_persona"],
                failure_class=m["failure_class"],
                case_summary=m["case_summary"],
                embedding=emb.tolist(),  # JSONB-stored list of 384 floats
                action_taken=m["action_taken"],
                outcome=m["outcome"],
                recovered_amount=m["recovered_amount"],
            ))

        db.add_all(precedents)
        db.commit()

        print(f"\nDone. Seeded {len(precedents)} precedents.")

        outcome_counts = {}
        for p in precedents:
            outcome_counts[p.outcome] = outcome_counts.get(p.outcome, 0) + 1
        print("Outcome distribution:", outcome_counts)

    finally:
        db.close()


if __name__ == "__main__":
    main()