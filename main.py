import requests
import time
import os

print("Starting bot...")
time.sleep(3)

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    print("Missing BOT_TOKEN")
    while True:
        time.sleep(60)

BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

users = set()
mode = "balanced"
paused = False
cooldown = 300

last_price = {}
last_volume = {}
last_alert = {}
last_update_id = None

history = []

# ===== TELEGRAM =====
def send(msg, chat_id):
    try:
        requests.post(f"{BASE_URL}/sendMessage", data={
            "chat_id": chat_id,
            "text": msg
        }, timeout=10)
    except:
        pass

def broadcast(msg):
    for u in users:
        send(msg, u)

def get_updates():
    global last_update_id
    try:
        url = f"{BASE_URL}/getUpdates"
        params = {"timeout": 10}
        if last_update_id:
            params["offset"] = last_update_id + 1

        return requests.get(url, params=params, timeout=15).json().get("result", [])
    except:
        return []

# ===== MARKET =====
def get_market():
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "order": "volume_desc",
            "per_page": 50,
            "page": 1
        }
        res = requests.get(url, params=params, timeout=15)

        if res.status_code != 200:
            return []

        data = res.json()
        if not isinstance(data, list):
            return []

        return data

    except:
        return []

# ===== ANALYSIS =====
def analyze(coins):
    results = []

    for c in coins:
        try:
            cid = c.get("id")
            name = c.get("name")
            sym = c.get("symbol", "").upper()
            price = c.get("current_price")
            volume = c.get("total_volume")
            change = c.get("price_change_percentage_24h") or 0

            if not cid or not price or not volume:
                continue

            p0 = last_price.get(cid)
            v0 = last_volume.get(cid)

            price_jump = ((price - p0)/p0*100) if p0 else 0
            vol_jump = ((volume - v0)/v0*100) if v0 else 0

            score = 0

            # SIMPLE BUT EFFECTIVE
            if change > 5:
                score += 1
            if change > 10:
                score += 2

            if volume > 2_000_000:
                score += 2
            elif volume > 1_000_000:
                score += 1

            if price_jump > 1:
                score += 1

            if vol_jump > 10:
                score += 2

            if change > 30:
                score -= 2

            if mode == "safe" and score < 5: continue
            if mode == "balanced" and score < 4: continue
            if mode == "aggressive" and score < 3: continue

            results.append({
                "id": cid,
                "name": name,
                "symbol": sym,
                "price": price,
                "change": change,
                "score": score
            })

            last_price[cid] = price
            last_volume[cid] = volume

        except:
            continue

    return sorted(results, key=lambda x: x["score"], reverse=True)

# ===== FORMAT =====
def format_signals(signals):
    if not signals:
        return "No signals"

    msg = "🚀 SIGNALS\n\n"

    for s in signals[:5]:
        conf = min(100, int((s["score"]/7)*100))

        msg += f"{s['name']} ({s['symbol']})\n"
        msg += f"${s['price']} | {s['change']:.2f}%\n"
        msg += f"Confidence: {conf}%\n\n"

    return msg

# ===== COMMANDS =====
def handle(text, chat_id):
    global mode, paused

    parts = text.lower().split()

    if text == "/start":
        send("Bot ready 🚀", chat_id)

    elif text == "/scan":
        send(format_signals(analyze(get_market())), chat_id)

    elif text == "/top":
        send(format_signals(analyze(get_market())[:5]), chat_id)

    elif text.startswith("/mode"):
        if len(parts) > 1:
            mode = parts[1]
            send(f"Mode: {mode}", chat_id)

    elif text == "/pause":
        paused = True
        send("Paused", chat_id)

    elif text == "/resume":
        paused = False
        send("Resumed", chat_id)

# ===== MAIN LOOP =====
print("BOT RUNNING...")

while True:
    try:
        print("Loop alive...")

        updates = get_updates()

        for u in updates:
            last_update_id = u["update_id"]
            msg = u.get("message")

            if not msg:
                continue

            chat_id = str(msg["chat"]["id"])
            text = msg.get("text")

            users.add(chat_id)

            if text:
                handle(text, chat_id)

        if not paused:
            signals = analyze(get_market())
            now = time.time()

            for s in signals[:3]:
                last = last_alert.get(s["id"], 0)

                if now - last < cooldown:
                    continue

                broadcast(format_signals([s]))
                last_alert[s["id"]] = now

        time.sleep(15)

    except Exception as e:
        print("CRASH:", e)
        time.sleep(5)
