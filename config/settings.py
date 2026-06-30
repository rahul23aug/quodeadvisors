"""Runtime settings for source collectors."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from collector.exceptions import ConfigurationError


@dataclass(frozen=True, slots=True)
class ThrottlingSettings:
    """Thresholds used to detect degraded collection conditions."""

    max_consecutive_empty_scrolls: int = 3
    max_duplicate_ratio: float = 0.85
    min_tweets_per_minute: float = 0.25
    rolling_window_size: int = 5
    backoff_base_seconds: float = 2.0
    backoff_max_seconds: float = 60.0

    def __post_init__(self) -> None:
        if self.max_consecutive_empty_scrolls < 1:
            raise ConfigurationError("max_consecutive_empty_scrolls must be >= 1")
        if not 0 <= self.max_duplicate_ratio <= 1:
            raise ConfigurationError("max_duplicate_ratio must be between 0 and 1")
        if self.rolling_window_size < 1:
            raise ConfigurationError("rolling_window_size must be >= 1")
        if self.backoff_base_seconds <= 0 or self.backoff_max_seconds <= 0:
            raise ConfigurationError("backoff settings must be positive")
        if self.backoff_base_seconds > self.backoff_max_seconds:
            raise ConfigurationError("backoff_base_seconds must be <= backoff_max_seconds")


@dataclass(frozen=True, slots=True)
class CollectorSettings:
    """Configuration for the Selenium-backed X collector."""

    headless: bool = True
    chrome_profile_path: str | Path | None = None
    chrome_binary_path: str | Path | None = None
    chrome_driver_path: str | Path | None = None
    checkpoint_path: str | Path = Path("data/checkpoints/x_collector_checkpoint.json")
    min_wait_seconds: float = 1.5
    max_wait_seconds: float = 4.0
    page_load_timeout_seconds: float = 30.0
    collection_timeout_seconds: float = 300.0
    max_retries: int = 3
    scroll_pause_min_seconds: float = 1.0
    scroll_pause_max_seconds: float = 3.0
    search_base_url: str = "https://x.com/search"
    throttling: ThrottlingSettings = field(default_factory=ThrottlingSettings)

    def __post_init__(self) -> None:
        checkpoint_path = Path(self.checkpoint_path)
        object.__setattr__(self, "checkpoint_path", checkpoint_path)

        if self.chrome_profile_path is not None:
            profile_path = Path(self.chrome_profile_path)
            if not profile_path.exists():
                raise ConfigurationError(f"chrome_profile_path does not exist: {profile_path}")
            object.__setattr__(self, "chrome_profile_path", profile_path)

        if self.chrome_binary_path is not None:
            binary_path = Path(self.chrome_binary_path)
            if not binary_path.exists():
                raise ConfigurationError(f"chrome_binary_path does not exist: {binary_path}")
            object.__setattr__(self, "chrome_binary_path", binary_path)

        if self.chrome_driver_path is not None:
            driver_path = Path(self.chrome_driver_path)
            if not driver_path.exists():
                raise ConfigurationError(f"chrome_driver_path does not exist: {driver_path}")
            object.__setattr__(self, "chrome_driver_path", driver_path)

        if self.min_wait_seconds < 0 or self.max_wait_seconds < 0:
            raise ConfigurationError("wait intervals must be non-negative")
        if self.min_wait_seconds > self.max_wait_seconds:
            raise ConfigurationError("min_wait_seconds must be <= max_wait_seconds")
        if self.scroll_pause_min_seconds > self.scroll_pause_max_seconds:
            raise ConfigurationError("scroll_pause_min_seconds must be <= scroll_pause_max_seconds")
        if self.max_retries < 0:
            raise ConfigurationError("max_retries must be >= 0")
