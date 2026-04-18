import requests
import time
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = str(os.getenv("CHAT_ID"))

if not BOT_TOKEN or not CHAT_ID:
    print("Missing BOT_TOKEN or CHAT_ID")
    exit()

BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ===== SETTINGS =====
mode = "meme"        # meme / safe
risk = "medium"      # low / medium / high
paused = False
cooldown = 300

watchlist = set()

last_price = {}
last_volume = {}
last_alert_time = {}
last_update_id = None

# ===== TELEGRAM =====
def send(msg):
    requests.post(f"{BASE_URL}/sendMessage", data={
        "chat_id": CHAT_ID,
        "text": msg
    })

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

# ===== SIGNAL ENGINE =====
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

            # MODE FILTER
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

            # RISK FILTER
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
                "score": score
            })

            last_price[cid] = price
            last_volume[cid] = vol

        except:
            continue

    return sorted(results, key=lambda x: x["score"], reverse=True)

# ===== COMMAND HANDLER =====
def handle_command(text):
    global mode, risk, paused, cooldown

    parts = text.lower().split()

    if text == "/scan":
        coins = get_market()
        signals = analyze(coins)
        send(format_signals(signals))

    elif text.startswith("/coin"):
        if len(parts) < 2:
            send("Usage: /coin btc")
            return

        target = parts[1]
        coins = get_market()

        for c in coins:
            if c["symbol"] == target or c["id"] == target:
                send(f"{c['name']} (${c['current_price']})\n24h: {c['price_change_percentage_24h']:.2f}%")
                return

        send("Coin not found")

    elif text.startswith("/add"):
        if len(parts) < 2:
            return
        watchlist.add(parts[1])
        send(f"Added {parts[1]}")

    elif text.startswith("/remove"):
        if len(parts) < 2:
            return
        watchlist.discard(parts[1])
        send(f"Removed {parts[1]}")

    elif text == "/list":
        send("Watchlist:\n" + "\n".join(watchlist) if watchlist else "Empty")

    elif text.startswith("/mode"):
        if len(parts) < 2:
            return
        mode = parts[1]
        send(f"Mode set to {mode}")

    elif text.startswith("/risk"):
        if len(parts) < 2:
            return
        risk = parts[1]
        send(f"Risk set to {risk}")

    elif text.startswith("/cooldown"):
        if len(parts) < 2:
            return
        cooldown = int(parts[1])
        send(f"Cooldown set to {cooldown}s")

    elif text == "/pause":
        paused = True
        send("Paused")

    elif text == "/resume":
        paused = False
        send("Resumed")

    elif text == "/top":
        coins = get_market()
        signals = analyze(coins)
        send(format_signals(signals[:5]))

# ===== FORMAT =====
def format_signals(signals):
    if not signals:
        return "No signals"

    msg = "🚀 SIGNALS\n\n"
    for s in signals[:5]:
        msg += f"{s['name']} ({s['symbol']})\n"
        msg += f"${s['price']} | {s['change']:.2f}%\n"
        msg += f"Score: {s['score']}\n\n"

    return msg

# ===== MAIN LOOP =====
print("BOT RUNNING...")

while True:
    try:
        # HANDLE COMMANDS
        updates = get_updates()
        for u in updates:
            last_update_id = u["update_id"]
            text = u.get("message", {}).get("text")

            if text and str(u["message"]["chat"]["id"]) == CHAT_ID:
                handle_command(text)

        # AUTO SIGNALS
        if not paused:
            coins = get_market()
            signals = analyze(coins)

            now = time.time()

            for s in signals[:3]:
                last = last_alert_time.get(s["id"], 0)

                if now - last < cooldown:
                    continue

                # watchlist filter
                if watchlist and s["symbol"].lower() not in watchlist:
                    continue

                send(format_signals([s]))
                last_alert_time[s["id"]] = now

        time.sleep(30)

    except Exception as e:
        print("Error:", e)
        time.sleep(10)
