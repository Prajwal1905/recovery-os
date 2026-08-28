
import sys
import os
import random
import json

sys.path.append(os.getcwd())

from app.database import SessionLocal
from app.models.models import Failure, Merchant, ActionType, BatchRunHistory
from app.services.retrieval import PrecedentRetriever
from app.services.reasoning import ReasoningEngine
from app.services.portfolio_scorer import PortfolioScorer
from app.services.executor import ActionExecutor
from app.services.policy_bandit import PolicyBandit

random.seed(11)


class BatchRunner:
    def __init__(self, db=None):
        self.db = db or SessionLocal()
        self.retriever = PrecedentRetriever(self.db)
        self.scorer = PortfolioScorer(self.retriever)
        self.reasoning_engine = ReasoningEngine()
        self.executor = ActionExecutor(self.db)
        self.bandit = PolicyBandit(self.db)

    def _simulate_customer_outcome(self, probability_of_success: float) -> bool:
        return random.random() < probability_of_success

    def run_batch(self, failures: list, merchant_lookup: dict, chase_capacity: int = None) -> dict:
        failures_by_merchant = {}
        for f in failures:
            failures_by_merchant.setdefault(f.merchant_id, []).append(f)

        policy_used = {}
        for merchant_id, merchant_failures in failures_by_merchant.items():
            merchant = merchant_lookup[merchant_id]
            aggressiveness, arm_index, context = self.bandit.select_arm(merchant, merchant_failures)
            policy_used[merchant_id] = (aggressiveness, arm_index, context)
            merchant.stopping_aggressiveness = aggressiveness

        print(f"Scoring batch of {len(failures)} failures...")
        for merchant_id, (aggressiveness, _, _) in policy_used.items():
            print(f"  Merchant {merchant_lookup[merchant_id].name}: bandit selected aggressiveness={aggressiveness}")

        ranked = self.scorer.score_batch(failures, merchant_lookup, chase_capacity=chase_capacity)

        failure_by_id = {str(f.id): f for f in failures}
        results = []
        exceptions = []

        chase_list = [r for r in ranked if r["decision"] == "chase"]
        stop_list = [r for r in ranked if r["decision"] == "stop_chasing"]

        print(f"Chasing {len(chase_list)}, stopping {len(stop_list)} (capacity/negative-EV cutoffs).")

        for r in chase_list:
            failure = failure_by_id[r["failure_id"]]
            merchant = merchant_lookup[failure.merchant_id]

            precedents = self.retriever.retrieve_similar(failure, merchant, top_k=3)
            decision = self.reasoning_engine.decide(failure, merchant, precedents)

            exec_result = self.executor.execute(failure, decision)

            simulated_recovered = None
            if exec_result.get("api_call") and exec_result.get("executed"):
                recovered = self._simulate_customer_outcome(r["probability_of_success"])
                simulated_recovered = round(failure.amount, 2) if recovered else 0.0

            results.append({
                **r,
                "llm_action": decision["action"],
                "llm_confidence": decision["confidence"],
                "llm_explanation": decision["explanation"],
                "execution": exec_result,
                "simulated_recovered_amount": simulated_recovered,
            })

        for r in stop_list:
            results.append({
                **r,
                "llm_action": None,
                "llm_confidence": None,
                "llm_explanation": None,
                "execution": {"executed": False, "final_action": "stop_chasing"},
                "simulated_recovered_amount": None,
            })
            exceptions.append({
                "failure_id": r["failure_id"],
                "amount": r["amount"],
                "reason": r["stop_reason"],
            })

        total_batch_value = sum(r["amount"] for r in ranked)
        total_expected_recovery = sum(r["expected_recovery_value"] for r in chase_list)
        total_simulated_recovered = sum(
            r["simulated_recovered_amount"] for r in results if r["simulated_recovered_amount"]
        )
        api_calls_made = sum(1 for r in results if r["execution"].get("api_call"))
        api_calls_successful = sum(
            1 for r in results if r["execution"].get("api_call") and r["execution"].get("executed")
        )

        policy_summaries = {}
        for merchant_id, merchant_failures in failures_by_merchant.items():
            merchant = merchant_lookup[merchant_id]
            aggressiveness, arm_index, context = policy_used[merchant_id]

            merchant_result_ids = {str(f.id) for f in merchant_failures}
            merchant_chase = [r for r in chase_list if r["failure_id"] in merchant_result_ids]
            merchant_stop = [r for r in stop_list if r["failure_id"] in merchant_result_ids]

            m_batch_value = sum(r["amount"] for r in merchant_chase + merchant_stop)
            m_expected = sum(r["expected_recovery_value"] for r in merchant_chase)
            m_simulated = sum(
                r["simulated_recovered_amount"]
                for r in results
                if r["failure_id"] in merchant_result_ids and r["simulated_recovered_amount"]
            )
            m_annoyance = sum(r["annoyance_cost"] for r in merchant_chase)

            reward = (m_simulated - m_annoyance) / m_batch_value if m_batch_value > 0 else 0.0
            reward = max(-1.0, min(1.0, reward))

            self.bandit.update(merchant, arm_index, context, reward)

            history_row = BatchRunHistory(
                merchant_id=merchant.id,
                batch_size=len(merchant_failures),
                chase_capacity=chase_capacity,
                aggressiveness_used=aggressiveness,
                arm_index_used=arm_index,
                context_features={"vector": context},
                total_batch_value=round(m_batch_value, 2),
                total_expected_recovery=round(m_expected, 2),
                total_simulated_recovered=round(m_simulated, 2),
                total_annoyance_cost=round(m_annoyance, 2),
                reward=round(reward, 4),
                chased_count=len(merchant_chase),
                stopped_count=len(merchant_stop),
            )
            self.db.add(history_row)

            policy_summaries[str(merchant_id)] = {
                "merchant_name": merchant.name,
                "aggressiveness_used_this_batch": aggressiveness,
                "reward_this_batch": round(reward, 4),
                "bandit_summary": self.bandit.get_policy_summary(merchant),
            }

        self.db.commit()

        summary = {
            "batch_size": len(failures),
            "total_batch_value": round(total_batch_value, 2),
            "chased_count": len(chase_list),
            "stopped_count": len(stop_list),
            "total_expected_recovery": round(total_expected_recovery, 2),
            "total_simulated_recovered": round(total_simulated_recovered, 2),
            "recovery_rate_of_chased_value": (
                round(total_simulated_recovered / sum(r["amount"] for r in chase_list), 3)
                if chase_list else 0.0
            ),
            "api_calls_made": api_calls_made,
            "api_calls_successful": api_calls_successful,
            "exception_count": len(exceptions),
            "exceptions": exceptions,
            "policy": policy_summaries,
        }

        return {"summary": summary, "results": results}


def main():
    persona_filter = sys.argv[1] if len(sys.argv) > 1 else None
    chase_capacity_arg = sys.argv[2] if len(sys.argv) > 2 else None
    chase_capacity = int(chase_capacity_arg) if chase_capacity_arg else None

    db = SessionLocal()
    try:
        merchant_lookup = {m.id: m for m in db.query(Merchant).all()}

        query = db.query(Failure).filter(Failure.failure_class.isnot(None))
        if persona_filter:
            merchant_ids = [m.id for m in merchant_lookup.values() if m.persona.value == persona_filter]
            query = query.filter(Failure.merchant_id.in_(merchant_ids))

        failures = query.limit(30).all()

        runner = BatchRunner(db)
        output = runner.run_batch(failures, merchant_lookup, chase_capacity=chase_capacity)

        print("\n=== BATCH SUMMARY ===")
        print(json.dumps(output["summary"], indent=2))

        print("\n=== EXCEPTION LIST (honest, not hidden) ===")
        for exc in output["summary"]["exceptions"][:10]:
            print(f"  - failure={exc['failure_id']} amount=INR {exc['amount']} | {exc['reason']}")

    finally:
        db.close()


if __name__ == "__main__":
    main()