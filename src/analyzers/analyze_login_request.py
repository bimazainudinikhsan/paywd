import json

def analyze_login_request(log_file):
    print(f"Analyzing {log_file} for login requests...")
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            logs = json.load(f)
            
        print(f"Total log entries: {len(logs)}")
        
        found_req = False
        
        for entry in logs:
            # Look for gameLogin request
            if entry.get('url', '').endswith('/auth/sys/gameLogin?l=id') and entry.get('type') == 'request':
                found_req = True
                print("\n[+] Found Login Request:")
                print(f"    Timestamp: {entry.get('timestamp')}")
                print(f"    Method: {entry.get('method')}")
                
                post_data_str = entry.get('postData')
                if not post_data_str:
                    print("    No postData found.")
                    continue
                    
                try:
                    post_data = json.loads(post_data_str)
                    
                    print("\n    [Credentials]")
                    print(f"    Username: {post_data.get('username')}")
                    print(f"    Password: {post_data.get('password')}")
                    print(f"    Access Type: {post_data.get('accessType')}")
                    print(f"    Access Code: {post_data.get('accessCode')}")
                    
                except json.JSONDecodeError:
                    print(f"    Error decoding postData JSON: {post_data_str}")
                    
        if not found_req:
            print("\n[-] No gameLogin request found in logs.")
            
    except Exception as e:
        print(f"Error reading log file: {e}")

if __name__ == "__main__":
    analyze_login_request('logs/network_logs.json')
