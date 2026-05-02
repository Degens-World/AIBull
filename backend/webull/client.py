"""
Webull OpenAPI client wrapper.
Trading/account endpoints use Webull API.
Market data (quotes, bars) uses Yahoo Finance — Webull data API requires a paid subscription.
"""
import asyncio
import logging
import logging.handlers
import uuid
from datetime import datetime
from typing import Optional
import httpx

from backend.config import settings

_YF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

# Known crypto base symbols — used for detection and symbol normalization
_CRYPTO_BASES = {
    "BTC", "ETH", "SOL", "DOGE", "ADA", "XRP", "AVAX", "LINK", "LTC",
    "DOT", "MATIC", "UNI", "SHIB", "BCH", "ATOM", "FIL", "NEAR", "APT",
    "OP", "ARB", "SUI", "TIA", "INJ", "PEPE", "WIF", "BONK",
}


def _is_crypto(symbol: str) -> bool:
    """Return True if symbol looks like a crypto asset."""
    s = symbol.upper().replace("-USD", "").replace("USD", "")
    return s in _CRYPTO_BASES or symbol.upper().endswith("-USD")


def _yf_symbol(symbol: str) -> str:
    """Normalize to Yahoo Finance format (e.g. BTC → BTC-USD)."""
    s = symbol.upper()
    if _is_crypto(s) and not s.endswith("-USD"):
        base = s.replace("USD", "").rstrip("-")
        return f"{base}-USD"
    return s


def _wb_symbol(symbol: str) -> str:
    """Normalize to Webull crypto format (e.g. BTC-USD → BTC-USD, BTC → BTC-USD)."""
    return _yf_symbol(symbol)  # Webull uses same dash format for crypto


async def _yf_quote(symbol: str) -> dict:
    async with httpx.AsyncClient(headers=_YF_HEADERS, timeout=10) as client:
        r = await client.get(
            "https://query1.finance.yahoo.com/v8/finance/spark",
            params={"symbols": symbol, "range": "1d", "interval": "5m"},
        )
        r.raise_for_status()
        d = r.json().get(symbol, {})
    closes = d.get("close") or []
    price = round(float(closes[-1]), 2) if closes else 0.0
    prev = float(d.get("chartPreviousClose") or price)
    change = round(price - prev, 2)
    pct = round((change / prev * 100) if prev else 0.0, 3)
    return {
        "symbol": symbol, "price": price,
        "bid": price, "ask": price, "volume": 0,
        "change": change, "change_pct": pct,
        "timestamp": datetime.utcnow().isoformat(),
    }


async def _yf_bars(symbol: str, timeframe: str = "1d", count: int = 100) -> list[dict]:
    tf_map = {
        "1m":  ("1m",  "7d"),  "5m":  ("5m",  "60d"),
        "15m": ("15m", "60d"), "30m": ("30m", "60d"),
        "1h":  ("60m", "730d"),"4h":  ("60m", "730d"),
        "1d":  ("1d",  "2y"),  "1w":  ("1wk", "10y"),
    }
    interval, period = tf_map.get(timeframe, ("1d", "2y"))
    async with httpx.AsyncClient(headers=_YF_HEADERS, timeout=15) as client:
        r = await client.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            params={"interval": interval, "range": period},
        )
        r.raise_for_status()
        result = r.json().get("chart", {}).get("result", [{}])[0]
    timestamps = result.get("timestamp", [])
    q = result.get("indicators", {}).get("quote", [{}])[0]
    bars = []
    for i, ts in enumerate(timestamps):
        c = (q.get("close") or [])[i] if i < len(q.get("close") or []) else None
        if c is None:
            continue
        bars.append({
            "timestamp": datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d"),
            "open":   round(float((q.get("open")  or [])[i] or 0), 4),
            "high":   round(float((q.get("high")  or [])[i] or 0), 4),
            "low":    round(float((q.get("low")   or [])[i] or 0), 4),
            "close":  round(float(c), 4),
            "volume": int((q.get("volume") or [])[i] or 0) if i < len(q.get("volume") or []) else 0,
        })
    return bars[-count:]


def _has_credentials() -> bool:
    return bool(settings.webull_app_key and settings.webull_app_secret)


def _make_api_client():
    from webull.core.client import ApiClient
    from webull.core.common.region import Region
    client = ApiClient(
        app_key=settings.webull_app_key,
        app_secret=settings.webull_app_secret,
        region_id=Region.US,
    )
    # Register endpoints explicitly — the SDK's enum-vs-string mismatch
    # prevents LocalConfigRegionalEndpointResolver from matching automatically.
    client.add_endpoint(Region.US, "api.webull.com")
    client.add_endpoint(Region.US, "data-api.webull.com", api_type="quotes-api")
    return client


def _fix_webull_logger():
    """Remove the SDK's TimedRotatingFileHandler — on Windows it crashes trying
    to rename open log files on rotation. Replace with NullHandler."""
    for name in ("webull", "webull.core.client", "webull.trade"):
        lg = logging.getLogger(name)
        for h in list(lg.handlers):
            if hasattr(h, 'baseFilename'):  # any FileHandler subclass
                lg.removeHandler(h)
        if not lg.handlers:
            lg.addHandler(logging.NullHandler())


class WebullClient:
    def __init__(self):
        self._trade = None
        self.auth_status: str = "unconfigured"   # unconfigured | pending | authorized | failed
        self.auth_message: str = ""
        # Cache: (timestamp, data) — refreshed every 5 minutes to avoid 429s
        self._account_list_cache: tuple[float, list] | None = None

    def _get_trade(self):
        from webull.trade.trade_client import TradeClient
        if self._trade is None and _has_credentials():
            _fix_webull_logger()
            self._trade = TradeClient(_make_api_client())
            self.auth_status = "authorized"
        return self._trade

    def _refresh(self):
        """Force SDK reconnect after credential update."""
        self._trade = None
        self._data = None
        self.auth_status = "unconfigured" if not _has_credentials() else "pending"
        self.auth_message = ""

    async def initialize(self):
        """Try to authenticate in the background; update auth_status."""
        if not _has_credentials():
            self.auth_status = "unconfigured"
            return
        self.auth_status = "pending"
        self.auth_message = "Check Webull app to approve API access"
        try:
            await asyncio.to_thread(self._get_trade)
            self.auth_status = "authorized"
            self.auth_message = ""
        except Exception as e:
            self.auth_status = "failed"
            self.auth_message = str(e)

    # ── Account ───────────────────────────────────────────────────────────────

    async def get_account(self) -> dict:
        if not _has_credentials():
            return _stub_account()
        for attempt in range(3):
            try:
                return await asyncio.to_thread(self._live_account)
            except Exception as e:
                if "429" in str(e) or "TOO_MANY_REQUESTS" in str(e):
                    await asyncio.sleep(15 * (attempt + 1))
                    continue
                raise RuntimeError(f"Webull account error: {e}") from e
        return _stub_account()

    def _get_account_list(self) -> list[dict]:
        import time
        now = time.monotonic()
        if self._account_list_cache and (now - self._account_list_cache[0]) < 300:
            return self._account_list_cache[1]
        trade = self._get_trade()
        result = trade.account_v2.get_account_list().json() or []
        self._account_list_cache = (now, result)
        return result

    def _selected_accounts(self) -> list[dict]:
        """Return only the selected account, or all if none selected."""
        all_accounts = self._get_account_list()
        sel = settings.selected_account_id
        if sel:
            filtered = [a for a in all_accounts if a["account_id"] == sel]
            return filtered if filtered else all_accounts
        return all_accounts

    def _live_account(self) -> dict:
        accounts = self._selected_accounts()
        net_liq = cash = buying_pwr = unrlzd = day_pnl = 0.0
        trade = self._get_trade()
        for acct in accounts:
            aid = acct["account_id"]
            try:
                bal = trade.account_v2.get_account_balance(aid).json()
                acct_cash   = float(bal.get("total_cash_balance", 0) or 0)
                # buying_power lives inside account_currency_assets; fall back to cash if missing/zero
                currency_assets = (bal.get("account_currency_assets") or [{}])[0]
                bp = float(currency_assets.get("buying_power", 0) or 0)
                if bp == 0:
                    bp = acct_cash
                net_liq    += float(bal.get("total_net_liquidation_value", 0) or 0)
                cash       += acct_cash
                buying_pwr += bp
                unrlzd     += float(bal.get("total_unrealized_profit_loss", 0) or 0)
                day_pnl    += float(bal.get("total_day_profit_loss",        0) or 0)
            except Exception:
                pass

        primary_id = accounts[0]["account_id"] if accounts else settings.webull_account_id
        return {
            "account_id": primary_id,
            "cash_balance": round(cash, 2),
            "net_liquidation": round(net_liq, 2),
            "unrealized_pnl": round(unrlzd, 2),
            "realized_pnl_day": round(day_pnl, 2),
            "buying_power": round(buying_pwr, 2),
            "mode": settings.trading_mode,
            "accounts": [{"id": a["account_id"], "label": a["account_label"], "class": a["account_class"]} for a in accounts],
        }

    async def get_positions(self) -> list[dict]:
        if not _has_credentials():
            return _stub_positions()
        for attempt in range(3):
            try:
                return await asyncio.to_thread(self._live_positions)
            except Exception as e:
                if "429" in str(e) or "TOO_MANY_REQUESTS" in str(e):
                    await asyncio.sleep(15 * (attempt + 1))
                    continue
                raise RuntimeError(f"Webull positions error: {e}") from e
        return _stub_positions()

    def _live_positions(self) -> list[dict]:
        trade = self._get_trade()
        accounts = self._selected_accounts()
        positions = []
        for acct in accounts:
            aid = acct["account_id"]
            try:
                raw = trade.account_v2.get_account_position(aid).json() or []
                for p in raw:
                    qty    = float(p.get("quantity", 0) or 0)
                    if qty == 0:
                        continue
                    avg    = float(p.get("cost_price", 0) or 0)
                    price  = float(p.get("last_price", avg) or avg)
                    mval   = float(p.get("market_value", qty * price) or qty * price)
                    unrlzd = float(p.get("unrealized_profit_loss", 0) or 0)
                    positions.append({
                        "symbol":        p.get("symbol", ""),
                        "quantity":      qty,
                        "avg_cost":      round(avg, 4),
                        "current_price": round(price, 4),
                        "market_value":  round(mval, 2),
                        "unrealized_pnl":round(unrlzd, 2),
                        "account_label": acct.get("account_label", ""),
                    })
            except Exception:
                pass
        return positions

    # ── Orders ────────────────────────────────────────────────────────────────

    @staticmethod
    def _market_session() -> str:
        """Return 'pre', 'regular', 'post', or 'closed' based on US ET time."""
        from datetime import timezone, timedelta
        et = datetime.now(timezone(timedelta(hours=-4)))  # EDT; close enough year-round
        h, m = et.hour, et.minute
        minutes = h * 60 + m
        wd = et.weekday()
        if wd >= 5:
            return "closed"
        if 240 <= minutes < 570:    # 4:00–9:30 AM ET
            return "pre"
        if 570 <= minutes < 960:    # 9:30 AM–4:00 PM ET
            return "regular"
        if 960 <= minutes < 1200:   # 4:00–8:00 PM ET
            return "post"
        return "closed"

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float] = None,
        account_id: Optional[str] = None,
        extended_hours: bool = False,
    ) -> dict:
        if not _has_credentials():
            return _stub_place_order(symbol, side, order_type, quantity, price)
        try:
            return await asyncio.to_thread(
                self._live_place_order, symbol, side, order_type, quantity, price, account_id, extended_hours
            )
        except Exception as e:
            err = str(e)
            if "REVERSE_OPTION" in err or "reverse" in err.lower():
                raise RuntimeError(f"REVERSE_BLOCKED:{symbol}:{side}") from e
            if "429" in err or "TOO_MANY_REQUESTS" in err:
                raise RuntimeError(f"RATE_LIMITED") from e
            # Wrap everything else as RuntimeError so the engine catches it cleanly
            raise RuntimeError(f"ORDER_FAILED:{err}") from e

    def _live_place_order(self, symbol, side, order_type, quantity, price, account_id=None, extended_hours=False) -> dict:
        # Use plain strings — the SDK serializes the order dict to JSON directly.
        # Enums are not JSON-serializable and should not be used here.
        order_type_map = {
            "MARKET":     "MARKET",
            "LIMIT":      "LIMIT",
            "STOP":       "STOP LOSS",
            "STOP_LIMIT": "STOP LOSS LIMIT",
        }
        side_str = side.upper()
        crypto = _is_crypto(symbol)
        wb_sym = _wb_symbol(symbol) if crypto else symbol.upper()

        if crypto:
            # Crypto trades 24/7 — no session restrictions, fractional qty allowed
            client_order_id = str(uuid.uuid4())
            order = {
                "client_order_id": client_order_id,
                "symbol":          wb_sym,
                "order_type":      order_type_map.get(order_type, "MARKET"),
                "side":            side_str,
                "time_in_force":   "DAY",
                "quantity":        str(quantity),   # fractional allowed
                "market":          "US",
                "instrument_type": "CRYPTO",
                "combo_type":      "NORMAL",
                "entrust_type":    "QTY",
            }
            if price and order_type != "MARKET":
                order["limit_price"] = str(price)
        else:
            session = self._market_session()
            is_extended = extended_hours and session in ("pre", "post")

            # Webull requires LIMIT orders during extended hours — always enforce this
            if is_extended and order_type == "MARKET":
                if not price:
                    raise RuntimeError(f"Extended hours order for {symbol} requires a limit price")
                order_type = "LIMIT"

            # Webull requires DAY for all equity orders — support_trading_session controls session scope
            time_in_force = "DAY"
            trading_session = "Y" if is_extended else "N"

            client_order_id = str(uuid.uuid4())
            order = {
                "client_order_id":         client_order_id,
                "symbol":                  wb_sym,
                "order_type":              order_type_map.get(order_type, "MARKET"),
                "side":                    side_str,
                "time_in_force":           time_in_force,
                "quantity":                str(int(quantity)),
                "market":                  "US",
                "instrument_type":         "EQUITY",
                "combo_type":              "NORMAL",
                "entrust_type":            "QTY",
                "support_trading_session": trading_session,
            }
            if price and order_type != "MARKET":
                order["limit_price"] = str(round(price, 2))

        trade = self._get_trade()
        # Use explicit account_id if provided, else respect global selection
        if account_id:
            aid = account_id
        else:
            accounts = self._selected_accounts()
            aid = accounts[0]["account_id"] if accounts else settings.webull_account_id
        resp = trade.order_v3.place_order(aid, [order])
        # Check HTTP status code — SDK does not raise on 4xx/5xx automatically
        if hasattr(resp, 'status_code') and resp.status_code >= 400:
            body = getattr(resp, 'text', '')[:300]
            raise RuntimeError(f"HTTP {resp.status_code}: {body}")
        # Parse JSON — raise if unparseable
        try:
            resp_data = resp.json() if hasattr(resp, 'json') else resp
        except Exception as parse_err:
            raise RuntimeError(f"Unparseable Webull response: {parse_err}")
        # Normalise: response may be a list
        if isinstance(resp_data, list):
            resp_data = resp_data[0] if resp_data else {}
        if not isinstance(resp_data, dict):
            raise RuntimeError(f"Unexpected response type from Webull: {type(resp_data).__name__}")
        # Check for any error indicator — Webull uses "error_code" or "code" depending on endpoint
        err_code = resp_data.get("error_code") or (
            resp_data.get("code")
            if str(resp_data.get("code", "")).lower() not in ("0", "success", "ok", "")
            else None
        )
        if err_code:
            err_msg = (resp_data.get("error_msg") or resp_data.get("msg")
                       or resp_data.get("message") or str(err_code))
            raise RuntimeError(f"Webull order error [{err_code}]: {err_msg}")
        # Extract order_id — may be nested under "data" or at top level
        data = resp_data.get("data") or resp_data
        if isinstance(data, list):
            data = data[0] if data else {}
        if not isinstance(data, dict):
            data = {}
        order_id = data.get("order_id") or data.get("combo_order_id")
        if not order_id:
            # Webull accepted our request but returned no order ID — the order did NOT land.
            # Log the full response so we can diagnose the format.
            raise RuntimeError(f"Webull returned no order ID — order was NOT placed. Raw response: {str(resp_data)[:500]}")
        return {
            "order_id": order_id,
            "symbol": symbol,
            "side": side,
            "order_type": order_type,
            "quantity": quantity,
            "price": price,
            "status": "PENDING",
            "account_id": aid,
            "created_at": datetime.utcnow().isoformat(),
        }

    async def cancel_order(self, order_id: str) -> dict:
        if not _has_credentials():
            return {"order_id": order_id, "status": "CANCELLED"}
        return await asyncio.to_thread(self._live_cancel, order_id)

    def _live_cancel(self, order_id: str) -> dict:
        accounts = self._selected_accounts()
        trade = self._get_trade()
        aid = accounts[0]["account_id"] if accounts else settings.webull_account_id
        trade.order_v3.cancel_order(aid, order_id)
        return {"order_id": order_id, "status": "CANCELLED"}

    async def get_orders(self) -> list[dict]:
        if not _has_credentials():
            return _stub_orders()
        return await asyncio.to_thread(self._live_orders)

    def _live_orders(self) -> list[dict]:
        trade = self._get_trade()
        accounts = self._selected_accounts()
        orders = []
        for acct in accounts:
            aid = acct["account_id"]
            try:
                # v3 returns combo envelopes: [{combo_order_id, orders: [{...}]}]
                raw = trade.order_v3.get_order_history(aid, page_size=50).json() or []
                for combo in raw:
                    for o in (combo.get("orders") or []):
                        orders.append({
                            "order_id":    o.get("order_id", combo.get("combo_order_id", "")),
                            "symbol":      o.get("symbol", ""),
                            "side":        (o.get("side", "") or "").upper(),
                            "order_type":  (o.get("order_type", "") or "").upper(),
                            "quantity":    float(o.get("total_quantity", 0) or 0),
                            "price":       float(o.get("limit_price", 0) or 0) or None,
                            "status":      (o.get("status", "") or "").upper(),
                            "filled_qty":  float(o.get("filled_quantity", 0) or 0),
                            "filled_price":float(o.get("filled_price", 0) or 0) or None,
                            "created_at":  o.get("place_time_at", ""),
                            "account_label": acct.get("account_label", ""),
                        })
            except Exception:
                pass
        return orders

    # ── Options ──────────────────────────────────────────────────────────────────

    async def get_option_chain(self, symbol: str, max_expirations: int = 3) -> dict:
        """
        Fetch option chain from Yahoo Finance.
        Returns dict with 'expirations' list and per-expiration calls/puts DataFrames as dicts.
        """
        try:
            return await asyncio.to_thread(self._yf_option_chain, symbol, max_expirations)
        except Exception as e:
            raise RuntimeError(f"Option chain error for {symbol}: {e}") from e

    @staticmethod
    def _yf_option_chain(symbol: str, max_expirations: int = 3) -> dict:
        import math
        import yfinance as yf

        def _safe_float(val, default=0.0) -> float:
            try:
                v = float(val)
                return default if math.isnan(v) or math.isinf(v) else v
            except (TypeError, ValueError):
                return default

        def _safe_int(val) -> int:
            return int(_safe_float(val))

        def _df_to_list(df) -> list:
            rows = []
            for _, row in df.iterrows():
                rows.append({
                    "contract_symbol": str(row.get("contractSymbol", "")),
                    "strike":          round(_safe_float(row.get("strike", 0)), 2),
                    "last_price":      round(_safe_float(row.get("lastPrice", 0)), 4),
                    "bid":             round(_safe_float(row.get("bid", 0)), 4),
                    "ask":             round(_safe_float(row.get("ask", 0)), 4),
                    "volume":          _safe_int(row.get("volume", 0)),
                    "open_interest":   _safe_int(row.get("openInterest", 0)),
                    "implied_vol":     round(_safe_float(row.get("impliedVolatility", 0)), 4),
                    "in_the_money":    bool(row.get("inTheMoney", False)),
                    "delta":           round(_safe_float(row.get("delta", 0)), 4) if "delta" in row else None,
                })
            return rows

        ticker = yf.Ticker(symbol)
        expirations = ticker.options
        if not expirations:
            return {"symbol": symbol, "expirations": [], "chains": {}}
        result = {"symbol": symbol, "expirations": list(expirations), "chains": {}}
        for exp in expirations[:max_expirations]:
            chain = ticker.option_chain(exp)
            result["chains"][exp] = {
                "calls": _df_to_list(chain.calls),
                "puts":  _df_to_list(chain.puts),
            }
        return result

    async def place_option_order(
        self,
        contract_symbol: str,   # e.g. "AAPL240517C00150000" (OCC format from YF)
        option_type: str,       # "CALL" or "PUT"
        side: str,              # "BUY" or "SELL"
        quantity: int,
        limit_price: float,
        account_id: Optional[str] = None,
    ) -> dict:
        if not _has_credentials():
            return _stub_place_order(contract_symbol, side, "LIMIT", quantity, limit_price)
        try:
            return await asyncio.to_thread(
                self._live_place_option, contract_symbol, option_type, side,
                quantity, limit_price, account_id
            )
        except Exception as e:
            err = str(e)
            if "429" in err or "TOO_MANY_REQUESTS" in err:
                raise RuntimeError("RATE_LIMITED") from e
            raise RuntimeError(f"ORDER_FAILED:{err}") from e

    def _live_place_option(self, contract_symbol, option_type, side, quantity, limit_price, account_id=None) -> dict:
        # Webull option API rejects any client-generated IDs (all UUID formats, hex, numeric).
        # Do NOT pass client_order_id in legs or client_combo_order_id — let Webull assign IDs.
        leg = {
            "symbol":           contract_symbol,
            "instrument_type":  "OPTION",
            "market":           "US",
            "side":             side.upper(),
            "order_type":       "LIMIT",
            "limit_price":      str(round(limit_price, 2)),
            "quantity":         str(int(quantity)),
            "time_in_force":    "DAY",
        }
        order_payload = [{"legs": [leg]}]

        trade = self._get_trade()
        accounts = self._selected_accounts()
        aid = account_id or (accounts[0]["account_id"] if accounts else "")

        resp = trade.order_v2.place_option(aid, order_payload)  # no client IDs — Webull rejects them
        if hasattr(resp, 'status_code') and resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code}: {getattr(resp, 'text', '')[:300]}")
        try:
            resp_data = resp.json() if hasattr(resp, 'json') else resp
        except Exception as e:
            raise RuntimeError(f"Unparseable option order response: {e}")
        if isinstance(resp_data, list):
            resp_data = resp_data[0] if resp_data else {}
        if not isinstance(resp_data, dict):
            raise RuntimeError(f"Unexpected option response type: {type(resp_data).__name__}")
        err_code = resp_data.get("error_code") or (
            resp_data.get("code")
            if str(resp_data.get("code", "")).lower() not in ("0", "success", "ok", "")
            else None
        )
        if err_code:
            err_msg = resp_data.get("error_msg") or resp_data.get("msg") or str(err_code)
            raise RuntimeError(f"Webull option error [{err_code}]: {err_msg}")
        data = resp_data.get("data") or resp_data
        if isinstance(data, list):
            data = data[0] if data else {}
        if not isinstance(data, dict):
            data = {}
        order_id = (data.get("combo_order_id") or data.get("order_id")
                    or data.get("client_combo_order_id") or data.get("clientComboOrderId"))
        if not order_id:
            raise RuntimeError(f"No order ID from Webull option order. Response: {str(resp_data)[:400]}")
        return {
            "order_id":        order_id,
            "contract_symbol": contract_symbol,
            "option_type":     option_type,
            "side":            side,
            "quantity":        quantity,
            "limit_price":     limit_price,
            "status":          "PENDING",
            "account_id":      aid,
            "created_at":      datetime.utcnow().isoformat(),
        }

    # ── Market Data (Yahoo Finance — Webull data API requires paid subscription) ─

    async def get_quote(self, symbol: str) -> dict:
        try:
            result = await _yf_quote(_yf_symbol(symbol))
            result["symbol"] = symbol.upper()   # return original symbol to caller
            result["is_crypto"] = _is_crypto(symbol)
            return result
        except Exception as e:
            raise RuntimeError(f"Quote error for {symbol}: {e}") from e

    async def get_bars(self, symbol: str, timeframe: str = "1d", count: int = 100) -> list[dict]:
        try:
            return await _yf_bars(_yf_symbol(symbol), timeframe, count)
        except Exception as e:
            raise RuntimeError(f"Bars error for {symbol}: {e}") from e


# ── Stub data (no credentials configured) ─────────────────────────────────────

def _stub_account():
    return {
        "account_id": "", "cash_balance": 0.0,
        "net_liquidation": 0.0, "unrealized_pnl": 0.0,
        "realized_pnl_day": 0.0, "buying_power": 0.0, "mode": "paper",
    }

def _stub_positions():
    return []

def _stub_place_order(symbol, side, order_type, quantity, price):
    return {
        "order_id": str(uuid.uuid4())[:8].upper(), "symbol": symbol, "side": side,
        "order_type": order_type, "quantity": quantity, "price": price,
        "status": "PENDING", "created_at": datetime.utcnow().isoformat(),
    }

def _stub_orders():
    return []



# Singleton — credentials hot-reloaded via _refresh()
STUB_MODE = False   # now dynamic, checked per-call via _has_credentials()
webull = WebullClient()
