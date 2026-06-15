"""Domain exceptions.

We fail loudly and explicitly: a silent guardrail is a broken guardrail.
"""


class TradingBotError(Exception):
    """Base class for all bot-specific errors."""


class ConfigError(TradingBotError):
    """Raised when configuration is missing or invalid."""


class RiskViolation(TradingBotError):
    """Raised when an action would breach a hard risk limit."""


class OrderRejected(TradingBotError):
    """Raised when an order fails pre-trade validation."""


class KillSwitchActive(TradingBotError):
    """Raised when an action is attempted while the kill switch is engaged."""


class LiveTradingLocked(TradingBotError):
    """Raised when live execution is attempted without the explicit unlock."""
