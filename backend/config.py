from pydantic_settings import BaseSettings
from typing import Literal

class Settings(BaseSettings):
    webull_app_key: str = ""
    webull_app_secret: str = ""
    webull_trading_pin: str = ""
    webull_account_id: str = ""
    anthropic_api_key: str = ""
    trading_mode: Literal["paper", "live"] = "paper"
    port: int = 8421
    telegram_bot_token: str = ""
    telegram_chat_id: int = 0
    # LLM backend: anthropic | ollama | claude_cli
    llm_backend: str = "claude_cli"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    # Selected Webull account (empty = aggregate all)
    selected_account_id: str = ""

    class Config:
        env_file = ".env"

settings = Settings()
