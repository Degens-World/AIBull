"""
Persistent memory for the AI agent.
Each strategy has a rolling log of observations and decisions stored in SQLite.
The agent reads its memory before each analysis and writes notes back after.
"""
from datetime import datetime
from sqlalchemy import select
from backend.db.database import AsyncSessionLocal, AgentMemory

MAX_ENTRIES = 60   # keep last 60 entries per strategy (~1 week of hourly ticks)


async def load(strategy_id: str) -> list[dict]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AgentMemory).where(AgentMemory.strategy_id == strategy_id)
        )
        mem = result.scalar_one_or_none()
        return list(mem.entries or []) if mem else []


async def append(strategy_id: str, entry: dict):
    entry.setdefault("ts", datetime.utcnow().isoformat())
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AgentMemory).where(AgentMemory.strategy_id == strategy_id)
        )
        mem = result.scalar_one_or_none()
        if mem is None:
            mem = AgentMemory(strategy_id=strategy_id, entries=[entry])
            db.add(mem)
        else:
            entries = list(mem.entries or [])
            entries.append(entry)
            mem.entries = entries[-MAX_ENTRIES:]
        await db.commit()


async def clear(strategy_id: str):
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AgentMemory).where(AgentMemory.strategy_id == strategy_id)
        )
        mem = result.scalar_one_or_none()
        if mem:
            mem.entries = []
            await db.commit()


def format_for_prompt(entries: list[dict]) -> str:
    """Render memory entries as a concise text block for injection into the LLM prompt."""
    if not entries:
        return "No prior memory."
    lines = []
    for e in entries[-20:]:   # last 20 entries in prompt
        ts = e.get("ts", "")[:16].replace("T", " ")
        sym = e.get("symbol", "")
        action = e.get("action", "")
        note = e.get("note", "")
        price = e.get("price", "")
        parts = [ts]
        if sym:
            parts.append(sym)
        if action:
            parts.append(action)
            if price:
                parts.append(f"@ ${price}")
        if note:
            parts.append(f"— {note}")
        lines.append(" ".join(parts))
    return "\n".join(lines)
