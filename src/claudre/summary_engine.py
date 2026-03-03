"""AI summarization engine using Claude Haiku."""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from claudre.config import ClaudreConfig
from claudre.logger import get_logger
from claudre.models import ClaudeState, WindowState

if TYPE_CHECKING:
    from claudre.state_detector import JournalStateDetector

log = get_logger(__name__)

SYSTEM_PROMPT = """
You are a concise status reporter for a terminal multiplexer. Given terminal output
and optional conversation history, write 1-2 sentences describing what is currently
happening in this terminal window. Focus on the active task, not tool names.
Be specific about what is being built, fixed, or investigated. If Claude is waiting
for user input, say so and describe what decision or feedback is needed.
""".strip()


@dataclass
class SummaryRequest:
    pane_id: str
    terminal_capture: str
    jsonl_context: list[dict] | None = None  # last 3-5 JSONL messages


class SummaryEngine:
    def __init__(
        self,
        config: ClaudreConfig,
        tmux: object,
        detector: "JournalStateDetector | None" = None,
    ) -> None:
        self._config = config
        self._tmux = tmux
        self._detector = detector
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._semaphore = asyncio.Semaphore(config.summary_concurrency)
        self._enabled = config.ai_summaries
        self._client: object | None = None

        if self._enabled:
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if not api_key:
                log.warning(
                    "ANTHROPIC_API_KEY not set — AI summaries disabled"
                )
                self._enabled = False
            else:
                try:
                    import anthropic
                    self._client = anthropic.AsyncAnthropic(api_key=api_key)
                except ImportError:
                    log.warning("anthropic package not installed — AI summaries disabled")
                    self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def update_config(self, config: ClaudreConfig) -> None:
        """Hot-reload config values without restarting the engine."""
        self._config = config
        # Update semaphore capacity if concurrency changed
        self._semaphore = asyncio.Semaphore(config.summary_concurrency)

    async def should_update(self, ws: WindowState) -> bool:
        """True if summary should be refreshed for this window."""
        if not self._enabled:
            return False
        if ws.summary_stale:
            return True
        if ws.summary_updated_at is None:
            return True
        age = time.time() - ws.summary_updated_at.timestamp()
        if ws.state == ClaudeState.WORKING and age > self._config.summary_interval:
            return True
        return False

    async def request_update(self, ws: WindowState, registry: object) -> None:
        """Enqueue a summary refresh for this window."""
        if not self._enabled:
            return
        ws.summary_stale = True
        asyncio.ensure_future(self._update_task(ws, registry))

    async def _update_task(self, ws: WindowState, registry: object) -> None:
        async with self._semaphore:
            try:
                req = await self._collect_input(ws.pane_id, ws.path, ws.state)
                summary = await self._summarize(req)
                if summary:
                    ws.summary = summary
                    ws.summary_updated_at = datetime.now()
                    ws.summary_stale = False
                    from claudre.models import SummaryUpdated
                    registry._emit(SummaryUpdated(pane_id=ws.pane_id, summary=summary))
            except Exception as e:
                log.warning("Summary update failed for %s: %s", ws.pane_id, e)

    async def _summarize(self, req: SummaryRequest) -> str:
        """Call the Anthropic API to generate a summary. Returns '' on error."""
        if not self._enabled or self._client is None:
            return ""

        user_parts = [f"Terminal output:\n```\n{req.terminal_capture[-3000:]}\n```"]

        if req.jsonl_context:
            ctx_lines = []
            for msg in req.jsonl_context[-5:]:
                role = msg.get("role", "?")
                content = msg.get("content", "")
                if isinstance(content, list):
                    text = " ".join(
                        c.get("text", "") for c in content
                        if isinstance(c, dict) and c.get("type") == "text"
                    )
                else:
                    text = str(content)
                ctx_lines.append(f"{role}: {text[:500]}")
            if ctx_lines:
                user_parts.append("Recent conversation:\n" + "\n".join(ctx_lines))

        user_content = "\n\n".join(user_parts)

        try:
            import anthropic
            response = await self._client.messages.create(  # type: ignore[union-attr]
                model=self._config.summary_model,
                max_tokens=150,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )
            return response.content[0].text.strip()
        except Exception as e:
            log.warning("Anthropic API error: %s", e)
            return ""

    async def _collect_input(
        self, pane_id: str, path: str, state: ClaudeState
    ) -> SummaryRequest:
        """Gather terminal capture and JSONL context."""
        from claudre.tmux_adapter import TmuxAdapter
        tmux: TmuxAdapter = self._tmux  # type: ignore[assignment]
        capture = await tmux.capture_pane(pane_id, lines=100)

        jsonl_ctx: list[dict] | None = None
        if state in (ClaudeState.WORKING, ClaudeState.WAITING):
            jsonl_ctx = self._read_jsonl_context(path)

        return SummaryRequest(
            pane_id=pane_id,
            terminal_capture=capture,
            jsonl_context=jsonl_ctx,
        )

    def _read_jsonl_context(self, path: str) -> list[dict] | None:
        """Read the last 5 JSONL messages for a project path.

        Uses the detector's shared path cache when available.
        """
        # Use shared detector cache if we have one
        if self._detector is not None:
            latest = self._detector.get_jsonl_path(path)
        else:
            latest = self._scan_for_jsonl(path)

        if latest is None:
            return None

        messages: list[dict] = []
        try:
            file_size = latest.stat().st_size
            with open(latest, "rb") as f:
                f.seek(max(0, file_size - 50 * 1024))
                data_bytes = f.read()
            lines = data_bytes.decode("utf-8", errors="replace").splitlines()
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    if msg.get("role") in ("assistant", "user"):
                        messages.insert(0, msg)
                    if len(messages) >= 5:
                        break
                except json.JSONDecodeError:
                    continue
        except OSError:
            return None

        return messages if messages else None

    def _scan_for_jsonl(self, path: str) -> Path | None:
        """Fallback: scan ~/.claude/projects/ without a shared cache."""
        from claudre.state_detector import CLAUDE_DIR
        if not CLAUDE_DIR.exists():
            return None

        for d in CLAUDE_DIR.iterdir():
            if not d.is_dir():
                continue
            for jf in sorted(d.glob("*.jsonl")):
                try:
                    with open(jf) as f:
                        first_line = f.readline().strip()
                    if not first_line:
                        continue
                    data = json.loads(first_line)
                    if data.get("cwd") == path:
                        jsonl_files = list(d.glob("*.jsonl"))
                        if jsonl_files:
                            return max(jsonl_files, key=lambda f: f.stat().st_mtime)
                except (json.JSONDecodeError, OSError):
                    continue
        return None
