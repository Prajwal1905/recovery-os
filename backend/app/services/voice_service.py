
import sys
import os
import base64

sys.path.append(os.getcwd())

import requests
from dotenv import load_dotenv

load_dotenv()

SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"
AUDIO_OUTPUT_DIR = os.path.join(os.getcwd(), "app", "generated_audio")
os.makedirs(AUDIO_OUTPUT_DIR, exist_ok=True)


def generate_hinglish_voice_message(failure_id: str, amount: float, merchant_name: str) -> str:
    
    api_key = os.getenv("SARVAM_API_KEY")
    if not api_key:
        raise RuntimeError("SARVAM_API_KEY not set in .env")

    text = (
        f"Namaste! Yeh {merchant_name} ki taraf se ek reminder hai. "
        f"Aapka payment of rupees {amount:.0f} complete nahi ho paya. "
        f"Kripya apna payment link check karein aur jaldi se complete karein. Dhanyavaad!"
    )

    response = requests.post(
        SARVAM_TTS_URL,
        headers={
            "api-subscription-key": api_key,
            "Content-Type": "application/json",
        },
        json={
            "text": text,
            "target_language_code": "hi-IN",
            "speaker": "shubh",
            "model": "bulbul:v3",
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    audio_b64 = data["audios"][0]
    audio_bytes = base64.b64decode(audio_b64)

    output_path = os.path.join(AUDIO_OUTPUT_DIR, f"{failure_id}.wav")
    with open(output_path, "wb") as f:
        f.write(audio_bytes)

    return output_path


def _demo():
    path = generate_hinglish_voice_message(
        failure_id="test123",
        amount=3294.10,
        merchant_name="UrbanCart",
    )
    print(f"Generated audio saved to: {path}")


if __name__ == "__main__":
    _demo()