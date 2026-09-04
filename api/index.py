import os
import logging
import traceback
import httpx
from fastapi import FastAPI, Request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("market-bot")

app = FastAPI()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

# Browser emulation headers - helps for some bot checks but TradingView's
# Cloudflare protection primarily flags datacenter IPs / TLS fingerprints,
# so this is not a guaranteed bypass.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.tradingview.com/",
    "Origin": "https://www.tradingview.com",
}


@app.get("/")
def health():
    return {"status": "online", "token_configured": bool(TOKEN)}


async def send_reply(chat_id: int, text: str):
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not configured.")
        return
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                TELEGRAM_API,
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                },
                timeout=10.0,
            )
            if resp.status_code != 200:
                logger.error(
                    "Telegram send failed: %s %s", resp.status_code, resp.text
                )
    except Exception:
        logger.error("Failed to send Telegram reply:\n%s", traceback.format_exc())


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


def _fmt(v):
    return f"{v:,.2f}" if isinstance(v, (int, float)) else "N/A"


async def get_stock_quote(query: str) -> str:
    search_url = "https://symbol-search.tradingview.com/symbol_search/v3/"
    params = {"text": query, "hl": "1", "lang": "en", "domain": "production"}

    try:
        async with httpx.AsyncClient(
            headers=HEADERS, follow_redirects=True, timeout=8.0
        ) as client:
            # Warm-up request: picks up cookies from TradingView's homepage
            # before hitting the API endpoints. Not a guaranteed bypass of
            # Cloudflare bot protection, but improves success rate somewhat.
            try:
                await client.get("https://www.tradingview.com/", timeout=6.0)
            except Exception:
                logger.warning("Warm-up request failed, continuing anyway")

            # 1. Search for symbol
            search_res = await client.get(search_url, params=params)

            if search_res.status_code == 403:
                logger.error("TradingView search blocked (403) for query=%s", query)
                return (
                    "⚠️ TradingView is currently blocking requests from this "
                    "server (bot protection). This isn't a bad ticker — it's "
                    "an infrastructure-level block. Try again in a bit."
                )
            if search_res.status_code != 200:
                return (
                    f"⚠️ Market search temporarily throttled "
                    f"(Code {search_res.status_code}). Try again shortly."
                )

            try:
                search_data = search_res.json()
            except ValueError:
                logger.error("Non-JSON search response: %s", search_res.text[:300])
                return "⚠️ Market search returned an unexpected response. Try again shortly."

            symbols = search_data.get("symbols", [])
            if not symbols:
                return f"❌ No market asset found matching `{query}`."

            top = symbols[0]
            ticker = top.get("symbol", query)
            exchange = top.get("exchange", "")
            description = top.get("description", ticker)

            # 2. Query scanner for real-time price
            scanner_payload = {
                "symbols": {"tickers": [f"{exchange}:{ticker}"]},
                "columns": ["close", "change", "high", "low", "currency"],
            }
            scan_res = await client.post(
                "https://scanner.tradingview.com/global/scan",
                json=scanner_payload,
            )

            if scan_res.status_code == 403:
                return (
                    f"📊 *{description}* (`{exchange}:{ticker}`)\n"
                    f"⚠️ Quote feed blocked by TradingView (bot protection)."
                )
            if scan_res.status_code != 200:
                return (
                    f"📊 *{description}* (`{exchange}:{ticker}`)\n"
                    f"⚠️ Quote feed temporarily unavailable "
                    f"(Code {scan_res.status_code})."
                )

            try:
                scan_json = scan_res.json()
            except ValueError:
                logger.error("Non-JSON scan response: %s", scan_res.text[:300])
                return (
                    f"📊 *{description}* (`{exchange}:{ticker}`)\n"
                    f"⚠️ Unexpected quote feed response."
                )

            scan_data = scan_json.get("data", [])
            if not scan_data or not scan_data[0].get("d"):
                return (
                    f"📊 *{description}* (`{exchange}:{ticker}`)\n"
                    f"⚠️ No recent trades recorded for this listing."
                )

            values = scan_data[0]["d"]
            # Defensive unpack - pad in case fewer columns come back than expected
            values = list(values) + [None] * (5 - len(values))
            price, change, high, low, currency = values[:5]
            currency = currency or "USD"
            direction = "🟢" if isinstance(change, (int, float)) and change >= 0 else "🔴"
            change_str = f"{change:+.2f}%" if isinstance(change, (int, float)) else "N/A"

            return (
                f"📊 *{description}* (`{exchange}:{ticker}`)\n\n"
                f"• *Price:* {_fmt(price)} {currency}\n"
                f"• *Change:* {direction} {change_str}\n"
                f"• *Day High:* {_fmt(high)} {currency}\n"
                f"• *Day Low:* {_fmt(low)} {currency}"
            )

    except httpx.TimeoutException:
        logger.error("Timeout fetching data for query=%s", query)
        return f"⌛ Request timed out fetching data for `{query}`. Try again."
    except Exception:
        logger.error("Fetch error for query=%s:\n%s", query, traceback.format_exc())
        return f"❌ Unexpected error fetching data for `{query}`."


def build_reply(text: str) -> str:
    """Pure text-processing, kept separate from I/O so it can't leak
    an unhandled exception out of the async webhook path silently."""
    if text.startswith("/start"):
        return (
            "🤖 *Market & Math Bot Online*\n\n"
            "Commands:\n"
            "• `/stock <ticker or company>` — e.g., `/stock AAPL`, `/stock KZAP`, `/stock Air Astana`\n"
            "• `/compound <principal> <rate%> <years>` — e.g., `/compound 10000 8 10`"
        )
    if text.startswith("/compound"):
        parts = text.split()
        if len(parts) == 4:
            try:
                p, r, y = float(parts[1]), float(parts[2]), int(parts[3])
                return calculate_compounding(p, r, y)
            except ValueError:
                return (
                    "⚠️ Format: `/compound <principal> <rate_percent> <years>`\n"
                    "Example: `/compound 5000 7.5 15`"
                )
        return "⚠️ Format: `/compound <principal> <rate_percent> <years>`"
    return None  # signal: needs async handling (stock) or fallback


@app.post("/api/index")
async def telegram_webhook(request: Request):
    # Everything in here is guarded so we ALWAYS return 200 to Telegram.
    # A non-200 response makes Telegram retry the same update repeatedly,
    # which is what caused the repeated crash loop in the logs.
    try:
        payload = await request.json()
    except Exception:
        logger.warning("Could not parse incoming request as JSON")
        return {"ok": True}

    if "message" not in payload:
        return {"ok": True}

    try:
        chat_id = payload["message"]["chat"]["id"]
        text = payload["message"].get("text", "").strip()
    except Exception:
        logger.error("Malformed message payload:\n%s", traceback.format_exc())
        return {"ok": True}

    try:
        if text.startswith("/stock"):
            parts = text.split(maxsplit=1)
            if len(parts) >= 2:
                reply = await get_stock_quote(parts[1])
            else:
                reply = "⚠️ Please provide a query: `/stock NVDA` or `/stock Halyk Bank`"
        else:
            reply = build_reply(text)
            if reply is None:
                reply = "Send `/stock <query>` or `/compound <principal> <rate> <years>`."
    except Exception:
        logger.error("Unhandled error processing update:\n%s", traceback.format_exc())
        reply = "❌ Something went wrong processing your request. Please try again."

    await send_reply(chat_id, reply)
    return {"ok": True}