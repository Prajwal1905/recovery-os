"""
Precedent retrieval service for Recovery OS.

Given a failure (new or existing), builds the same style of text
description used when seeding precedents, embeds it with the same local
model, and retrieves the top-k most similar past cases by cosine
similarity - computed in Python/numpy since we're storing embeddings as
JSONB rather than using pgvector (see project notes on Windows pgvector
install friction).

Usage:
    from app.services.retrieval import PrecedentRetriever
    retriever = PrecedentRetriever()
    results = retriever.retrieve_similar(failure, merchant, top_k=3)
"""

import sys
import os
from functools import lru_cache

sys.path.append(os.getcwd())

import numpy as np
from sentence_transformers import SentenceTransformer
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.models import Precedent, Failure, Merchant

EMBED_MODEL_NAME = "all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    
    return SentenceTransformer(EMBED_MODEL_NAME)


def build_query_text(failure: Failure, merchant: Merchant) -> str:
    
    return (
        f"Merchant persona: {merchant.persona.value}. "
        f"Failure class: {failure.failure_class.value if failure.failure_class else 'unknown'}. "
        f"Payment method: {failure.payment_method}. "
        f"Error: {failure.razorpay_error_code} / {failure.razorpay_error_reason}. "
        f"Amount: INR {failure.amount:.2f}. Attempt count: {failure.attempt_count}."
    )


def cosine_similarity_batch(query_vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    
    query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-10)
    matrix_norms = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-10)
    return matrix_norms @ query_norm


class PrecedentRetriever:
    def __init__(self, db: Session = None):
        self._db = db
        self.model = get_embedding_model()

    def _get_db(self) -> Session:
        return self._db if self._db is not None else SessionLocal()

    def retrieve_similar(self, failure: Failure, merchant: Merchant, top_k: int = 3,
                          filter_same_persona: bool = False):
        
        db = self._get_db()
        owns_session = self._db is None
        try:
            query = db.query(Precedent)
            if filter_same_persona:
                query = query.filter(Precedent.merchant_persona == merchant.persona)

            precedents = query.all()
            if not precedents:
                return []

            query_text = build_query_text(failure, merchant)
            query_embedding = self.model.encode([query_text], convert_to_numpy=True)[0]

            precedent_matrix = np.array([p.embedding for p in precedents], dtype=np.float32)
            similarities = cosine_similarity_batch(query_embedding, precedent_matrix)

            ranked_idx = np.argsort(-similarities)[:top_k]

            results = []
            for idx in ranked_idx:
                p = precedents[idx]
                results.append({
                    "precedent_id": str(p.id),
                    "case_summary": p.case_summary,
                    "action_taken": p.action_taken.value,
                    "outcome": p.outcome,
                    "recovered_amount": p.recovered_amount,
                    "similarity": float(similarities[idx]),
                })
            return results
        finally:
            if owns_session:
                db.close()


def _demo():
   
    db = SessionLocal()
    try:
        failure = db.query(Failure).filter(Failure.failure_class.isnot(None)).first()
        merchant = db.query(Merchant).filter(Merchant.id == failure.merchant_id).first()

        retriever = PrecedentRetriever(db)
        results = retriever.retrieve_similar(failure, merchant, top_k=3)

        print(f"Query failure: {build_query_text(failure, merchant)}\n")
        print(f"Top {len(results)} similar precedents:\n")
        for r in results:
            print(f"  similarity={r['similarity']:.3f} | action={r['action_taken']} | outcome={r['outcome']}")
            print(f"    {r['case_summary']}\n")
    finally:
        db.close()


if __name__ == "__main__":
    _demo()