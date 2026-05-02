"""
Market movers via Yahoo Finance free screener API.
No API key required.
"""
import httpx
from datetime import datetime

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

BASE = "https://query1.finance.yahoo.com"

SCREENS = {
    "gainers":    "day_gainers",
    "losers":     "day_losers",
    "actives":    "most_actives",
    "trending":   None,           # uses different endpoint
}


def _parse_quote(q: dict) -> dict:
    return {
        "symbol":      q.get("symbol", ""),
        "name":        q.get("shortName") or q.get("longName", ""),
        "price":       round(float(q.get("regularMarketPrice",       q.get("ask", 0)) or 0), 2),
        "change":      round(float(q.get("regularMarketChange",      0) or 0), 2),
        "change_pct":  round(float(q.get("regularMarketChangePercent", 0) or 0), 3),
        "volume":      int(q.get("regularMarketVolume", 0) or 0),
        "market_cap":  int(q.get("marketCap", 0) or 0),
        "avg_volume":  int(q.get("averageDailyVolume3Month", 0) or 0),
    }


async def get_screen(screen: str, count: int = 25) -> list[dict]:
    """Fetch a predefined screener list from Yahoo Finance."""
    scr_id = SCREENS.get(screen)
    if screen == "trending":
        return await get_trending()

    url = f"{BASE}/v1/finance/screener/predefined/saved"
    params = {"scrIds": scr_id, "count": count, "region": "US", "lang": "en-US"}
    async with httpx.AsyncClient(headers=HEADERS, timeout=10) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        quotes = resp.json().get("finance", {}).get("result", [{}])[0].get("quotes", [])
    return [_parse_quote(q) for q in quotes]


async def get_trending(count: int = 20) -> list[dict]:
    """Fetch trending tickers from Yahoo Finance."""
    url = f"{BASE}/v1/finance/trending/US"
    async with httpx.AsyncClient(headers=HEADERS, timeout=10) as client:
        resp = await client.get(url, params={"count": count, "region": "US"})
        resp.raise_for_status()
        symbols_raw = resp.json().get("finance", {}).get("result", [{}])[0].get("quotes", [])
    symbols = [q["symbol"] for q in symbols_raw if "symbol" in q]
    if not symbols:
        return []
    # Fetch quotes for trending symbols
    return await get_snapshots(symbols[:count])


async def get_snapshots(symbols: list[str]) -> list[dict]:
    """Fetch quote data for a list of symbols via spark endpoint."""
    if not symbols:
        return []
    joined = ",".join(symbols)
    async with httpx.AsyncClient(headers=HEADERS, timeout=10) as client:
        r = await client.get(
            f"{BASE}/v8/finance/spark",
            params={"symbols": joined, "range": "1d", "interval": "1d"},
        )
        if r.status_code != 200:
            return [{"symbol": s, "name": "", "price": 0, "change": 0, "change_pct": 0, "volume": 0, "market_cap": 0} for s in symbols]
        spark = r.json()
    results = []
    for sym in symbols:
        entry = spark.get(sym, {})
        closes = entry.get("close") or []
        price = round(float(closes[-1]), 2) if closes else 0.0
        prev = float(entry.get("chartPreviousClose") or price)
        change = round(price - prev, 2)
        change_pct = round((change / prev * 100) if prev else 0.0, 3)
        results.append({
            "symbol":     sym,
            "name":       sym,
            "price":      price,
            "change":     change,
            "change_pct": change_pct,
            "volume":     0,
            "market_cap": 0,
        })
    return results


CRYPTO_WATCHLIST = [
    ("BTC-USD",  "Bitcoin"),
    ("ETH-USD",  "Ethereum"),
    ("SOL-USD",  "Solana"),
    ("XRP-USD",  "XRP"),
    ("DOGE-USD", "Dogecoin"),
    ("ADA-USD",  "Cardano"),
    ("AVAX-USD", "Avalanche"),
    ("LINK-USD", "Chainlink"),
    ("LTC-USD",  "Litecoin"),
    ("DOT-USD",  "Polkadot"),
    ("UNI-USD",  "Uniswap"),
    ("SHIB-USD", "Shiba Inu"),
    ("BCH-USD",  "Bitcoin Cash"),
    ("ATOM-USD", "Cosmos"),
    ("NEAR-USD", "NEAR Protocol"),
    ("APT-USD",  "Aptos"),
    ("OP-USD",   "Optimism"),
    ("ARB-USD",  "Arbitrum"),
]


async def get_crypto_markets() -> list[dict]:
    """Fetch live data for major crypto assets via Yahoo Finance."""
    symbols = [s for s, _ in CRYPTO_WATCHLIST]
    names   = {s: n for s, n in CRYPTO_WATCHLIST}
    joined  = ",".join(symbols)

    async with httpx.AsyncClient(headers=HEADERS, timeout=15) as client:
        r = await client.get(
            f"{BASE}/v8/finance/spark",
            params={"symbols": joined, "range": "1d", "interval": "5m"},
        )
        r.raise_for_status()
        spark = r.json()

    # Also grab 7d change via chart endpoint for each (batch via spark 7d)
    async with httpx.AsyncClient(headers=HEADERS, timeout=15) as client:
        r7 = await client.get(
            f"{BASE}/v8/finance/spark",
            params={"symbols": joined, "range": "7d", "interval": "1d"},
        )
        spark7 = r7.json() if r7.status_code == 200 else {}

    results = []
    for sym in symbols:
        entry = spark.get(sym, {})
        closes = entry.get("close") or []
        price  = round(float(closes[-1]), 4) if closes else 0.0
        prev   = float(entry.get("chartPreviousClose") or price)
        change     = round(price - prev, 4)
        change_pct = round((change / prev * 100) if prev else 0.0, 3)

        # 7d change — filter out None values before arithmetic
        e7 = spark7.get(sym, {})
        c7 = [v for v in (e7.get("close") or []) if v is not None]
        if len(c7) >= 2:
            change_7d = round(((c7[-1] - c7[0]) / c7[0] * 100) if c7[0] else 0.0, 2)
        else:
            change_7d = 0.0

        # Intraday sparkline (last 20 points)
        sparkline = [round(float(v), 4) for v in closes[-20:] if v is not None]

        results.append({
            "symbol":     sym,
            "base":       sym.replace("-USD", ""),
            "name":       names.get(sym, sym),
            "price":      price,
            "change":     change,
            "change_pct": change_pct,
            "change_7d":  change_7d,
            "volume":     int(entry.get("volume", [0])[-1] if entry.get("volume") else 0),
            "sparkline":  sparkline,
        })
    return results


async def get_all_movers() -> dict:
    """Fetch all mover categories in parallel."""
    import asyncio
    gainers, losers, actives, trending = await asyncio.gather(
        get_screen("gainers"),
        get_screen("losers"),
        get_screen("actives"),
        get_trending(),
        return_exceptions=True,
    )
    return {
        "gainers":  gainers  if isinstance(gainers,  list) else [],
        "losers":   losers   if isinstance(losers,   list) else [],
        "actives":  actives  if isinstance(actives,  list) else [],
        "trending": trending if isinstance(trending, list) else [],
        "updated":  datetime.utcnow().isoformat(),
    }
