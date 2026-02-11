import json
import datetime

def analyze_wallet_logs(log_file):
    print(f"Analyzing {log_file} for wallet info...")
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            logs = json.load(f)
            
        print(f"Total log entries: {len(logs)}")
        
        found_wallet = False
        
        for entry in logs:
            # Look for getWalletInfo response
            if entry.get('url', '').endswith('/auth/playerInfo/getWalletInfo?l=id') and entry.get('type') == 'response':
                found_wallet = True
                print("\n[+] Found Wallet Info Response:")
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
                        money = result.get('money')
                        reward_money = result.get('rewardMoney')
                        
                        print("\n    [Wallet Balance]")
                        print(f"    Main Money: {money}")
                        print(f"    Reward Money: {reward_money}")
                        print(f"    Total Assets: {float(money) + float(reward_money):.3f}")
                        
                        # Add timestamp analysis if present in body
                        if 'timestamp' in body_json:
                             ts = body_json['timestamp'] / 1000 # Convert ms to seconds
                             dt = datetime.datetime.fromtimestamp(ts)
                             print(f"    Server Time: {dt}")

                    else:
                        print(f"    [Request Failed] Message: {body_json.get('message')}")
                        
                except json.JSONDecodeError:
                    print("    Error decoding response body JSON")
                    
        if not found_wallet:
            print("\n[-] No getWalletInfo response found in logs.")
            
    except Exception as e:
        print(f"Error reading log file: {e}")

if __name__ == "__main__":
    analyze_wallet_logs('logs/network_logs.json')
