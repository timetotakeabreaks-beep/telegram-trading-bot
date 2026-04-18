import requests
import time
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": text}, timeout=10)

def get_market_data():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "volume_desc",
        "per_page": 50,
        "page": 1
    }
    return requests.get(url, params=params, timeout=10).json()

last_price = {}
last_volume = {}
last_alert_time = {}

COOLDOWN = 300  # 5 min

while True:
    try:
        coins = get_market_data()
        now = time.time()
        signals = []

        for c in coins:
            try:
                cid = c["id"]
                name = c["name"]
                sym = c["symbol"].upper()
                price = c["current_price"]
                vol = c["total_volume"]
                change = c["price_change_percentage_24h"] or 0
                market_cap = c["market_cap"] or 0

                if not price or not vol:
                    continue

                # meme-style filter (avoid huge coins)
                if market_cap > 5_000_000_000:
                    continue

                p0 = last_price.get(cid)
                v0 = last_volume.get(cid)

                price_jump = ((price - p0) / p0 * 100) if p0 else 0
                vol_jump = ((vol - v0) / v0 * 100) if v0 else 0

                score = 0

                if vol > 5_000_000:
                    score += 2
                elif vol > 2_000_000:
                    score += 1

                if change > 15:
                    score += 2
                elif change > 5:
                    score += 1

                if price_jump > 2:
                    score += 1
                if vol_jump > 25:
                    score += 1

                if now - last_alert_time.get(cid, 0) < COOLDOWN:
                    continue

                if score >= 3:
                    signals.append({
                        "name": name,
                        "symbol": sym,
                        "price": price,
                        "change": change,
                        "volume": vol,
                        "price_jump": price_jump,
                        "vol_jump": vol_jump,
                        "score": score
                    })
                    last_alert_time[cid] = now

                last_price[cid] = price
                last_volume[cid] = vol

            except:
                continue

        signals = sorted(signals, key=lambda x: x["score"], reverse=True)

        if signals:
            message = "TOP MOMENTUM SIGNALS\n\n"

            for s in signals[:5]:
                message += f"{s['name']} ({s['symbol']})\n"
                message += f"Price: ${s['price']}\n"
                message += f"24h: {s['change']:.2f}%\n"
                message += f"Jump: +{s['price_jump']:.2f}% | Vol: +{s['vol_jump']:.2f}%\n"
                message += f"Volume: ${s['volume']:,}\n"
                message += f"Score: {s['score']}\n\n"

            send_message(message)

        time.sleep(120)

    except Exception as e:
        print("Error:", e)
        time.sleep(60)
