import requests
import time
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    print("Missing BOT_TOKEN")
    exit()

BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ===== GLOBAL STATE =====
users = set()

mode = "meme"
risk = "medium"
paused = False
cooldown = 300

watchlist = set()

last_price = {}
last_volume = {}
last_alert_time = {}
last_update_id = None

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
    for user in users:
        send(msg, user)

def get_updates():
    global last_update_id
    url = f"{BASE_URL}/getUpdates"
    params = {"timeout": 10}

    if last_update_id:
        params["offset"] = last_update_id + 1

    res = requests.get(url, params=params).json()
    return res.get("result", [])

# ===== DATA =====
def get_market():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "volume_desc",
        "per_page": 50,
        "page": 1
    }
    return requests.get(url, params=params).json()

# ===== SIGNAL LOGIC =====
def classify(change, price_jump, vol_jump, volume):
    entry = "MID"
    risk_flag = "LOW"
    action = "WATCH"

    if 3 < change < 12 and price_jump > 1 and vol_jump > 10:
        entry = "EARLY"
        action = "CONSIDER ENTRY"

    elif change > 20:
        entry = "LATE"
        risk_flag = "HIGH"
        action = "WAIT"

    if volume < 1_000_000:
        risk_flag = "LOW VOLUME"

    return entry, risk_flag, action

def analyze(coins):
    results = []

    for c in coins:
        try:
            cid = c["id"]
            name = c["name"]
            sym = c["symbol"].upper()
            price = c["current_price"]
            vol = c["total_volume"]
            change = c["price_change_percentage_24h"] or 0
            mc = c["market_cap"] or 0

            if not price or not vol:
                continue

            if mode == "meme" and mc > 5_000_000_000:
                continue
            if mode == "safe" and mc < 1_000_000_000:
                continue

            p0 = last_price.get(cid)
            v0 = last_volume.get(cid)

            price_jump = ((price - p0) / p0 * 100) if p0 else 0
            vol_jump = ((vol - v0) / v0 * 100) if v0 else 0

            score = 0

            if vol > 5_000_000: score += 2
            elif vol > 2_000_000: score += 1

            if change > 15: score += 2
            elif change > 5: score += 1

            if price_jump > 2: score += 1
            if vol_jump > 25: score += 1

            if risk == "low" and score < 4:
                continue
            if risk == "medium" and score < 3:
                continue

            results.append({
                "id": cid,
                "name": name,
                "symbol": sym,
                "price": price,
                "change": change,
                "volume": vol,
                "price_jump": price_jump,
                "vol_jump": vol_jump,
                "score": score
            })

            last_price[cid] = price
            last_volume[cid] = vol

        except:
            continue

    return sorted(results, key=lambda x: x["score"], reverse=True)

# ===== FORMAT =====
def format_signals(signals):
    if not signals:
        return "No signals"

    msg = "🚀 SMART SIGNALS\n\n"

    for s in signals[:5]:
        entry, risk_flag, action = classify(
            s["change"],
            s["price_jump"],
            s["vol_jump"],
            s["volume"]
        )

        msg += f"{s['name']} ({s['symbol']})\n"
        msg += f"💰 ${s['price']}\n"
        msg += f"📈 {s['change']:.2f}%\n"
        msg += f"📊 Vol: ${s['volume']:,}\n\n"

        msg += f"🎯 Entry: {entry}\n"
        msg += f"⚠️ Risk: {risk_flag}\n"
        msg += f"📊 Action: {action}\n"
        msg += f"⭐ Score: {s['score']}\n\n"

    return msg

# ===== COMMANDS =====
def handle_command(text, chat_id):
    global mode, risk, paused, cooldown

    parts = text.lower().split()

    if text == "/start":
        send("Bot activated 🚀", chat_id)

    elif text == "/scan":
        coins = get_market()
        signals = analyze(coins)
        send(format_signals(signals), chat_id)

    elif text.startswith("/coin"):
        if len(parts) < 2:
            send("Usage: /coin btc", chat_id)
            return

        target = parts[1]
        coins = get_market()

        for c in coins:
            if c["symbol"] == target or c["id"] == target:
                send(f"{c['name']} ${c['current_price']}\n24h: {c['price_change_percentage_24h']:.2f}%", chat_id)
                return

        send("Coin not found", chat_id)

    elif text.startswith("/add"):
        if len(parts) < 2: return
        watchlist.add(parts[1])
        send("Added", chat_id)

    elif text.startswith("/remove"):
        if len(parts) < 2: return
        watchlist.discard(parts[1])
        send("Removed", chat_id)

    elif text == "/list":
        send("\n".join(watchlist) or "Empty", chat_id)

    elif text.startswith("/mode"):
        if len(parts) < 2: return
        mode = parts[1]
        send(f"Mode: {mode}", chat_id)

    elif text.startswith("/risk"):
        if len(parts) < 2: return
        risk = parts[1]
        send(f"Risk: {risk}", chat_id)

    elif text == "/pause":
        paused = True
        send("Paused", chat_id)

    elif text == "/resume":
        paused = False
        send("Resumed", chat_id)

    elif text == "/top":
        coins = get_market()
        signals = analyze(coins)
        send(format_signals(signals[:5]), chat_id)

# ===== MAIN LOOP =====
print("BOT RUNNING...")

while True:
    try:
        updates = get_updates()

        for u in updates:
            last_update_id = u["update_id"]
            message = u.get("message")

            if not message:
                continue

            text = message.get("text")
            chat_id = str(message["chat"]["id"])

            users.add(chat_id)

            if text:
                handle_command(text, chat_id)

        if not paused:
            coins = get_market()
            signals = analyze(coins)

            now = time.time()

            for s in signals[:3]:
                last = last_alert_time.get(s["id"], 0)

                if now - last < cooldown:
                    continue

                if watchlist and s["symbol"].lower() not in watchlist:
                    continue

                broadcast(format_signals([s]))
                last_alert_time[s["id"]] = now

        time.sleep(10)

    except Exception as e:
        print("Error:", e)
        time.sleep(5)
