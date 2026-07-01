"""Selenium-backed X/Twitter collector.

The Selenium dependency is isolated behind ``BaseCollector`` so downstream
pipeline code can later swap this collector for another implementation without
changing ingestion, storage, or orchestration layers.
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Deque
from urllib.parse import quote, urlencode, urlparse

from collector.base import BaseCollector
from collector.exceptions import CollectorError, ExtractionError, LoginWallDetected, RateLimited
from collector.models import CollectorResult, CollectorStatus, Tweet
from config.settings import CollectorSettings

try:  # Selenium is optional until initialize() creates a browser session.
    from selenium import webdriver
    from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, WebDriverException
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.webdriver.common.by import By
    from selenium.webdriver.remote.webdriver import WebDriver
    from selenium.webdriver.remote.webelement import WebElement
except Exception:  # pragma: no cover - exercised only when Selenium is missing.
    webdriver = None  # type: ignore[assignment]
    StaleElementReferenceException = TimeoutException = WebDriverException = Exception  # type: ignore[misc,assignment]
    By = None  # type: ignore[assignment]
    WebDriver = Any  # type: ignore[misc,assignment]
    WebElement = Any  # type: ignore[misc,assignment]

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class CollectorMetrics:
    """Rolling metrics used for throttling and observability."""

    rolling_window_size: int = 5
    started_monotonic: float = field(default_factory=time.monotonic)
    total_collected: int = 0
    total_duplicates: int = 0
    total_scrolls: int = 0
    consecutive_empty_scrolls: int = 0
    scroll_history: Deque[tuple[int, int]] = field(init=False)

    def __post_init__(self) -> None:
        self.scroll_history = deque(maxlen=self.rolling_window_size)

    def record_collected(self, count: int) -> None:
        self.total_collected += count

    def record_scroll(self, new_tweets: int, duplicates: int) -> None:
        self.total_scrolls += 1
        self.total_duplicates += duplicates
        self.scroll_history.append((new_tweets, duplicates))
        if new_tweets == 0:
            self.consecutive_empty_scrolls += 1
        else:
            self.consecutive_empty_scrolls = 0

    @property
    def tweets_per_minute(self) -> float:
        elapsed = max(time.monotonic() - self.started_monotonic, 1.0)
        return self.total_collected / (elapsed / 60.0)

    @property
    def new_tweets_per_scroll(self) -> float:
        if not self.scroll_history:
            return 0.0
        return sum(new for new, _ in self.scroll_history) / len(self.scroll_history)

    @property
    def duplicate_ratio(self) -> float:
        total_seen = self.total_collected + self.total_duplicates
        if total_seen == 0:
            return 0.0
        return self.total_duplicates / total_seen

    def to_dict(self) -> dict[str, int | float]:
        return {
            "total_collected": self.total_collected,
            "total_duplicates": self.total_duplicates,
            "total_scrolls": self.total_scrolls,
            "consecutive_empty_scrolls": self.consecutive_empty_scrolls,
            "tweets_per_minute": self.tweets_per_minute,
            "new_tweets_per_scroll": self.new_tweets_per_scroll,
            "duplicate_ratio": self.duplicate_ratio,
        }


class SeleniumCollector(BaseCollector):
    """Defensive Selenium collector for public X/Twitter search pages.

    The implementation does not inject cookies, alter authentication tokens,
    spoof browser fingerprints, rotate sessions, or bypass CAPTCHAs. If a Chrome
    profile is supplied, authentication occurs naturally through that local
    browser profile.
    """

    def __init__(
        self,
        settings: CollectorSettings,
        driver: WebDriver | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        random_source: random.Random | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.settings = settings
        self.driver = driver
        self._owns_driver = driver is None
        self._sleeper = sleeper
        self._random = random_source or random.SystemRandom()
        self.logger = logger or LOGGER
        self.metrics = CollectorMetrics(settings.throttling.rolling_window_size)
        self.collected_tweets: dict[str, Tweet] = {}
        self.seen_tweet_ids: set[str] = set()
        self.retry_attempts = 0
        self._initialized = driver is not None
        self._last_status = CollectorStatus.SUCCESS
        self._last_error: str | None = None

    def initialize(self) -> None:
        """Start Chrome unless a driver was injected by the caller."""
        if self._initialized:
            return
        if webdriver is None:
            raise CollectorError("selenium is not installed")

        options = webdriver.ChromeOptions()
        if self.settings.headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1440,1200")

        if self.settings.chrome_profile_path is not None:
            options.add_argument(f"--user-data-dir={self.settings.chrome_profile_path}")
            self._log(logging.INFO, "chrome_profile_loaded", path=str(self.settings.chrome_profile_path))

        if self.settings.chrome_binary_path is not None:
            options.binary_location = str(self.settings.chrome_binary_path)

        service = None
        if self.settings.chrome_driver_path is not None:
            service = ChromeService(executable_path=str(self.settings.chrome_driver_path))

        self.driver = webdriver.Chrome(service=service, options=options)
        self.driver.set_page_load_timeout(self.settings.page_load_timeout_seconds)
        self._initialized = True
        self._log(logging.INFO, "collector_started", headless=self.settings.headless)

    def collect(self, query: str, limit: int) -> list[Tweet]:
        """Collect tweets from X search until a stop condition is met."""
        if limit < 1:
            return []
        self._last_status = CollectorStatus.SUCCESS
        self._last_error = None
        self.initialize()
        assert self.driver is not None

        deadline = time.monotonic() + self.settings.collection_timeout_seconds
        url = self.build_search_url(query)
        self._log(logging.INFO, "navigating_to_search", query=query, url=url, limit=limit)

        try:
            self.driver.get(url)
            self._bounded_wait(self.settings.min_wait_seconds, self.settings.max_wait_seconds)

            while len(self.collected_tweets) < limit and time.monotonic() < deadline:
                if self.login_wall_detected():
                    raise LoginWallDetected("login wall detected while collecting X search results")

                new_count, duplicate_count = self.extract_current_batch(limit=limit)
                self.metrics.record_scroll(new_count, duplicate_count)
                self._log(
                    logging.INFO,
                    "scroll_batch_processed",
                    new_tweets=new_count,
                    duplicates=duplicate_count,
                    total=len(self.collected_tweets),
                )

                if len(self.collected_tweets) >= limit:
                    break

                if self.should_backoff():
                    self.handle_possible_throttling()

                self.scroll_once()
                self._bounded_wait(self.settings.scroll_pause_min_seconds, self.settings.scroll_pause_max_seconds)

        except LoginWallDetected:
            self._log(logging.WARNING, "login_wall_detected")
            self._last_status = CollectorStatus.LOGIN_REQUIRED
            self._last_error = "login wall detected"
            self.checkpoint()
        except TimeoutException as exc:
            self._log(logging.WARNING, "collection_timeout", error=str(exc))
            self._last_status = CollectorStatus.PARTIAL
            self._last_error = str(exc)
            self.checkpoint()
        except RateLimited:
            self._last_status = CollectorStatus.THROTTLED
            self._last_error = "possible throttling persisted after retries were exhausted"
            raise
        except WebDriverException as exc:
            self.checkpoint()
            self._last_status = CollectorStatus.FAILED
            self._last_error = str(exc)
            raise ExtractionError(f"browser collection failed: {exc}") from exc
        finally:
            self.checkpoint()

        return list(self.collected_tweets.values())[:limit]

    def collect_result(self, query: str, limit: int) -> CollectorResult:
        """Collect records without surfacing Selenium/source errors to pipelines."""
        started = datetime.now(timezone.utc)
        records: list[Tweet] = []

        if self.should_backoff():
            self._log(logging.WARNING, "possible_throttling_detected", **self.metrics.to_dict())
            self.checkpoint()
            return CollectorResult(
                records=[],
                status=CollectorStatus.THROTTLED,
                started_at=started,
                ended_at=datetime.now(timezone.utc),
                error_message="throttling metrics were already above threshold",
                source_name="selenium_x",
            )

        try:
            records = self.collect(query=query, limit=limit)
            status = self._last_status
            error = self._last_error
            if not records and status in {CollectorStatus.SUCCESS, CollectorStatus.PARTIAL}:
                status = CollectorStatus.THROTTLED
                error = error or "source returned no records before stop condition"
            elif status == CollectorStatus.SUCCESS and len(records) < limit:
                status = CollectorStatus.PARTIAL if records else CollectorStatus.THROTTLED
                error = error or "collection ended before desired record count"
        except RateLimited as exc:
            records = list(self.collected_tweets.values())[:limit]
            status = CollectorStatus.THROTTLED
            error = str(exc)
        except LoginWallDetected as exc:
            records = list(self.collected_tweets.values())[:limit]
            status = CollectorStatus.LOGIN_REQUIRED
            error = str(exc)
        except Exception as exc:  # noqa: BLE001 - result envelope is the pipeline boundary.
            records = list(self.collected_tweets.values())[:limit]
            status = CollectorStatus.FAILED
            error = str(exc)

        return CollectorResult(
            records=records,
            status=status,
            started_at=started,
            ended_at=datetime.now(timezone.utc),
            error_message=error,
            source_name="selenium_x",
        )

    def checkpoint(self) -> Path:
        """Persist current collection state to JSON."""
        path = Path(self.settings.checkpoint_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "written_at": datetime.now(timezone.utc).isoformat(),
            "tweet_count": len(self.collected_tweets),
            "metrics": self.metrics.to_dict(),
            "tweets": [tweet.to_dict() for tweet in self.collected_tweets.values()],
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        self._log(logging.INFO, "checkpoint_written", path=str(path), tweet_count=len(self.collected_tweets))
        return path

    def shutdown(self) -> None:
        """Close the browser session if this collector owns it."""
        if self.driver is not None and self._owns_driver:
            try:
                self.driver.quit()
            finally:
                self.driver = None
                self._initialized = False
        self._log(logging.INFO, "collector_shutting_down")

    def build_search_url(self, query: str) -> str:
        """Build an X live-search URL for a query."""
        params = urlencode(
            {"q": query, "src": "typed_query", "f": "live"},
            quote_via=quote,
        )
        return f"{self.settings.search_base_url}?{params}"

    def extract_current_batch(self, limit: int) -> tuple[int, int]:
        """Extract visible tweet articles and update de-duplication state."""
        assert self.driver is not None
        articles = self.driver.find_elements(By.CSS_SELECTOR, 'article[data-testid="tweet"]')
        new_count = 0
        duplicate_count = 0

        for article in articles:
            if len(self.collected_tweets) >= limit:
                break
            try:
                tweet = self.extract_tweet(article)
            except (ExtractionError, StaleElementReferenceException) as exc:
                self._log(logging.DEBUG, "tweet_extraction_skipped", error=str(exc))
                continue

            if tweet.tweet_id in self.seen_tweet_ids:
                duplicate_count += 1
                self._log(logging.DEBUG, "duplicate_skipped", tweet_id=tweet.tweet_id)
                continue

            self.seen_tweet_ids.add(tweet.tweet_id)
            self.collected_tweets[tweet.tweet_id] = tweet
            self.metrics.record_collected(1)
            new_count += 1
            self._log(logging.INFO, "tweet_collected", tweet_id=tweet.tweet_id, username=tweet.username)

        return new_count, duplicate_count

    def extract_tweet(self, article: WebElement) -> Tweet:
        """Extract a normalized tweet from a Selenium article element."""
        url = self._extract_status_url(article)
        tweet_id = self._tweet_id_from_url(url)
        username = self._username_from_url(url)
        content = self._extract_content(article)
        if not tweet_id or not content:
            raise ExtractionError("tweet article missing status URL or content")

        return Tweet(
            tweet_id=tweet_id,
            username=username,
            display_name=self._extract_display_name(article),
            timestamp=self._extract_timestamp(article),
            content=content,
            hashtags=self.extract_hashtags(content),
            mentions=self.extract_mentions(content),
            reply_count=self._extract_action_count(article, "reply"),
            retweet_count=self._extract_action_count(article, "retweet"),
            like_count=self._extract_action_count(article, "like"),
            view_count=self._extract_view_count(article),
            follower_count=None,
            following_count=None,
            url=url,
        )

    def login_wall_detected(self) -> bool:
        """Detect obvious login-wall states without trying to bypass them."""
        assert self.driver is not None
        page_text = ""
        try:
            page_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
        except WebDriverException:
            return False
        markers = (
            "sign in to x",
            "log in to x",
            "sign in to twitter",
            "log in to twitter",
            "don't miss what's happening",
        )
        return any(marker in page_text for marker in markers)

    def scroll_once(self) -> None:
        """Scroll the current page down once."""
        assert self.driver is not None
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

    def should_backoff(self) -> bool:
        """Return true when rolling metrics indicate degraded source access."""
        throttling = self.settings.throttling
        if self.metrics.consecutive_empty_scrolls >= throttling.max_consecutive_empty_scrolls:
            return True
        if self.metrics.duplicate_ratio > throttling.max_duplicate_ratio and self.metrics.total_duplicates > 0:
            return True
        if self.metrics.total_scrolls >= throttling.rolling_window_size and self.metrics.tweets_per_minute < throttling.min_tweets_per_minute:
            return True
        return False

    def handle_possible_throttling(self) -> None:
        """Checkpoint and back off, or stop if retry budget is exhausted."""
        if not self.should_backoff():
            return
        self._log(logging.WARNING, "possible_throttling_detected", **self.metrics.to_dict())
        self.checkpoint()

        if self.retry_attempts >= self.settings.max_retries:
            self._log(logging.WARNING, "retry_limit_exhausted", retries=self.retry_attempts)
            raise RateLimited("possible throttling persisted after retries were exhausted")

        delay = self._backoff_delay(self.retry_attempts)
        self.retry_attempts += 1
        self._log(logging.WARNING, "retrying_after_backoff", delay_seconds=delay, retry=self.retry_attempts)
        self._sleeper(delay)

    def parse_count(self, raw: str | None) -> int | None:
        """Parse compact social-count strings such as 1.2K or 3M."""
        if raw is None:
            return None
        text = raw.strip().replace(",", "")
        if not text:
            return None
        match = re.search(r"(?P<num>\d+(?:\.\d+)?)(?P<suffix>[KMBkmb]?)", text)
        if not match:
            return None
        value = float(match.group("num"))
        suffix = match.group("suffix").upper()
        multiplier = {"": 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[suffix]
        return int(value * multiplier)

    def extract_hashtags(self, text: str) -> list[str]:
        """Extract hashtags without the leading #."""
        return re.findall(r"(?<!\w)#([A-Za-z0-9_]+)", text)

    def extract_mentions(self, text: str) -> list[str]:
        """Extract mentions without the leading @."""
        return re.findall(r"(?<!\w)@([A-Za-z0-9_]+)", text)

    def _extract_status_url(self, article: WebElement) -> str | None:
        links = article.find_elements(By.CSS_SELECTOR, 'a[href*="/status/"]')
        for link in links:
            href = link.get_attribute("href")
            if href and "/status/" in href:
                return href.split("?", 1)[0]
        return None

    def _tweet_id_from_url(self, url: str | None) -> str | None:
        if not url:
            return None
        match = re.search(r"/status/(\d+)", url)
        return match.group(1) if match else None

    def _username_from_url(self, url: str | None) -> str | None:
        if not url:
            return None
        parsed = urlparse(url)
        parts = [part for part in parsed.path.split("/") if part]
        return parts[0] if len(parts) >= 2 else None

    def _extract_content(self, article: WebElement) -> str:
        nodes = article.find_elements(By.CSS_SELECTOR, 'div[data-testid="tweetText"]')
        if nodes:
            return nodes[0].text.strip()
        return article.text.strip()

    def _extract_display_name(self, article: WebElement) -> str | None:
        text = article.text.strip()
        if not text:
            return None
        first_line = text.splitlines()[0].strip()
        return first_line or None

    def _extract_timestamp(self, article: WebElement) -> str | None:
        times = article.find_elements(By.CSS_SELECTOR, "time")
        if not times:
            return None
        return times[0].get_attribute("datetime")

    def _extract_action_count(self, article: WebElement, testid_fragment: str) -> int | None:
        selectors = [
            f'div[data-testid="{testid_fragment}"]',
            f'div[data-testid="{testid_fragment}s"]',
            f'div[aria-label*="{testid_fragment}"]',
        ]
        for selector in selectors:
            nodes = article.find_elements(By.CSS_SELECTOR, selector)
            if not nodes:
                continue
            for attr in ("aria-label", "textContent"):
                raw = nodes[0].get_attribute(attr) or nodes[0].text
                parsed = self.parse_count(raw)
                if parsed is not None:
                    return parsed
        return None

    def _extract_view_count(self, article: WebElement) -> int | None:
        nodes = article.find_elements(By.CSS_SELECTOR, 'a[href$="/analytics"], a[aria-label*="views"], div[aria-label*="views"]')
        for node in nodes:
            raw = node.get_attribute("aria-label") or node.text
            parsed = self.parse_count(raw)
            if parsed is not None:
                return parsed
        return None

    def _bounded_wait(self, minimum: float, maximum: float) -> None:
        if maximum <= 0:
            return
        self._sleeper(self._random.uniform(minimum, maximum))

    def _backoff_delay(self, attempt: int) -> float:
        base = self.settings.throttling.backoff_base_seconds * (2**attempt)
        jitter = self._random.uniform(0, self.settings.throttling.backoff_base_seconds)
        return min(base + jitter, self.settings.throttling.backoff_max_seconds)

    def _log(self, level: int, event: str, **fields: Any) -> None:
        suffix = " ".join(f"{key}={value!r}" for key, value in sorted(fields.items()))
        self.logger.log(level, f"event={event} {suffix}".rstrip())
