import requests
import time
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    print("Missing BOT_TOKEN")
    exit()

BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ===== STATE =====
users = set()

mode = "balanced"   # aggressive / balanced / safe
paused = False
cooldown = 300

last_price = {}
last_volume = {}
last_alert = {}
last_update_id = None

# ===== TELEGRAM =====
def send(msg, chat_id):
    try:
        requests.post(f"{BASE_URL}/sendMessage", data={
            "chat_id": chat_id,
            "text": msg
        })
    except:
        pass

def broadcast(msg):
    for u in users:
        send(msg, u)

def get_updates():
    global last_update_id
    url = f"{BASE_URL}/getUpdates"
    params = {"timeout": 10}

    if last_update_id:
        params["offset"] = last_update_id + 1

    return requests.get(url, params=params).json().get("result", [])

# ===== MARKET =====
def get_market():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "volume_desc",
        "per_page": 50,
        "page": 1
    }
    return requests.get(url, params=params).json()

# ===== RSI =====
def get_rsi(cid):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{cid}/market_chart"
        data = requests.get(url, params={"vs_currency": "usd", "days": 1}).json()
        prices = [p[1] for p in data["prices"]]

        gains, losses = [], []
        for i in range(1, len(prices)):
            diff = prices[i] - prices[i-1]
            if diff > 0:
                gains.append(diff)
            else:
                losses.append(abs(diff))

        if not gains or not losses:
            return 50

        avg_gain = sum(gains)/len(gains)
        avg_loss = sum(losses)/len(losses)

        rs = avg_gain / avg_loss if avg_loss else 0
        return round(100 - (100/(1+rs)), 2)
    except:
        return 50

# ===== TREND =====
def get_trend(cid):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{cid}/market_chart"
        data = requests.get(url, params={"vs_currency": "usd", "days": 3}).json()
        prices = [p[1] for p in data["prices"]]

        short = sum(prices[-10:]) / 10
        long = sum(prices[-50:]) / 50

        return "UPTREND" if short > long else "DOWNTREND"
    except:
        return "UNKNOWN"

# ===== ANALYSIS =====
def analyze(coins):
    results = []

    for c in coins:
        try:
            cid = c["id"]
            name = c["name"]
            sym = c["symbol"].upper()
            price = c["current_price"]
            volume = c["total_volume"]
            change = c["price_change_percentage_24h"] or 0

            if not price or not volume:
                continue

            rsi = get_rsi(cid)
            trend = get_trend(cid)

            p0 = last_price.get(cid)
            v0 = last_volume.get(cid)

            price_jump = ((price - p0) / p0 * 100) if p0 else 0
            vol_jump = ((volume - v0) / v0 * 100) if v0 else 0

            score = 0

            # RSI
            if 30 <= rsi <= 65: score += 2
            elif rsi < 30: score += 1
            elif rsi > 75: score -= 1

            # Trend
            if trend == "UPTREND": score += 2
            else: score -= 1

            # Momentum
            if price_jump > 1: score += 1

            # Volume
            if vol_jump > 10: score += 2
            elif volume > 1_000_000: score += 1

            # Avoid late pumps
            if change > 35: score -= 2

            # MODE CONTROL
            if mode == "safe" and score < 5:
                continue
            if mode == "balanced" and score < 4:
                continue
            if mode == "aggressive" and score < 3:
                continue

            results.append({
                "id": cid,
                "name": name,
                "symbol": sym,
                "price": price,
                "change": change,
                "volume": volume,
                "score": score,
                "rsi": rsi,
                "trend": trend,
                "price_jump": price_jump,
                "vol_jump": vol_jump
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

    msg = "🚀 SMART SIGNALS\n\n"

    for s in signals[:5]:
        confidence = min(100, int((s["score"]/7)*100))

        msg += f"{s['name']} ({s['symbol']})\n"
        msg += f"💰 ${s['price']}\n"
        msg += f"📈 {s['change']:.2f}%\n"
        msg += f"📉 RSI: {s['rsi']}\n"
        msg += f"📈 Trend: {s['trend']}\n"
        msg += f"⚡ Confidence: {confidence}%\n"
        msg += f"⭐ Score: {s['score']}\n\n"

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

        time.sleep(10)

    except Exception as e:
        print("Error:", e)
        time.sleep(5)
