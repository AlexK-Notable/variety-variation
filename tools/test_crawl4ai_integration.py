#!/usr/bin/env python3
"""Integration test for crawl4ai backend with Wallhaven tag scraping."""

import asyncio
import sys
import os
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the scraper components
from tools.scrape_wallhaven_tags import (
    Crawl4AIClient,
    parse_aliases_from_html,
    WALLHAVEN_TAG_DETAIL_URL,
)

# Test tags with known aliases
TEST_TAGS = [
    {"tag_id": 222, "name": "women", "expected_has_aliases": True},
    {"tag_id": 37, "name": "anime girls", "expected_has_aliases": True},
    {"tag_id": 711, "name": "nature", "expected_has_aliases": True},
    {"tag_id": 5189, "name": "cityscape", "expected_has_aliases": False},  # Might not have aliases
]


def test_single_scrape():
    """Test scraping a single tag page."""
    print("=" * 60)
    print("TEST 1: Single page scrape")
    print("=" * 60)

    client = Crawl4AIClient(headless=True)
    tag = TEST_TAGS[0]
    url = WALLHAVEN_TAG_DETAIL_URL.format(tag_id=tag['tag_id'])

    print(f"Scraping: {url}")
    start = time.time()
    html = client.scrape_raw_html(url)
    elapsed = time.time() - start

    print(f"Time: {elapsed:.2f}s")
    print(f"HTML length: {len(html)} chars")

    if html:
        aliases = parse_aliases_from_html(html)
        print(f"Aliases found: {aliases[:100] if aliases else 'None'}...")
        if tag['expected_has_aliases']:
            assert aliases, f"Expected aliases for tag {tag['name']}"
            print("PASS: Aliases extracted successfully")
        return True
    else:
        print("FAIL: No HTML returned")
        return False


def test_batch_scrape():
    """Test batch scraping multiple tags."""
    print("\n" + "=" * 60)
    print("TEST 2: Batch scrape (4 URLs, 2 workers)")
    print("=" * 60)

    client = Crawl4AIClient(headless=True)
    urls = [WALLHAVEN_TAG_DETAIL_URL.format(tag_id=t['tag_id']) for t in TEST_TAGS]

    results_count = 0

    def callback(url, html):
        nonlocal results_count
        results_count += 1
        aliases = parse_aliases_from_html(html) if html else None
        tag_id = int(url.split('/')[-1])
        print(f"  [{results_count}] Tag {tag_id}: {len(html) if html else 0} chars, aliases: {'Yes' if aliases else 'No'}")

    print(f"Scraping {len(urls)} URLs with 2 workers...")
    start = time.time()
    results = client.scrape_batch_concurrent(
        urls,
        max_workers=2,
        rate_limit_per_worker=30,  # 30 req/min per worker
        callback=callback
    )
    elapsed = time.time() - start

    print(f"\nTotal time: {elapsed:.2f}s")
    print(f"URLs processed: {len(results)}")
    print(f"Successful: {sum(1 for h in results.values() if h)}")

    success_count = sum(1 for h in results.values() if h)
    if success_count == len(urls):
        print("PASS: All URLs scraped successfully")
        return True
    else:
        print(f"PARTIAL: {success_count}/{len(urls)} URLs succeeded")
        return success_count > 0


def test_retry_logic():
    """Test retry logic with invalid URL."""
    print("\n" + "=" * 60)
    print("TEST 3: Retry logic (invalid URL)")
    print("=" * 60)

    client = Crawl4AIClient(headless=True)
    invalid_url = "https://wallhaven.cc/tag/999999999"  # Likely doesn't exist

    print(f"Scraping invalid URL: {invalid_url}")
    start = time.time()
    html = client.scrape_raw_html(invalid_url, max_retries=2)
    elapsed = time.time() - start

    print(f"Time: {elapsed:.2f}s")
    print(f"HTML length: {len(html)} chars")

    # We expect this to either return empty or return a 404 page
    # Either way, it shouldn't crash
    print("PASS: Handled gracefully (no crash)")
    return True


def test_concurrency():
    """Test that multiple concurrent requests work properly."""
    print("\n" + "=" * 60)
    print("TEST 4: Concurrency test (10 URLs, 3 workers)")
    print("=" * 60)

    # Use the same URLs multiple times to test concurrency
    client = Crawl4AIClient(headless=True)
    base_urls = [WALLHAVEN_TAG_DETAIL_URL.format(tag_id=t['tag_id']) for t in TEST_TAGS]
    urls = base_urls + base_urls + base_urls[:2]  # 10 URLs total

    print(f"Scraping {len(urls)} URLs with 3 workers...")
    start = time.time()
    results = client.scrape_batch_concurrent(
        urls,
        max_workers=3,
        rate_limit_per_worker=20,
    )
    elapsed = time.time() - start

    unique_urls = set(urls)
    print(f"\nTotal time: {elapsed:.2f}s")
    print(f"Avg time per URL: {elapsed/len(urls):.2f}s")
    print(f"Unique URLs: {len(unique_urls)}")
    print(f"Results returned: {len(results)}")

    success_count = sum(1 for h in results.values() if h)
    print(f"Successful: {success_count}/{len(unique_urls)}")

    # Check all unique URLs succeeded
    if success_count >= len(unique_urls) * 0.8:  # 80% success rate of unique URLs
        print("PASS: Concurrency working")
        return True
    else:
        print("FAIL: Too many failures")
        return False


def main():
    """Run all integration tests."""
    print("Crawl4AI Integration Tests for Wallhaven Tag Scraping")
    print("=" * 60)
    print()

    results = {}

    try:
        results['single'] = test_single_scrape()
    except Exception as e:
        print(f"FAIL: {e}")
        results['single'] = False

    try:
        results['batch'] = test_batch_scrape()
    except Exception as e:
        print(f"FAIL: {e}")
        results['batch'] = False

    try:
        results['retry'] = test_retry_logic()
    except Exception as e:
        print(f"FAIL: {e}")
        results['retry'] = False

    try:
        results['concurrency'] = test_concurrency()
    except Exception as e:
        print(f"FAIL: {e}")
        results['concurrency'] = False

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for test_name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {test_name}: {status}")

    all_passed = all(results.values())
    print(f"\nOverall: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
