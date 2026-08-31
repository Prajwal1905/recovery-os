
import sys
import os
import random

sys.path.append(os.getcwd())

from sentence_transformers import SentenceTransformer

from app.database import SessionLocal
from app.models.models import Failure, Merchant, Precedent, ActionType, FailureClass, MerchantPersona

random.seed(31)

N_PER_CLASS = 80
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"

ACTIONS_BY_CLASS = {
    FailureClass.subscription_failure: [ActionType.mandate_reauth, ActionType.retry_scheduled, ActionType.stop_chasing],
    FailureClass.overdue_receivable: [ActionType.escalate_human, ActionType.whatsapp_nudge, ActionType.stop_chasing],
}

ACTION_SUCCESS_BASE_RATE = {
    ActionType.mandate_reauth: 0.55,
    ActionType.retry_scheduled: 0.45,
    ActionType.escalate_human: 0.60,
    ActionType.whatsapp_nudge: 0.35,
    ActionType.stop_chasing: 0.0,
}

PERSONA_MODIFIER = {
    MerchantPersona.relationship_b2b: 0.10,   # B2B relationships tend to eventually pay
    MerchantPersona.neutral_midmarket: 0.0,
    MerchantPersona.aggressive_d2c: 0.0,
}


def pick_action(failure_class: FailureClass) -> ActionType:
    return random.choice(ACTIONS_BY_CLASS[failure_class])


def simulate_outcome(action: ActionType, persona: MerchantPersona, amount: float):
    if action == ActionType.stop_chasing:
        return "not_attempted", None

    base_rate = ACTION_SUCCESS_BASE_RATE[action] + PERSONA_MODIFIER.get(persona, 0.0)
    if amount > 50000:
        base_rate -= 0.08
    base_rate = max(0.05, min(0.9, base_rate))

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

        all_precedents = []
        for failure_class in [FailureClass.subscription_failure, FailureClass.overdue_receivable]:
            class_failures = db.query(Failure).filter(Failure.failure_class == failure_class).all()
            sample = random.sample(class_failures, min(N_PER_CLASS, len(class_failures)))
            print(f"Seeding {len(sample)} precedents for {failure_class.value}...")

            summaries = []
            meta = []
            for failure in sample:
                merchant = merchants[failure.merchant_id]
                action = pick_action(failure_class)
                outcome, recovered_amount = simulate_outcome(action, merchant.persona, failure.amount)
                summary = build_case_summary(failure, merchant, action, outcome)

                summaries.append(summary)
                meta.append({
                    "merchant_persona": merchant.persona,
                    "failure_class": failure_class,
                    "action_taken": action,
                    "outcome": outcome,
                    "recovered_amount": recovered_amount,
                    "case_summary": summary,
                })

            embeddings = model.encode(summaries, show_progress_bar=True, convert_to_numpy=True)
            for m, emb in zip(meta, embeddings):
                all_precedents.append(Precedent(
                    merchant_persona=m["merchant_persona"],
                    failure_class=m["failure_class"],
                    case_summary=m["case_summary"],
                    embedding=emb.tolist(),
                    action_taken=m["action_taken"],
                    outcome=m["outcome"],
                    recovered_amount=m["recovered_amount"],
                ))

        db.add_all(all_precedents)
        db.commit()

        print(f"\nDone. Seeded {len(all_precedents)} total precedents.")
        outcome_counts = {}
        for p in all_precedents:
            outcome_counts[p.outcome] = outcome_counts.get(p.outcome, 0) + 1
        print("Outcome distribution:", outcome_counts)

    finally:
        db.close()


if __name__ == "__main__":
    main()