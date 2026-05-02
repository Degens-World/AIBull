"""
LLM abstraction — swap between backends without changing strategy code.

Backends:
  anthropic  — Anthropic API (requires ANTHROPIC_API_KEY)
  ollama     — Local Ollama instance at localhost:11434 (free, no key needed)
  claude_cli — Claude Code CLI via subprocess (free if you have claude installed)
"""
import asyncio
import json
import logging
from typing import Literal

import httpx

from backend.config import settings

log = logging.getLogger(__name__)

Backend = Literal["anthropic", "ollama", "claude_cli"]


async def chat(prompt: str, system: str = "") -> str:
    """Send a prompt to the configured LLM backend, return the text response."""
    backend: Backend = settings.llm_backend  # type: ignore[assignment]

    if backend == "ollama":
        return await _ollama(prompt, system)
    elif backend == "claude_cli":
        return await _claude_cli(prompt, system)
    else:
        return await _anthropic(prompt, system)


# ── Anthropic API ─────────────────────────────────────────────────────────────

async def _anthropic(prompt: str, system: str) -> str:
    try:
        import anthropic as sdk
    except ImportError:
        raise RuntimeError("anthropic package not installed — run: pip install anthropic")

    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    client = sdk.Anthropic(api_key=settings.anthropic_api_key)
    kwargs: dict = dict(
        model="claude-sonnet-4-6",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    if system:
        kwargs["system"] = system

    resp = client.messages.create(**kwargs)
    return resp.content[0].text.strip()


# ── Ollama ────────────────────────────────────────────────────────────────────

async def _ollama(prompt: str, system: str) -> str:
    model = settings.ollama_model or "llama3.2"
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{settings.ollama_url}/api/chat",
            json={"model": model, "messages": messages, "stream": False},
        )
        resp.raise_for_status()
        data = resp.json()
        return data["message"]["content"].strip()


async def ollama_list_models() -> list[str]:
    """Return list of locally available Ollama models."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{settings.ollama_url}/api/tags")
            resp.raise_for_status()
            return [m["name"] for m in resp.json().get("models", [])]
    except Exception:
        return []


async def ollama_is_running() -> bool:
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{settings.ollama_url}/api/tags")
            return r.status_code == 200
    except Exception:
        return False


# ── Claude CLI ────────────────────────────────────────────────────────────────

async def _claude_cli(prompt: str, system: str) -> str:
    full_prompt = f"{system}\n\n{prompt}" if system else prompt

    proc = await asyncio.create_subprocess_exec(
        "claude", "--print", full_prompt,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError("Claude CLI timed out after 120s")

    if proc.returncode != 0:
        err = stderr.decode().strip()
        raise RuntimeError(f"Claude CLI error (exit {proc.returncode}): {err}")

    return stdout.decode().strip()


async def claude_cli_available() -> bool:
    """Check whether the claude CLI is on PATH."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "claude", "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=5)
        return proc.returncode == 0
    except Exception:
        return False
