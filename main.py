import requests
import time
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

users = set()
mode = "balanced"
paused = False
cooldown = 300

last_price = {}
last_volume = {}
last_alert = {}
last_update_id = None

# CACHE
cache = {}
CACHE_TIME = 60

history = []

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

# ===== RSI (MULTI TIMEFRAME) =====
def get_rsi_multi(cid):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{cid}/market_chart"
        data = requests.get(url, params={"vs_currency":"usd","days":1}).json()
        prices = [p[1] for p in data["prices"]]

        gains, losses = [], []
        for i in range(1,len(prices)):
            diff = prices[i]-prices[i-1]
            if diff>0: gains.append(diff)
            else: losses.append(abs(diff))

        if not gains or not losses:
            return 50

        avg_gain = sum(gains)/len(gains)
        avg_loss = sum(losses)/len(losses)

        rs = avg_gain/avg_loss if avg_loss else 0
        return round(100-(100/(1+rs)),2)
    except:
        return 50

def cached_rsi(cid):
    now = time.time()
    if cid in cache and now - cache[cid]["time"] < CACHE_TIME:
        return cache[cid]["rsi"]

    val = get_rsi_multi(cid)
    cache[cid] = {"rsi": val, "time": now}
    return val

# ===== EMA TREND =====
def get_trend(cid):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{cid}/market_chart"
        data = requests.get(url, params={"vs_currency":"usd","days":2}).json()
        prices = [p[1] for p in data["prices"]]

        ema20 = sum(prices[-20:])/20
        ema50 = sum(prices[-50:])/50

        return "UPTREND" if ema20 > ema50 else "DOWNTREND"
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

            rsi = cached_rsi(cid)
            trend = get_trend(cid)

            p0 = last_price.get(cid)
            v0 = last_volume.get(cid)

            price_jump = ((price - p0)/p0*100) if p0 else 0
            vol_jump = ((volume - v0)/v0*100) if v0 else 0

            score = 0

            if 35 <= rsi <= 60: score += 2
            elif rsi < 30: score += 1
            elif rsi > 70: score -= 1

            if trend == "UPTREND": score += 2
            else: score -= 1

            if price_jump > 1: score += 1

            if vol_jump > 10: score += 2
            elif volume > 1_000_000: score += 1

            if change > 30: score -= 2

            if mode == "safe" and score < 5: continue
            if mode == "balanced" and score < 4: continue
            if mode == "aggressive" and score < 3: continue

            results.append({
                "id": cid,
                "name": name,
                "symbol": sym,
                "price": price,
                "change": change,
                "volume": volume,
                "score": score,
                "rsi": rsi,
                "trend": trend
            })

            last_price[cid] = price
            last_volume[cid] = volume

        except:
            continue

    return sorted(results, key=lambda x: x["score"], reverse=True)

# ===== DEX =====
def get_dex():
    url = "https://api.dexscreener.com/latest/dex/pairs/solana"
    try:
        return requests.get(url).json().get("pairs", [])
    except:
        return []

def analyze_dex(pairs):
    results = []
    for p in pairs[:50]:
        try:
            name = p["baseToken"]["name"]
            symbol = p["baseToken"]["symbol"]
            price = float(p.get("priceUsd",0))
            volume = float(p.get("volume",{}).get("h24",0))
            liquidity = float(p.get("liquidity",{}).get("usd",0))
            change = float(p.get("priceChange",{}).get("h24",0))

            if liquidity < 50000: continue
            if volume < 100000: continue
            if change > 80 or change < 5: continue

            score = 0
            if volume > 200000: score += 2
            if change > 10: score += 2
            if liquidity > 100000: score += 1

            if score >= 3:
                results.append({
                    "name": name,
                    "symbol": symbol,
                    "price": price,
                    "change": change,
                    "volume": volume,
                    "liquidity": liquidity,
                    "score": score
                })
        except:
            continue

    return sorted(results, key=lambda x: x["score"], reverse=True)

# ===== FORMAT =====
def format_signals(signals):
    if not signals: return "No signals"

    msg = "🚀 SIGNALS\n\n"
    for s in signals[:5]:
        conf = min(100, int((s["score"]/7)*100))
        msg += f"{s['name']} ({s['symbol']})\n"
        msg += f"${s['price']} | {s['change']:.2f}%\n"
        msg += f"RSI: {s['rsi']} | {s['trend']}\n"
        msg += f"Confidence: {conf}%\n\n"
    return msg

def format_dex(signals):
    if not signals: return "No DEX signals"

    msg = "🔥 DEX SIGNALS\n\n"
    for s in signals[:5]:
        msg += f"{s['name']} ({s['symbol']})\n"
        msg += f"${s['price']} | {s['change']:.2f}%\n"
        msg += f"Liq: {s['liquidity']}\n\n"
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

    elif text == "/dex":
        send(format_dex(analyze_dex(get_dex())), chat_id)

    elif text.startswith("/mode"):
        if len(parts)>1:
            mode = parts[1]
            send(f"Mode: {mode}", chat_id)

    elif text == "/pause":
        paused = True
        send("Paused", chat_id)

    elif text == "/resume":
        paused = False
        send("Resumed", chat_id)

    elif text == "/history":
        msg = "Recent Signals\n\n"
        for h in history[-5:]:
            msg += f"{h['coin']} @ {h['price']}\n"
        send(msg, chat_id)

# ===== MAIN =====
print("BOT RUNNING...")

while True:
    try:
        updates = get_updates()

        for u in updates:
            last_update_id = u["update_id"]
            msg = u.get("message")

            if not msg: continue

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

                history.append({
                    "coin": s["symbol"],
                    "price": s["price"],
                    "time": now
                })

                last_alert[s["id"]] = now

        time.sleep(10)

    except Exception as e:
        print("Error:", e)
        time.sleep(5)
    
