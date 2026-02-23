"""Unified LLM client supporting OpenAI and Google Gemini with automatic fallback."""

import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import openai
import google.generativeai as genai

logger = logging.getLogger(__name__)


@dataclass
class UsageStats:
    """Tracks token usage and estimated cost."""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_requests: int = 0
    total_cost_usd: float = 0.0
    monthly_cost_usd: float = 0.0
    month_start: float = field(default_factory=time.time)

    def add_usage(self, input_tokens: int, output_tokens: int,
                  cost_per_1k_input: float = 0.00015,
                  cost_per_1k_output: float = 0.0006) -> float:
        """Record token usage and return cost for this call."""
        cost = (input_tokens / 1000) * cost_per_1k_input + \
               (output_tokens / 1000) * cost_per_1k_output
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_requests += 1
        self.total_cost_usd += cost
        self.monthly_cost_usd += cost
        return cost

    def reset_monthly(self) -> None:
        """Reset monthly counters."""
        self.monthly_cost_usd = 0.0
        self.month_start = time.time()


class ResponseCache:
    """Simple in-memory LRU cache for LLM responses."""

    def __init__(self, max_size: int = 10000, ttl_hours: int = 24):
        self._cache: dict[str, tuple[float, Any]] = {}
        self._max_size = max_size
        self._ttl_seconds = ttl_hours * 3600

    @staticmethod
    def _make_key(prompt: str, model: str, **kwargs) -> str:
        raw = f"{model}:{prompt}:{json.dumps(kwargs, sort_keys=True)}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, prompt: str, model: str, **kwargs) -> Optional[Any]:
        key = self._make_key(prompt, model, **kwargs)
        if key in self._cache:
            ts, value = self._cache[key]
            if time.time() - ts < self._ttl_seconds:
                return value
            del self._cache[key]
        return None

    def set(self, prompt: str, model: str, value: Any, **kwargs) -> None:
        if len(self._cache) >= self._max_size:
            oldest_key = min(self._cache, key=lambda k: self._cache[k][0])
            del self._cache[oldest_key]
        key = self._make_key(prompt, model, **kwargs)
        self._cache[key] = (time.time(), value)


class RateLimiter:
    """Simple async rate limiter using token bucket approach."""

    def __init__(self, requests_per_minute: int = 60):
        self._rpm = requests_per_minute
        self._timestamps: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            self._timestamps = [t for t in self._timestamps if now - t < 60.0]
            if len(self._timestamps) >= self._rpm:
                wait = 60.0 - (now - self._timestamps[0])
                if wait > 0:
                    logger.debug("Rate limiter sleeping %.2fs", wait)
                    await asyncio.sleep(wait)
            self._timestamps.append(time.monotonic())


class LLMClient:
    """Unified async LLM client with OpenAI primary and Gemini fallback.

    Usage::

        client = LLMClient()
        text = await client.generate_text("Explain SEO basics")
        data = await client.generate_json("Return top 5 keywords as JSON list")
        embeddings = await client.generate_embeddings(["hello", "world"])
    """

    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        openai_model: str = "gpt-4o-mini",
        gemini_model: str = "gemini-2.0-flash",
        embedding_model: str = "text-embedding-3-small",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        timeout: int = 60,
        openai_rpm: int = 60,
        gemini_rpm: int = 15,
        cache_enabled: bool = True,
        cache_ttl_hours: int = 24,
        cache_max_size: int = 10000,
        max_monthly_budget: float = 100.0,
        budget_warning_pct: float = 80.0,
    ):
        # API keys
        self._openai_key = openai_api_key or os.getenv("OPENAI_API_KEY", "")
        self._gemini_key = gemini_api_key or os.getenv("GEMINI_API_KEY", "")

        # Model configuration
        self._openai_model = openai_model
        self._gemini_model = gemini_model
        self._embedding_model = embedding_model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._timeout = timeout

        # Clients
        self._openai_client: Optional[openai.AsyncOpenAI] = None
        if self._openai_key:
            self._openai_client = openai.AsyncOpenAI(
                api_key=self._openai_key, timeout=timeout
            )

        if self._gemini_key:
            genai.configure(api_key=self._gemini_key)

        # Rate limiters
        self._openai_limiter = RateLimiter(openai_rpm)
        self._gemini_limiter = RateLimiter(gemini_rpm)

        # Cache
        self._cache_enabled = cache_enabled
        self._cache = ResponseCache(max_size=cache_max_size, ttl_hours=cache_ttl_hours)

        # Usage tracking
        self.usage = UsageStats()
        self._max_monthly_budget = max_monthly_budget
        self._budget_warning_pct = budget_warning_pct

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str = "You are a helpful SEO assistant.",
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        use_cache: bool = True,
    ) -> str:
        """Generate text from the LLM.  Falls back to Gemini on OpenAI failure."""
        max_tokens = max_tokens or self._max_tokens
        temperature = temperature if temperature is not None else self._temperature

        if use_cache and self._cache_enabled:
            cached = self._cache.get(prompt, self._openai_model,
                                     system=system_prompt, temp=temperature)
            if cached is not None:
                logger.debug("Cache hit for prompt (len=%d)", len(prompt))
                return cached

        # Try OpenAI first
        if self._openai_client:
            try:
                result = await self._call_openai(
                    prompt, system_prompt, max_tokens, temperature
                )
                if use_cache and self._cache_enabled:
                    self._cache.set(prompt, self._openai_model, result,
                                    system=system_prompt, temp=temperature)
                return result
            except Exception as exc:
                logger.warning("OpenAI call failed: %s — falling back to Gemini", exc)

        # Fallback to Gemini
        if self._gemini_key:
            try:
                result = await self._call_gemini(
                    prompt, system_prompt, max_tokens, temperature
                )
                if use_cache and self._cache_enabled:
                    self._cache.set(prompt, self._gemini_model, result,
                                    system=system_prompt, temp=temperature)
                return result
            except Exception as exc:
                logger.error("Gemini call also failed: %s", exc)
                raise

        raise RuntimeError("No LLM provider configured. Set OPENAI_API_KEY or GEMINI_API_KEY.")

    async def generate_json(
        self,
        prompt: str,
        system_prompt: str = "You are a helpful assistant. Respond ONLY with valid JSON.",
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> Any:
        """Generate a JSON response and parse it."""
        raw = await self.generate_text(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature or 0.3,
            use_cache=True,
        )
        # Strip markdown code fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = lines[1:]  # remove opening ```json
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse JSON from LLM response: %s", exc)
            logger.debug("Raw response: %s", raw[:500])
            raise ValueError(f"LLM returned invalid JSON: {exc}") from exc

    async def generate_embeddings(
        self,
        texts: list[str],
        model: Optional[str] = None,
    ) -> list[list[float]]:
        """Generate embeddings via OpenAI embeddings API."""
        if not self._openai_client:
            raise RuntimeError("OpenAI client required for embeddings.")

        model = model or self._embedding_model
        await self._openai_limiter.acquire()

        try:
            response = await self._openai_client.embeddings.create(
                model=model, input=texts
            )
            self.usage.add_usage(
                input_tokens=response.usage.total_tokens,
                output_tokens=0,
                cost_per_1k_input=0.00002,
                cost_per_1k_output=0.0,
            )
            return [item.embedding for item in response.data]
        except Exception as exc:
            logger.error("Embedding generation failed: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _call_openai(
        self, prompt: str, system_prompt: str,
        max_tokens: int, temperature: float
    ) -> str:
        """Call OpenAI Chat Completions API."""
        self._check_budget()
        await self._openai_limiter.acquire()

        response = await self._openai_client.chat.completions.create(
            model=self._openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        choice = response.choices[0].message.content or ""
        usage = response.usage
        if usage:
            cost = self.usage.add_usage(usage.prompt_tokens, usage.completion_tokens)
            logger.info(
                "OpenAI call: %d in / %d out tokens, $%.6f",
                usage.prompt_tokens, usage.completion_tokens, cost,
            )
        return choice.strip()

    async def _call_gemini(
        self, prompt: str, system_prompt: str,
        max_tokens: int, temperature: float
    ) -> str:
        """Call Google Gemini API."""
        await self._gemini_limiter.acquire()

        model = genai.GenerativeModel(
            model_name=self._gemini_model,
            system_instruction=system_prompt,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=max_tokens,
                temperature=temperature,
            ),
        )
        # Run synchronous Gemini call in a thread to keep async interface
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, model.generate_content, prompt
        )
        text = response.text or ""
        logger.info("Gemini call completed (len=%d)", len(text))
        return text.strip()

    def _check_budget(self) -> None:
        """Raise if monthly budget is exceeded; warn if approaching."""
        if self.usage.monthly_cost_usd >= self._max_monthly_budget:
            raise RuntimeError(
                f"Monthly LLM budget exceeded: ${self.usage.monthly_cost_usd:.2f} "
                f">= ${self._max_monthly_budget:.2f}"
            )
        warning_threshold = self._max_monthly_budget * (self._budget_warning_pct / 100)
        if self.usage.monthly_cost_usd >= warning_threshold:
            logger.warning(
                "LLM budget warning: $%.2f / $%.2f (%.0f%%)",
                self.usage.monthly_cost_usd,
                self._max_monthly_budget,
                (self.usage.monthly_cost_usd / self._max_monthly_budget) * 100,
            )

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def get_usage_summary(self) -> dict[str, Any]:
        """Return a summary of token usage and costs."""
        return {
            "total_requests": self.usage.total_requests,
            "total_input_tokens": self.usage.total_input_tokens,
            "total_output_tokens": self.usage.total_output_tokens,
            "total_cost_usd": round(self.usage.total_cost_usd, 6),
            "monthly_cost_usd": round(self.usage.monthly_cost_usd, 6),
            "max_monthly_budget": self._max_monthly_budget,
            "budget_remaining": round(
                self._max_monthly_budget - self.usage.monthly_cost_usd, 6
            ),
        }
