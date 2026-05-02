from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy import Column, String, Float, Integer, DateTime, Boolean, Text, JSON
from datetime import datetime

engine = create_async_engine("sqlite+aiosqlite:///./aibull.db", echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class Order(Base):
    __tablename__ = "orders"
    id = Column(String, primary_key=True)
    symbol = Column(String, nullable=False)
    side = Column(String)           # BUY / SELL
    order_type = Column(String)     # MARKET / LIMIT / STOP
    quantity = Column(Float)
    price = Column(Float, nullable=True)
    status = Column(String)
    filled_qty = Column(Float, default=0)
    filled_price = Column(Float, nullable=True)
    source = Column(String, default="manual")  # manual / strategy / agent
    strategy_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Strategy(Base):
    __tablename__ = "strategies"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    strategy_type = Column(String)  # rules / claude
    config = Column(JSON)
    enabled = Column(Boolean, default=False)
    symbols = Column(JSON)          # list of ticker symbols
    created_at = Column(DateTime, default=datetime.utcnow)

class TradeLog(Base):
    __tablename__ = "trade_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    level = Column(String, default="INFO")
    message = Column(Text)
    data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class AgentMemory(Base):
    __tablename__ = "agent_memory"
    strategy_id = Column(String, primary_key=True)
    entries = Column(JSON, default=list)   # list of {ts, symbol, action, note} dicts
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
