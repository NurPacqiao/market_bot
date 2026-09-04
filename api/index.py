import httpx

async def get_stock_quote(query: str) -> str:
    search_url = f"https://symbol-search.tradingview.com/symbol_search/v3/?text={query}&hl=1&lang=en&domain=production"

    async with httpx.AsyncClient() as client:
        # 1. Search for the symbol across global exchanges
        search_res = await client.get(search_url)
        search_data = search_res.json()

        symbols = search_data.get("symbols", [])
        if not symbols:
            return f"❌ No market data found for `{query}`."

        top = symbols[0]
        ticker = top["symbol"]
        exchange = top["exchange"]
        description = top.get("description", ticker)

        # 2. Query TradingView scanner for real-time price data
        scanner_payload = {
            "symbols": {"tickers": [f"{exchange}:{ticker}"]},
            "columns": ["close", "change", "high", "low", "currency"]
        }
        scan_res = await client.post("https://scanner.tradingview.com/global/scan", json=scanner_payload)
        scan_data = scan_res.json().get("data", [])

        if not scan_data:
            return f"📊 *{description}* (`{exchange}:{ticker}`)\n⚠️ Real-time quotes unavailable."

        values = scan_data[0]["d"]
        price, change, high, low, currency = values[0], values[1], values[2], values[3], values[4] or "USD"
        direction = "🟢" if change >= 0 else "🔴"

        return (
            f"📊 *{description}* (`{exchange}:{ticker}`)\n\n"
            f"• *Price:* {price:,.2f} {currency}\n"
            f"• *Change:* {direction} {change:+.2f}%\n"
            f"• *High:* {high:,.2f} {currency}\n"
            f"• *Low:* {low:,.2f} {currency}"
        )