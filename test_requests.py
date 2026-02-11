import requests
import os

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "your_token_here") # Replace with actual token if env not loaded

try:
    print("Testing with requests (verify=False)...")
    r = requests.get(f"https://api.telegram.org/bot{TOKEN}/getMe", verify=False)
    print(r.status_code)
    print(r.json())
except Exception as e:
    print(e)
