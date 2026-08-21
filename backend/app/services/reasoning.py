
import sys
import os
import json

sys.path.append(os.getcwd())

from dotenv import load_dotenv
from openai import OpenAI

from app.models.models import Failure, Merchant, ActionType

load_dotenv()

OPENAI_MODEL = "gpt-4o-mini"  

ALLOWED_ACTIONS = [a.value for a in ActionType]

SYSTEM_PROMPT = f"""You are a revenue recovery decision engine for Razorpay merchants.

You must recommend exactly ONE action from this fixed list, never anything else:
{ALLOWED_ACTIONS}

Rules:
- You are NEVER allowed to move money directly or invent a new action. Only pick from the list above.
- Ground your reasoning in the retrieved precedent cases you are given - cite what happened in similar past cases.
- Your explanation must be ROI-justified: state the expected recovery value vs the cost of acting (support time, customer annoyance, message quota), and give a plain-language reason for the decision.
- If precedents show this type of case rarely recovers or costs more than it recovers, recommend stop_chasing and say why explicitly.
- Respond ONLY with valid JSON, no markdown, no preamble, in this exact schema:
{{
  "action": "<one of the allowed actions>",
  "confidence": <float 0-1>,
  "explanation": "<plain language ROI-justified explanation citing precedent>"
}}
"""


class ReasoningEngine:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set in .env")
        self.client = OpenAI(api_key=api_key)

    def _build_user_prompt(self, failure: Failure, merchant: Merchant, precedents: list) -> str:
        precedent_lines = []
        for p in precedents:
            precedent_lines.append(
                f"- similarity={p['similarity']:.2f} | action_taken={p['action_taken']} | "
                f"outcome={p['outcome']} | recovered_amount={p['recovered_amount']} | {p['case_summary']}"
            )
        precedent_text = "\n".join(precedent_lines) if precedent_lines else "No similar precedents found."

        return f"""New failure to decide on:
- Merchant persona: {merchant.persona.value} (stopping_aggressiveness={merchant.stopping_aggressiveness})
- Failure class: {failure.failure_class.value if failure.failure_class else 'unknown'}
- Payment method: {failure.payment_method}
- Error: {failure.razorpay_error_code} / {failure.razorpay_error_reason}
- Amount: INR {failure.amount:.2f}
- Attempt count so far: {failure.attempt_count}

Retrieved similar past cases (most similar first):
{precedent_text}

Recommend the single best action and explain your reasoning with ROI justification.
"""

    def _fallback_decision(self, reason: str) -> dict:
        return {
            "action": ActionType.escalate_human.value,
            "confidence": 0.0,
            "explanation": f"Fallback to human escalation: {reason}",
        }

    def decide(self, failure: Failure, merchant: Merchant, precedents: list) -> dict:
        user_prompt = self._build_user_prompt(failure, merchant, precedents)

        try:
            response = self.client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content
            parsed = json.loads(raw)
        except Exception as e:
            return self._fallback_decision(f"LLM call or parsing failed ({e})")

        
        action = parsed.get("action")
        if action not in ALLOWED_ACTIONS:
            return self._fallback_decision(f"LLM returned invalid action '{action}', rejected")

        confidence = parsed.get("confidence")
        if not isinstance(confidence, (int, float)) or not (0 <= confidence <= 1):
            confidence = 0.5  

        explanation = parsed.get("explanation", "").strip()
        if not explanation:
            return self._fallback_decision("LLM returned empty explanation, rejected")

        return {
            "action": action,
            "confidence": float(confidence),
            "explanation": explanation,
        }


def _demo():
    from app.database import SessionLocal
    from app.services.retrieval import PrecedentRetriever

    db = SessionLocal()
    try:
        failure = db.query(Failure).filter(Failure.failure_class.isnot(None)).first()
        merchant = db.query(Merchant).filter(Merchant.id == failure.merchant_id).first()

        retriever = PrecedentRetriever(db)
        precedents = retriever.retrieve_similar(failure, merchant, top_k=3)

        engine = ReasoningEngine()
        decision = engine.decide(failure, merchant, precedents)

        print("=== Decision ===")
        print(json.dumps(decision, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    _demo()