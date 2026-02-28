#!/usr/bin/env python3
"""Scrape Wallhaven tags using Firecrawl and API fallback.

This tool fetches tag metadata from Wallhaven to enable accurate tag-based
search queries. It uses a three-phase approach:

1. Phase 1 (List Pages): Scrape /tags/tagged pages to get tag stubs (~50 per page)
2. Phase 2 (Detail Pages): Use Firecrawl to scrape individual tag pages for aliases
3. Phase 3 (API Fallback): Use Wallhaven API for tags that failed Firecrawl

Usage:
    # Run smoke test first (uses 3 credits)
    python tools/scrape_wallhaven_tags.py --smoke-test

    # Run test with ~20 credits
    python tools/scrape_wallhaven_tags.py --test-run

    # Run full scrape with default budget
    python tools/scrape_wallhaven_tags.py

    # Custom budget
    python tools/scrape_wallhaven_tags.py --credits 1500

    # Resume interrupted job
    python tools/scrape_wallhaven_tags.py --resume
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Callable

import requests

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from variety.smart_selection.database import ImageDatabase

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


# ============================================================================
# Configuration
# ============================================================================

# Correct URLs (use path-based, not query params)
WALLHAVEN_TAGS_LIST_URL = "https://wallhaven.cc/tags/tagged"  # Most tagged
WALLHAVEN_TAG_DETAIL_URL = "https://wallhaven.cc/tag/{tag_id}"
WALLHAVEN_API_TAG_URL = "https://wallhaven.cc/api/v1/tag/{tag_id}"

# Agentic prompts for LLM extraction
TAG_LIST_PROMPT = """This is Wallhaven's "Most Tagged" page showing popular wallpaper tags.

Each tag entry has:
- A link like [Tag Name](https://wallhaven.cc/tag/12345) - extract the NUMBER as tag_id
- The tag name from the link text
- Wallpaper count (number of wallpapers using this tag)
- Category path like "People » Artists" or "Anime & Manga » Characters"

Extract ALL tag entries from the main listing (should be ~50 per page).
The tag_id MUST be the actual number from the /tag/XXXXX URL, NOT sequential numbers.

Return JSON: {"tags": [{"tag_id": 222, "name": "women", "wallpaper_count": 123456, "category": "People"}, ...]}"""

TAG_DETAIL_PROMPT = """This is a Wallhaven tag detail page. Extract the tag information:

- tag_id: numeric ID (from the URL, /tag/37 means 37)
- name: the primary tag name shown on the page
- alias: Look for a div with id="aliases" - it contains comma-separated alternative names.
  The div may be collapsed/hidden but the text content is there. Extract ALL aliases as a
  comma-separated string. Example: "ai ladies, babes, cute girl, female, girl, woman"
  If no aliases div exists, use null.
- category: general/anime/people (the main category)
- purity: sfw/sketchy/nsfw (content rating)
- wallpaper_count: total number of wallpapers with this tag

Return as a flat JSON object with these fields."""


def parse_tag_list_html(html: str) -> List[Dict]:
    """Parse tag list page HTML to extract tags.

    Extracts tag_id, name, purity, and category from the Wallhaven tag list page.
    Much faster than LLM extraction (~1 second vs ~30-60 seconds per page).

    Args:
        html: Raw HTML of the tag list page.

    Returns:
        List of tag dictionaries with tag_id, name, purity, category.
    """
    tags = []

    # Pattern: <a class="purity" href=".../tag/ID">NAME</a>
    # followed by category in taglist-category span
    pattern = (
        r'<a class="(sfw|sketchy|nsfw)" href="https://wallhaven\.cc/tag/(\d+)"[^>]*>'
        r'([^<]+)</a>.*?<span class="taglist-category">'
        r'([^<]*(?:<a[^>]*>([^<]+)</a>[^<]*)*)</span>'
    )

    for match in re.finditer(pattern, html, re.DOTALL):
        purity = match.group(1)
        tag_id = int(match.group(2))
        name = match.group(3).strip()
        category_html = match.group(4)

        # Extract category from the last link in category_html
        cat_links = re.findall(r'<a[^>]*>([^<]+)</a>', category_html)
        category = cat_links[-1] if cat_links else None

        tags.append({
            'tag_id': tag_id,
            'name': name,
            'purity': purity,
            'category': category
        })

    return tags


def parse_aliases_from_html(html: str) -> Optional[str]:
    """Extract aliases from the #aliases div in Wallhaven tag detail HTML.

    The aliases are in a div like:
    <div class="collapsed" id="aliases"><h3>aliases</h3>alias1, alias2, alias3...</div>

    Args:
        html: Raw HTML of the tag detail page.

    Returns:
        Comma-separated string of aliases, or None if not found.
    """
    if not html:
        return None

    # Pattern to match the aliases div content
    # Handles: <div ... id="aliases">...<h3>aliases</h3>ACTUAL_ALIASES...</div>
    pattern = r'<div[^>]*id=["\']aliases["\'][^>]*>.*?<h3>[^<]*</h3>([^<]+)'
    match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)

    if match:
        aliases_text = match.group(1).strip()
        # Clean up: remove excessive whitespace, HTML entities
        aliases_text = re.sub(r'\s+', ' ', aliases_text)
        aliases_text = aliases_text.replace('&nbsp;', ' ')
        aliases_text = aliases_text.replace('&amp;', '&')

        # Validate: should be readable text, not garbage
        # Accept single words/phrases (no comma required) as long as it's not empty
        # and contains actual word characters
        if aliases_text and re.search(r'[a-zA-Z]', aliases_text):
            return aliases_text

    return None


@dataclass
class PipelineConfig:
    """Configuration for the tag scraping pipeline."""

    # Credit budget (only applies to Firecrawl)
    total_credits: int = 3000
    phase1_credits: int = 200
    phase2_credits: Optional[int] = None  # Calculated if None
    credit_reserve: int = 50
    smoke_test_credits: int = 3
    test_run_credits: int = 20

    # Rate limits
    api_rate_limit: int = 45  # requests per minute

    # Paths
    db_path: str = field(default_factory=lambda: os.path.expanduser(
        "~/.config/variety/smart_selection.db"
    ))

    # API keys
    firecrawl_api_key: Optional[str] = None
    wallhaven_api_key: Optional[str] = None

    # Backend settings
    backend: str = "firecrawl"  # "firecrawl" or "crawl4ai"
    headless: bool = True  # For crawl4ai
    concurrency: int = 5  # Number of concurrent workers

    @property
    def phase2_budget(self) -> int:
        """Calculate phase 2 budget."""
        if self.phase2_credits is not None:
            return self.phase2_credits
        return self.total_credits - self.phase1_credits - self.credit_reserve

    def validate(self) -> List[str]:
        """Validate configuration and return list of errors."""
        errors = []
        if self.backend == "firecrawl" and not self.firecrawl_api_key:
            errors.append("Firecrawl API key is required (set FIRECRAWL_API_KEY)")
        if self.backend == "firecrawl" and self.total_credits < self.smoke_test_credits:
            errors.append(f"Total credits ({self.total_credits}) must be >= smoke test credits ({self.smoke_test_credits})")
        return errors


# ============================================================================
# Firecrawl Client (using SDK)
# ============================================================================

class FirecrawlClient:
    """Client for Firecrawl using the official SDK."""

    def __init__(self, api_key: str):
        from firecrawl import FirecrawlApp
        self.app = FirecrawlApp(api_key=api_key)

    def scrape_with_prompt(self, url: str, prompt: str) -> Dict:
        """Scrape a URL with agentic LLM extraction.

        Args:
            url: URL to scrape.
            prompt: Natural language prompt describing what to extract.

        Returns:
            Extracted JSON data.
        """
        result = self.app.scrape(
            url,
            formats=[{
                "type": "json",
                "prompt": prompt
            }]
        )
        return result.json if result.json else {}

    def scrape_markdown(self, url: str) -> str:
        """Scrape a URL and return markdown.

        Args:
            url: URL to scrape.

        Returns:
            Markdown content.
        """
        result = self.app.scrape(url, formats=["markdown"])
        return result.markdown or ""

    def scrape_raw_html(self, url: str, max_retries: int = 3, timeout: int = 60) -> str:
        """Scrape a URL and return raw HTML with retry logic and timeout.

        Args:
            url: URL to scrape.
            max_retries: Maximum number of retry attempts.
            timeout: Timeout in seconds per request (default 60s).

        Returns:
            Raw HTML content, or empty string if all retries failed.
        """
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

        def do_scrape():
            result = self.app.scrape(url, formats=["rawHtml"])
            return result.raw_html or ""

        last_error = None
        for attempt in range(max_retries):
            try:
                # Wrap in executor with timeout to prevent indefinite hangs
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(do_scrape)
                    return future.result(timeout=timeout)
            except FuturesTimeoutError:
                last_error = TimeoutError(f"Request timed out after {timeout}s")
                logger.warning(f"Scrape timed out (attempt {attempt + 1}/{max_retries}): {url}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff: 1, 2, 4 seconds
                    logger.warning(f"Scrape failed (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)

        # Check if we ran out of credits
        error_str = str(last_error).lower()
        if "credit" in error_str or "quota" in error_str or "limit" in error_str:
            logger.warning(f"Possible credit exhaustion: {last_error}")
        else:
            logger.error(f"Scrape failed after {max_retries} attempts: {last_error}")
        return ""  # Return empty string instead of crashing

    def batch_scrape_with_prompt(
        self,
        urls: List[str],
        prompt: str,
        poll_interval: int = 5,
        timeout: int = 600
    ) -> List[Dict]:
        """Batch scrape multiple URLs with the same prompt.

        Args:
            urls: List of URLs to scrape.
            prompt: Natural language prompt for extraction.
            poll_interval: Seconds between status checks.
            timeout: Maximum wait time.

        Returns:
            List of extracted JSON data for each URL.
        """
        # Start batch job
        batch_result = self.app.batch_scrape(
            urls,
            params={
                "formats": [{
                    "type": "json",
                    "prompt": prompt
                }]
            },
            poll_interval=poll_interval
        )

        # Extract results
        results = []
        if hasattr(batch_result, 'data'):
            for item in batch_result.data:
                results.append(item.json if item.json else {})
        elif isinstance(batch_result, dict) and 'data' in batch_result:
            for item in batch_result['data']:
                if isinstance(item, dict):
                    results.append(item.get('json') or item.get('extract') or {})
                else:
                    results.append(item.json if hasattr(item, 'json') else {})

        return results

    def scrape_batch_concurrent(
        self,
        urls: List[str],
        max_workers: int = 5,
        rate_limit_per_worker: int = 18,
        callback: Optional[Callable[[str, str], None]] = None
    ) -> Dict[str, str]:
        """Scrape multiple URLs concurrently with per-worker rate limiting.

        Each worker has its own rate limit bucket, so all workers run
        truly in parallel.

        Args:
            urls: List of URLs to scrape.
            max_workers: Number of concurrent workers (default 5).
            rate_limit_per_worker: Max requests per minute PER WORKER (default 18).
            callback: Optional callback(url, html) called after each successful scrape.

        Returns:
            Dict mapping URL to HTML content.
        """
        import threading
        import queue

        results = {}
        url_queue = queue.Queue()
        for url in urls:
            url_queue.put(url)

        results_lock = threading.Lock()
        min_interval = 60.0 / rate_limit_per_worker  # Each worker's interval

        def worker(worker_id: int):
            last_request_time = 0.0

            while True:
                try:
                    url = url_queue.get_nowait()
                except queue.Empty:
                    break

                # Per-worker rate limiting
                now = time.time()
                wait_time = last_request_time + min_interval - now
                if wait_time > 0:
                    time.sleep(wait_time)
                last_request_time = time.time()

                # Make request
                html = self.scrape_raw_html(url)

                with results_lock:
                    results[url] = html

                if callback:
                    callback(url, html)

                url_queue.task_done()

        # Start workers
        threads = []
        for i in range(max_workers):
            t = threading.Thread(target=worker, args=(i,))
            t.start()
            threads.append(t)

        # Wait for all to complete
        for t in threads:
            t.join()

        return results


# ============================================================================
# Crawl4AI Client (local, free alternative to Firecrawl)
# ============================================================================

class Crawl4AIClient:
    """Client for Crawl4AI - a free, local web crawler.

    Uses the crawl4ai library installed at ~/repos/crawl4ai.
    Supports async crawling with Playwright browser.
    """

    def __init__(self, headless: bool = True, browser_type: str = "chromium"):
        """Initialize the Crawl4AI client.

        Args:
            headless: Run browser in headless mode (default True).
            browser_type: Browser to use (chromium, firefox, webkit).
        """
        self.headless = headless
        self.browser_type = browser_type
        self._crawler = None
        self._loop = None

    def _get_event_loop(self):
        """Get or create an event loop."""
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            if self._loop is None or self._loop.is_closed():
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
            return self._loop

    def _setup_crawl4ai_path(self):
        """Add crawl4ai venv to path if needed."""
        crawl4ai_path = os.path.expanduser("~/repos/crawl4ai")
        venv_lib = os.path.join(crawl4ai_path, ".venv", "lib")

        # Dynamically find the Python version directory
        venv_site_packages = None
        if os.path.exists(venv_lib):
            for entry in os.listdir(venv_lib):
                if entry.startswith("python"):
                    candidate = os.path.join(venv_lib, entry, "site-packages")
                    if os.path.exists(candidate):
                        venv_site_packages = candidate
                        break

        if venv_site_packages and venv_site_packages not in sys.path:
            sys.path.insert(0, venv_site_packages)
        if crawl4ai_path not in sys.path:
            sys.path.insert(0, crawl4ai_path)

    async def _scrape_async(self, url: str, timeout: int = 60) -> str:
        """Async scrape implementation.

        Args:
            url: URL to scrape.
            timeout: Timeout in seconds.

        Returns:
            Raw HTML content.
        """
        # Import here to avoid loading crawl4ai until needed
        self._setup_crawl4ai_path()
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

        browser_config = BrowserConfig(
            headless=self.headless,
            browser_type=self.browser_type,
        )

        run_config = CrawlerRunConfig(
            page_timeout=timeout * 1000,  # Convert to milliseconds
        )

        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(url=url, config=run_config)
            if result.success:
                return result.html or ""
            else:
                logger.warning(f"Crawl4AI failed for {url}: {result.error_message}")
                return ""

    def scrape_raw_html(self, url: str, max_retries: int = 3, timeout: int = 60) -> str:
        """Scrape a URL and return raw HTML with retry logic.

        Args:
            url: URL to scrape.
            max_retries: Maximum number of retry attempts.
            timeout: Timeout in seconds per request.

        Returns:
            Raw HTML content, or empty string if all retries failed.
        """
        last_error = None
        for attempt in range(max_retries):
            try:
                loop = self._get_event_loop()
                html = loop.run_until_complete(
                    asyncio.wait_for(self._scrape_async(url, timeout), timeout=timeout + 10)
                )
                if html:
                    return html
                # Empty result counts as failure, retry
                if attempt < max_retries - 1:
                    logger.warning(f"Empty result (attempt {attempt + 1}/{max_retries}), retrying...")
                    time.sleep(2 ** attempt)
            except asyncio.TimeoutError:
                last_error = TimeoutError(f"Request timed out after {timeout}s")
                logger.warning(f"Scrape timed out (attempt {attempt + 1}/{max_retries}): {url}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Scrape failed (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)

        logger.error(f"Scrape failed after {max_retries} attempts: {last_error}")
        return ""

    def scrape_batch_concurrent(
        self,
        urls: List[str],
        max_workers: int = 5,
        rate_limit_per_worker: int = 18,
        callback: Optional[Callable[[str, str], None]] = None
    ) -> Dict[str, str]:
        """Scrape multiple URLs concurrently with per-worker rate limiting.

        For Crawl4AI, we use async concurrency instead of threads since it's
        natively async. Each "worker" is a concurrent async task.

        Includes automatic retry with exponential backoff for 429 rate limit errors.

        Args:
            urls: List of URLs to scrape.
            max_workers: Number of concurrent tasks (default 5).
            rate_limit_per_worker: Max requests per minute PER WORKER (default 18).
            callback: Optional callback(url, html) called after each successful scrape.

        Returns:
            Dict mapping URL to HTML content.
        """
        import asyncio
        import random

        def is_rate_limited(html: str) -> bool:
            """Check if response indicates rate limiting (429 error)."""
            if not html:
                return False
            # Short responses with 429 in them are rate limit errors
            if len(html) < 5000 and "429" in html:
                return True
            if "Too Many Requests" in html:
                return True
            return False

        async def scrape_all():
            self._setup_crawl4ai_path()
            from crawl4ai import AsyncWebCrawler, BrowserConfig

            browser_config = BrowserConfig(
                headless=self.headless,
                browser_type=self.browser_type,
            )

            results = {}
            semaphore = asyncio.Semaphore(max_workers)
            min_interval = 60.0 / rate_limit_per_worker

            # Each worker has its own state for rate limiting
            worker_states = [{} for _ in range(max_workers)]

            # Track rate limit events for adaptive backoff
            rate_limit_count = 0
            max_retries = 3

            async with AsyncWebCrawler(config=browser_config) as crawler:
                self._crawler = crawler

                async def scrape_one(url: str, worker_id: int, attempt: int = 0) -> Tuple[str, str, bool]:
                    """Scrape one URL, returns (url, html, needs_retry)."""
                    nonlocal rate_limit_count

                    async with semaphore:
                        state = worker_states[worker_id % max_workers]
                        now = time.time()
                        wait_time = state.get('last_time', 0) + min_interval - now

                        # Stagger initial requests to avoid burst (only on first request per worker)
                        if 'last_time' not in state and attempt == 0:
                            stagger = (worker_id % max_workers) * 0.5 + random.uniform(0, 0.3)
                            wait_time = max(wait_time, stagger)

                        # Add extra delay if we've been rate limited
                        if rate_limit_count > 0:
                            wait_time += rate_limit_count * 2  # Progressive delay

                        if wait_time > 0:
                            await asyncio.sleep(wait_time)
                        state['last_time'] = time.time()

                        result = await crawler.arun(url=url)
                        html = result.html if result.success else ""

                        # Check for rate limiting
                        if is_rate_limited(html):
                            rate_limit_count += 1
                            logger.warning(f"Rate limited on {url} (attempt {attempt + 1})")
                            return url, "", True  # needs_retry

                        return url, html, False  # success

                # Initial scrape of all URLs
                pending_urls = list(urls)
                url_to_worker = {url: i for i, url in enumerate(urls)}

                for attempt in range(max_retries + 1):
                    if not pending_urls:
                        break

                    if attempt > 0:
                        # Exponential backoff with jitter before retry
                        backoff = (2 ** attempt) + random.uniform(0, 1)
                        logger.info(f"Retrying {len(pending_urls)} rate-limited URLs after {backoff:.1f}s backoff...")
                        await asyncio.sleep(backoff)

                    tasks = [
                        scrape_one(url, url_to_worker[url], attempt)
                        for url in pending_urls
                    ]

                    retry_urls = []
                    for coro in asyncio.as_completed(tasks):
                        url, html, needs_retry = await coro
                        if needs_retry:
                            retry_urls.append(url)
                        else:
                            results[url] = html
                            if callback:
                                callback(url, html)

                    pending_urls = retry_urls

                # Log any URLs that still failed after all retries
                if pending_urls:
                    logger.error(f"Failed to scrape {len(pending_urls)} URLs after {max_retries} retries: {pending_urls[:5]}...")
                    for url in pending_urls:
                        results[url] = ""  # Empty result for failed URLs

            return results

        loop = self._get_event_loop()
        return loop.run_until_complete(scrape_all())


# ============================================================================
# Wallhaven API Client
# ============================================================================

class WallhavenAPIClient:
    """Client for Wallhaven API."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.session = requests.Session()
        if api_key:
            self.session.headers.update({"X-API-Key": api_key})

    def get_tag(self, tag_id: int) -> Optional[Dict]:
        """Fetch tag details from API.

        Args:
            tag_id: The tag ID.

        Returns:
            Tag data or None if not found.
        """
        url = WALLHAVEN_API_TAG_URL.format(tag_id=tag_id)
        try:
            response = self.session.get(url, timeout=30)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()
            return data.get("data")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to fetch tag {tag_id}: {e}")
            return None


# ============================================================================
# Pipeline
# ============================================================================

class TagScrapePipeline:
    """Main pipeline for scraping Wallhaven tags."""

    def __init__(self, config: PipelineConfig, db: ImageDatabase):
        self.config = config
        self.db = db
        self.credits_used = 0

        # Initialize scraping client based on backend
        if config.backend == "crawl4ai":
            logger.info(f"Using Crawl4AI backend (headless={config.headless})")
            self.scraper = Crawl4AIClient(headless=config.headless)
        else:
            if config.firecrawl_api_key:
                logger.info("Using Firecrawl backend")
                self.scraper = FirecrawlClient(config.firecrawl_api_key)
            else:
                self.scraper = None

        # Keep firecrawl alias for backward compatibility
        self.firecrawl = self.scraper
        self.wallhaven = WallhavenAPIClient(config.wallhaven_api_key)

    def run_smoke_test(self) -> bool:
        """Run smoke test to verify pipeline works.

        Uses 3 credits: 2 list pages + 1 detail page.

        Returns:
            True if smoke test passed.
        """
        logger.info("=" * 60)
        logger.info("SMOKE TEST - Verifying pipeline with 3 credits")
        logger.info("=" * 60)

        if not self.firecrawl:
            logger.error("Firecrawl API key required for smoke test")
            return False

        job_id = self.db.create_scrape_job(
            'smoke_test',
            credits_budget=self.config.smoke_test_credits
        )
        self.db.update_scrape_job(job_id, status='in_progress')

        try:
            # Test 1: Scrape 2 list pages
            logger.info("Step 1/3: Testing list page scrape (2 pages)...")

            tags_found = 0
            for page in [1, 2]:
                url = f"{WALLHAVEN_TAGS_LIST_URL}?page={page}"
                logger.info(f"  Scraping page {page}...")
                result = self.firecrawl.scrape_with_prompt(url, TAG_LIST_PROMPT)
                tags = result.get('tags', [])
                tags_found += len(tags)
                self.credits_used += 1

                if tags:
                    logger.info(f"    Found {len(tags)} tags")
                    logger.info(f"    Sample: {tags[0]}")

            logger.info(f"  Total tags from 2 pages: {tags_found}")

            if tags_found < 20:
                logger.warning("  Low tag count - extraction may need tuning")

            # Test 2: Scrape 1 detail page
            logger.info("Step 2/3: Testing detail page scrape...")

            detail_url = WALLHAVEN_TAG_DETAIL_URL.format(tag_id=37)  # nature
            detail_result = self.firecrawl.scrape_with_prompt(detail_url, TAG_DETAIL_PROMPT)
            self.credits_used += 1

            logger.info(f"  Detail result: {detail_result}")

            # Test 3: Test API fallback
            logger.info("Step 3/3: Testing API fallback...")
            api_result = self.wallhaven.get_tag(37)
            if api_result:
                logger.info(f"  API result: id={api_result.get('id')}, name={api_result.get('name')}")
            else:
                logger.warning("  API fallback returned no data")

            # Success
            self.db.update_scrape_job(
                job_id,
                status='completed',
                credits_used=self.credits_used,
                items_completed=3
            )

            logger.info("")
            logger.info("=" * 60)
            logger.info("SMOKE TEST PASSED")
            logger.info(f"Credits used: {self.credits_used}/{self.config.smoke_test_credits}")
            logger.info("=" * 60)
            return True

        except Exception as e:
            logger.exception("Smoke test failed")
            self.db.update_scrape_job(
                job_id,
                status='failed',
                error_message=str(e)
            )
            return False

    def run_test_run(self) -> Tuple[int, int]:
        """Run a test with ~20 credits.

        Scrapes 10 list pages (500 tags) + 10 detail pages.

        Returns:
            Tuple of (tags_found, aliases_found).
        """
        logger.info("=" * 60)
        logger.info("TEST RUN - ~20 credits (10 list + 10 detail pages)")
        logger.info("=" * 60)

        if not self.firecrawl:
            logger.error("Firecrawl API key required")
            return 0, 0

        job_id = self.db.create_scrape_job(
            'test_run',
            credits_budget=self.config.test_run_credits
        )
        self.db.update_scrape_job(job_id, status='in_progress')

        try:
            # Phase 1: 10 list pages (using fast HTML parsing)
            logger.info("\n[Phase 1] Scraping 10 list pages (~500 tags)...")
            logger.info("  Using HTML parsing (fast mode)...")
            all_tags = []

            for page in range(1, 11):
                url = f"{WALLHAVEN_TAGS_LIST_URL}?page={page}"
                logger.info(f"  Page {page}/10...")

                # Use HTML parsing instead of LLM extraction (much faster)
                html = self.firecrawl.scrape_raw_html(url)
                self.credits_used += 1

                tags = parse_tag_list_html(html)
                for i, tag in enumerate(tags):
                    tag['popularity_rank'] = (page - 1) * 50 + i + 1
                    tag['alias_source'] = 'firecrawl'
                all_tags.extend(tags)

                logger.info(f"    Found {len(tags)} tags (total: {len(all_tags)})")

            # Store tags in database
            if all_tags:
                tag_dicts = [{
                    'tag_id': t['tag_id'],
                    'name': t['name'],
                    'purity': t.get('purity'),
                    'category': t.get('category'),
                    'popularity_rank': t.get('popularity_rank'),
                    'alias_source': t.get('alias_source'),
                } for t in all_tags]
                self.db.upsert_tags_batch(tag_dicts)
                logger.info(f"  Stored {len(all_tags)} tags in database")

            # Phase 2: 10 detail pages (top 10 tags)
            # Use HTML parsing for reliable alias extraction
            logger.info("\n[Phase 2] Scraping 10 detail pages (top 10 tags)...")
            aliases_found = 0

            top_tags = all_tags[:10] if all_tags else []
            for i, tag in enumerate(top_tags, 1):
                tag_id = tag['tag_id']
                tag_name = tag['name']
                url = WALLHAVEN_TAG_DETAIL_URL.format(tag_id=tag_id)

                logger.info(f"  {i}/10: {tag_name} (ID: {tag_id})...")

                # Fetch raw HTML and parse aliases directly
                html = self.firecrawl.scrape_raw_html(url)
                self.credits_used += 1

                alias = parse_aliases_from_html(html)
                if alias:
                    self.db.upsert_tag(
                        tag_id=tag_id,
                        name=tag_name,
                        alias=alias,
                        alias_source='firecrawl'
                    )
                    self.db.update_tag_scrape_status(
                        tag_id,
                        firecrawl_status='success',
                        firecrawl_job_id=job_id
                    )
                    aliases_found += 1
                    # Truncate long alias lists for display
                    display_alias = alias[:80] + "..." if len(alias) > 80 else alias
                    logger.info(f"    Alias: {display_alias}")
                else:
                    # Clear any stale alias data from previous runs
                    self.db.upsert_tag(
                        tag_id=tag_id,
                        name=tag_name,
                        alias='',  # Empty string to clear stale data
                        alias_source='firecrawl'
                    )
                    self.db.update_tag_scrape_status(
                        tag_id,
                        firecrawl_status='no_alias',
                        firecrawl_job_id=job_id
                    )
                    logger.info(f"    No alias (cleared stale data)")

            # Complete
            self.db.update_scrape_job(
                job_id,
                status='completed',
                credits_used=self.credits_used,
                items_completed=len(all_tags)
            )

            logger.info("")
            logger.info("=" * 60)
            logger.info("TEST RUN COMPLETE")
            logger.info(f"Tags found: {len(all_tags)}")
            logger.info(f"Aliases found: {aliases_found}")
            logger.info(f"Credits used: {self.credits_used}")
            logger.info("=" * 60)

            return len(all_tags), aliases_found

        except Exception as e:
            logger.exception("Test run failed")
            self.db.update_scrape_job(
                job_id,
                status='failed',
                error_message=str(e)
            )
            raise

    def run_phase1_list_scrape(self, max_pages: int = 200) -> int:
        """Phase 1: Scrape tag list pages.

        Args:
            max_pages: Maximum number of pages to scrape.

        Returns:
            Number of tags found.
        """
        logger.info("=" * 60)
        logger.info(f"PHASE 1: Scraping tag list pages (up to {max_pages} pages)")
        logger.info(f"Budget: {self.config.phase1_credits} credits")
        logger.info("=" * 60)

        if not self.firecrawl:
            logger.error("Firecrawl API key required")
            return 0

        job_id = self.db.create_scrape_job(
            'tag_list',
            credits_budget=self.config.phase1_credits
        )
        self.db.update_scrape_job(job_id, status='in_progress', items_total=max_pages)

        # Check for resumable job
        existing = self.db.get_resumable_job('tag_list')
        start_page = 1
        if existing and existing['progress_cursor']:
            cursor = json.loads(existing['progress_cursor'])
            start_page = cursor.get('next_page', 1)
            self.credits_used = existing.get('credits_used', 0)
            logger.info(f"Resuming from page {start_page}")

        total_tags = 0

        try:
            for page in range(start_page, max_pages + 1):
                # Check budget
                if self.credits_used >= self.config.phase1_credits:
                    logger.info("Phase 1 budget exhausted")
                    break

                url = f"{WALLHAVEN_TAGS_LIST_URL}?page={page}"
                logger.info(f"[{page}/{max_pages}] Scraping...")

                # Use HTML parsing for fast, reliable extraction
                html = self.firecrawl.scrape_raw_html(url)
                self.credits_used += 1

                tags = parse_tag_list_html(html)

                if not tags:
                    logger.warning(f"  No tags found - may have reached end")
                    break

                # Add metadata
                for i, tag in enumerate(tags):
                    tag['popularity_rank'] = (page - 1) * 50 + i + 1
                    tag['alias_source'] = 'firecrawl'

                # Store in database
                tag_dicts = [{
                    'tag_id': t['tag_id'],
                    'name': t['name'],
                    'purity': t.get('purity'),
                    'category': t.get('category'),
                    'popularity_rank': t.get('popularity_rank'),
                } for t in tags]
                self.db.upsert_tags_batch(tag_dicts)

                tag_ids = [t['tag_id'] for t in tags]
                self.db.update_tag_scrape_status_batch(tag_ids, list_scraped=True)

                total_tags += len(tags)

                # Update progress
                self.db.update_scrape_job(
                    job_id,
                    items_completed=page,
                    credits_used=self.credits_used,
                    progress_cursor=json.dumps({'next_page': page + 1})
                )

                logger.info(f"  Found {len(tags)} tags (total: {total_tags})")

            self.db.update_scrape_job(job_id, status='completed')
            logger.info(f"Phase 1 complete: {total_tags} tags, {self.credits_used} credits used")
            return total_tags

        except Exception as e:
            logger.exception("Phase 1 failed")
            self.db.update_scrape_job(job_id, status='failed', error_message=str(e))
            raise

    def run_phase2_detail_scrape(self, max_workers: int = None) -> int:
        """Phase 2: Scrape tag detail pages for aliases using concurrent requests.

        Args:
            max_workers: Number of concurrent workers. Defaults to config.concurrency.

        Returns:
            Number of tags with aliases found.
        """
        if max_workers is None:
            max_workers = self.config.concurrency

        logger.info("=" * 60)
        logger.info("PHASE 2: Scraping tag detail pages")
        logger.info(f"Backend: {self.config.backend}")
        logger.info(f"Budget: {self.config.phase2_budget} {'credits' if self.config.backend == 'firecrawl' else 'pages'}")
        logger.info(f"Concurrency: {max_workers} workers")
        logger.info("=" * 60)

        if not self.scraper:
            logger.error("No scraping backend available")
            return 0

        job_id = self.db.create_scrape_job(
            'tag_detail_firecrawl',
            credits_budget=self.config.phase2_budget
        )

        # Get tags needing detail
        tags_to_fetch = self.db.get_tags_needing_detail(limit=self.config.phase2_budget)
        total = len(tags_to_fetch)

        if total == 0:
            logger.info("No tags need detail fetching")
            self.db.update_scrape_job(job_id, status='completed')
            return 0

        self.db.update_scrape_job(job_id, status='in_progress', items_total=total)
        logger.info(f"Found {total} tags needing details")

        aliases_found = 0
        phase2_credits = 0
        processed = 0

        # Build tag lookup by URL
        url_to_tag = {}
        for tag in tags_to_fetch:
            url = WALLHAVEN_TAG_DETAIL_URL.format(tag_id=tag['tag_id'])
            url_to_tag[url] = tag

        # Process in batches - smaller batches to respect rate limits (100 req/min)
        # With 80 req/min target and 5 workers, we process ~80 per minute
        batch_size = 40  # Process 40 at a time, ~30 seconds per batch
        urls = list(url_to_tag.keys())

        try:
            for batch_start in range(0, len(urls), batch_size):
                # Check budget
                if phase2_credits >= self.config.phase2_budget:
                    logger.info("Phase 2 budget exhausted")
                    break

                batch_urls = urls[batch_start:batch_start + batch_size]
                remaining_budget = self.config.phase2_budget - phase2_credits
                batch_urls = batch_urls[:remaining_budget]  # Don't exceed budget

                logger.info(f"[Batch {batch_start // batch_size + 1}] Scraping {len(batch_urls)} tags ({processed}/{total})...")

                # Concurrent scraping with rate limiting to avoid Cloudflare 429s
                # Firecrawl: 18 req/min per worker (API rate limit)
                # Crawl4ai: 15 req/min per worker (4 sec gaps to avoid Cloudflare detection)
                rate_limit = 18 if self.config.backend == "firecrawl" else 15
                results = self.scraper.scrape_batch_concurrent(
                    batch_urls, max_workers=max_workers, rate_limit_per_worker=rate_limit
                )
                phase2_credits += len(batch_urls)
                self.credits_used += len(batch_urls)

                # Process results
                for url, html in results.items():
                    tag = url_to_tag[url]
                    tag_id = tag['tag_id']
                    tag_name = tag['name']
                    processed += 1

                    alias = parse_aliases_from_html(html)
                    if alias:
                        self.db.upsert_tag(
                            tag_id=tag_id,
                            name=tag_name,
                            alias=alias,
                            alias_source='firecrawl'
                        )
                        self.db.update_tag_scrape_status(
                            tag_id,
                            firecrawl_status='success',
                            firecrawl_job_id=job_id
                        )
                        aliases_found += 1
                    else:
                        # Clear any stale alias data
                        self.db.upsert_tag(
                            tag_id=tag_id,
                            name=tag_name,
                            alias='',
                            alias_source='firecrawl'
                        )
                        self.db.update_tag_scrape_status(
                            tag_id,
                            firecrawl_status='no_alias',
                            firecrawl_job_id=job_id
                        )

                self.db.update_scrape_job(
                    job_id,
                    items_completed=processed,
                    credits_used=phase2_credits
                )
                logger.info(f"  Aliases found so far: {aliases_found}")

            self.db.update_scrape_job(job_id, status='completed')
            logger.info(f"Phase 2 complete: {aliases_found} aliases, {phase2_credits} credits used")
            return aliases_found

        except Exception as e:
            logger.exception("Phase 2 failed")
            self.db.update_scrape_job(job_id, status='failed', error_message=str(e))
            raise

    def run_phase3_api_fallback(self, limit: int = 1000) -> int:
        """Phase 3: Use Wallhaven API for remaining tags.

        Args:
            limit: Maximum tags to fetch via API.

        Returns:
            Number of aliases found.
        """
        logger.info("=" * 60)
        logger.info("PHASE 3: API fallback for remaining tags")
        logger.info(f"Rate limit: {self.config.api_rate_limit} req/min")
        logger.info("=" * 60)

        job_id = self.db.create_scrape_job('tag_detail_api')

        # Get tags that need API fallback
        tags_to_fetch = self.db.get_tags_for_api_fallback(limit=limit)

        if not tags_to_fetch:
            # Also get tags never attempted
            tags_to_fetch = self.db.get_tags_needing_detail(limit=limit)

        total = len(tags_to_fetch)
        if total == 0:
            logger.info("No tags need API fallback")
            self.db.update_scrape_job(job_id, status='completed')
            return 0

        self.db.update_scrape_job(job_id, status='in_progress', items_total=total)
        logger.info(f"Found {total} tags to fetch via API")

        delay = 60.0 / self.config.api_rate_limit
        aliases_found = 0

        try:
            for i, tag in enumerate(tags_to_fetch, 1):
                tag_id = tag['tag_id']
                logger.info(f"[{i}/{total}] Fetching tag {tag_id} ({tag['name']})...")

                result = self.wallhaven.get_tag(tag_id)

                if result:
                    alias = result.get("alias")
                    if alias:
                        self.db.upsert_tag(
                            tag_id=tag_id,
                            name=result.get("name", tag['name']),
                            alias=alias,
                            category=result.get("category"),
                            purity=result.get("purity"),
                            alias_source='api'
                        )
                        aliases_found += 1
                        logger.info(f"  Found alias: {alias}")

                    self.db.update_tag_scrape_status(
                        tag_id,
                        api_status='success'
                    )
                else:
                    self.db.update_tag_scrape_status(
                        tag_id,
                        api_status='failed',
                        last_error='Not found or API error'
                    )

                self.db.update_scrape_job(job_id, items_completed=i)

                # Rate limiting
                if i < total:
                    time.sleep(delay)

            self.db.update_scrape_job(job_id, status='completed')
            logger.info(f"Phase 3 complete: {aliases_found} aliases found")
            return aliases_found

        except Exception as e:
            logger.exception("Phase 3 failed")
            self.db.update_scrape_job(job_id, status='failed', error_message=str(e))
            raise

    def print_statistics(self):
        """Print current scrape statistics."""
        stats = self.db.get_scrape_statistics()
        logger.info("")
        logger.info("=" * 60)
        logger.info("SCRAPE STATISTICS")
        logger.info("=" * 60)
        logger.info(f"Total tags:       {stats['total_tags']}")
        logger.info(f"With aliases:     {stats['tags_with_alias']}")
        logger.info(f"Needs detail:     {stats['needs_detail']}")
        logger.info(f"List scraped:     {stats.get('list_scraped', 0)}")
        logger.info(f"Firecrawl:        {stats.get('firecrawl', {})}")
        logger.info(f"API:              {stats.get('api', {})}")
        logger.info(f"Credits used:     {self.credits_used}")


# ============================================================================
# CLI
# ============================================================================

def get_api_keys() -> Tuple[Optional[str], Optional[str]]:
    """Get API keys from environment or config files."""
    # Firecrawl key
    firecrawl_key = os.environ.get("FIRECRAWL_API_KEY")
    if not firecrawl_key:
        key_file = os.path.expanduser("~/.config/firecrawl/api_key")
        if os.path.exists(key_file):
            with open(key_file) as f:
                firecrawl_key = f.read().strip()

    # Wallhaven key
    wallhaven_key = os.environ.get("WALLHAVEN_API_KEY")
    if not wallhaven_key:
        config_path = os.path.expanduser("~/.config/variety/variety.conf")
        if os.path.exists(config_path):
            with open(config_path) as f:
                for line in f:
                    if line.startswith("wallhaven_api_key"):
                        value = line.split("=", 1)[1].strip()
                        if value and value not in ('""', "''"):
                            wallhaven_key = value.strip('"\'')
                            break

    return firecrawl_key, wallhaven_key


def main():
    parser = argparse.ArgumentParser(
        description="Scrape Wallhaven tags using Firecrawl and API fallback"
    )

    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Run smoke test only (uses 3 credits)"
    )
    parser.add_argument(
        "--test-run",
        action="store_true",
        help="Run test with ~20 credits (10 list + 10 detail pages)"
    )
    parser.add_argument(
        "--phase1-only",
        action="store_true",
        help="Run only phase 1 (list pages)"
    )
    parser.add_argument(
        "--phase2-only",
        action="store_true",
        help="Run only phase 2 (detail pages via Firecrawl)"
    )
    parser.add_argument(
        "--phase3-only",
        action="store_true",
        help="Run only phase 3 (API fallback)"
    )
    parser.add_argument(
        "--credits",
        type=int,
        default=3000,
        help="Total Firecrawl credit budget (default: 3000)"
    )
    parser.add_argument(
        "--phase1-credits",
        type=int,
        default=200,
        help="Credits for phase 1 list scraping (default: 200)"
    )
    parser.add_argument(
        "--phase2-credits",
        type=int,
        default=None,
        help="Credits for phase 2 detail scraping (default: remaining budget)"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from previous incomplete job"
    )
    parser.add_argument(
        "--db",
        default=os.path.expanduser("~/.config/variety/smart_selection.db"),
        help="Path to database"
    )
    parser.add_argument(
        "--api-limit",
        type=int,
        default=1000,
        help="Maximum tags to fetch via API in phase 3"
    )
    parser.add_argument(
        "--stats-only",
        action="store_true",
        help="Just print statistics and exit"
    )
    parser.add_argument(
        "--unlimited",
        action="store_true",
        help="Run until credits exhausted (no budget limit)"
    )
    parser.add_argument(
        "--backend",
        choices=["firecrawl", "crawl4ai"],
        default="firecrawl",
        help="Scraping backend to use (default: firecrawl)"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Run browser in headless mode (crawl4ai only, default: True)"
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Run browser with visible window (crawl4ai only)"
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=3,
        help="Number of concurrent workers/browsers (default: 3, safer for Cloudflare)"
    )

    args = parser.parse_args()

    # Handle headless option
    if args.no_headless:
        args.headless = False

    # Handle unlimited mode
    if args.unlimited:
        args.credits = 999999  # Effectively unlimited
        args.phase1_credits = 999999
        args.phase2_credits = 999999

    # Get API keys
    firecrawl_key, wallhaven_key = get_api_keys()

    # Create config
    config = PipelineConfig(
        total_credits=args.credits,
        phase1_credits=args.phase1_credits,
        phase2_credits=args.phase2_credits,
        db_path=args.db,
        firecrawl_api_key=firecrawl_key,
        wallhaven_api_key=wallhaven_key,
        backend=args.backend,
        headless=args.headless,
        concurrency=args.concurrency,
    )

    # Validate config
    if not args.stats_only and not args.phase3_only and args.backend == "firecrawl":
        errors = config.validate()
        if errors:
            for err in errors:
                logger.error(err)
            sys.exit(1)

    # Initialize database
    db = ImageDatabase(args.db)

    try:
        pipeline = TagScrapePipeline(config, db)

        if args.stats_only:
            pipeline.print_statistics()
            return

        if args.smoke_test:
            success = pipeline.run_smoke_test()
            pipeline.print_statistics()
            sys.exit(0 if success else 1)

        if args.test_run:
            pipeline.run_test_run()
            pipeline.print_statistics()
            return

        # Run selected phases
        if args.phase1_only:
            pipeline.run_phase1_list_scrape()
        elif args.phase2_only:
            pipeline.run_phase2_detail_scrape()
        elif args.phase3_only:
            pipeline.run_phase3_api_fallback(limit=args.api_limit)
        else:
            # Run all phases
            pipeline.run_phase1_list_scrape()
            pipeline.run_phase2_detail_scrape()
            pipeline.run_phase3_api_fallback(limit=args.api_limit)

        pipeline.print_statistics()

    finally:
        db.close()


if __name__ == "__main__":
    main()
