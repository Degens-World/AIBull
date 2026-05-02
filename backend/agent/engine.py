"""
Strategy engine: runs enabled strategies on a tick loop.
Strategies emit trade signals → engine validates + routes to Webull.
"""
import asyncio
from collections import deque
from datetime import datetime
from typing import Callable
from backend.webull.client import webull
from backend.config import settings

_running = False
_strategies: dict = {}
_log_callbacks: list[Callable] = []
_decisions: dict[str, deque] = {}   # strategy_id → last 30 decisions

# PDT guard: track symbols bought today (US ET date) to block same-day sells
_bought_today: dict[str, set] = {}  # "YYYY-MM-DD" → set of symbols


def _et_date() -> str:
    from datetime import timezone, timedelta
    return datetime.now(timezone(timedelta(hours=-4))).strftime("%Y-%m-%d")


def _pdt_record_buy(symbol: str):
    d = _et_date()
    _bought_today.setdefault(d, set()).add(symbol.upper())


def _pdt_blocks_sell(symbol: str) -> bool:
    """Return True if selling this symbol today would be a same-day round-trip (PDT risk)."""
    return symbol.upper() in _bought_today.get(_et_date(), set())


def register_log_callback(cb: Callable):
    _log_callbacks.append(cb)


def _log(level: str, msg: str, data: dict = None):
    entry = {"level": level, "message": msg, "data": data, "ts": datetime.utcnow().isoformat()}
    for cb in _log_callbacks:
        try:
            cb(entry)
        except Exception:
            pass


def _record_decision(strategy_id: str, entry: dict):
    if strategy_id not in _decisions:
        _decisions[strategy_id] = deque(maxlen=30)
    _decisions[strategy_id].appendleft(entry)


def get_decisions(strategy_id: str | None = None) -> dict:
    if strategy_id:
        return {strategy_id: list(_decisions.get(strategy_id, []))}
    return {sid: list(d) for sid, d in _decisions.items()}


async def run_strategy(strategy: dict):
    stype = strategy.get("strategy_type")
    if stype == "sma_crossover":
        await _sma_crossover(strategy)
    elif stype == "claude":
        await _claude_agent(strategy)
    elif stype == "options":
        await _options_agent(strategy)
    elif stype == "momentum":
        await _momentum_agent(strategy)
    elif stype == "events":
        await _events_agent(strategy)


async def _sma_crossover(strategy: dict):
    cfg = strategy.get("config", {})
    symbols = strategy.get("symbols", [])
    fast = cfg.get("fast_period", 9)
    slow = cfg.get("slow_period", 21)
    qty = cfg.get("quantity", 1)
    account_id = cfg.get("account_id") or None
    strat_id = strategy.get("id", "")

    for symbol in symbols:
        try:
            bars = await webull.get_bars(symbol, count=slow + 5)
            closes = [b["close"] for b in bars]
            if len(closes) < slow:
                continue
            sma_fast = sum(closes[-fast:]) / fast
            sma_slow = sum(closes[-slow:]) / slow
            prev_fast = sum(closes[-fast - 1:-1]) / fast
            prev_slow = sum(closes[-slow - 1:-1]) / slow

            if prev_fast < prev_slow and sma_fast > sma_slow:
                _log("SIGNAL", f"SMA crossover BUY signal: {symbol}", {"fast": sma_fast, "slow": sma_slow})
                decision = {"ts": datetime.utcnow().isoformat(), "symbol": symbol, "action": "BUY", "qty": qty,
                            "reason": f"SMA{fast} crossed above SMA{slow}", "mode": settings.trading_mode}
                if settings.trading_mode == "live":
                    result = await webull.place_order(symbol, "BUY", "MARKET", qty, account_id=account_id)
                    _log("ORDER", f"Placed BUY {qty} {symbol}", result)
                    decision["order_id"] = result.get("order_id")
                else:
                    _log("PAPER", f"[PAPER] Would BUY {qty} {symbol} @ market", {"sma_fast": sma_fast, "sma_slow": sma_slow})
                _record_decision(strat_id, decision)

            elif prev_fast > prev_slow and sma_fast < sma_slow:
                _log("SIGNAL", f"SMA crossover SELL signal: {symbol}", {"fast": sma_fast, "slow": sma_slow})
                decision = {"ts": datetime.utcnow().isoformat(), "symbol": symbol, "action": "SELL", "qty": qty,
                            "reason": f"SMA{fast} crossed below SMA{slow}", "mode": settings.trading_mode}
                if settings.trading_mode == "live":
                    result = await webull.place_order(symbol, "SELL", "MARKET", qty, account_id=account_id)
                    _log("ORDER", f"Placed SELL {qty} {symbol}", result)
                    decision["order_id"] = result.get("order_id")
                else:
                    _log("PAPER", f"[PAPER] Would SELL {qty} {symbol} @ market", {"sma_fast": sma_fast, "sma_slow": sma_slow})
                _record_decision(strat_id, decision)

            else:
                _record_decision(strat_id, {
                    "ts": datetime.utcnow().isoformat(), "symbol": symbol, "action": "HOLD",
                    "reason": f"No crossover (fast={sma_fast:.2f}, slow={sma_slow:.2f})", "mode": settings.trading_mode,
                })
        except Exception as e:
            _log("ERROR", f"SMA crossover error on {symbol}: {e}")


# Stocks confirmed to support extended-hours trading on Webull.
# Leveraged/inverse ETFs (SQQQ, TQQQ, SPXU, VXX) excluded — Webull rejects AH orders for them.
AH_TRADABLE = [
    # Broad market ETFs
    "SPY", "QQQ", "IWM", "DIA", "TLT", "GLD", "SLV",
    # Sector ETFs with AH volume
    "XLF", "XLE", "XLK", "XLV", "XLI", "XLB", "XLU", "XLP", "XLY",
    "SMH", "ARKK", "SOXX", "IBB",
    # Mega-cap tech
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "NVDA", "TSLA", "AMD",
    "INTC", "NFLX", "ORCL", "CRM", "ADBE", "QCOM", "AVGO",
    # Large-cap financials
    "JPM", "BAC", "WFC", "GS", "MS", "C", "V", "MA", "AXP", "BLK",
    # Large-cap other
    "BRK-B", "UNH", "JNJ", "PFE", "ABBV", "MRK", "LLY",
    "XOM", "CVX", "KO", "PEP", "MCD", "SBUX", "WMT", "TGT", "COST", "AMGN",
    # High-volume growth / momentum
    "PLTR", "SOFI", "COIN", "MSTR", "RIVN", "LCID", "NIO", "BABA", "JD",
    "UBER", "LYFT", "SNAP", "PINS", "RBLX", "U", "DKNG", "HOOD",
    "F", "GM", "AMAT", "LRCX", "MU", "WDC", "STX",
]
_AH_TRADABLE_SET = set(AH_TRADABLE)


def _is_scan_eligible(item: dict, min_price: float = 1.0) -> bool:
    """Filter out OTC, warrants, and illiquid symbols from screener results."""
    sym = item.get("symbol", "")
    if not sym or not sym.replace("-", "").isalpha():
        return False
    if sym.endswith(("W", "R", "P")) and len(sym) > 4:
        return False
    return item.get("price", 0) >= min_price


async def _get_scan_symbols(cfg: dict, session: str = "regular") -> list[str]:
    """
    Return symbol list to analyze.

    During pre/post sessions, equity scan is supplemented with a live fetch of
    Yahoo Finance's most-actives (filtered to AH-eligible), then backfilled from
    AH_TRADABLE so we always have enough candidates.

    If symbols are pinned in config, they are returned as-is (user override).
    asset_class: 'crypto' | 'stocks' | 'mixed'
    """
    pinned = [s for s in (cfg.get("symbols") or []) if s]
    if pinned:
        if session in ("pre", "post"):
            from backend.webull.client import _is_crypto
            pinned = [s for s in pinned if _is_crypto(s) or s.upper() in _AH_TRADABLE_SET]
        return pinned

    asset_class = cfg.get("asset_class", "stocks")
    scan_limit = int(cfg.get("scan_limit", 20))
    candidates: list[str] = []
    seen: set[str] = set()

    def _add(sym: str):
        s = sym.upper()
        if s and s not in seen:
            seen.add(s)
            candidates.append(s)

    if asset_class in ("crypto", "mixed"):
        from backend.market.movers import CRYPTO_WATCHLIST
        for s, _ in CRYPTO_WATCHLIST:
            _add(s)

    if asset_class in ("stocks", "mixed") or asset_class not in ("crypto",):
        from backend.market.movers import get_screen, get_trending

        if session in ("pre", "post"):
            # AH session — try live actives/trending from YF, filtered to AH-eligible symbols
            try:
                actives, trending = await asyncio.gather(
                    get_screen("actives", count=50),
                    get_trending(count=30),
                    return_exceptions=True,
                )
                for group in (actives, trending):
                    if not isinstance(group, list):
                        continue
                    for item in group:
                        sym = item.get("symbol", "")
                        # Only include symbols we know Webull supports AH, OR high-volume single-class equities
                        if not _is_scan_eligible(item, min_price=5.0):
                            continue
                        avg_vol = item.get("avg_volume", 0)
                        in_curated = sym.upper() in _AH_TRADABLE_SET
                        is_high_vol = avg_vol >= 1_000_000  # >1M avg daily volume → likely AH-tradable
                        if in_curated or is_high_vol:
                            _add(sym)
            except Exception as e:
                _log("WARN", f"AH live scan failed ({e}) — using curated list")
            # Backfill with curated AH_TRADABLE to ensure we always have candidates
            for sym in AH_TRADABLE:
                _add(sym)
            _log("INFO", f"AH session — {len(candidates)} AH-eligible symbols found")
        else:
            # Regular / closed — scan live market movers with higher counts
            try:
                gainers, actives, trending = await asyncio.gather(
                    get_screen("gainers",  count=25),
                    get_screen("actives",  count=25),
                    get_trending(count=25),
                    return_exceptions=True,
                )
                for group in (gainers, actives, trending):
                    if not isinstance(group, list):
                        continue
                    for item in group:
                        if _is_scan_eligible(item, min_price=1.0):
                            _add(item["symbol"])
            except Exception as e:
                _log("ERROR", f"Market scan failed: {e}")

    return candidates[:scan_limit]


async def _claude_agent(strategy: dict):
    from backend.agent.llm import chat as llm_chat
    from backend.agent import memory as mem
    import json, re

    cfg = strategy.get("config", {})
    system_prompt = cfg.get("system_prompt", "You are a disciplined stock trading assistant.")
    account_id = cfg.get("account_id") or None
    strat_id = strategy.get("id", "")
    max_position_usd = float(cfg.get("max_position_usd", 200))
    extended_hours = bool(cfg.get("extended_hours", False))

    from backend.webull.client import _is_crypto
    session = webull._market_session()

    symbols = await _get_scan_symbols(cfg, session=session)
    if not symbols:
        _log("AGENT", "No symbols to scan — market data unavailable")
        return

    # Separate crypto (24/7) from equities (session-gated)
    crypto_symbols = [s for s in symbols if _is_crypto(s)]
    equity_symbols = [s for s in symbols if not _is_crypto(s)]

    # Session gating
    if session == "closed":
        if not crypto_symbols:
            _log("INFO", "Market closed overnight — skipping tick (no crypto)")
            return
        equity_symbols = []
    elif session in ("pre", "post") and not extended_hours:
        # Strategy has AH disabled — skip equities but keep crypto
        equity_symbols = []

    # During AH, only execute orders for symbols confirmed in AH_TRADABLE_SET.
    # Live-scan symbols (high-volume but not in the curated list) are analyzed but NOT executed —
    # Webull silently rejects AH orders for most non-curated symbols without returning an error_code.
    execute_equities = session == "regular" or (extended_hours and session in ("pre", "post"))

    symbols = equity_symbols + crypto_symbols
    if not symbols:
        _log("INFO", f"No symbols to scan this tick [{session}]")
        return
    _log("AGENT", f"Scanning {len(symbols)} symbols [{session}]: {', '.join(symbols)}"
         + (" [AH execution ON]" if execute_equities and session in ("pre", "post") else ""))

    # Load persistent memory once per tick
    memory_entries = await mem.load(strat_id)
    memory_text = mem.format_for_prompt(memory_entries)

    try:
        positions = await webull.get_positions()
    except Exception as e:
        _log("WARN", f"Could not fetch positions ({e}) — skipping tick")
        return
    pos_map = {p["symbol"]: p for p in positions}

    # Fetch recent order history so the agent can review past trades per symbol
    recent_orders: list[dict] = []
    try:
        recent_orders = await webull.get_orders()
    except Exception:
        pass  # non-fatal — agent just won't have history context

    # Track available buying power so we don't over-commit within a single tick
    try:
        acct = await webull.get_account()
        available_bp = float(acct.get("buying_power", 0))
    except Exception as e:
        _log("WARN", f"Could not fetch account ({e}) — skipping tick")
        return

    # Webull requires buying power to be 2% above order value during regular hours.
    # Apply that buffer to all calculations so orders never get rejected for this reason.
    WB_BP_BUFFER = 1.02
    MIN_TRADE_BP = 20.0  # don't attempt buys below this threshold
    # Effective buying power after the 2% buffer
    effective_bp = available_bp / WB_BP_BUFFER
    monitor_only = effective_bp < MIN_TRADE_BP
    if monitor_only:
        _log("AGENT", f"Buying power ${available_bp:.2f} (effective ${effective_bp:.2f} after 2% buffer) below ${MIN_TRADE_BP:.0f} minimum — monitoring only, no new buys this tick")
    else:
        _log("AGENT", f"Available buying power: ${available_bp:.2f} (effective ${effective_bp:.2f} after 2% Webull buffer)")

    for symbol in symbols:
        await asyncio.sleep(2)  # 2s gap between symbols to avoid Webull rate limiting
        try:
            bars = await webull.get_bars(symbol, count=30)
            if len(bars) < 5:
                continue
            quote = await webull.get_quote(symbol)
            is_crypto_sym = _is_crypto(symbol)
            pos = pos_map.get(symbol)
            price = quote["price"]
            held_qty = float(pos["quantity"]) if pos else 0.0

            if is_crypto_sym and price > 0:
                # Fractional crypto: size against effective bp (crypto exempt from 2% rule but keep consistent)
                raw_qty = min(max_position_usd, effective_bp) / price
                max_qty = round(max(0.0001, raw_qty), 4)
            else:
                # Cap at effective buying power so we never exceed what Webull will accept
                affordable_max = int(min(max_position_usd, effective_bp) / price) if price > 0 else 1
                max_qty = max(1, affordable_max)
            pos_info = f' (avg cost ${pos["avg_cost"]}, P&L ${pos["unrealized_pnl"]:.2f})' if pos else ''
            pdt_blocked = not is_crypto_sym and _pdt_blocks_sell(symbol)

            # Determine whether this symbol can actually be executed in the current session
            ah_session = session in ("pre", "post")
            ah_confirmed = not is_crypto_sym and symbol.upper() in _AH_TRADABLE_SET
            can_execute = is_crypto_sym or (
                session == "regular" or
                (extended_hours and ah_session and (is_crypto_sym or ah_confirmed))
            )

            # Tell the model exactly which actions are valid given current holdings
            if monitor_only:
                if held_qty > 0:
                    if pdt_blocked:
                        valid_actions = f'HOLD   [BUY invalid — low buying power. SELL invalid — bought today, selling would trigger PDT rule]'
                    else:
                        valid_actions = f'SELL (up to {held_qty} shares held) | HOLD   [BUY is NOT valid — insufficient buying power ${available_bp:.2f}]'
                else:
                    valid_actions = 'HOLD   [BUY and SELL are NOT valid — no position and insufficient buying power]'
            elif held_qty > 0:
                if pdt_blocked:
                    valid_actions = f'BUY (add up to {max_qty} more) | HOLD   [SELL is NOT valid today — position opened today, selling same day triggers the PDT rule. Hold until tomorrow.]'
                else:
                    valid_actions = f'BUY (add up to {max_qty} more) | SELL (up to {held_qty} shares held) | HOLD'
            else:
                valid_actions = f'BUY (1-{max_qty} shares) | HOLD   [SELL is NOT valid — no position held]'

            # Build recent trade history for this symbol (last 10 fills)
            sym_orders = [
                o for o in recent_orders
                if o.get("symbol", "").upper() == symbol.upper()
                and o.get("status") in ("FILLED", "filled")
            ][-10:]
            trade_history_text = ""
            if sym_orders:
                trade_history_text = f"=== RECENT TRADES: {symbol} (last {len(sym_orders)}) ===\n"
                for o in sym_orders:
                    fill_price = o.get("filled_price") or o.get("price") or "?"
                    trade_history_text += (
                        f"  {o.get('created_at','')[:10]} {o.get('side','')} {o.get('quantity','')} "
                        f"@ ${fill_price} — {o.get('status','')}\n"
                    )
            else:
                trade_history_text = f"=== RECENT TRADES: {symbol} ===\n  No previous fills on record.\n"

            context = (
                f"=== YOUR MEMORY ===\n{memory_text}\n\n"
                f"{trade_history_text}\n"
                f"=== CURRENT ANALYSIS: {symbol} ===\n"
                f"Price: ${price} ({quote['change_pct']:+.2f}% today)\n"
                f"Held: {held_qty} shares{pos_info}\n"
                f"Valid actions: {valid_actions}\n"
                f"Session: {session} — {('orders execute immediately' if can_execute else ('ANALYSIS ONLY — ' + symbol + ' is not in the confirmed AH-tradable list; orders will be deferred to next market open' if ah_session and not is_crypto_sym and not ah_confirmed else 'ANALYSIS ONLY — equity orders will NOT be placed until regular market hours (9:30am-4pm ET)'))}\n"
                f"PDT rule: Margin account under $25,000. Never buy AND sell the same stock on the same calendar day. Plan exits for the NEXT trading day or later.\n"
                f"Re-entry rule: Review your recent trades above before buying again. If you previously exited at a loss, require a clear new catalyst before re-entering.\n"
                f"Recent 10 daily bars (OHLCV):\n"
            )
            for b in bars[-10:]:
                context += f"  {b['timestamp']}: O={b['open']} H={b['high']} L={b['low']} C={b['close']} V={b['volume']}\n"

            # Compute simple trend signal to guide the model
            closes = [b["close"] for b in bars if b["close"]]
            if len(closes) >= 10:
                sma5  = sum(closes[-5:])  / 5
                sma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else sum(closes) / len(closes)
                trend = "UPTREND" if sma5 > sma20 else "DOWNTREND"
                context += f"Trend signal: {trend} (5-day avg ${sma5:.2f} vs 20-day avg ${sma20:.2f})\n"

            context += (
                f'\nRespond ONLY with valid JSON — no markdown, no extra text:\n'
                f'{{"action":"BUY"|"SELL"|"HOLD","quantity":<int>,"reason":"<1 sentence>","note":"<observation for memory>"}}'
            )

            _log("AGENT", f"Analyzing {symbol} @ ${price} (held: {held_qty})…")
            raw = await llm_chat(context, system=system_prompt)

            # Extract JSON even if model wraps it in markdown
            match = re.search(r'\{[^{}]+\}', raw, re.DOTALL)
            if not match:
                _log("ERROR", f"LLM non-JSON for {symbol}: {raw[:120]}")
                continue
            decision_raw = json.loads(match.group())
            action = decision_raw.get("action", "HOLD").upper()
            qty = int(decision_raw.get("quantity", 0))
            reason = decision_raw.get("reason", "")
            note = decision_raw.get("note", "")

            # Safety clamps — enforce valid actions
            if action == "SELL" and held_qty == 0:
                action = "HOLD"
                qty = 0
            elif action == "SELL" and pdt_blocked and not is_crypto_sym:
                # Hard PDT guard — never allow same-day sell of a position opened today
                _log("WARN", f"PDT guard: blocking same-day SELL of {symbol} — will hold until next session")
                action = "HOLD"
                qty = 0
            elif action == "BUY":
                qty = max(1, min(qty, max_qty))
            elif action == "SELL":
                qty = max(1, min(qty, held_qty))
            else:
                qty = 0

            _log("AGENT", f"Decision {symbol}: {action} {qty} — {reason}")

            decision = {"ts": datetime.utcnow().isoformat(), "symbol": symbol, "action": action,
                        "qty": qty, "reason": reason, "mode": settings.trading_mode}

            if action in ("BUY", "SELL") and qty > 0:
                if not can_execute:
                    _log("INFO", f"[NOTED for next open] {action} {qty} {symbol} @ ~${price} — {reason}")
                elif settings.trading_mode == "live":
                    order_cost = price * qty if action == "BUY" else 0.0
                    if action == "BUY" and order_cost > effective_bp:
                        # Trim qty to fit inside effective buying power (accounts for Webull's 2% buffer)
                        affordable_qty = int(effective_bp / price) if price > 0 else 0
                        if affordable_qty <= 0:
                            _log("WARN", f"Skipping BUY {qty} {symbol} — insufficient buying power (${available_bp:.2f} available, need ${order_cost * WB_BP_BUFFER:.2f})")
                            action = "HOLD"
                            qty = 0
                        else:
                            _log("WARN", f"Trimming BUY {qty}→{affordable_qty} {symbol} to fit buying power ${available_bp:.2f}")
                            qty = affordable_qty
                            order_cost = price * qty

                    if action in ("BUY", "SELL") and qty > 0:
                        try:
                            result = await webull.place_order(
                                symbol, action, "MARKET", qty,
                                price=round(price, 2),
                                account_id=account_id,
                                extended_hours=(session in ("pre", "post")),
                            )
                            order_id = result.get("order_id", "?")
                            _log("ORDER", f"Placed {action} {qty} {symbol} [{session}] — order_id={order_id}", result)
                            decision["order_id"] = result.get("order_id")
                            if action == "BUY":
                                available_bp -= order_cost * WB_BP_BUFFER
                                effective_bp = available_bp / WB_BP_BUFFER
                                if not is_crypto_sym:
                                    _pdt_record_buy(symbol)  # block same-day sell
                        except RuntimeError as e:
                            err = str(e)
                            if err.startswith("REVERSE_BLOCKED"):
                                _log("WARN", f"Skipping {action} {symbol} — would reverse position (open order conflict)")
                                decision["action"] = "HOLD"
                            elif err == "RATE_LIMITED":
                                _log("WARN", f"Rate limited — pausing 30s")
                                await asyncio.sleep(30)
                            elif err.startswith("ORDER_FAILED:"):
                                _log("ERROR", f"Order rejected for {symbol}: {err[len('ORDER_FAILED:'):]}")
                            else:
                                _log("ERROR", f"Order failed for {symbol}: {e}")
                else:
                    _log("PAPER", f"[PAPER] Would {action} {qty} {symbol} @ ~${price} [{session}] — {reason}")

            _record_decision(strat_id, decision)

            # Save memory entry
            await mem.append(strat_id, {
                "ts": datetime.utcnow().isoformat(),
                "symbol": symbol,
                "action": action,
                "price": price,
                "note": note or reason,
            })

        except Exception as e:
            _log("ERROR", f"Agent error on {symbol}: {e}")


async def _options_agent(strategy: dict):
    """
    Options trading agent: for each symbol, fetches the option chain from Yahoo Finance,
    asks the LLM to pick a contract (call or put, strike, expiration), and executes via Webull.
    Only runs during regular market hours — options don't trade AH.
    """
    from backend.agent.llm import chat as llm_chat
    from backend.agent import memory as mem
    import json, re

    cfg = strategy.get("config", {})
    system_prompt = cfg.get("system_prompt", "You are a disciplined options trading assistant.")
    account_id = cfg.get("account_id") or None
    strat_id = strategy.get("id", "")
    max_position_usd = float(cfg.get("max_position_usd", 200))

    session = webull._market_session()
    if session != "regular":
        _log("INFO", f"Options agent: market is {session} — options only execute during regular hours")
        return

    symbols = await _get_scan_symbols(cfg, session=session)
    if not symbols:
        _log("AGENT", "Options agent: no symbols to scan")
        return

    try:
        acct = await webull.get_account()
        available_bp = float(acct.get("buying_power", 0))
    except Exception as e:
        _log("WARN", f"Could not fetch account ({e}) — skipping tick")
        return

    memory_entries = await mem.load(strat_id)
    memory_text = mem.format_for_prompt(memory_entries)

    try:
        positions = await webull.get_positions()
    except Exception as e:
        _log("WARN", f"Could not fetch positions ({e}) — skipping tick")
        return
    option_pos_map = {p["symbol"]: p for p in positions if p.get("symbol", "").count("_") >= 2 or len(p.get("symbol", "")) > 8}

    for symbol in symbols:
        await asyncio.sleep(3)
        try:
            quote = await webull.get_quote(symbol)
            price = quote["price"]
            if price <= 0:
                continue

            _log("AGENT", f"Fetching option chain for {symbol} @ ${price}…")
            try:
                chain_data = await webull.get_option_chain(symbol, max_expirations=2)
            except Exception as e:
                _log("WARN", f"Option chain unavailable for {symbol}: {e}")
                continue

            expirations = chain_data.get("expirations", [])
            if not expirations:
                _log("WARN", f"No option contracts found for {symbol}")
                continue

            # Build a compact summary of available contracts (near-the-money, liquid)
            # Also track valid contract symbols so we can reject LLM hallucinations
            valid_contracts: set[str] = set()
            chain_summary = f"=== OPTION CHAIN: {symbol} @ ${price} ===\n"
            for exp in expirations[:2]:
                chain_summary += f"\nExpiration: {exp}\n"
                exp_data = chain_data.get("chains", {}).get(exp, {})
                for otype in ("calls", "puts"):
                    contracts = exp_data.get(otype, [])
                    # Filter to near-the-money (within 10% of current price) with some volume
                    ntm = [c for c in contracts
                           if c.get("bid", 0) > 0
                           and abs(c["strike"] - price) / price <= 0.10]
                    if not ntm:
                        ntm = contracts[:5]
                    chain_summary += f"  {otype.upper()} (near-the-money):\n"
                    for c in ntm[:6]:
                        valid_contracts.add(c["contract_symbol"])
                        chain_summary += (
                            f"    {c['contract_symbol']} strike=${c['strike']} "
                            f"bid=${c['bid']} ask=${c['ask']} IV={c['implied_vol']:.1%} "
                            f"OI={c['open_interest']} vol={c['volume']}"
                            + (f" ITM" if c.get("in_the_money") else "") + "\n"
                        )

            bars = await webull.get_bars(symbol, count=20)
            closes = [b["close"] for b in bars if b["close"]]
            trend_text = ""
            if len(closes) >= 10:
                sma5  = sum(closes[-5:]) / 5
                sma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else sum(closes) / len(closes)
                trend_text = f"Trend: {'UPTREND' if sma5 > sma20 else 'DOWNTREND'} (5d avg ${sma5:.2f} vs 20d avg ${sma20:.2f})\n"

            # Current option positions for this underlying
            held_contracts = {sym: p for sym, p in option_pos_map.items() if symbol.upper() in sym.upper()}
            held_text = ""
            if held_contracts:
                held_text = "Open option positions:\n"
                for sym, p in held_contracts.items():
                    held_text += f"  {sym}: {p['quantity']} contracts @ avg ${p['avg_cost']}, P&L ${p['unrealized_pnl']:.2f}\n"
            else:
                held_text = "No open option positions for this underlying.\n"

            max_contracts = max(1, int(max_position_usd / (price * 100 * 0.05)))  # rough: assume ~5% of stock price per contract

            context = (
                f"=== YOUR MEMORY ===\n{memory_text}\n\n"
                f"{held_text}\n"
                f"=== UNDERLYING: {symbol} ===\n"
                f"Price: ${price} ({quote['change_pct']:+.2f}% today)\n"
                f"{trend_text}"
                f"Buying power available: ${available_bp:.2f}\n"
                f"Max position: ${max_position_usd:.0f} (approx {max_contracts} contract(s) depending on premium)\n\n"
                f"{chain_summary}\n"
                f"=== INSTRUCTIONS ===\n"
                f"Analyze the underlying price action and option chain above.\n"
                f"Each contract represents 100 shares. Buy premium is debit (cost = ask × 100 × qty).\n"
                f"Only pick contracts with bid > 0 and open_interest > 0 (liquid contracts).\n"
                f"Choose PASS if there is no clear high-conviction setup.\n"
                f"PDT rule does NOT apply to options — you can open and close same day.\n\n"
                f"Respond ONLY with valid JSON:\n"
                f'{{"action":"BUY_CALL"|"BUY_PUT"|"SELL_TO_CLOSE"|"PASS",'
                f'"contract_symbol":"<exact contract_symbol from chain above>",'
                f'"option_type":"CALL"|"PUT","quantity":<int 1-{max_contracts}>,'
                f'"limit_price":<float — use midpoint of bid/ask>,'
                f'"reason":"<1 sentence>","note":"<observation for memory>"}}'
            )

            _log("AGENT", f"Analyzing options for {symbol} @ ${price}…")
            raw = await llm_chat(context, system=system_prompt)

            match = re.search(r'\{[^{}]+\}', raw, re.DOTALL)
            if not match:
                _log("ERROR", f"LLM non-JSON for {symbol} options: {raw[:120]}")
                continue
            dec = json.loads(match.group())
            action = dec.get("action", "PASS").upper()
            contract_sym = dec.get("contract_symbol", "")
            opt_type = (dec.get("option_type") or "CALL").upper()
            qty = max(1, int(dec.get("quantity", 1)))
            limit_px = float(dec.get("limit_price", 0))
            reason = dec.get("reason", "")
            note = dec.get("note", "")

            # Hard validation — only allow known option actions
            _VALID_OPT_ACTIONS = {"BUY_CALL", "BUY_PUT", "SELL_TO_CLOSE", "PASS"}
            if action not in _VALID_OPT_ACTIONS:
                _log("WARN", f"Options agent: LLM returned unknown action '{action}' for {symbol} — forcing PASS (this prevents accidental equity orders)")
                action = "PASS"

            # Validate contract symbol was in the chain we sent — prevents LLM hallucination from placing equity orders
            if action != "PASS" and contract_sym and contract_sym not in valid_contracts:
                _log("WARN", f"Options agent: '{contract_sym}' was not in the provided option chain for {symbol} — forcing PASS (LLM hallucinated a contract symbol)")
                action = "PASS"

            _log("AGENT", f"Options decision {symbol}: {action} {qty}x {contract_sym} @ ${limit_px} — {reason}")

            if action == "PASS" or not contract_sym or limit_px <= 0:
                pass
            elif settings.trading_mode == "live":
                order_cost = limit_px * 100 * qty
                if order_cost > available_bp:
                    _log("WARN", f"Skipping {action} {contract_sym} — insufficient buying power (${available_bp:.2f} available, need ${order_cost:.2f})")
                else:
                    try:
                        side = "BUY" if action in ("BUY_CALL", "BUY_PUT") else "SELL"
                        result = await webull.place_option_order(
                            contract_sym, opt_type, side, qty, limit_px, account_id=account_id
                        )
                        _log("ORDER", f"Option order placed: {action} {qty}x {contract_sym} @ ${limit_px} — order_id={result.get('order_id', '?')}", result)
                        if side == "BUY":
                            available_bp -= order_cost
                    except RuntimeError as e:
                        err = str(e)
                        if err.startswith("ORDER_FAILED:"):
                            _log("ERROR", f"Option order rejected for {contract_sym}: {err[len('ORDER_FAILED:'):]}")
                        elif err == "RATE_LIMITED":
                            _log("WARN", "Rate limited — pausing 30s")
                            await asyncio.sleep(30)
                        else:
                            _log("ERROR", f"Option order failed for {contract_sym}: {e}")
            else:
                _log("PAPER", f"[PAPER] Would {action} {qty}x {contract_sym} @ ${limit_px} — {reason}")

            _record_decision(strat_id, {
                "ts": datetime.utcnow().isoformat(),
                "symbol": contract_sym or symbol,
                "action": action, "qty": qty,
                "reason": reason, "mode": settings.trading_mode,
            })
            await mem.append(strat_id, {
                "ts": datetime.utcnow().isoformat(),
                "symbol": symbol, "action": action,
                "price": price, "note": note or reason,
            })

        except Exception as e:
            _log("ERROR", f"Options agent error on {symbol}: {e}")


async def _events_agent(strategy: dict):
    """
    Prediction market agent. Fetches open Webull event contracts,
    gets live YES/NO prices, asks LLM to pick bets, executes BUY YES/NO orders.
    Each contract settles at $1.00 (win) or $0.00 (loss) — price = implied probability.
    """
    from backend.agent.llm import chat as llm_chat
    import json, re

    cfg = strategy.get("config", {})
    system_prompt = cfg.get("system_prompt", (
        "You are a disciplined prediction market trader on Webull. "
        "Each contract pays $1 if the event happens, $0 if it doesn't. "
        "The price IS the implied probability. You make money by finding mispriced probabilities. "
        "Only bet when you have a strong opinion that the market price is significantly wrong. "
        "Return [] if no contracts offer clear edge."
    ))
    account_id   = cfg.get("account_id") or None
    strat_id     = strategy.get("id", "")
    max_position = float(cfg.get("max_position_usd", 100))

    session = webull._market_session()
    if session == "closed":
        _log("INFO", "Events agent: market closed overnight — skipping tick")
        return

    try:
        acct = await webull.get_account()
        available_bp = float(acct.get("buying_power", 0))
    except Exception as e:
        _log("WARN", f"Events: could not fetch account ({e}) — skipping tick")
        return

    if available_bp < 10:
        _log("AGENT", f"Events: insufficient buying power (${available_bp:.2f}) — skipping tick")
        return

    # Fetch active event series
    _log("AGENT", "Events agent: fetching prediction market series…")
    try:
        series_list = await webull.get_event_series()
    except Exception as e:
        _log("ERROR", f"Events: could not fetch series ({e})")
        return

    if not series_list:
        _log("AGENT", "Events: no active prediction market series found")
        return

    # Collect contracts across all series (respect scan_limit)
    scan_limit = int(cfg.get("scan_limit", 20))
    all_contracts: list[dict] = []
    for series in series_list[:10]:  # cap at 10 series
        sym = series.get("series_symbol", "")
        if not sym:
            continue
        try:
            contracts = await webull.get_event_contracts(sym)
            for c in contracts:
                c["series_name"] = series.get("name", sym)
            all_contracts.extend(contracts)
        except Exception:
            pass
        await asyncio.sleep(0.5)

    if not all_contracts:
        _log("AGENT", "Events: no open contracts found across all series")
        return

    all_contracts = all_contracts[:scan_limit]
    _log("AGENT", f"Events: found {len(all_contracts)} open contracts — fetching live prices…")

    # Get live YES/NO snapshots
    contract_symbols = [c["symbol"] for c in all_contracts if c.get("symbol")]
    snapshot_map: dict[str, dict] = {}
    try:
        snapshots = await webull.get_event_snapshot(contract_symbols)
        snapshot_map = {s["symbol"]: s for s in snapshots}
    except Exception as e:
        _log("WARN", f"Events: snapshot fetch failed ({e}) — proceeding without live prices")

    # Build batch context for LLM
    contract_blocks: list[str] = []
    for c in all_contracts:
        sym = c.get("symbol", "")
        snap = snapshot_map.get(sym, {})
        yes_price = snap.get("yes_price") or snap.get("yes_ask") or 0
        no_price  = round(1 - yes_price, 4) if yes_price else 0
        vol       = snap.get("volume", 0)
        oi        = snap.get("open_interest", 0)
        if yes_price <= 0:
            continue  # skip contracts with no live price
        max_contracts = max(1, int(max_position / yes_price)) if yes_price > 0 else 1
        contract_blocks.append(
            f"--- {sym} ---\n"
            f"Question: {c.get('question') or c.get('series_name', '')}\n"
            f"Underlying: {c.get('underlying', 'N/A')} | Expires: {c.get('expiration', 'N/A')}\n"
            f"YES price: ${yes_price:.2f} (implied {yes_price*100:.0f}% probability)\n"
            f"NO  price: ${no_price:.2f} (implied {no_price*100:.0f}% probability)\n"
            f"Volume: {vol:,} | Open Interest: {oi:,}\n"
            f"Max contracts @ max_position (${max_position:.0f}): {max_contracts}\n"
        )

    if not contract_blocks:
        _log("AGENT", "Events: no contracts with live prices — skipping LLM call")
        return

    context = (
        f"=== PREDICTION MARKET SCAN — {len(contract_blocks)} CONTRACTS ===\n"
        f"Available buying power: ${available_bp:.2f}\n"
        f"Max position per trade: ${max_position:.0f}\n\n"
        + "\n".join(contract_blocks)
        + "\n=== INSTRUCTIONS ===\n"
        "Each contract pays $1.00 if YES, $0.00 if NO at expiration.\n"
        "Price = implied probability. Edge = your probability - market probability.\n"
        "Only bet when you have strong conviction the market is mispriced by >10%.\n"
        "quantity = int(max_position / limit_price)\n\n"
        "Respond ONLY with a JSON array ([] if no bets):\n"
        '[{"rank":1,"symbol":"SYM","outcome":"yes"|"no","quantity":<int>,'
        '"limit_price":<float 0.01-0.99>,"reason":"<1 sentence>"}]'
    )

    _log("AGENT", f"Events: sending {len(contract_blocks)} contracts to LLM…")
    raw = await llm_chat(context, system=system_prompt)

    match = re.search(r'\[.*\]', raw, re.DOTALL)
    if not match:
        _log("ERROR", f"Events: LLM returned non-array: {raw[:200]}")
        return
    try:
        bets: list[dict] = json.loads(match.group())
    except json.JSONDecodeError as exc:
        _log("ERROR", f"Events: JSON parse error ({exc})")
        return

    if not isinstance(bets, list) or not bets:
        _log("AGENT", "Events: LLM found no prediction market edge this tick")
        return

    valid_syms = {c["symbol"] for c in all_contracts if c.get("symbol")}
    for bet in bets:
        sym      = (bet.get("symbol") or "").strip()
        outcome  = (bet.get("outcome") or "yes").lower()
        quantity = int(bet.get("quantity") or 0)
        limit_px = float(bet.get("limit_price") or 0)
        reason   = bet.get("reason", "")

        if not sym or quantity <= 0 or not (0.01 <= limit_px <= 0.99):
            continue
        if sym not in valid_syms:
            _log("WARN", f"Events: '{sym}' not in scanned contracts — skipping (hallucination guard)")
            continue
        if outcome not in ("yes", "no"):
            continue

        order_cost = limit_px * quantity
        if order_cost > available_bp:
            affordable = int(available_bp / limit_px)
            if affordable <= 0:
                _log("WARN", f"Events: skipping {sym} — insufficient BP (${available_bp:.2f} < ${order_cost:.2f})")
                continue
            quantity = affordable
            order_cost = limit_px * quantity

        _log("AGENT", f"Events decision: BUY {outcome.upper()} {quantity}x {sym} @ ${limit_px} — {reason}")

        if settings.trading_mode == "live":
            try:
                result = await webull.place_event_order(sym, outcome, quantity, limit_px, account_id)
                _log("ORDER", f"Event order: BUY {outcome.upper()} {quantity}x {sym} @ ${limit_px} — order_id={result.get('order_id','?')}", result)
                available_bp -= order_cost
            except RuntimeError as e:
                err = str(e)
                if err.startswith("ORDER_FAILED:"):
                    _log("ERROR", f"Event order rejected {sym}: {err[len('ORDER_FAILED:'):]}")
                elif err == "RATE_LIMITED":
                    _log("WARN", "Rate limited — pausing 30s")
                    await asyncio.sleep(30)
                else:
                    _log("ERROR", f"Event order failed {sym}: {e}")
        else:
            _log("PAPER", f"[PAPER] Events BUY {outcome.upper()} {quantity}x {sym} @ ${limit_px} — {reason}")

        _record_decision(strat_id, {
            "ts":     datetime.utcnow().isoformat(),
            "symbol": sym, "action": f"BUY_{outcome.upper()}",
            "qty":    quantity, "reason": reason, "mode": settings.trading_mode,
        })
        await asyncio.sleep(1)


async def _momentum_agent(strategy: dict):
    """
    Small-cap momentum trader: $2–$20 universe, batch LLM analysis, proportional allocation.

    Flow:
      1. Scan gainers + actives, filter to $2-$20 / 750k avg vol / 2x rel-vol
      2. Fetch bars for all candidates in parallel
      3. One LLM call — returns ranked JSON array of 0–5 trades
      4. Execute with allocation-model sizing (2=40%BP, 3=30%, 4=22.5%, 5=18%)
      5. PDT guard on every order
    """
    from backend.agent.llm import chat as llm_chat
    from backend.market.movers import get_screen
    import json, re

    cfg = strategy.get("config", {})
    system_prompt = cfg.get("system_prompt", (
        "You are a disciplined small-cap momentum day trader. "
        "Universe: stocks priced $2–$20 only — never trade large-caps or mega-caps. "
        "Focus on 2x+ relative volume, strong intraday momentum, and clear breakout setups. "
        "Require at least 2:1 risk/reward. Cut losers fast at the stop. "
        "Return [] if there are no high-conviction setups."
    ))
    account_id = cfg.get("account_id") or None
    strat_id = strategy.get("id", "")
    max_position_usd = float(cfg.get("max_position_usd", 500))

    session = webull._market_session()
    if session == "closed":
        _log("INFO", "Momentum agent: market closed overnight — skipping tick")
        return

    WB_BP_BUFFER = 1.02
    ah_session = session in ("pre", "post")

    try:
        acct = await webull.get_account()
        available_bp = float(acct.get("buying_power", 0))
    except Exception as e:
        _log("WARN", f"Momentum: could not fetch account ({e}) — skipping tick")
        return

    effective_bp = available_bp / WB_BP_BUFFER
    if effective_bp < 50:
        _log("AGENT", f"Momentum: insufficient buying power (${available_bp:.2f}) — skipping tick")
        return

    try:
        positions = await webull.get_positions()
    except Exception as e:
        _log("WARN", f"Momentum: could not fetch positions ({e}) — skipping tick")
        return

    pos_map = {p["symbol"].upper(): p for p in positions}
    held_symbols = {sym for sym, p in pos_map.items() if float(p.get("quantity", 0)) > 0}

    _log("AGENT", f"Momentum: scanning gainers + actives for $2–$20 candidates [{session}]…")
    try:
        gainers_raw, actives_raw = await asyncio.gather(
            get_screen("gainers", count=50),
            get_screen("actives", count=50),
            return_exceptions=True,
        )
    except Exception as e:
        _log("ERROR", f"Momentum scan failed: {e}")
        return

    # Merge and deduplicate
    all_items: list[dict] = []
    seen_syms: set[str] = set()
    for group in (gainers_raw, actives_raw):
        if not isinstance(group, list):
            continue
        for item in group:
            sym = item.get("symbol", "").upper()
            if sym and sym not in seen_syms:
                seen_syms.add(sym)
                all_items.append(item)

    MIN_PRICE, MAX_PRICE = 2.0, 20.0
    MIN_AVG_VOL = 750_000
    MIN_REL_VOL = 2.0

    candidates: list[dict] = []
    for item in all_items:
        sym = item.get("symbol", "").upper()
        price = item.get("price", 0)
        avg_vol = item.get("avg_volume", 0)
        vol = item.get("volume", 0)
        if not (MIN_PRICE <= price <= MAX_PRICE):
            continue
        if avg_vol < MIN_AVG_VOL:
            continue
        rel_vol = (vol / avg_vol) if avg_vol > 0 else 0
        if rel_vol < MIN_REL_VOL:
            continue
        # Skip warrants / OTC (symbols with digits or > 5 chars)
        if not sym.replace("-", "").isalpha() or len(sym) > 5:
            continue
        item["symbol"] = sym
        item["rel_vol"] = round(rel_vol, 2)
        candidates.append(item)

    if not candidates:
        _log("AGENT", "Momentum: no candidates meet filter criteria ($2–$20, 750k avg vol, 2x rel vol)")
        return

    _log("AGENT", f"Momentum: {len(candidates)} candidates — fetching bars in parallel")

    async def _safe_bars(sym: str):
        try:
            return sym, await webull.get_bars(sym, count=20)
        except Exception:
            return sym, []

    bars_results = await asyncio.gather(*[_safe_bars(c["symbol"]) for c in candidates])
    bars_map: dict[str, list] = {sym: bars for sym, bars in bars_results if bars}

    # Allocation model: total positions → % of buying power per slot
    _ALLOC = {1: 0.40, 2: 0.40, 3: 0.30, 4: 0.225, 5: 0.18}

    max_new_positions = max(0, 5 - len(held_symbols))
    if max_new_positions == 0:
        _log("AGENT", f"Momentum: already at 5 open positions — monitoring only")
        return

    # Estimate total slots to determine allocation %
    projected_total = min(len(candidates), max_new_positions) + len(held_symbols)
    alloc_pct = _ALLOC.get(min(projected_total, 5), 0.18)
    position_bp = min(effective_bp * alloc_pct, max_position_usd)

    # Build batch context
    candidate_blocks: list[str] = []
    for item in candidates:
        sym = item["symbol"]
        price = item["price"]
        change_pct = item.get("change_pct", 0)
        rel_vol = item.get("rel_vol", 0)
        avg_vol = item.get("avg_volume", 0)
        vol = item.get("volume", 0)
        bars = bars_map.get(sym, [])
        closes = [b["close"] for b in bars if b.get("close")]
        trend = ""
        if len(closes) >= 5:
            sma5 = sum(closes[-5:]) / 5
            sma10 = sum(closes[-10:]) / 10 if len(closes) >= 10 else sum(closes) / len(closes)
            trend = f"Trend: {'UP' if sma5 > sma10 else 'DOWN'} (5d avg ${sma5:.2f} / 10d avg ${sma10:.2f})"
        bar_lines = "".join(
            f"  {b.get('timestamp','')}: O={b['open']} H={b['high']} L={b['low']} C={b['close']} V={b['volume']}\n"
            for b in bars[-5:]
        )
        candidate_blocks.append(
            f"--- {sym} ---\n"
            f"Price: ${price} ({change_pct:+.2f}%) | RelVol: {rel_vol:.1f}x (vol {vol:,} / avg {avg_vol:,})\n"
            f"{trend}\nRecent bars:\n{bar_lines}"
            f"Currently held: {'YES' if sym in held_symbols else 'NO'}\n"
        )

    context = (
        f"=== MOMENTUM SCAN — {len(candidates)} CANDIDATES ===\n"
        f"Available buying power: ${available_bp:.2f} (effective ${effective_bp:.2f})\n"
        f"Current open positions ({len(held_symbols)}): {', '.join(held_symbols) if held_symbols else 'none'}\n"
        f"Max new positions this tick: {max_new_positions}\n"
        f"Allocated BP per new position: ${position_bp:.2f} "
        f"({int(alloc_pct * 100)}% of effective BP)\n\n"
        + "\n".join(candidate_blocks)
        + "\n=== INSTRUCTIONS ===\n"
        f"Select 0 to {max_new_positions} stocks. Do NOT exceed {max_new_positions} picks.\n"
        f"For each trade:\n"
        f"  shares = int(${position_bp:.0f} / entry_price) — apply 70% initial chunk (round down)\n"
        f"  stop_loss: recent swing low or entry * 0.95 max\n"
        f"  target: minimum 2x the risk (target - entry >= 2 * (entry - stop_loss))\n"
        f"  Skip any setup that is already extended >5% from the day's open\n"
        f"PDT rule: margin account under $25k — never open AND close same stock same day.\n\n"
        f"Respond ONLY with a valid JSON array ([] if no trades):\n"
        f'[{{"rank":1,"ticker":"SYM","action":"BUY","shares":<int>,"entry_price":<float>,"stop_loss":<float>,"target":<float>,"reason":"<1 sentence>"}}, ...]'
    )

    _log("AGENT", f"Momentum: sending {len(candidates)} candidates to LLM…")
    raw = await llm_chat(context, system=system_prompt)

    # Parse JSON array from LLM response
    match = re.search(r'\[.*\]', raw, re.DOTALL)
    if not match:
        _log("ERROR", f"Momentum: LLM returned non-array: {raw[:200]}")
        return
    try:
        trades: list[dict] = json.loads(match.group())
    except json.JSONDecodeError as exc:
        _log("ERROR", f"Momentum: JSON parse error ({exc}) — raw: {raw[:200]}")
        return

    if not isinstance(trades, list):
        _log("ERROR", "Momentum: LLM did not return a list")
        return
    if not trades:
        _log("AGENT", "Momentum: LLM found no high-conviction setups this tick")
        return

    trades = trades[:max_new_positions]
    _log("AGENT", f"Momentum: executing {len(trades)} trade(s): {[t.get('ticker','?') for t in trades]}")

    valid_tickers = {c["symbol"].upper() for c in candidates}
    for trade in trades:
        ticker = (trade.get("ticker") or "").upper().strip()
        action = (trade.get("action") or "BUY").upper()
        shares = int(trade.get("shares") or 0)
        entry_price = float(trade.get("entry_price") or 0)
        stop_loss = float(trade.get("stop_loss") or 0)
        reason = trade.get("reason", "")

        if not ticker or shares <= 0 or entry_price <= 0 or action != "BUY":
            continue
        if ticker not in valid_tickers:
            _log("WARN", f"Momentum: LLM returned ticker '{ticker}' not in candidate list — skipping (hallucination guard)")
            continue
        if _pdt_blocks_sell(ticker):
            _log("WARN", f"Momentum: PDT guard — {ticker} already traded today, skipping")
            continue

        order_cost = entry_price * shares
        if order_cost > effective_bp:
            affordable = int(effective_bp / entry_price)
            if affordable <= 0:
                _log("WARN", f"Momentum: skipping {ticker} — insufficient BP (${effective_bp:.2f} < ${order_cost:.2f})")
                continue
            _log("WARN", f"Momentum: trimming {ticker} {shares}→{affordable} shares to fit BP")
            shares = affordable
            order_cost = entry_price * shares

        _log("AGENT", f"Momentum decision: BUY {shares} {ticker} @ ${entry_price} stop=${stop_loss:.2f} — {reason}")

        if settings.trading_mode == "live":
            try:
                result = await webull.place_order(
                    ticker, "BUY", "LIMIT", shares,
                    price=round(entry_price, 2),
                    account_id=account_id,
                    extended_hours=ah_session,
                )
                order_id = result.get("order_id", "?")
                _log("ORDER", f"Momentum BUY {shares} {ticker} @ ${entry_price} — order_id={order_id}", result)
                available_bp -= order_cost * WB_BP_BUFFER
                effective_bp = available_bp / WB_BP_BUFFER
                _pdt_record_buy(ticker)
            except RuntimeError as e:
                err = str(e)
                if err.startswith("ORDER_FAILED:"):
                    _log("ERROR", f"Momentum order rejected {ticker}: {err[len('ORDER_FAILED:'):]}")
                elif err == "RATE_LIMITED":
                    _log("WARN", "Rate limited — pausing 30s")
                    await asyncio.sleep(30)
                else:
                    _log("ERROR", f"Momentum order failed {ticker}: {e}")
        else:
            _log("PAPER", f"[PAPER] Momentum BUY {shares} {ticker} @ ${entry_price} stop=${stop_loss:.2f} [{session}] — {reason}")

        _record_decision(strat_id, {
            "ts": datetime.utcnow().isoformat(),
            "symbol": ticker, "action": "BUY", "qty": shares,
            "reason": reason, "mode": settings.trading_mode,
        })
        await asyncio.sleep(1)


async def tick_loop(interval_seconds: int = 60):
    global _running
    _running = True
    _log("INFO", f"Engine started (interval={interval_seconds}s, mode={settings.trading_mode})")
    while _running:
        for strat in list(_strategies.values()):
            if strat.get("enabled"):
                await run_strategy(strat)
        await asyncio.sleep(interval_seconds)


def start_engine(strategies: list[dict], interval: int = 60):
    global _strategies
    _strategies = {s["id"]: s for s in strategies}
    loop = asyncio.get_event_loop()
    loop.create_task(tick_loop(interval))


def stop_engine():
    global _running
    _running = False
    _log("INFO", "Engine stopped")


def update_strategies(strategies: list[dict]):
    global _strategies
    _strategies = {s["id"]: s for s in strategies}
