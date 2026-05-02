# AIBull

AI-powered trading dashboard with autonomous agent strategies for stocks, crypto, options, and small-cap momentum plays. Connects to Webull for live order execution.

![Python](https://img.shields.io/badge/Python-3.11+-blue) ![React](https://img.shields.io/badge/React-18-61dafb) ![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688) ![License](https://img.shields.io/badge/license-MIT-green)

---

## Features

- **AI Agent Strategies** — Claude (Anthropic API) or local Ollama models analyze market data and place trades autonomously
- **Momentum Agent** — Scans for $2–$20 small-cap stocks with 2x+ relative volume, batch LLM analysis, proportional position sizing (2–5 positions, 40%/30%/22.5%/18% BP allocation)
- **Options Agent** — Fetches live option chains via yfinance, LLM picks calls/puts, executes via Webull
- **SMA Crossover** — Classic moving average crossover strategy
- **Crypto Trading** — 24/7 crypto execution (BTC, ETH, SOL, and 15+ more)
- **Extended Hours** — Pre-market (4am) and after-hours (8pm ET) trading for eligible symbols
- **PDT Protection** — Automatically blocks same-day round-trips on margin accounts under $25k
- **Paper / Live modes** — Test with paper trading before going live
- **Telegram Bot** — Remote control and trade alerts from your phone
- **Live Dashboard** — Real-time quotes, P&L, open positions, agent log, and price charts

## Strategy Types

| Type | Universe | Hours |
|------|----------|-------|
| AI Agent (Stocks) | Auto-scan gainers/actives or pinned symbols | Regular + optional AH |
| AI Agent (Crypto) | 18-coin watchlist | 24/7 |
| Options Agent | Auto-scan or pinned underlyings | Regular hours only |
| Momentum Agent | $2–$20, 750k+ avg vol, 2x+ rel vol | Regular + AH |
| SMA Crossover | Pinned symbols | Regular |

Each strategy has Conservative / Moderate / Aggressive presets with tuned prompts, position sizes, and scan limits.

## Stack

- **Backend** — Python, FastAPI, SQLite (via SQLAlchemy + aiosqlite)
- **Frontend** — React 18, TypeScript, Vite, Tailwind CSS, Recharts
- **LLM** — Anthropic Claude API or local Ollama (configurable)
- **Broker** — Webull via `webull-openapi-python-sdk`
- **Market Data** — Yahoo Finance (quotes, bars, option chains, screeners)
- **Desktop** — pywebview (optional — wraps the app in a native window)

## Setup

**Requirements:** Python 3.11+, Node 18+

### 1. Clone and install

```bash
git clone https://github.com/Degens-World/AIBull.git
cd AIBull
```

**Windows (one-click):**
```
setup.bat
```

**Manual:**
```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

pip install -r requirements.txt

cd frontend
npm install
npm run build
cd ..
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Webull credentials
WEBULL_APP_KEY=your_app_key
WEBULL_APP_SECRET=your_app_secret
WEBULL_TRADING_PIN=your_6digit_pin
WEBULL_ACCOUNT_ID=your_account_id

# LLM — pick one backend
LLM_BACKEND=anthropic          # uses ANTHROPIC_API_KEY below
# LLM_BACKEND=ollama           # local Ollama, no API key needed
# LLM_BACKEND=claude_cli       # uses Claude Code CLI session

ANTHROPIC_API_KEY=sk-ant-...

# Trading mode
TRADING_MODE=paper             # paper | live

# Optional Telegram alerts
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

### 3. Run

**Desktop app (production build):**
```
run.bat
# or: python desktop.py
```

**Dev mode (hot reload):**
```
start_dev.bat
# Backend → http://localhost:8421
# Frontend → http://localhost:5173
```

## Project Structure

```
AIBull/
├── backend/
│   ├── agent/
│   │   ├── engine.py       # Strategy engine, tick loop, all agent types
│   │   ├── llm.py          # LLM abstraction (Claude / Ollama / claude_cli)
│   │   ├── memory.py       # Per-strategy persistent memory
│   │   └── presets.py      # Conservative/Moderate/Aggressive presets
│   ├── market/
│   │   └── movers.py       # Yahoo Finance screener, quotes, crypto data
│   ├── webull/
│   │   └── client.py       # Webull SDK wrapper (orders, quotes, bars, options)
│   ├── db/
│   │   └── database.py     # SQLite models and strategy persistence
│   ├── main.py             # FastAPI app, WebSocket live feed, API routes
│   ├── config.py           # Settings via pydantic-settings
│   └── telegram_bot.py     # Telegram remote control bot
├── frontend/
│   └── src/pages/
│       ├── Dashboard.tsx   # Live quotes, P&L cards, chart, positions, agent log
│       ├── Strategies.tsx  # Strategy manager, preset picker, decisions panel
│       ├── Trading.tsx     # Manual order entry
│       ├── Portfolio.tsx   # Order history, trade P&L
│       ├── Market.tsx      # Market movers, gainers, actives
│       ├── Crypto.tsx      # Crypto market overview
│       └── Performance.tsx # Equity curve, stats
├── .env.example
├── requirements.txt
├── setup.bat
├── run.bat
└── start_dev.bat
```

## Webull Setup

1. Apply for Webull API access at [developer.webull.com](https://developer.webull.com)
2. Create an app to get your `APP_KEY` and `APP_SECRET`
3. Log in through the app once to generate the auth token (stored in `conf/token.txt`)
4. Your `ACCOUNT_ID` is visible in the Webull desktop app under Account → Account Info

> **Note:** Webull's API supports paper trading. Set `TRADING_MODE=paper` until you've verified your strategy performs as expected.

## LLM Backends

| Backend | Config | Notes |
|---------|--------|-------|
| `anthropic` | `ANTHROPIC_API_KEY` set | Calls Claude API directly — costs per token |
| `ollama` | Ollama running locally | Free, private, slower — set `OLLAMA_MODEL` |
| `claude_cli` | Claude Code CLI installed | Uses your existing Claude Code session |

## Risk Warning

This software places real orders with real money. Always:
- Start in `TRADING_MODE=paper` and validate behavior
- Set conservative `max_position_usd` limits
- Monitor the Agent Log on the dashboard
- Understand the PDT rule if your account is under $25,000
- Never commit your `.env` file — it contains your trading credentials

## License

MIT
