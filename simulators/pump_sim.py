import requests
import time

APP_URL = "http://localhost:8000/transactions"

sample_tx = {
    "terminal_id": "pump_sim_1",
    "items": [{"name": "Fuel 95", "qty": 1, "price": 500.0}],
    "subtotal": 500.0,
    "tax": 0.0,
    "total": 500.0,
    "payment_method": "cash",
    "member_id": None
}


def run_once():
    try:
        r = requests.post(APP_URL, json=sample_tx, timeout=5)
        print('Posted sample tx:', r.status_code, r.text)
    except Exception as e:
        print('Error posting to app:', e)


if __name__ == '__main__':
    # send a sample transaction every 10 seconds
    while True:
        run_once()
        time.sleep(10)
