import time
import json
import os
import base64
import datetime
# import requests  <-- Replaced with curl_cffi for SSL Fingerprint Bypass
from curl_cffi import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from webdriver_manager.chrome import ChromeDriverManager
from colorama import init, Fore, Style

import urllib3
import qrcode


# Initialize colorama
init(autoreset=True)

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Fix for webdriver_manager connection issues
os.environ['WDM_SSL_VERIFY'] = '0'

class WDBot:
    def __init__(self, username=None):
        self.driver = None
        self.token = None
        # Gunakan impersonate="chrome" agar TLS Fingerprint terlihat seperti browser asli
        self.session = requests.Session(impersonate="chrome")
        self.base_url = "https://wdbos.com/#/index?category=hot"
        self.api_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://wdbos.com",
            "Referer": "https://wdbos.com/",
            "X-Requested-With": "XMLHttpRequest"
        }
        
        self.current_username = username
        self.credentials_path = 'config/credentials.json'

        # Path untuk menyimpan profil browser agar login tersimpan (Auto Login)
        # Jika username ada, gunakan folder khusus agar tidak bentrok antar user
        profile_dir_name = f"chrome_data_{username}" if username else "chrome_data"
        self.profile_path = os.path.join(os.getcwd(), profile_dir_name)
        
        if not os.path.exists(self.profile_path):
            os.makedirs(self.profile_path)

    # ==========================================
    # MENU 1: SNIFFING (BROWSER)
    # ==========================================
    def start_browser(self):
        print(f"{Fore.YELLOW}[*] Memulai Browser Chrome...{Style.RESET_ALL}")
        
        # Setup Chrome options
        chrome_options = Options()
        chrome_options.add_argument("--log-level=3")  # Suppress logs
        chrome_options.add_argument("--start-maximized") # Maximize window
        
        # Stability & Network Fixes
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--ignore-certificate-errors")
        chrome_options.add_argument("--disable-gpu")
        
        # Enable Auto Login by using persistent profile
        print(f"{Fore.CYAN}[i] Menggunakan profil browser di: {self.profile_path}{Style.RESET_ALL}")
        chrome_options.add_argument(f"--user-data-dir={self.profile_path}")
        
        # Stealth settings to make it look "like ori"
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        
        # Enable performance logging to "snap network"
        chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
        
        try:
            self.driver = webdriver.Chrome(
                service=ChromeService(ChromeDriverManager().install()),
                options=chrome_options
            )
            print(f"{Fore.GREEN}[+] Browser berhasil dibuka!{Style.RESET_ALL}")
            return True
        except Exception as e:
            print(f"{Fore.RED}[!] Gagal membuka browser: {e}{Style.RESET_ALL}")
            return False

    def menu_sniffing(self):
        if not self.driver:
            if not self.start_browser():
                print(f"{Fore.RED}[!] Membatalkan login karena browser gagal dibuka.{Style.RESET_ALL}")
                return

        print(f"{Fore.CYAN}[i] Navigasi ke halaman login...{Style.RESET_ALL}")
        try:
            self.driver.get(self.base_url)
            
            print(f"\n{Fore.YELLOW}=== SNIFFING MODE ==={Style.RESET_ALL}")
            print("Browser telah dibuka. Silakan lakukan aktivitas (Login/Game).")
            print("Tekan Enter di sini untuk capture network logs saat ini.")
            input(f"{Fore.GREEN}Tekan Enter untuk SNAP NETWORK...{Style.RESET_ALL}")
            
            # Snap network logs
            self.snap_network()
            
            # Sync cookies to requests session
            if self.is_browser_alive():
                self.sync_cookies()
            else:
                print(f"{Fore.RED}[!] Browser sudah tertutup, tidak bisa sync cookies.{Style.RESET_ALL}")
            
        except Exception as e:
            print(f"{Fore.RED}[!] Error saat sniffing: {e}{Style.RESET_ALL}")

    def is_browser_alive(self):
        try:
            return len(self.driver.window_handles) > 0
        except Exception:
            return False

    def snap_network(self):
        print(f"{Fore.CYAN}[i] Snapping Network Logs...{Style.RESET_ALL}")
        if not self.is_browser_alive():
            print(f"{Fore.RED}[!] Browser tertutup. Tidak bisa mengambil log network.{Style.RESET_ALL}")
            return

        try:
            logs = self.driver.get_log('performance')
            captured_apis = []
            
            for entry in logs:
                try:
                    message = json.loads(entry['message'])['message']
                    method = message.get('method')

                    # Capture Responses
                    if method == 'Network.responseReceived':
                        resp = message['params']['response']
                        url = resp['url']
                        res_type = message['params'].get('type', 'Unknown')
                        
                        is_relevant = False
                        if res_type in ['XHR', 'Fetch', 'WebSocket']:
                            is_relevant = True
                        elif 'wdbos.com' in url or '24dgame.com' in url:
                            is_relevant = True
                        
                        if is_relevant:
                            request_id = message['params']['requestId']
                            response_body = None
                            try:
                                body_resp = self.driver.execute_cdp_cmd('Network.getResponseBody', {'requestId': request_id})
                                response_body = body_resp.get('body')
                            except Exception:
                                response_body = "<Body Not Available / Garbage Collected>"

                            captured_apis.append({
                                'type': 'response',
                                'resourceType': res_type,
                                'url': url,
                                'status': resp.get('status'),
                                'headers': resp.get('headers'),
                                'mimeType': resp.get('mimeType'),
                                'body': response_body,
                                'timestamp': entry.get('timestamp')
                            })
                    
                    # Capture Requests
                    elif method == 'Network.requestWillBeSent':
                        req = message['params']['request']
                        url = req['url']
                        res_type = message['params'].get('type', 'Unknown')
                        
                        is_relevant = False
                        if res_type in ['XHR', 'Fetch', 'WebSocket']:
                            is_relevant = True
                        elif 'wdbos.com' in url or '24dgame.com' in url:
                            is_relevant = True

                        if is_relevant:
                            post_data = req.get('postData')
                            if not post_data and 'postDataEntries' in req:
                                try:
                                    post_data = json.dumps(req['postDataEntries'])
                                except:
                                    post_data = str(req['postDataEntries'])

                            captured_apis.append({
                                'type': 'request',
                                'resourceType': res_type,
                                'url': url,
                                'method': req.get('method'),
                                'headers': req.get('headers'),
                                'postData': post_data,
                                'timestamp': entry.get('timestamp')
                            })
                    
                    # Capture WebSocket
                    elif method == 'Network.webSocketFrameSent':
                        payload = message['params']['response']['payloadData']
                        captured_apis.append({'type': 'ws_sent', 'payload': payload, 'timestamp': entry.get('timestamp')})
                    elif method == 'Network.webSocketFrameReceived':
                        payload = message['params']['response']['payloadData']
                        captured_apis.append({'type': 'ws_recv', 'payload': payload, 'timestamp': entry.get('timestamp')})

                except Exception:
                    pass
            
            if captured_apis:
                # Tentukan nama file log berikutnya (increment)
                log_index = 1
                while os.path.exists(f'logs/network_logs_{log_index}.json'):
                    log_index += 1
                
                log_filename = f'logs/network_logs_{log_index}.json'
                
                # Simpan ke file dengan nomor urut
                with open(log_filename, 'w', encoding='utf-8') as f:
                    json.dump(captured_apis, f, indent=4)
                
                # Simpan juga ke 'network_logs.json' sebagai yang terbaru (untuk kompatibilitas)
                with open('logs/network_logs.json', 'w', encoding='utf-8') as f:
                    json.dump(captured_apis, f, indent=4)

                print(f"{Fore.GREEN}[+] {len(captured_apis)} Log API disimpan ke '{log_filename}' (dan update 'network_logs.json'){Style.RESET_ALL}")
            else:
                print(f"{Fore.YELLOW}[!] Tidak ada log API yang tertangkap.{Style.RESET_ALL}")

        except Exception as e:
            print(f"{Fore.RED}[!] Gagal snap network: {e}{Style.RESET_ALL}")

    def sync_cookies(self):
        print(f"{Fore.CYAN}[i] Sinkronisasi Cookies ke Requests...{Style.RESET_ALL}")
        try:
            selenium_cookies = self.driver.get_cookies()
            cookie_file = f'data/cookies_{self.current_username}.json' if self.current_username else 'data/cookies.json'
            with open(cookie_file, 'w', encoding='utf-8') as f:
                json.dump(selenium_cookies, f, indent=4)
            
            local_storage = self.driver.execute_script("return window.localStorage;")
            ls_file = f'data/local_storage_{self.current_username}.json' if self.current_username else 'data/local_storage.json'
            with open(ls_file, 'w', encoding='utf-8') as f:
                json.dump(local_storage, f, indent=4)
            
            token = local_storage.get('token') or local_storage.get('X-Access-Token')
            if not token and 'wdbos.com' in local_storage:
                try:
                    wdbos_data = json.loads(local_storage['wdbos.com'])
                    token = wdbos_data.get('token')
                except: pass
            
            if token:
                 self.save_token(token)
                 print(f"{Fore.GREEN}[+] Token berhasil disinkronisasi dan disimpan.{Style.RESET_ALL}")
            
            for cookie in selenium_cookies:
                self.session.cookies.set(cookie['name'], cookie['value'])
        except Exception as e:
            print(f"{Fore.RED}[!] Gagal sync cookies: {e}{Style.RESET_ALL}")

    # ==========================================
    # HELPER: MULTI-USER MANAGEMENT
    # ==========================================
    def load_all_credentials(self):
        """Loads all credentials from credentials.json, migrating old format if needed."""
        if not os.path.exists(self.credentials_path):
            return []
        
        try:
            with open(self.credentials_path, 'r') as f:
                data = json.load(f)
            
            # Check if old format (dict) or new format (list of dicts or dict with 'users' key)
            if isinstance(data, dict):
                if 'users' in data:
                    return data['users']
                elif 'username' in data:
                    # Migrate old single user to list
                    return [data]
            elif isinstance(data, list):
                return data
            
            return []
        except Exception:
            return []

    def save_all_credentials(self, users):
        """Saves list of users to credentials.json in new format."""
        with open(self.credentials_path, 'w') as f:
            json.dump({'users': users}, f, indent=4)

    def get_user_by_username(self, username):
        users = self.load_all_credentials()
        for u in users:
            if u.get('username') == username:
                return u
        return None

    def update_user_credential(self, username, password, token=None, bot_token=None, admin_id=None):
        users = self.load_all_credentials()
        found = False
        for u in users:
            if u.get('username') == username:
                if password:
                    u['password'] = password
                if token:
                    u['token'] = token
                if bot_token is not None:
                    u['telegram_bot_token'] = bot_token
                if admin_id is not None:
                    u['telegram_admin_id'] = admin_id
                u['last_login'] = datetime.datetime.now().isoformat()
                found = True
                break
        
        if not found:
            new_user = {
                'username': username,
                'password': password,
                'token': token,
                'last_login': datetime.datetime.now().isoformat(),
                'telegram_bot_token': bot_token if bot_token else "",
                'telegram_admin_id': admin_id if admin_id else ""
            }
            users.append(new_user)
        
        self.save_all_credentials(users)

    # ==========================================
    # MENU 2: LOGIN API & TOKEN MANAGEMENT
    # ==========================================
    def save_token(self, token):
        self.token = token
        
        # Save to user-specific file if username exists, else legacy
        if self.current_username:
            with open(f'config/auth_token_{self.current_username}.txt', 'w') as f:
                f.write(token)
        else:
            with open('config/auth_token.txt', 'w') as f:
                f.write(token)
                
        self.session.headers.update({"X-Access-Token": token})
        
        # If we have a current user context, update their token in the list
        if self.current_username:
            # We need the password to update, let's try to find it or just update token
            users = self.load_all_credentials()
            for u in users:
                if u.get('username') == self.current_username:
                    u['token'] = token
                    u['last_login'] = datetime.datetime.now().isoformat()
                    self.save_all_credentials(users)
                    break

    def load_token(self):
        # Prioritize loading from current user context
        if self.current_username:
            user = self.get_user_by_username(self.current_username)
            if user and user.get('token'):
                self.token = user['token']
                self.session.headers.update({"X-Access-Token": self.token})
                return self.token
            
            # Check user-specific file
            token_path = f'config/auth_token_{self.current_username}.txt'
            if os.path.exists(token_path):
                with open(token_path, 'r') as f:
                    token = f.read().strip()
                if token:
                    self.token = token
                    self.session.headers.update({"X-Access-Token": token})
                    return token

        # Fallback to legacy file
        if os.path.exists('config/auth_token.txt'):
            with open('config/auth_token.txt', 'r') as f:
                token = f.read().strip()
            if token:
                self.token = token
                self.session.headers.update({"X-Access-Token": token})
                return token
        return None

    def parse_jwt(self, token):
        try:
            parts = token.split('.')
            if len(parts) != 3: return None
            payload = parts[1]
            padded = payload + '=' * (4 - len(payload) % 4)
            decoded = base64.urlsafe_b64decode(padded)
            return json.loads(decoded)
        except: return None

    def is_token_expired(self, token):
        payload = self.parse_jwt(token)
        if payload and 'exp' in payload:
            exp_ts = payload['exp']
            # Buffer 60 detik sebelum expired
            if datetime.datetime.now().timestamp() > (exp_ts - 60):
                return True
        return False

    def check_token_valid(self):
        """Checks if token exists, is a valid JWT, and is not expired."""
        if not self.token:
            return False
        # Ensure token is a valid JWT structure
        if not self.parse_jwt(self.token):
            return False
        # Check expiry
        return not self.is_token_expired(self.token)

    def login_api(self, username, password):
        print(f"{Fore.CYAN}[i] Mencoba login sebagai {username}...{Style.RESET_ALL}")
        
        # Clear existing cookies to prevent session bleeding
        self.session.cookies.clear()
        
        url = "https://wdbos.com/auth/sys/gameLogin?l=id"
        payload = {
            "accessCode": "",
            "accessType": 2,
            "username": username,
            "password": password,
            "randomCode": "",
            "redirectUrl": ""
        }
        
        try:
            # Set timeout to 60 seconds to avoid connection timeout
            resp = self.session.post(url, json=payload, headers=self.api_headers, timeout=60)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    if data.get('success'):
                        result = data.get('result', {})
                        token = result.get('token')
                        if token:
                            print(f"{Fore.GREEN}[+] Login Berhasil! Token didapatkan.{Style.RESET_ALL}")
                            self.current_username = username
                            self.update_user_credential(username, password, token)
                            self.save_token(token)
                            
                            # Simpan Profile Info (jika ada)
                            player_info = result.get('playerInfo', {})
                            if player_info:
                                print(f"{Fore.GREEN}[+] Selamat datang, {player_info.get('nickName')}!{Style.RESET_ALL}")
                                
                                # Simpan ke file spesifik user
                                profile_file = f'data/profile_{username}.json'
                                with open(profile_file, 'w') as f:
                                    json.dump(player_info, f, indent=4)
                                    
                                # Juga simpan ke global current_profile.json (hanya untuk backward compatibility/sniffing)
                                # Tapi hati-hati, ini bisa bikin conflict kalau multi-bot. 
                                # Sebaiknya dihindari untuk usage critical.
                                with open('data/current_profile.json', 'w') as f:
                                    json.dump(player_info, f, indent=4)

                            return True
                        else:
                            print(f"{Fore.RED}[!] Login sukses tapi tidak ada token.{Style.RESET_ALL}")
                    else:
                        print(f"{Fore.RED}[!] Login Gagal: {data.get('message')}{Style.RESET_ALL}")
                except json.JSONDecodeError:
                    print(f"{Fore.RED}[!] Error Login API: Respon bukan JSON valid.{Style.RESET_ALL}")
                    print(f"{Fore.YELLOW}Preview Respon: {resp.text[:500]}...{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}[!] HTTP Error: {resp.status_code}{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}Respon: {resp.text[:200]}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}[!] Error Login API: {e}{Style.RESET_ALL}")
        return False

    def ensure_logged_in(self):
        # 1. Cek Token di session/legacy
        token = self.load_token()
        
        if token:
            # 2. Cek Expired?
            if self.is_token_expired(token):
                print(f"{Fore.YELLOW}[!] Token expired. Mencoba auto-relogin...{Style.RESET_ALL}")
                
                # 3. Auto Login jika expired
                # Try to use current_username context first
                creds = None
                if self.current_username:
                    creds = self.get_user_by_username(self.current_username)
                
                # Fallback: try to find ANY valid credential if no current user but we have a token (legacy state)
                if not creds and not self.current_username:
                    users = self.load_all_credentials()
                    if users:
                        creds = users[0] # Just pick the first one

                if creds:
                    return self.login_api(creds['username'], creds['password'])
                else:
                    print(f"{Fore.RED}[!] Tidak ada credentials tersimpan untuk auto-login.{Style.RESET_ALL}")
                    return False
            else:
                # print(f"{Fore.GREEN}[+] Token valid.{Style.RESET_ALL}")
                return True
        else:
            print(f"{Fore.YELLOW}[!] Belum ada token. Silakan Login dulu.{Style.RESET_ALL}")
            return False

    def get_wallet_info(self):
        try:
            url = "https://wdbos.com/auth/playerInfo/getWalletInfo?l=id"
            resp = self.session.get(url, headers=self.api_headers)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('success'):
                    res = data.get('result', {})
                    money = float(res.get('money', 0))
                    reward = float(res.get('rewardMoney', 0))
                    return {"money": money, "reward": reward, "total": money + reward}
        except Exception:
            pass
        return None

    def menu_user_management(self):
        while True:
            print(f"\n{Fore.YELLOW}=== USER MANAGEMENT ==={Style.RESET_ALL}")
            if self.current_username:
                print(f"Aktif User: {Fore.GREEN}{self.current_username}{Style.RESET_ALL}")
            else:
                print(f"Aktif User: {Fore.RED}None{Style.RESET_ALL}")

            users = self.load_all_credentials()
            print("\nSaved Users:")
            for idx, u in enumerate(users):
                mark = "*" if u['username'] == self.current_username else " "
                print(f"{idx+1}. [{mark}] {u['username']}")

            print("\nOptions:")
            print("1. Login Baru / Tambah User")
            print("2. Ganti User (Switch)")
            print("3. Kembali ke Main Menu")
            
            choice = input("Pilih: ")
            
            if choice == '1':
                user = input("Username: ")
                pwd = input("Password: ")
                self.login_api(user, pwd)
            elif choice == '2':
                if not users:
                    print(f"{Fore.RED}[!] Belum ada user tersimpan.{Style.RESET_ALL}")
                    continue
                try:
                    idx = int(input("Pilih nomor user: ")) - 1
                    if 0 <= idx < len(users):
                        selected = users[idx]
                        print(f"{Fore.CYAN}[i] Switching to {selected['username']}...{Style.RESET_ALL}")
                        self.current_username = selected['username']
                        
                        # Clear cookies for clean switch
                        self.session.cookies.clear()
                        
                        # Try to use saved token first
                        if selected.get('token') and not self.is_token_expired(selected['token']):
                            self.save_token(selected['token'])
                            print(f"{Fore.GREEN}[+] Token restored.{Style.RESET_ALL}")
                        else:
                            print(f"{Fore.YELLOW}[!] Token expired/missing, re-logging in...{Style.RESET_ALL}")
                            self.login_api(selected['username'], selected['password'])
                    else:
                        print(f"{Fore.RED}[!] Pilihan tidak valid.{Style.RESET_ALL}")
                except ValueError:
                    print(f"{Fore.RED}[!] Input harus angka.{Style.RESET_ALL}")
            elif choice == '3':
                break
            else:
                print("Pilihan tidak valid.")

    # ==========================================
    # MENU 3: ANALYZE DATA (LIVE SESSION)
    # ==========================================
    def run_analysis(self):
        print(f"\n{Fore.YELLOW}=== ANALISIS DATA (LIVE SESSION) ==={Style.RESET_ALL}")
        
        # Cek apakah user sudah login (punya token valid)
        if not self.ensure_logged_in():
             return

        # --- 1. Info Kredensial ---
        print(f"\n{Fore.CYAN}--- Info Kredensial (User Login) ---{Style.RESET_ALL}")
        if self.current_username:
             print(f"Username Aktif: {self.current_username}")
        else:
             print("Username Aktif: Unknown (Legacy Session)")

        # --- 2. Info Profil User (Dari current_profile.json + Token + Live Base Info) ---
        print(f"\n{Fore.CYAN}--- Info Profil User ---{Style.RESET_ALL}")
        
        # Fetch Live Base Info (untuk Real Name & Bank)
        base_info_result = {}
        real_name = '-'
        try:
            url = "https://wdbos.com/auth/commonpay/pay/common/getPlayerBaseInfo?l=id"
            resp = self.session.get(url, headers=self.api_headers)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('success'):
                    base_info_result = data.get('result', {})
                    attach_list = base_info_result.get('attachInfoList', [])
                    if attach_list:
                        for item in attach_list:
                            if item.get('realName'):
                                real_name = item.get('realName')
                                break
        except Exception as e:
            print(f"{Fore.RED}[!] Gagal fetch base info: {e}{Style.RESET_ALL}")

        if os.path.exists('data/current_profile.json'):
            try:
                with open('data/current_profile.json', 'r') as f:
                    pInfo = json.load(f)
                print(f"Nickname : {pInfo.get('nickName')}")
                print(f"Full Name: {real_name}")
                print(f"Email    : {pInfo.get('mailAddress')}")
                print(f"Mobile   : {pInfo.get('mobile')}")
                print(f"Currency : {pInfo.get('currencyCode')} ({pInfo.get('icon')})")
            except Exception as e:
                print(f"{Fore.RED}[!] Gagal baca current_profile.json: {e}{Style.RESET_ALL}")
        else:
            print(f"{Fore.YELLOW}[-] File current_profile.json tidak ditemukan.{Style.RESET_ALL}")
        
        # Info Token Exp
        if self.token:
            jwt_data = self.parse_jwt(self.token)
            if jwt_data and 'exp' in jwt_data:
                dt = datetime.datetime.fromtimestamp(jwt_data['exp'])
                print(f"Token Exp: {dt}")

        # --- 3. Info Bank (Live Fetch) ---
        print(f"\n{Fore.CYAN}--- Info Bank Penarikan ---{Style.RESET_ALL}")
        if base_info_result:
            attach_list = base_info_result.get('attachInfoList', [])
            if attach_list:
                for bank in attach_list:
                    print(f"Bank Name : {bank.get('bankName')}")
                    print(f"Bank Code : {bank.get('bankCode')}")
                    # print(f"Acc Name  : {bank.get('realName')}") 
                    print("-" * 20)
            else:
                print(f"{Fore.YELLOW}[-] Belum ada data bank tersimpan.{Style.RESET_ALL}")
        else:
            print(f"{Fore.YELLOW}[!] Data bank tidak tersedia (gagal fetch base info).{Style.RESET_ALL}")

        # --- 4. Info Wallet (Live Fetch) ---
        print(f"\n{Fore.CYAN}--- Info Wallet (Live Fetch) ---{Style.RESET_ALL}")
        try:
            url = "https://wdbos.com/auth/playerInfo/getWalletInfo?l=id"
            resp = self.session.get(url, headers=self.api_headers)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('success'):
                    res = data.get('result', {})
                    money = float(res.get('money', 0))
                    reward = float(res.get('rewardMoney', 0))
                    print(f"Main Money   : {money}")
                    print(f"Reward Money : {reward}")
                    print(f"Total Aset   : {money + reward:.3f}")
                else:
                    print(f"{Fore.RED}[!] Gagal fetch wallet: {data.get('message')}{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}[!] Gagal fetch wallet (Status {resp.status_code}){Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}[!] Error fetch wallet: {e}{Style.RESET_ALL}")

    # ==========================================
    # MENU 4: DEPOSIT (QRIS)
    # ==========================================
    def menu_deposit(self):
        print(f"\n{Fore.YELLOW}=== MENU DEPOSIT (QRIS) ==={Style.RESET_ALL}")
        
        if not self.ensure_logged_in():
            return

        if self.current_username:
             print(f"Processing Deposit for: {Fore.GREEN}{self.current_username}{Style.RESET_ALL}")

        # 1. Get Active QRIS Type & Status
        qris_type = "P2M" # Default fallback
        is_online = False
        
        try:
            print(f"{Fore.YELLOW}[i] Mengecek status QRIS Server...{Style.RESET_ALL}")
            url_active = "https://wdbos.com/auth/commonpay/ida/common/getQrisActive?l=id"
            resp = self.session.get(url_active, headers=self.api_headers)
            
            if resp.status_code == 200:
                data = resp.json()
                if data.get('success'):
                    result_type = data.get('result')
                    if result_type:
                        qris_type = result_type
                        is_online = True
                        print(f"{Fore.GREEN}[OK] STATUS QRIS: ONLINE (Tipe: {qris_type}){Style.RESET_ALL}")
                    else:
                         print(f"{Fore.RED}[!] STATUS QRIS: OFFLINE (Server tidak mengembalikan tipe QRIS){Style.RESET_ALL}")
                else:
                     print(f"{Fore.RED}[!] STATUS QRIS: OFFLINE (API Success False: {data.get('message')}){Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}[!] STATUS QRIS: OFFLINE (HTTP {resp.status_code}){Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}[!] Gagal cek QRIS Active: {e}. Mengasumsikan OFFLINE/Default P2M.{Style.RESET_ALL}")

        if not is_online:
            print(f"{Fore.RED}[WARNING] QRIS sedang gangguan atau tidak aktif. Deposit mungkin gagal.{Style.RESET_ALL}")
            confirm = input("Tetap lanjutkan? (y/n): ")
            if confirm.lower() != 'y':
                return

        # 2. Input Nominal
        print("Masukkan jumlah deposit (Contoh: 50000).")
        try:
            nominal_input = input("Nominal: ")
            nominal = int(nominal_input)
        except ValueError:
            print(f"{Fore.RED}[!] Nominal harus angka.{Style.RESET_ALL}")
            return

        # 3. Send Deposit Request
        print(f"{Fore.CYAN}[i] Memproses deposit sebesar Rp {nominal:,} ...{Style.RESET_ALL}")
        url_deposit = "https://wdbos.com/auth/commonpay/ida/common/getYukkQris?l=id"
        payload = {
            "nominal": nominal,
            "qrisType": qris_type
        }

        try:
            resp = self.session.post(url_deposit, json=payload, headers=self.api_headers)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('success'):
                    result = data.get('result', {})
                    inner_res = result.get('result', {})
                    
                    order_id = inner_res.get('order_id')
                    timeout = inner_res.get('timeout_datetime')
                    qris_string = inner_res.get('qris_string')
                    
                    print(f"\n{Fore.GREEN}[+] DEPOSIT BERHASIL DIBUAT!{Style.RESET_ALL}")
                    print(f"Order ID       : {order_id}")
                    print(f"Batas Waktu    : {timeout}")
                    print(f"Nominal        : Rp {nominal:,}")
                    print(f"\n{Fore.YELLOW}QRIS STRING (Copy dan generate QR Code):{Style.RESET_ALL}")
                    print(f"{qris_string}")
                    
                    # Generate and Print QR Code ASCII
                    print(f"\n{Fore.CYAN}=== QR CODE ==={Style.RESET_ALL}")
                    try:
                        qr = qrcode.QRCode()
                        qr.add_data(qris_string)
                        qr.print_ascii(invert=True)
                    except Exception as e:
                         print(f"{Fore.RED}[!] Gagal menampilkan QR Code di terminal: {e}{Style.RESET_ALL}")

                    # 4. Auto Check Status (300s Timeout)
                    print(f"\n{Fore.YELLOW}[i] Menunggu pembayaran masuk... (Timeout 300 detik){Style.RESET_ALL}")
                    start_time = time.time()
                    timeout_duration = 300
                    
                    while (time.time() - start_time) < timeout_duration:
                        try:
                            url_status = f"https://wdbos.com/auth/commonpay/ida/common/queryOrderIsPayment?l=id&orderId={order_id}"
                            resp_status = self.session.get(url_status, headers=self.api_headers)
                            
                            if resp_status.status_code == 200:
                                data_status = resp_status.json()
                                res_status = data_status.get('result', {})
                                
                                order_status = res_status.get('orderStatus')
                                real_amount = res_status.get('realAmount')
                                
                                # Status 0 = Pending
                                # Status 1 (or others) = Success
                                
                                timestamp = datetime.datetime.now().strftime("%H:%M:%S")
                                
                                if order_status == 0:
                                    print(f"[{timestamp}] Status: PENDING (Belum dibayar)...")
                                else:
                                    print(f"\n{Fore.GREEN}[SUCCESS] PEMBAYARAN DITERIMA!{Style.RESET_ALL}")
                                    print(f"Status Code : {order_status}")
                                    print(f"Jumlah Masuk: {real_amount}")
                                    print(f"Waktu Bayar : {res_status.get('paymentTime')}")
                                    break
                            else:
                                print(f"{Fore.RED}[!] Gagal cek status (HTTP {resp_status.status_code}){Style.RESET_ALL}")
                            
                            time.sleep(5)
                            
                        except KeyboardInterrupt:
                            print(f"\n{Fore.YELLOW}[!] Pemantauan dihentikan oleh user.{Style.RESET_ALL}")
                            break
                        except Exception as e:
                            print(f"{Fore.RED}[!] Error monitoring: {e}{Style.RESET_ALL}")
                            time.sleep(5)
                    else:
                        # Loop finished without break (Timeout)
                        print(f"\n{Fore.RED}[!] Waktu habis! Pembayaran belum terdeteksi dalam 300 detik.{Style.RESET_ALL}")
                        print(f"{Fore.YELLOW}Silakan lakukan deposit ulang jika sudah transfer namun belum masuk.{Style.RESET_ALL}")

                else:
                     print(f"{Fore.RED}[!] Deposit Gagal: {data.get('message')}{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}[!] HTTP Error: {resp.status_code}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}[!] Error request deposit: {e}{Style.RESET_ALL}")

def main():
    bot = WDBot()
    while True:
        print(f"\n{Fore.MAGENTA}=== WDBOS BOT MAIN MENU ==={Style.RESET_ALL}")
        if bot.current_username:
             print(f"User: {Fore.GREEN}{bot.current_username}{Style.RESET_ALL}")
        else:
             print(f"User: {Fore.RED}None{Style.RESET_ALL}")

        print("1. Sniffing (Browser & Capture Logs)")
        print("2. User Management (Login/Switch)")
        print("3. Baca Data Analisis (Log & Live)")
        print("4. Deposit (QRIS)")
        print("5. Keluar")
        
        choice = input("Pilih menu (1-5): ")
        
        if choice == '1':
            bot.menu_sniffing()
        elif choice == '2':
            bot.menu_user_management()
        elif choice == '3':
            bot.run_analysis()
        elif choice == '4':
            bot.menu_deposit()
        elif choice == '5':
            print("Bye!")
            if bot.driver:
                bot.driver.quit()
            break
        else:
            print("Pilihan tidak valid.")

if __name__ == "__main__":
    main()
