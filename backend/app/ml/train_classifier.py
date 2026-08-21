
import sys
import os
import json
import pickle

sys.path.append(os.getcwd())

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    precision_recall_fscore_support,
)
import xgboost as xgb
import shap

from app.database import SessionLocal
from app.models.models import Failure, Merchant

MODEL_DIR = os.path.join(os.getcwd(), "app", "ml", "artifacts")
os.makedirs(MODEL_DIR, exist_ok=True)

CATEGORICAL_FEATURES = ["razorpay_error_code", "razorpay_error_reason", "payment_method", "persona"]
NUMERIC_FEATURES = ["amount", "attempt_count"]
TARGET = "failure_class"


def load_data() -> pd.DataFrame:
    db = SessionLocal()
    try:
        rows = (
            db.query(Failure, Merchant.persona)
            .join(Merchant, Failure.merchant_id == Merchant.id)
            .all()
        )
        records = []
        for failure, persona in rows:
            records.append({
                "razorpay_error_code": failure.razorpay_error_code,
                "razorpay_error_reason": failure.razorpay_error_reason,
                "payment_method": failure.payment_method,
                "persona": persona.value,
                "amount": failure.amount,
                "attempt_count": failure.attempt_count,
                "failure_class": failure.failure_class.value,
            })
        return pd.DataFrame.from_records(records)
    finally:
        db.close()


def build_pipeline(label_encoder: LabelEncoder) -> Pipeline:
    preprocessor = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
            ("num", "passthrough", NUMERIC_FEATURES),
        ]
    )

    model = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.1,
        objective="multi:softprob",
        num_class=len(label_encoder.classes_),
        eval_metric="mlogloss",
        random_state=42,
    )

    return Pipeline(steps=[("preprocess", preprocessor), ("model", model)])


def main():
    print("Loading data from Postgres...")
    df = load_data()
    print(f"Loaded {len(df)} rows.")
    print(df[TARGET].value_counts())

    X = df[CATEGORICAL_FEATURES + NUMERIC_FEATURES]
    y_raw = df[TARGET]

    label_encoder = LabelEncoder()
    y = label_encoder.fit_transform(y_raw)


    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )
    print(f"\nTrain size: {len(X_train)}, Test size: {len(X_test)} (held out, untouched during training)")

    pipeline = build_pipeline(label_encoder)
    pipeline.fit(X_train, y_train)

    
    y_pred = pipeline.predict(X_test)
    y_pred_labels = label_encoder.inverse_transform(y_pred)
    y_test_labels = label_encoder.inverse_transform(y_test)

    print("\n=== Held-out test set classification report ===")
    report = classification_report(y_test_labels, y_pred_labels, digits=3)
    print(report)

    precision, recall, f1, support = precision_recall_fscore_support(
        y_test_labels, y_pred_labels, labels=label_encoder.classes_, zero_division=0
    )
    metrics_summary = {
        cls: {"precision": float(p), "recall": float(r), "f1": float(f), "support": int(s)}
        for cls, p, r, f, s in zip(label_encoder.classes_, precision, recall, f1, support)
    }

    print("\n=== Confusion matrix (rows=true, cols=predicted) ===")
    cm = confusion_matrix(y_test_labels, y_pred_labels, labels=label_encoder.classes_)
    cm_df = pd.DataFrame(cm, index=label_encoder.classes_, columns=label_encoder.classes_)
    print(cm_df)

    # ---- SHAP explainability on a sample of the test set ----
    print("\nComputing SHAP values for explainability...")
    preprocessor = pipeline.named_steps["preprocess"]
    model = pipeline.named_steps["model"]
    X_test_transformed = preprocessor.transform(X_test)

    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_test_transformed)

    feature_names = preprocessor.get_feature_names_out()

   
    if isinstance(shap_values, list):
        mean_abs_shap = np.mean([np.abs(sv).mean(axis=0) for sv in shap_values], axis=0)
    else:
        mean_abs_shap = np.abs(shap_values).mean(axis=(0, 2)) if shap_values.ndim == 3 else np.abs(shap_values).mean(axis=0)

    importance_df = pd.DataFrame({
        "feature": feature_names,
        "mean_abs_shap": mean_abs_shap,
    }).sort_values("mean_abs_shap", ascending=False)

    print("\n=== Top 10 features by mean |SHAP value| ===")
    print(importance_df.head(10).to_string(index=False))

    
    with open(os.path.join(MODEL_DIR, "classifier_pipeline.pkl"), "wb") as f:
        pickle.dump(pipeline, f)

    with open(os.path.join(MODEL_DIR, "label_encoder.pkl"), "wb") as f:
        pickle.dump(label_encoder, f)

    with open(os.path.join(MODEL_DIR, "metrics.json"), "w") as f:
        json.dump({
            "test_size": len(X_test),
            "train_size": len(X_train),
            "per_class_metrics": metrics_summary,
            "confusion_matrix": cm_df.to_dict(),
            "top_features": importance_df.head(10).to_dict(orient="records"),
        }, f, indent=2)

    print(f"\nSaved model, label encoder, and metrics.json to {MODEL_DIR}")


if __name__ == "__main__":
    main()