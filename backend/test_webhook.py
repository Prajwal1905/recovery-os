import hmac
import hashlib
import json
import requests

WEBHOOK_SECRET = "recovery-os-webhook-secret-2026"  # must match your .env value exactly

payload = {
    "event": "payment.failed",
    "payload": {
        "payment": {
            "entity": {
                "id": "pay_test_simulated123",
                "amount": 250000,
                "currency": "INR",
                "error_code": "BAD_REQUEST_ERROR",
                "error_description": "insufficient_balance_in_account",
                "method": "upi",
                "customer_id": "cust_test_simulated456",
            }
        }
    },
}

body = json.dumps(payload).encode()
signature = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()

response = requests.post(
    "http://localhost:8000/webhooks/razorpay",
    data=body,
    headers={
        "Content-Type": "application/json",
        "X-Razorpay-Signature": signature,
    },
)

print("Status:", response.status_code)
print("Response:", response.json())