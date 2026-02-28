#!/usr/bin/env python3
"""Test crawl4ai with Ollama LLM extraction for Wallhaven tag aliases."""

import asyncio
import sys
import os
import json

# Add crawl4ai to path
crawl4ai_path = os.path.expanduser("~/repos/crawl4ai")
venv_site_packages = os.path.join(crawl4ai_path, ".venv", "lib", "python3.12", "site-packages")
if not os.path.exists(venv_site_packages):
    venv_site_packages = os.path.join(crawl4ai_path, ".venv", "lib", "python3.11", "site-packages")
if os.path.exists(venv_site_packages):
    sys.path.insert(0, venv_site_packages)
sys.path.insert(0, crawl4ai_path)

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, LLMConfig
from crawl4ai.extraction_strategy import LLMExtractionStrategy

# Wallhaven tag page to test
TEST_URL = "https://wallhaven.cc/tag/222"  # "women" tag - has aliases

# Ollama model configuration
OLLAMA_MODEL = "nemo-12b-abl"
# Don't set base_url - litellm handles Ollama connection automatically
OLLAMA_BASE_URL = None  # "http://localhost:11434" for custom Ollama host

# Extraction instruction - focused and specific
EXTRACTION_INSTRUCTION = """Extract the tag aliases from this Wallhaven tag page.

Look for a section labeled "aliases" (may be collapsed/hidden). It contains alternative names for this tag, separated by commas.

Return a JSON object with exactly this structure:
{
    "tag_name": "the main tag name shown on the page",
    "aliases": "comma-separated string of all aliases, or null if none found",
    "found_aliases_section": true/false (whether you found an aliases section)
}

IMPORTANT:
- Only extract from the aliases section, not from other parts of the page
- If no aliases section exists, set aliases to null
- Keep the aliases as a single comma-separated string, exactly as shown on the page
"""

# Pydantic-style schema for structured output
EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "tag_name": {
            "type": "string",
            "description": "The main tag name"
        },
        "aliases": {
            "type": ["string", "null"],
            "description": "Comma-separated aliases or null if none"
        },
        "found_aliases_section": {
            "type": "boolean",
            "description": "Whether an aliases section was found"
        }
    },
    "required": ["tag_name", "aliases", "found_aliases_section"]
}


async def test_raw_html_extraction():
    """Test 1: Just fetch raw HTML and check for aliases div."""
    print("=" * 60)
    print("TEST 1: Raw HTML extraction (no LLM)")
    print("=" * 60)

    browser_config = BrowserConfig(headless=True)

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url=TEST_URL)

        if result.success:
            print(f"URL: {result.url}")
            print(f"HTML length: {len(result.html)} chars")

            # Check for aliases div
            if 'id="aliases"' in result.html:
                print("Found aliases div in HTML!")
                # Extract the aliases section
                import re
                pattern = r'<div[^>]*id=["\']aliases["\'][^>]*>.*?<h3>[^<]*</h3>([^<]+)'
                match = re.search(pattern, result.html, re.IGNORECASE | re.DOTALL)
                if match:
                    aliases = match.group(1).strip()
                    print(f"Aliases found: {aliases[:200]}...")
                else:
                    print("Could not extract aliases text from div")
            else:
                print("No aliases div found in HTML")

            return True
        else:
            print(f"Failed: {result.error_message}")
            return False


async def test_llm_extraction():
    """Test 2: Use LLM to extract structured data."""
    print("\n" + "=" * 60)
    print("TEST 2: LLM extraction with Ollama")
    print("=" * 60)

    # Configure LLM
    llm_kwargs = {
        "provider": f"ollama/{OLLAMA_MODEL}",
        "temperature": 0.1,  # Low temperature for consistent extraction
        "max_tokens": 500,
    }
    if OLLAMA_BASE_URL:
        llm_kwargs["base_url"] = OLLAMA_BASE_URL
    llm_config = LLMConfig(**llm_kwargs)

    # Create extraction strategy
    extraction_strategy = LLMExtractionStrategy(
        llm_config=llm_config,
        instruction=EXTRACTION_INSTRUCTION,
        schema=EXTRACTION_SCHEMA,
        extraction_type="schema",
        verbose=True,
    )

    browser_config = BrowserConfig(headless=True)
    run_config = CrawlerRunConfig(
        extraction_strategy=extraction_strategy,
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url=TEST_URL, config=run_config)

        if result.success:
            print(f"URL: {result.url}")
            print(f"Extracted content type: {type(result.extracted_content)}")
            print(f"Extracted content:")

            if result.extracted_content:
                try:
                    # Parse the extracted content
                    data = json.loads(result.extracted_content)
                    print(json.dumps(data, indent=2))
                except json.JSONDecodeError as e:
                    print(f"Raw content (not valid JSON): {result.extracted_content[:500]}")
                    print(f"JSON error: {e}")
            else:
                print("No extracted content")

            return True
        else:
            print(f"Failed: {result.error_message}")
            return False


async def test_simple_llm():
    """Test 3: Simpler LLM test without schema."""
    print("\n" + "=" * 60)
    print("TEST 3: Simple LLM extraction (no schema)")
    print("=" * 60)

    # Simpler instruction
    simple_instruction = """Find and extract the tag aliases from this page.

Look for a section or div labeled "aliases" that contains alternative names for the tag.
Return the aliases as a comma-separated string.
If no aliases section exists, return "NO_ALIASES_FOUND".
"""

    llm_kwargs = {
        "provider": f"ollama/{OLLAMA_MODEL}",
        "temperature": 0.1,
        "max_tokens": 300,
    }
    if OLLAMA_BASE_URL:
        llm_kwargs["base_url"] = OLLAMA_BASE_URL
    llm_config = LLMConfig(**llm_kwargs)

    extraction_strategy = LLMExtractionStrategy(
        llm_config=llm_config,
        instruction=simple_instruction,
        extraction_type="block",
        verbose=True,
    )

    browser_config = BrowserConfig(headless=True)
    run_config = CrawlerRunConfig(
        extraction_strategy=extraction_strategy,
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url=TEST_URL, config=run_config)

        if result.success:
            print(f"URL: {result.url}")
            print(f"Extracted content:")
            print(result.extracted_content[:1000] if result.extracted_content else "None")
            return True
        else:
            print(f"Failed: {result.error_message}")
            return False


async def main():
    """Run all tests."""
    print("Testing crawl4ai with Ollama for Wallhaven tag extraction")
    print(f"Model: {OLLAMA_MODEL}")
    print(f"Test URL: {TEST_URL}")
    print()

    # Test 1: Raw HTML
    test1_ok = await test_raw_html_extraction()

    # Test 2: LLM with schema
    test2_ok = await test_llm_extraction()

    # Test 3: Simple LLM
    test3_ok = await test_simple_llm()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Test 1 (Raw HTML): {'PASS' if test1_ok else 'FAIL'}")
    print(f"Test 2 (LLM + Schema): {'PASS' if test2_ok else 'FAIL'}")
    print(f"Test 3 (Simple LLM): {'PASS' if test3_ok else 'FAIL'}")


if __name__ == "__main__":
    asyncio.run(main())
