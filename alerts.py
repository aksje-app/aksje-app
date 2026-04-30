
import os
import requests

def send_pushover(message, title="AI Aksje Analyzer"):
    token = os.getenv("PUSHOVER_APP_TOKEN", "").strip()
    user = os.getenv("PUSHOVER_USER_KEY", "").strip()

    if not token or not user:
        print("Pushover ikke konfigurert")
        return False

    try:
        r = requests.post(
            "https://api.pushover.net/1/messages.json",
            data={
                "token": token,
                "user": user,
                "title": title,
                "message": message,
            },
            timeout=15,
        )
        print(f"Pushover status: {r.status_code}")
        return r.ok
    except Exception as e:
        print(f"Pushover-feil: {e}")
        return False
