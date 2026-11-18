"""What an investigation costs, from the token usage the API reports on each turn.

USD per million tokens, from https://platform.claude.com/docs/en/about-claude/pricing
(checked 2026-11-18). Cache writes are 5-minute writes, which is what the loop uses.
"""

from typing import Any

PRICES: dict[str, dict[str, float]] = {
    "claude-opus-5-5": {"input": 4.0, "cache_write": 5.0, "cache_read": 0.20, "output": 20.0},
    # Opus 5 cache prices are the page's 1.25x write / 0.1x read multipliers on its $5 input.
    "claude-opus-5": {"input": 5.0, "cache_write": 6.25, "cache_read": 0.50, "output": 25.0},
    "claude-sonnet-5-5": {"input": 2.0, "cache_write": 2.50, "cache_read": 0.10, "output": 10.0},
}


def turn_cost(model: str, usage: Any) -> float | None:
    """Cost of one API response in USD, or None for a model without a known price."""
    price = PRICES.get(model)
    if price is None:
        return None

    def tokens(name: str) -> int:
        return getattr(usage, name, None) or 0

    return (
        tokens("input_tokens") * price["input"]
        + tokens("cache_creation_input_tokens") * price["cache_write"]
        + tokens("cache_read_input_tokens") * price["cache_read"]
        + tokens("output_tokens") * price["output"]
    ) / 1_000_000


def format_cost(cost_usd: float | None) -> str:
    return "n/a" if cost_usd is None else f"${cost_usd:.2f}"
