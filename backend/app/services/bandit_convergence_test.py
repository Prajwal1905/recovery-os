
import sys
import os

sys.path.append(os.getcwd())

from collections import defaultdict

from app.database import SessionLocal
from app.models.models import Failure, Merchant
from app.services.batch_runner import BatchRunner


def main():
    persona_filter = sys.argv[1] if len(sys.argv) > 1 else "aggressive_d2c"
    n_runs = int(sys.argv[2]) if len(sys.argv) > 2 else 20

    db = SessionLocal()
    try:
        merchant_lookup = {m.id: m for m in db.query(Merchant).all()}
        merchant_ids = [m.id for m in merchant_lookup.values() if m.persona.value == persona_filter]

        query = db.query(Failure).filter(Failure.failure_class.isnot(None))
        query = query.filter(Failure.merchant_id.in_(merchant_ids))
        failures = query.limit(30).all()

        if not failures:
            print(f"No failures found for persona '{persona_filter}'.")
            return

        runner = BatchRunner(db)

        arm_pulls = defaultdict(int)
        arm_rewards = defaultdict(list)

        print(f"Running {n_runs} batches for persona '{persona_filter}'...\n")

        for i in range(n_runs):
            output = runner.run_batch(failures, merchant_lookup, chase_capacity=None)
            policy = list(output["summary"]["policy"].values())[0]
            arm = policy["aggressiveness_used_this_batch"]
            reward = policy["reward_this_batch"]

            arm_pulls[arm] += 1
            arm_rewards[arm].append(reward)

            print(f"  Run {i+1:2d}: arm={arm:.1f}  reward={reward:+.4f}  "
                  f"current_best={policy['bandit_summary']['current_best_aggressiveness']}")

        print("\n=== CONVERGENCE SUMMARY ===")
        print(f"{'Arm':<8}{'Pulls':<8}{'Avg Reward':<14}{'Min':<10}{'Max':<10}")
        for arm in sorted(arm_pulls.keys()):
            rewards = arm_rewards[arm]
            avg = sum(rewards) / len(rewards)
            print(f"{arm:<8}{arm_pulls[arm]:<8}{avg:<14.4f}{min(rewards):<10.4f}{max(rewards):<10.4f}")

        best_arm = max(arm_rewards.keys(), key=lambda a: sum(arm_rewards[a]) / len(arm_rewards[a]))
        print(f"\nEmpirically best arm so far (by average reward): {best_arm}")

        final_policy = list(output["summary"]["policy"].values())[0]
        print(f"Bandit's current belief (current_best_aggressiveness): "
              f"{final_policy['bandit_summary']['current_best_aggressiveness']}")

    finally:
        db.close()


if __name__ == "__main__":
    main()