import certifi
import httpx
import os

print(f"Certifi path: {certifi.where()}")
print(f"SSL_CERT_FILE env: {os.environ.get('SSL_CERT_FILE')}")

try:
    print("Testing connection to api.telegram.org with certifi...")
    with httpx.Client(verify=certifi.where()) as client:
        resp = client.get("https://api.telegram.org")
        print(f"Success! Status: {resp.status_code}")
except Exception as e:
    print(f"Failed with certifi: {e}")

try:
    print("\nTesting connection to api.telegram.org WITHOUT verification...")
    with httpx.Client(verify=False) as client:
        resp = client.get("https://api.telegram.org")
        print(f"Success (Insecure)! Status: {resp.status_code}")
except Exception as e:
    print(f"Failed insecure: {e}")
