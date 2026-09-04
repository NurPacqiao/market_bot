import os
import yfinance as yf
import httpx
from fastapi import FastAPI, Request

app = FastAPI()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

async def send_reply(chat_id: int, text: str):
    async with httpx.AsyncClient() as client:
        await client.post(TELEGRAM_API, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        })

def calculate_compounding(principal: float, rate_percent: float, years: int) -> str:
    r = rate_percent / 100
    # Annual compounding: A = P * (1 + r)^t
    future_value = principal * ((1 + r) ** years)
    total_interest = future_value - principal

    return (
        f"📈 *Compounding Growth Result*\n\n"
        f"• *Initial Principal:* ${principal:,.2f}\n"
        f"• *Annual Rate:* {rate_percent}%\n"
        f"• *Timeframe:* {years} years\n"
        f"• *Final Balance:* `${future_value:,.2f}`\n"
        f"• *Total Interest Earned:* `${total_interest:,.2f}`"
    )

def fetch_stock_data(ticker: str) -> str:
    stock = yf.Ticker(ticker.strip().upper())
    info = stock.fast_info

    try:
        price = info.last_price
        prev_close = info.previous_close
        change = ((price - prev_close) / prev_close) * 100

        direction = "🟢" if change >= 0 else "🔴"
        return (
            f"📊 *{ticker.upper()} Market Summary*\n\n"
            f"• *Price:* ${price:,.2f}\n"
            f"• *Daily Change:* {direction} {change:+.2f}%\n"
            f"• *Year High:* ${info.year_high:,.2f}\n"
            f"• *Year Low:* ${info.year_low:,.2f}"
        )
    except Exception:
        return f"❌ Could not retrieve data for `{ticker}`. Verify the ticker symbol."

@app.post("/api/index")
async def telegram_webhook(request: Request):
    payload = await request.json()

    if "message" not in payload:
        return {"ok": True}

    chat_id = payload["message"]["chat"]["id"]
    text = payload["message"].get("text", "").strip()

    # Routing commands
    if text.startswith("/start"):
        reply = (
            "🤖 *Market & Math Bot Ready*\n\n"
            "Commands:\n"
            "1. `/stock <ticker>` — e.g., `/stock NVDA`\n"
            "2. `/compound <principal> <rate%> <years>` — e.g., `/compound 10000 8 10`"
        )
    elif text.startswith("/compound"):
        parts = text.split()
        if len(parts) == 4:
            try:
                p, r, y = float(parts[1]), float(parts[2]), int(parts[3])
                reply = calculate_compounding(p, r, y)
            except ValueError:
                reply = "⚠️ Format: `/compound <principal> <rate_percent> <years>`\nExample: `/compound 5000 7.5 15`"
        else:
            reply = "⚠️ Format: `/compound <principal> <rate_percent> <years>`"

    elif text.startswith("/stock"):
        parts = text.split()
        if len(parts) >= 2:
            reply = fetch_stock_data(parts[1])
        else:
            reply = "⚠️ Provide a ticker: `/stock AAPL`"
    else:
        reply = "Send `/stock <ticker>` or `/compound <principal> <rate> <years>`."

    await send_reply(chat_id, reply)
    return {"ok": True}