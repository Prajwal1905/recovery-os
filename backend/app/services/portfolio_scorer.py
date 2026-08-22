
import sys
import os

sys.path.append(os.getcwd())

from app.models.models import Failure, Merchant, ActionType
from app.services.retrieval import PrecedentRetriever

# Base "cost" per action if it's taken - rough proxy for support bandwidth /
# message quota / customer goodwill spent. Tunable per merchant later.
ACTION_ANNOYANCE_COST = {
    ActionType.retry_now: 5,
    ActionType.retry_scheduled: 8,
    ActionType.update_payment_method_flow: 15,
    ActionType.mandate_reauth: 20,
    ActionType.whatsapp_nudge: 25,
    ActionType.hinglish_voice_call: 60,
    ActionType.escalate_human: 150,   # real human time is the most expensive resource
    ActionType.stop_chasing: 0,
}

# Marginal annoyance multiplier per prior attempt already made on this
# failure - chasing someone for the 4th time costs more goodwill than the 1st.
ATTEMPT_ANNOYANCE_MULTIPLIER = 0.15


class PortfolioScorer:
    def __init__(self, retriever: PrecedentRetriever = None):
        self.retriever = retriever or PrecedentRetriever()

    def estimate_probability(self, failure: Failure, merchant: Merchant, top_k: int = 5) -> tuple:
        """
        Returns (probability_of_success, retrieved_precedents).
        Probability = recovered_count / attempted_count among top-k similar
        precedents (excludes not_attempted/stop_chasing cases from the
        denominator, since those tell us nothing about recovery odds).
        """
        precedents = self.retriever.retrieve_similar(failure, merchant, top_k=top_k)
        attempted = [p for p in precedents if p["outcome"] != "not_attempted"]

        if not attempted:
            # no grounded signal at all - use a conservative neutral prior
            return 0.3, precedents

        recovered = [p for p in attempted if p["outcome"] == "recovered"]
        probability = len(recovered) / len(attempted)
        return probability, precedents

    def estimate_annoyance_cost(self, failure: Failure, likely_action: ActionType) -> float:
        base = ACTION_ANNOYANCE_COST.get(likely_action, 20)
        attempt_penalty = base * ATTEMPT_ANNOYANCE_MULTIPLIER * max(0, failure.attempt_count - 1)
        return base + attempt_penalty

    def guess_likely_action(self, precedents: list) -> ActionType:
        """
        Before the full LLM reasoning call, use the most common *actionable*
        (non stop_chasing) action among retrieved precedents as a cheap
        proxy for annoyance-cost estimation during scoring. Precedents where
        the historical policy chose not to attempt recovery are excluded
        here, since this estimate specifically answers "what would it cost
        to chase this" - the chase/stop decision itself is made separately
        by priority_score and capacity, not by this label.
        """
        actionable = [p for p in precedents if p["action_taken"] != ActionType.stop_chasing.value]
        if not actionable:
            return ActionType.escalate_human
        action_values = [p["action_taken"] for p in actionable]
        most_common = max(set(action_values), key=action_values.count)
        return ActionType(most_common)

    def score_failure(self, failure: Failure, merchant: Merchant) -> dict:
        probability, precedents = self.estimate_probability(failure, merchant)
        likely_action = self.guess_likely_action(precedents)
        annoyance_cost = self.estimate_annoyance_cost(failure, likely_action)

        expected_recovery_value = failure.amount * probability
        priority_score = expected_recovery_value - annoyance_cost

        return {
            "failure_id": str(failure.id),
            "amount": failure.amount,
            "probability_of_success": round(probability, 3),
            "expected_recovery_value": round(expected_recovery_value, 2),
            "annoyance_cost": round(annoyance_cost, 2),
            "priority_score": round(priority_score, 2),
            "likely_action": likely_action.value,
            "top_precedent_summary": precedents[0]["case_summary"] if precedents else None,
        }

    def score_batch(self, failures: list, merchant_lookup: dict, chase_capacity: int = None) -> list:
        """
        merchant_lookup: dict mapping merchant_id -> Merchant object
        chase_capacity: max number of failures to actively chase; if None,
                        capacity is unlimited and only the cost-vs-value
                        cutoff (priority_score <= 0) determines stopping.

        Returns list of scored dicts, sorted by priority_score descending,
        each annotated with a final "decision" of "chase" or "stop_chasing"
        and a plain-language "stop_reason" when stopped.
        """
        scored = []
        for failure in failures:
            merchant = merchant_lookup[failure.merchant_id]
            result = self.score_failure(failure, merchant)
            scored.append(result)

        scored.sort(key=lambda r: r["priority_score"], reverse=True)

        for rank, result in enumerate(scored, start=1):
            result["rank"] = rank

            if result["priority_score"] <= 0:
                result["decision"] = "stop_chasing"
                result["stop_reason"] = (
                    f"Negative expected value: expected recovery INR {result['expected_recovery_value']:.2f} "
                    f"does not cover estimated cost INR {result['annoyance_cost']:.2f}."
                )
            elif chase_capacity is not None and rank > chase_capacity:
                result["decision"] = "stop_chasing"
                result["stop_reason"] = (
                    f"Capacity cutoff: ranked #{rank} of {len(scored)}, "
                    f"chase capacity is {chase_capacity}. Positive expected value but "
                    f"lower priority than {chase_capacity} other cases this batch."
                )
            else:
                result["decision"] = "chase"
                result["stop_reason"] = None

        return scored


def _demo():
    from app.database import SessionLocal
    from app.models.models import Merchant

    db = SessionLocal()
    try:
        merchants = {m.id: m for m in db.query(Merchant).all()}
        # sample a modest batch for a readable demo
        failures = db.query(Failure).filter(Failure.failure_class.isnot(None)).limit(20).all()

        scorer = PortfolioScorer()
        ranked = scorer.score_batch(failures, merchants, chase_capacity=10)

        print(f"{'rank':<5}{'decision':<14}{'score':<10}{'prob':<7}{'amount':<10}{'action':<25}reason")
        for r in ranked:
            reason = r["stop_reason"] or ""
            print(f"{r['rank']:<5}{r['decision']:<14}{r['priority_score']:<10}{r['probability_of_success']:<7}"
                  f"{r['amount']:<10}{r['likely_action']:<25}{reason}")

        total_chased = sum(1 for r in ranked if r["decision"] == "chase")
        total_expected_recovery = sum(r["expected_recovery_value"] for r in ranked if r["decision"] == "chase")
        print(f"\nChasing {total_chased}/{len(ranked)} failures. "
              f"Total expected recovery: INR {total_expected_recovery:.2f}")
    finally:
        db.close()


if __name__ == "__main__":
    _demo()