import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.config import settings
from backend.db.database import init_db, get_db, Order, Strategy, TradeLog, AsyncSessionLocal
from backend.webull.client import webull, STUB_MODE, _has_credentials
from backend.agent import engine as agent_engine
import backend.telegram_bot as tg_bot
from sqlalchemy import select, desc
import json, os

# ── WebSocket connection manager ──────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active.remove(ws)


manager = ConnectionManager()
log_buffer: list[dict] = []


def on_log_entry(entry: dict):
    log_buffer.append(entry)
    if len(log_buffer) > 500:
        log_buffer.pop(0)
    asyncio.get_event_loop().create_task(manager.broadcast({"type": "log", "data": entry}))


agent_engine.register_log_callback(on_log_entry)


# ── App lifecycle ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # Load enabled strategies from DB and start engine
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Strategy).where(Strategy.enabled == True))
        strategies = [_strategy_to_dict(s) for s in result.scalars().all()]
    if strategies:
        agent_engine.start_engine(strategies)
    # Authenticate with Webull in background (prompts mobile app approval if first time)
    if _has_credentials():
        asyncio.get_event_loop().create_task(webull.initialize())
    # Start Telegram bot if token is configured
    if settings.telegram_bot_token:
        await tg_bot.start_bot(settings.telegram_bot_token, settings.telegram_chat_id or None)
    yield
    agent_engine.stop_engine()
    if settings.telegram_bot_token:
        await tg_bot.stop_bot()


app = FastAPI(title="AIBull", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class PlaceOrderRequest(BaseModel):
    symbol: str
    side: str
    order_type: str
    quantity: float
    price: Optional[float] = None

class StrategyCreate(BaseModel):
    name: str
    description: str = ""
    strategy_type: str      # sma_crossover | claude
    config: dict = {}
    symbols: list[str] = []
    enabled: bool = False

class StrategyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None
    symbols: Optional[list[str]] = None
    enabled: Optional[bool] = None


# ── Account routes ────────────────────────────────────────────────────────────

@app.get("/api/account")
async def get_account():
    return await webull.get_account()

@app.get("/api/positions")
async def get_positions():
    return await webull.get_positions()

@app.get("/api/accounts")
async def list_accounts():
    if not _has_credentials():
        return []
    accts = await asyncio.to_thread(webull._get_account_list)
    return [{"id": a["account_id"], "label": a["account_label"], "class": a["account_class"]} for a in accts]

class SelectAccountRequest(BaseModel):
    account_id: str  # empty string = all accounts

@app.post("/api/accounts/select")
async def select_account(req: SelectAccountRequest):
    object.__setattr__(settings, "selected_account_id", req.account_id)
    _write_env({"SELECTED_ACCOUNT_ID": req.account_id})
    return {"selected": req.account_id}


# ── Market data routes ────────────────────────────────────────────────────────

@app.get("/api/quote/{symbol}")
async def get_quote(symbol: str):
    return await webull.get_quote(symbol.upper())

@app.get("/api/bars/{symbol}")
async def get_bars(symbol: str, timeframe: str = "1d", count: int = 100):
    return await webull.get_bars(symbol.upper(), timeframe, count)


# ── Order routes ──────────────────────────────────────────────────────────────

@app.post("/api/orders")
async def place_order(req: PlaceOrderRequest):
    result = await webull.place_order(req.symbol.upper(), req.side, req.order_type, req.quantity, req.price)
    # Persist to DB
    async with AsyncSessionLocal() as db:
        order = Order(
            id=result.get("order_id", str(uuid.uuid4())),
            symbol=result["symbol"],
            side=result["side"],
            order_type=result["order_type"],
            quantity=result["quantity"],
            price=result.get("price"),
            status=result.get("status", "PENDING"),
            source="manual",
        )
        db.add(order)
        await db.commit()
    await manager.broadcast({"type": "order", "data": result})
    return result

@app.delete("/api/orders/{order_id}")
async def cancel_order(order_id: str):
    return await webull.cancel_order(order_id)

@app.get("/api/orders")
async def list_orders():
    try:
        return await webull.get_orders()
    except Exception:
        # Fall back to local DB if Webull is unavailable
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Order).order_by(desc(Order.created_at)).limit(100))
            orders = result.scalars().all()
        return [_order_to_dict(o) for o in orders]


# ── Strategy routes ───────────────────────────────────────────────────────────

@app.get("/api/strategies/presets")
async def list_strategy_presets():
    from backend.agent.presets import PRESETS
    return [{"key": k, **v} for k, v in PRESETS.items()]


@app.get("/api/strategies")
async def list_strategies():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Strategy))
        strats = result.scalars().all()
    return [_strategy_to_dict(s) for s in strats]

@app.post("/api/strategies")
async def create_strategy(req: StrategyCreate):
    async with AsyncSessionLocal() as db:
        strat = Strategy(
            id=str(uuid.uuid4()),
            name=req.name,
            description=req.description,
            strategy_type=req.strategy_type,
            config=req.config,
            symbols=req.symbols,
            enabled=req.enabled,
        )
        db.add(strat)
        await db.commit()
        await db.refresh(strat)
    _sync_engine()
    return _strategy_to_dict(strat)

@app.patch("/api/strategies/{strategy_id}")
async def update_strategy(strategy_id: str, req: StrategyUpdate):
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Strategy).where(Strategy.id == strategy_id))
        strat = result.scalar_one_or_none()
        if not strat:
            raise HTTPException(404, "Strategy not found")
        if req.name is not None:
            strat.name = req.name
        if req.description is not None:
            strat.description = req.description
        if req.config is not None:
            from sqlalchemy.orm.attributes import flag_modified
            strat.config = dict(req.config)
            flag_modified(strat, "config")
        if req.symbols is not None:
            from sqlalchemy.orm.attributes import flag_modified
            strat.symbols = list(req.symbols)
            flag_modified(strat, "symbols")
        if req.enabled is not None:
            strat.enabled = req.enabled
        await db.commit()
        await db.refresh(strat)
    _sync_engine()
    return _strategy_to_dict(strat)

@app.delete("/api/strategies/{strategy_id}")
async def delete_strategy(strategy_id: str):
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Strategy).where(Strategy.id == strategy_id))
        strat = result.scalar_one_or_none()
        if strat:
            await db.delete(strat)
            await db.commit()
    _sync_engine()
    return {"status": "deleted"}


# ── Agent / engine routes ─────────────────────────────────────────────────────

@app.post("/api/engine/start")
async def start_engine():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Strategy).where(Strategy.enabled == True))
        strategies = [_strategy_to_dict(s) for s in result.scalars().all()]
    agent_engine.start_engine(strategies)
    return {"status": "started", "strategies": len(strategies)}

@app.post("/api/engine/stop")
async def stop_engine():
    agent_engine.stop_engine()
    return {"status": "stopped"}

@app.get("/api/engine/status")
async def engine_status():
    return {
        "running": agent_engine._running,
        "mode": settings.trading_mode,
        "stub_mode": STUB_MODE,
    }

@app.get("/api/engine/decisions")
async def engine_decisions(strategy_id: str = None):
    return agent_engine.get_decisions(strategy_id)

@app.get("/api/engine/memory/{strategy_id}")
async def engine_memory(strategy_id: str):
    from backend.agent.memory import load
    return await load(strategy_id)

@app.delete("/api/engine/memory/{strategy_id}")
async def clear_memory(strategy_id: str):
    from backend.agent.memory import clear
    await clear(strategy_id)
    return {"status": "cleared"}

@app.get("/api/logs")
async def get_logs():
    return log_buffer[-200:]

# ── Market movers routes ──────────────────────────────────────────────────────

from backend.market.movers import get_all_movers, get_screen, get_snapshots, get_crypto_markets

@app.get("/api/market/movers")
async def market_movers():
    return await get_all_movers()

@app.get("/api/crypto/markets")
async def crypto_markets():
    return await get_crypto_markets()

@app.get("/api/market/{screen}")
async def market_screen(screen: str, count: int = 25):
    return await get_screen(screen, count)


# ── Settings routes ───────────────────────────────────────────────────────────

ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")

def _read_env() -> dict[str, str]:
    """Parse .env file into a dict."""
    env: dict[str, str] = {}
    if not os.path.exists(ENV_PATH):
        return env
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env

def _write_env(updates: dict[str, str]):
    """Write/update keys in .env, preserving comments and other lines."""
    lines: list[str] = []
    seen: set[str] = set()

    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    k = stripped.split("=", 1)[0].strip()
                    if k in updates:
                        lines.append(f"{k}={updates[k]}\n")
                        seen.add(k)
                        continue
                lines.append(line if line.endswith("\n") else line + "\n")

    # Append any keys not already present
    for k, v in updates.items():
        if k not in seen:
            lines.append(f"{k}={v}\n")

    with open(ENV_PATH, "w") as f:
        f.writelines(lines)


class CredentialsUpdate(BaseModel):
    webull_app_key: str = ""
    webull_app_secret: str = ""
    webull_trading_pin: str = ""
    webull_account_id: str = ""
    anthropic_api_key: str = ""
    trading_mode: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    llm_backend: str = ""
    ollama_url: str = ""
    ollama_model: str = ""


@app.get("/api/settings")
async def get_settings():
    from backend.agent.llm import ollama_is_running, claude_cli_available
    ollama_up = await ollama_is_running()
    cli_ok = await claude_cli_available()
    return {
        "trading_mode": settings.trading_mode,
        "stub_mode": not bool(settings.webull_app_key and settings.webull_app_secret),
        "has_webull_key": bool(settings.webull_app_key),
        "has_webull_secret": bool(settings.webull_app_secret),
        "has_anthropic_key": bool(settings.anthropic_api_key),
        "has_telegram_token": bool(settings.telegram_bot_token),
        "telegram_bot_active": tg_bot._app is not None,
        "telegram_chat_id": settings.telegram_chat_id,
        "llm_backend": settings.llm_backend,
        "ollama_url": settings.ollama_url,
        "ollama_model": settings.ollama_model,
        "ollama_running": ollama_up,
        "claude_cli_available": cli_ok,
        "webull_auth_status": webull.auth_status,
        "webull_auth_message": webull.auth_message,
        "selected_account_id": settings.selected_account_id,
    }

@app.get("/api/ollama/models")
async def list_ollama_models():
    from backend.agent.llm import ollama_list_models
    return await ollama_list_models()

@app.post("/api/credentials")
async def save_credentials(req: CredentialsUpdate):
    """Write credentials to .env and hot-reload settings in memory."""
    updates: dict[str, str] = {}
    field_map = {
        "webull_app_key":    ("webull_app_key",    "WEBULL_APP_KEY"),
        "webull_app_secret": ("webull_app_secret",  "WEBULL_APP_SECRET"),
        "webull_trading_pin":("webull_trading_pin", "WEBULL_TRADING_PIN"),
        "webull_account_id": ("webull_account_id",  "WEBULL_ACCOUNT_ID"),
        "anthropic_api_key": ("anthropic_api_key",  "ANTHROPIC_API_KEY"),
        "trading_mode":      ("trading_mode",        "TRADING_MODE"),
        "telegram_bot_token":("telegram_bot_token", "TELEGRAM_BOT_TOKEN"),
        "telegram_chat_id":  ("telegram_chat_id",   "TELEGRAM_CHAT_ID"),
        "llm_backend":       ("llm_backend",         "LLM_BACKEND"),
        "ollama_url":        ("ollama_url",          "OLLAMA_URL"),
        "ollama_model":      ("ollama_model",        "OLLAMA_MODEL"),
    }

    had_telegram = bool(settings.telegram_bot_token)

    for req_field, (settings_field, env_key) in field_map.items():
        value = getattr(req, req_field, "").strip()
        if value:  # only overwrite non-empty submissions
            updates[env_key] = value
            # Hot-reload into settings object
            if settings_field == "telegram_chat_id":
                try:
                    object.__setattr__(settings, settings_field, int(value))
                except ValueError:
                    pass
            else:
                object.__setattr__(settings, settings_field, value)

    if updates:
        _write_env(updates)

    # Force SDK client reconnect with new credentials
    webull._refresh()
    if _has_credentials():
        asyncio.get_event_loop().create_task(webull.initialize())

    # Start Telegram bot if token was just added
    has_telegram_now = bool(settings.telegram_bot_token)
    if has_telegram_now and not had_telegram and tg_bot._app is None:
        await tg_bot.start_bot(settings.telegram_bot_token, settings.telegram_chat_id or None)
    elif has_telegram_now and had_telegram and tg_bot._app is not None:
        # Token changed — restart bot
        await tg_bot.stop_bot()
        await tg_bot.start_bot(settings.telegram_bot_token, settings.telegram_chat_id or None)

    return {"status": "saved", "updated_keys": list(updates.keys())}


# ── Event / Prediction Market routes ─────────────────────────────────────────

@app.get("/api/events/series")
async def event_series():
    return await webull.get_event_series()

@app.get("/api/events/contracts/{series_symbol}")
async def event_contracts(series_symbol: str):
    return await webull.get_event_contracts(series_symbol)

@app.get("/api/events/snapshot")
async def event_snapshot(symbols: str):
    return await webull.get_event_snapshot(symbols.split(","))

class EventOrderRequest(BaseModel):
    symbol: str
    outcome: str       # "yes" or "no"
    quantity: int
    limit_price: float

@app.post("/api/events/order")
async def place_event_order(req: EventOrderRequest):
    return await webull.place_event_order(
        req.symbol, req.outcome, req.quantity, req.limit_price
    )


# ── Telegram routes ───────────────────────────────────────────────────────────

class TelegramAlertRequest(BaseModel):
    message: str

@app.post("/api/telegram/alert")
async def send_telegram_alert(req: TelegramAlertRequest):
    if not settings.telegram_bot_token:
        raise HTTPException(400, "Telegram bot not configured")
    await tg_bot.send_alert(req.message)
    return {"status": "sent"}

@app.get("/api/telegram/status")
async def telegram_status():
    return {
        "active": tg_bot._app is not None,
        "chat_id": tg_bot._allowed_chat_id,
        "has_token": bool(settings.telegram_bot_token),
    }


# ── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        # Push initial quote stream for known symbols
        while True:
            try:
                positions = await webull.get_positions()
                for pos in positions:
                    q = await webull.get_quote(pos["symbol"])
                    await ws.send_json({"type": "quote", "data": q})
                await asyncio.sleep(5)
            except Exception:
                await asyncio.sleep(5)
    except WebSocketDisconnect:
        manager.disconnect(ws)


# ── Static files (frontend build) ─────────────────────────────────────────────

FRONTEND_BUILD = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.exists(FRONTEND_BUILD):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_BUILD, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        return FileResponse(os.path.join(FRONTEND_BUILD, "index.html"))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _order_to_dict(o: Order) -> dict:
    return {
        "id": o.id, "symbol": o.symbol, "side": o.side, "order_type": o.order_type,
        "quantity": o.quantity, "price": o.price, "status": o.status,
        "filled_qty": o.filled_qty, "filled_price": o.filled_price,
        "source": o.source, "created_at": o.created_at.isoformat() if o.created_at else None,
    }

def _strategy_to_dict(s: Strategy) -> dict:
    return {
        "id": s.id, "name": s.name, "description": s.description,
        "strategy_type": s.strategy_type, "config": s.config,
        "symbols": s.symbols, "enabled": s.enabled,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }

def _sync_engine():
    async def _do():
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Strategy).where(Strategy.enabled == True))
            strategies = [_strategy_to_dict(s) for s in result.scalars().all()]
        agent_engine.update_strategies(strategies)
    asyncio.get_event_loop().create_task(_do())
