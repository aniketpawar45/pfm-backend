import requests
import json

# The exact URL Telegram is trying to hit
WEBHOOK_URL = "https://pfm-backend-navy.vercel.app//telegram/webhook"

# A fake Telegram message payload
payload = {
    "update_id": 10000,
    "message": {
        "message_id": 1,
        "date": 1785270000,
        "chat": {
            "id": 999999999, # Fake chat ID
            "type": "private",
            "first_name": "TestUser"
        },
        "text": "I spent 500 on lunch today"
    }
}

print(f"🚀 Simulating Telegram POST request to {WEBHOOK_URL}...")

try:
    response = requests.post(WEBHOOK_URL, json=payload)
    print(f"\n📡 Status Code: {response.status_code}")
    
    # If the server crashes, FastAPI often returns the exact error in the body
    if response.status_code == 500:
        print("\n❌ CRASH DETECTED. Server responded with:")
        print(response.text)
    elif response.status_code == 200:
        print("\n✅ SUCCESS! The server processed it perfectly.")
        print("Response:", response.text)
    else:
        print(f"\n⚠️ Unexpected Status: {response.status_code}")
        print("Response:", response.text)

except Exception as e:
    print(f"Failed to connect: {e}")