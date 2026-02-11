import json
import datetime

def analyze_logs(file_path):
    print(f"--- Analyzing {file_path} ---")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            logs = json.load(f)
    except FileNotFoundError:
        print(f"File not found: {file_path}")
        return

    deposit_requests = []
    status_checks = []

    for entry in logs:
        # Check for Deposit Creation (POST getYukkQris)
        if entry.get('url', '').endswith('getYukkQris?l=id') and entry.get('method') == 'POST':
            if entry.get('type') == 'response':
                try:
                    body = json.loads(entry.get('body', '{}'))
                    if body.get('success'):
                        result = body.get('result', {}).get('result', {})
                        order_id = result.get('order_id')
                        timestamp = entry.get('timestamp', 0) / 1000
                        dt_object = datetime.datetime.fromtimestamp(timestamp)
                        print(f"[{dt_object}] DEPOSIT CREATED: Order ID {order_id}")
                except:
                    pass

        # Check for Status Polling (GET queryOrderIsPayment)
        if 'queryOrderIsPayment' in entry.get('url', ''):
            if entry.get('type') == 'response':
                try:
                    url = entry.get('url')
                    # Extract Order ID from URL
                    order_id_query = url.split('orderId=')[1].split('&')[0]
                    
                    body = json.loads(entry.get('body', '{}'))
                    result = body.get('result', {})
                    status = result.get('orderStatus')
                    payment_time = result.get('paymentTime')
                    
                    timestamp = entry.get('timestamp', 0) / 1000
                    dt_object = datetime.datetime.fromtimestamp(timestamp)
                    
                    status_str = "PENDING" if status == 0 else "SUCCESS" if status == 1 else f"UNKNOWN ({status})"
                    
                    print(f"[{dt_object}] CHECK STATUS: {order_id_query} -> {status_str} (Status Code: {status})")
                    if payment_time:
                        print(f"    -> Payment Time: {payment_time}")
                except:
                    pass

if __name__ == "__main__":
    analyze_logs('logs/network_logs_1.json')
    analyze_logs('logs/network_logs_2.json')
