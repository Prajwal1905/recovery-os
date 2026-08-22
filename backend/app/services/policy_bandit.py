
import sys
import os

sys.path.append(os.getcwd())

import numpy as np

from app.models.models import Merchant, MerchantBanditState, Failure, FailureClass

ARMS = [0.1, 0.3, 0.5, 0.7, 0.9]
NUM_ARMS = len(ARMS)

FAILURE_CLASSES = [c.value for c in FailureClass]

CONTEXT_DIM = 2 + len(FAILURE_CLASSES) + 1

ALPHA = 1.0  


class PolicyBandit:
    def __init__(self, db):
        self.db = db

    def _get_or_create_state(self, merchant: Merchant) -> MerchantBanditState:
        state = (
            self.db.query(MerchantBanditState)
            .filter(MerchantBanditState.merchant_id == merchant.id)
            .first()
        )
        if state:
            return state

        a_matrices = [np.eye(CONTEXT_DIM).tolist() for _ in range(NUM_ARMS)]
        b_vectors = [np.zeros(CONTEXT_DIM).tolist() for _ in range(NUM_ARMS)]

        state = MerchantBanditState(
            merchant_id=merchant.id,
            arms=ARMS,
            a_matrices=a_matrices,
            b_vectors=b_vectors,
            total_batches_run=0,
            current_best_arm_index=2,  
        )
        self.db.add(state)
        self.db.commit()
        self.db.refresh(state)
        return state

    def _build_context(self, failures: list) -> np.ndarray:
        if not failures:
            return np.zeros(CONTEXT_DIM)

        amounts = [f.amount for f in failures]
        avg_amount_normalized = min(np.mean(amounts) / 50000.0, 1.0)  # rough normalization

        high_attempt_ratio = sum(1 for f in failures if f.attempt_count >= 3) / len(failures)

        class_counts = {c: 0 for c in FAILURE_CLASSES}
        for f in failures:
            if f.failure_class:
                class_counts[f.failure_class.value] += 1
        class_proportions = [class_counts[c] / len(failures) for c in FAILURE_CLASSES]

        bias = 1.0

        return np.array([avg_amount_normalized, high_attempt_ratio] + class_proportions + [bias])

    def select_arm(self, merchant: Merchant, failures: list):
        
        state = self._get_or_create_state(merchant)
        context = self._build_context(failures)

        ucb_scores = []
        for i in range(NUM_ARMS):
            A = np.array(state.a_matrices[i])
            b = np.array(state.b_vectors[i])
            A_inv = np.linalg.inv(A)
            theta = A_inv @ b

            estimated_reward = float(theta @ context)
            exploration_bonus = ALPHA * float(np.sqrt(context @ A_inv @ context))
            ucb_scores.append(estimated_reward + exploration_bonus)

        chosen_arm = int(np.argmax(ucb_scores))
        return ARMS[chosen_arm], chosen_arm, context.tolist()

    def update(self, merchant: Merchant, arm_index: int, context: list, reward: float):
        
        state = self._get_or_create_state(merchant)
        context_vec = np.array(context)

        A = np.array(state.a_matrices[arm_index])
        b = np.array(state.b_vectors[arm_index])

        A_updated = A + np.outer(context_vec, context_vec)
        b_updated = b + reward * context_vec

        a_matrices = state.a_matrices.copy()
        b_vectors = state.b_vectors.copy()
        a_matrices[arm_index] = A_updated.tolist()
        b_vectors[arm_index] = b_updated.tolist()

        state.a_matrices = a_matrices
        state.b_vectors = b_vectors
        state.total_batches_run += 1

        best_estimates = []
        for i in range(NUM_ARMS):
            Ai = np.array(a_matrices[i])
            bi = np.array(b_vectors[i])
            theta_i = np.linalg.inv(Ai) @ bi
            best_estimates.append(float(theta_i @ context_vec))
        state.current_best_arm_index = int(np.argmax(best_estimates))

        self.db.add(state)
        self.db.commit()

    def get_policy_summary(self, merchant: Merchant) -> dict:
        """Human-readable summary of current bandit state, for dashboard/judge Q&A."""
        state = self._get_or_create_state(merchant)
        return {
            "merchant_id": str(merchant.id),
            "arms": state.arms,
            "current_best_aggressiveness": ARMS[state.current_best_arm_index],
            "total_batches_run": state.total_batches_run,
        }