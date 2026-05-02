"""
AIBull Telegram bot.
Provides remote control and trade alerts via Telegram.

Commands:
  /account   — account summary
  /positions — open positions
  /quote SYMBOL
  /buy SYMBOL QTY [PRICE]
  /sell SYMBOL QTY [PRICE]
  /engine start|stop|status
  /logs      — last 10 agent log entries
  /help
"""
import asyncio
import logging
from typing import Optional

from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode

from backend.config import settings
from backend.webull.client import webull
from backend.agent import engine as agent_engine

log = logging.getLogger(__name__)

_app: Optional[Application] = None
_allowed_chat_id: Optional[int] = None   # set from first /start, or via TELEGRAM_CHAT_ID env


def _save_chat_id(chat_id: int):
    """Persist chat_id to .env and hot-reload settings."""
    import os
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    lines: list[str] = []
    found = False
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("TELEGRAM_CHAT_ID="):
                    lines.append(f"TELEGRAM_CHAT_ID={chat_id}\n")
                    found = True
                else:
                    lines.append(line if line.endswith("\n") else line + "\n")
    if not found:
        lines.append(f"TELEGRAM_CHAT_ID={chat_id}\n")
    with open(env_path, "w") as f:
        f.writelines(lines)
    object.__setattr__(settings, "telegram_chat_id", chat_id)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt(value: float, prefix: str = "$") -> str:
    return f"{prefix}{value:,.2f}"

def _pnl(value: float) -> str:
    sign = "+" if value >= 0 else ""
    color = "🟢" if value >= 0 else "🔴"
    return f"{color} {sign}{_fmt(value)}"

def _guard(update: Update) -> bool:
    """Return False and warn if sender is not the authorized chat."""
    if _allowed_chat_id is None:
        return True
    if update.effective_chat.id != _allowed_chat_id:
        return False
    return True


# ── Command handlers ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global _allowed_chat_id
    _allowed_chat_id = update.effective_chat.id
    # Persist so it survives restarts
    _save_chat_id(_allowed_chat_id)
    await update.message.reply_text(
        "🤖 *AIBull Trading Bot*\n\n"
        "Authorized this chat. Use /help to see commands.",
        parse_mode=ParseMode.MARKDOWN,
    )

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _guard(update):
        return
    text = (
        "📖 *AIBull Commands*\n\n"
        "`/account` — account summary\n"
        "`/positions` — open positions\n"
        "`/quote SYMBOL` — live quote\n"
        "`/buy SYMBOL QTY` — market buy\n"
        "`/buy SYMBOL QTY PRICE` — limit buy\n"
        "`/sell SYMBOL QTY` — market sell\n"
        "`/sell SYMBOL QTY PRICE` — limit sell\n"
        "`/engine start|stop|status` — engine control\n"
        "`/logs` — recent agent logs\n"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def cmd_account(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _guard(update):
        return
    acct = await webull.get_account()
    mode_tag = "📄 PAPER" if acct.get("mode") == "paper" else "⚡ LIVE"
    text = (
        f"💼 *Account Summary* {mode_tag}\n\n"
        f"Net Liq:      `{_fmt(acct['net_liquidation'])}`\n"
        f"Cash:         `{_fmt(acct['cash_balance'])}`\n"
        f"Buying Power: `{_fmt(acct['buying_power'])}`\n"
        f"Unrealized:   {_pnl(acct['unrealized_pnl'])}\n"
        f"Day P&L:      {_pnl(acct['realized_pnl_day'])}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def cmd_positions(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _guard(update):
        return
    positions = await webull.get_positions()
    if not positions:
        await update.message.reply_text("No open positions.")
        return
    lines = ["📊 *Open Positions*\n"]
    for p in positions:
        pnl_str = _pnl(p["unrealized_pnl"])
        lines.append(
            f"`{p['symbol']:6}` {p['quantity']} shares  "
            f"avg ${p['avg_cost']}  →  ${p['current_price']}\n"
            f"  P&L: {pnl_str}  (${p['market_value']:,.0f} mkt val)"
        )
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

async def cmd_quote(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _guard(update):
        return
    args = ctx.args
    if not args:
        await update.message.reply_text("Usage: /quote SYMBOL")
        return
    symbol = args[0].upper()
    q = await webull.get_quote(symbol)
    sign = "+" if q["change_pct"] >= 0 else ""
    emoji = "🟢" if q["change_pct"] >= 0 else "🔴"
    text = (
        f"{emoji} *{symbol}*  `${q['price']}`\n"
        f"Change: `{sign}{q['change_pct']:.2f}%`  ({sign}{_fmt(q['change'])})\n"
        f"Bid: `${q['bid']}`  Ask: `${q['ask']}`\n"
        f"Volume: `{q['volume']:,}`"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def _place(update: Update, side: str, args: list[str]):
    if not _guard(update):
        return
    if len(args) < 2:
        await update.message.reply_text(f"Usage: /{side.lower()} SYMBOL QTY [PRICE]")
        return
    symbol = args[0].upper()
    try:
        qty = float(args[1])
    except ValueError:
        await update.message.reply_text("Invalid quantity.")
        return
    price = None
    order_type = "MARKET"
    if len(args) >= 3:
        try:
            price = float(args[2])
            order_type = "LIMIT"
        except ValueError:
            await update.message.reply_text("Invalid price.")
            return

    await update.message.reply_text(f"⏳ Placing {side} order for {qty} {symbol}…")
    result = await webull.place_order(symbol, side, order_type, qty, price)
    mode_note = "📄 *[PAPER]*" if settings.trading_mode == "paper" else "⚡ *[LIVE]*"
    price_str = f"@ ${price}" if price else "@ MARKET"
    text = (
        f"✅ Order placed {mode_note}\n"
        f"`{result['order_id']}` — {side} {qty} {symbol} {price_str}\n"
        f"Status: `{result['status']}`"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def cmd_buy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _place(update, "BUY", ctx.args or [])

async def cmd_sell(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _place(update, "SELL", ctx.args or [])

async def cmd_engine(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _guard(update):
        return
    args = ctx.args or []
    sub = args[0].lower() if args else "status"

    if sub == "start":
        from sqlalchemy import select
        from backend.db.database import AsyncSessionLocal, Strategy
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Strategy).where(Strategy.enabled == True))
            strategies = [_strategy_to_dict(s) for s in result.scalars().all()]
        agent_engine.start_engine(strategies)
        await update.message.reply_text(f"▶️ Engine started with {len(strategies)} strategy(s).")

    elif sub == "stop":
        agent_engine.stop_engine()
        await update.message.reply_text("⏹ Engine stopped.")

    else:
        state = "🟢 RUNNING" if agent_engine._running else "⚫ STOPPED"
        mode = settings.trading_mode.upper()
        await update.message.reply_text(
            f"Engine: {state}\nMode: `{mode}`",
            parse_mode=ParseMode.MARKDOWN,
        )

async def cmd_memory(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _guard(update):
        return
    from backend.db.database import AsyncSessionLocal, AgentMemory, Strategy
    from sqlalchemy import select
    async with AsyncSessionLocal() as db:
        strats = (await db.execute(select(Strategy).where(Strategy.strategy_type == "claude"))).scalars().all()
    if not strats:
        await update.message.reply_text("No AI strategies found.")
        return
    lines = []
    for s in strats:
        async with AsyncSessionLocal() as db:
            mem = (await db.execute(select(AgentMemory).where(AgentMemory.strategy_id == s.id))).scalar_one_or_none()
        entries = list(mem.entries or []) if mem else []
        lines.append(f"*{s.name}* — {len(entries)} memory entries")
        for e in entries[-5:]:
            ts = (e.get("ts",""))[:16].replace("T"," ")
            sym = e.get("symbol","")
            note = e.get("note","")
            lines.append(f"  `{ts}` {sym} — {note[:60]}")
    await update.message.reply_text("\n".join(lines) or "No memory.", parse_mode=ParseMode.MARKDOWN)


async def cmd_logs(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _guard(update):
        return
    from backend.main import log_buffer
    entries = log_buffer[-10:]
    if not entries:
        await update.message.reply_text("No logs yet.")
        return
    lines = ["📋 *Recent Agent Logs*\n"]
    for e in reversed(entries):
        lvl = e.get("level", "INFO")
        msg = e.get("message", "")
        emoji = {"ERROR": "🔴", "SIGNAL": "🟡", "ORDER": "🟢", "PAPER": "🔵"}.get(lvl, "⚪")
        lines.append(f"{emoji} `[{lvl}]` {msg}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# ── Free-form chat ───────────────────────────────────────────────────────────

_CHAT_SYSTEM = """You are AIBull, an AI trading assistant accessible via Telegram.
You have access to the user's Webull brokerage account.
Be concise — Telegram messages should be short and actionable.
When asked about account, positions, quotes, or orders, say you can retrieve that via commands or describe the situation.
For trade suggestions, be conservative and always mention risk.
Never guarantee profits. Format numbers clearly (e.g. $1,234.56).
"""

async def cmd_chat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle any plain text message as a chat with the LLM."""
    if not _guard(update):
        return
    user_msg = update.message.text or ""
    if not user_msg:
        return

    await update.message.chat.send_action("typing")

    # Build context snapshot
    try:
        acct = await webull.get_account()
        positions = await webull.get_positions()
        pos_summary = ", ".join(
            f"{p['symbol']} x{int(p['quantity'])} (P&L ${p['unrealized_pnl']:+.2f})"
            for p in positions
        ) or "none"
        account_context = (
            f"Account net liquidation: ${acct['net_liquidation']:,.2f}, "
            f"cash: ${acct['cash_balance']:,.2f}, "
            f"buying power: ${acct['buying_power']:,.2f}. "
            f"Open positions: {pos_summary}."
        )
    except Exception:
        account_context = "Account data unavailable."

    from backend.agent.llm import chat as llm_chat
    prompt = f"[Account context: {account_context}]\n\nUser: {user_msg}"
    try:
        response = await llm_chat(prompt, system=_CHAT_SYSTEM)
        # Truncate to Telegram's 4096 char limit
        if len(response) > 4000:
            response = response[:3997] + "…"
        await update.message.reply_text(response)
    except Exception as e:
        await update.message.reply_text(f"Sorry, LLM unavailable: {e}")


# ── Alert broadcaster ─────────────────────────────────────────────────────────

async def send_alert(text: str):
    """Push a message to the authorized chat (called from engine log callback)."""
    if _app is None or _allowed_chat_id is None:
        return
    try:
        await _app.bot.send_message(
            chat_id=_allowed_chat_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        log.warning(f"Telegram alert failed: {e}")


def _make_alert_callback():
    """Returns a sync log callback that schedules an async alert."""
    ALERT_LEVELS = {"SIGNAL", "ORDER", "PAPER", "ERROR"}

    def callback(entry: dict):
        lvl = entry.get("level", "")
        if lvl not in ALERT_LEVELS:
            return
        emoji = {"ERROR": "🔴", "SIGNAL": "🟡", "ORDER": "🟢", "PAPER": "🔵"}.get(lvl, "⚪")
        msg = f"{emoji} `[{lvl}]` {entry.get('message', '')}"
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(send_alert(msg))
        except Exception:
            pass

    return callback


# ── Lifecycle ─────────────────────────────────────────────────────────────────

def _strategy_to_dict(s):
    return {
        "id": s.id, "name": s.name, "description": s.description,
        "strategy_type": s.strategy_type, "config": s.config,
        "symbols": s.symbols, "enabled": s.enabled,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


async def start_bot(token: str, chat_id: Optional[int] = None):
    global _app, _allowed_chat_id
    _allowed_chat_id = chat_id

    _app = (
        Application.builder()
        .token(token)
        .build()
    )

    _app.add_handler(CommandHandler("start",     cmd_start))
    _app.add_handler(CommandHandler("help",      cmd_help))
    _app.add_handler(CommandHandler("account",   cmd_account))
    _app.add_handler(CommandHandler("positions", cmd_positions))
    _app.add_handler(CommandHandler("quote",     cmd_quote))
    _app.add_handler(CommandHandler("buy",       cmd_buy))
    _app.add_handler(CommandHandler("sell",      cmd_sell))
    _app.add_handler(CommandHandler("engine",    cmd_engine))
    _app.add_handler(CommandHandler("logs",      cmd_logs))
    _app.add_handler(CommandHandler("memory",    cmd_memory))
    # Free-form chat — must be last so commands take priority
    _app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, cmd_chat))

    # Register alert hook with the strategy engine
    agent_engine.register_log_callback(_make_alert_callback())

    await _app.initialize()
    await _app.start()
    await _app.updater.start_polling(drop_pending_updates=True)
    log.info("Telegram bot started")


async def stop_bot():
    if _app:
        await _app.updater.stop()
        await _app.stop()
        await _app.shutdown()
        log.info("Telegram bot stopped")
