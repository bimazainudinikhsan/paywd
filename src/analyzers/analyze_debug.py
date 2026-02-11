import json
import os
from colorama import init, Fore, Style

# Initialize colorama
init(autoreset=True)

def analyze_network_logs():
    print(f"{Fore.CYAN}=== ANALISIS NETWORK LOGS ==={Style.RESET_ALL}")
    
    if not os.path.exists('logs/network_logs.json'):
        print(f"{Fore.RED}[!] File 'network_logs.json' tidak ditemukan.{Style.RESET_ALL}")
        return

    try:
        with open('logs/network_logs.json', 'r', encoding='utf-8') as f:
            logs = json.load(f)
        
        print(f"{Fore.GREEN}[+] Memuat {len(logs)} log network.{Style.RESET_ALL}")
        
        found_token = False
        api_endpoints = set()
        
        for entry in logs:
            if entry.get('type') == 'request':
                url = entry.get('url', '')
                method = entry.get('method', '')
                headers = entry.get('headers', {})
                
                # Filter hanya API wdbos
                if 'wdbos.com' in url:
                    # Bersihkan URL parameter untuk grouping
                    base_url = url.split('?')[0]
                    api_endpoints.add(f"{method} {base_url}")
                
                # Cek Token
                x_access_token = headers.get('X-Access-Token')
                authorization = headers.get('Authorization')
                
                if x_access_token and x_access_token != "":
                    print(f"{Fore.GREEN}[!!!] FOUND X-Access-Token di URL: {url}{Style.RESET_ALL}")
                    print(f"{Fore.YELLOW}Token: {x_access_token}{Style.RESET_ALL}")
                    found_token = True
                    
                if authorization and authorization != "":
                    print(f"{Fore.GREEN}[!!!] FOUND Authorization di URL: {url}{Style.RESET_ALL}")
                    print(f"{Fore.YELLOW}Token: {authorization}{Style.RESET_ALL}")
                    found_token = True

        print(f"\n{Fore.CYAN}[i] Endpoint API yang terdeteksi:{Style.RESET_ALL}")
        for endpoint in sorted(api_endpoints):
            print(f" - {endpoint}")
            
        if not found_token:
             print(f"\n{Fore.RED}[!] TIDAK DITEMUKAN token non-kosong di network logs.{Style.RESET_ALL}")
             print(f"{Fore.YELLOW}    Kemungkinan login belum berhasil saat log dicapture, atau token dikirim via body (jarang).{Style.RESET_ALL}")

    except Exception as e:
        print(f"{Fore.RED}[!] Error membaca network logs: {e}{Style.RESET_ALL}")

def analyze_local_storage():
    print(f"\n{Fore.CYAN}=== ANALISIS LOCAL STORAGE ==={Style.RESET_ALL}")
    
    if not os.path.exists('data/local_storage.json'):
        print(f"{Fore.RED}[!] File 'local_storage.json' tidak ditemukan.{Style.RESET_ALL}")
        return

    try:
        with open('data/local_storage.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        # Cek root keys
        print(f"{Fore.BLUE}[i] Root keys: {list(data.keys())}{Style.RESET_ALL}")
        
        # Cek khusus key 'wdbos.com' yang sepertinya berisi nested JSON
        if 'wdbos.com' in data:
            print(f"{Fore.CYAN}[i] Menganalisis key 'wdbos.com'...{Style.RESET_ALL}")
            try:
                inner_data = json.loads(data['wdbos.com'])
                
                # Cari keyword token di dalam nested json
                keys_to_check = ['token', 'accessToken', 'user', 'session', 'auth']
                found_in_inner = False
                
                for k, v in inner_data.items():
                    print(f"  - Found key: {k}")
                    if any(x in k.lower() for x in keys_to_check):
                        print(f"{Fore.GREEN}    [POTENTIAL MATCH] {k}: {str(v)[:100]}...{Style.RESET_ALL}")
                        found_in_inner = True
                
                if not found_in_inner:
                    print(f"{Fore.YELLOW}    Tidak ditemukan keyword umum (token, auth, user) di level 1 nested JSON.{Style.RESET_ALL}")
                    
            except json.JSONDecodeError:
                print(f"{Fore.RED}[!] Key 'wdbos.com' bukan valid JSON string.{Style.RESET_ALL}")
        
        # Cek token di root
        token_candidates = [k for k in data.keys() if 'token' in k.lower() or 'auth' in k.lower()]
        if token_candidates:
            print(f"{Fore.GREEN}[+] Kandidat token di root storage: {token_candidates}{Style.RESET_ALL}")
            for k in token_candidates:
                print(f"    {k}: {data[k]}")
        else:
            print(f"{Fore.YELLOW}[!] Tidak ditemukan keyword 'token'/'auth' di root storage.{Style.RESET_ALL}")

    except Exception as e:
        print(f"{Fore.RED}[!] Error membaca local storage: {e}{Style.RESET_ALL}")

if __name__ == "__main__":
    analyze_network_logs()
    analyze_local_storage()
