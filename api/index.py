import os
import httpx
from fastapi import FastAPI, Request

app = FastAPI()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

@app.get("/")
def health_check():
    return {"status": "online", "service": "Telegram Market Bot"}

async def send_reply(chat_id: int, text: str):
    async with httpx.AsyncClient() as client:
        await client.post(
            TELEGRAM_API,
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown"
            },
            timeout=10.0
        )

def calculate_compounding(principal: float, rate_percent: float, years: int) -> str:
    r = rate_percent / 100
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

async def get_stock_quote(query: str) -> str:
    search_url = f"https://symbol-search.tradingview.com/symbol_search/v3/?text={query}&hl=1&lang=en&domain=production"

    async with httpx.AsyncClient() as client:
        search_res = await client.get(search_url, timeout=10.0)
        search_data = search_res.json()

        symbols = search_data.get("symbols", [])
        if not symbols:
            return f"❌ No market data found for `{query}`."

        top = symbols[0]
        ticker = top["symbol"]
        exchange = top["exchange"]
        description = top.get("description", ticker)

        scanner_payload = {
            "symbols": {"tickers": [f"{exchange}:{ticker}"]},
            "columns": ["close", "change", "high", "low", "currency"]
        }
        scan_res = await client.post(
            "https://scanner.tradingview.com/global/scan",
            json=scanner_payload,
            timeout=10.0
        )
        scan_data = scan_res.json().get("data", [])

        if not scan_data:
            return f"📊 *{description}* (`{exchange}:{ticker}`)\n⚠️ Real-time quotes unavailable."

        values = scan_data[0]["d"]
        price, change, high, low = values[0], values[1], values[2], values[3]
        currency = values[4] or "USD"
        direction = "🟢" if change >= 0 else "🔴"

        return (
            f"📊 *{description}* (`{exchange}:{ticker}`)\n\n"
            f"• *Price:* {price:,.2f} {currency}\n"
            f"• *Change:* {direction} {change:+.2f}%\n"
            f"• *High:* {high:,.2f} {currency}\n"
            f"• *Low:* {low:,.2f} {currency}"
        )

@app.post("/api/index")
async def telegram_webhook(request: Request):
    payload = await request.json()

    if "message" not in payload:
        return {"ok": True}

    chat_id = payload["message"]["chat"]["id"]
    text = payload["message"].get("text", "").strip()

    if text.startswith("/start"):
        reply = (
            "🤖 *Market & Math Bot Ready*\n\n"
            "Commands:\n"
            "• `/stock <ticker or company>` — e.g., `/stock AAPL`, `/stock KZAP`, `/stock Kazatomprom`\n"
            "• `/compound <principal> <rate%> <years>` — e.g., `/compound 10000 8 10`"
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
        parts = text.split(maxsplit=1)
        if len(parts) >= 2:
            reply = await get_stock_quote(parts[1])
        else:
            reply = "⚠️ Please specify a stock or company: `/stock TSLA`"
    else:
        reply = "Send `/stock <query>` or `/compound <principal> <rate> <years>`."

    await send_reply(chat_id, reply)
    return {"ok": True}