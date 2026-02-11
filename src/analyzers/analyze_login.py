import json
import base64
import datetime

def parse_jwt(token):
    try:
        # JWT is header.payload.signature
        parts = token.split('.')
        if len(parts) != 3:
            return "Invalid JWT format"
        
        # Padding for base64 decoding
        payload = parts[1]
        padded = payload + '=' * (4 - len(payload) % 4)
        decoded = base64.urlsafe_b64decode(padded)
        return json.loads(decoded)
    except Exception as e:
        return f"Error decoding JWT: {str(e)}"

def analyze_login_logs(log_file):
    print(f"Analyzing {log_file}...")
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            logs = json.load(f)
            
        print(f"Total log entries: {len(logs)}")
        
        found_login = False
        
        for entry in logs:
            # Look for gameLogin response
            if entry.get('url', '').endswith('/auth/sys/gameLogin?l=id') and entry.get('type') == 'response':
                found_login = True
                print("\n[+] Found Login Response:")
                print(f"    Timestamp: {entry.get('timestamp')}")
                print(f"    Status: {entry.get('status')}")
                
                body_str = entry.get('body')
                if not body_str:
                    print("    No body content found.")
                    continue
                    
                try:
                    body_json = json.loads(body_str)
                    
                    if body_json.get('success'):
                        result = body_json.get('result', {})
                        player_info = result.get('playerInfo', {})
                        token = result.get('token')
                        
                        print("\n    [Login Success]")
                        print(f"    Nickname: {player_info.get('nickName')}")
                        print(f"    Account ID: {player_info.get('accountId')}")
                        print(f"    Mobile: {player_info.get('mobile')}")
                        print(f"    Currency Code: {player_info.get('currencyCode')}")
                        print(f"    Currency Icon: {player_info.get('icon')}")
                        print(f"    Formatted Currency: {player_info.get('currencyCode')} ({player_info.get('icon')})")
                        print(f"    Email: {player_info.get('mailAddress')}")
                        
                        if token:
                            print(f"\n    [Token Analysis]")
                            print(f"    Token: {token[:20]}...{token[-20:]}")
                            decoded_token = parse_jwt(token)
                            print(f"    Decoded Payload: {decoded_token}")
                            
                            if isinstance(decoded_token, dict) and 'exp' in decoded_token:
                                exp_ts = decoded_token['exp']
                                exp_date = datetime.datetime.fromtimestamp(exp_ts)
                                print(f"    Token Expires: {exp_date}")
                    else:
                        print(f"    [Login Failed] Message: {body_json.get('message')}")
                        
                except json.JSONDecodeError:
                    print("    Error decoding response body JSON")
                    
        if not found_login:
            print("\n[-] No gameLogin response found in logs.")
            
    except Exception as e:
        print(f"Error reading log file: {e}")

if __name__ == "__main__":
    analyze_login_logs('logs/network_logs.json')
