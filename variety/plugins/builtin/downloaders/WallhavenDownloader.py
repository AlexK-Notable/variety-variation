# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
### BEGIN LICENSE
# Copyright (c) 2012, Peter Levi <peterlevi@peterlevi.com>
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranties of
# MERCHANTABILITY, SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR
# PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.
### END LICENSE
import logging
import random
import urllib.parse

import requests

from variety.plugins.builtin.downloaders.WallhavenLegacyDownloader import WallhavenLegacyDownloader
from variety.plugins.downloaders.DefaultDownloader import DefaultDownloader
from variety.Util import Util, _

API_SEARCH = "https://wallhaven.cc/api/v1/search"
API_SAFE_SEARCH_URL = (
    "https://wallhaven.cc/api/v1/search?q=%s&categories=111&purity=100&sorting=favorites&order=desc"
)
WEB_DOMAIN_SEARCH = "https://wallhaven.cc/search"
WALLPAPER_INFO_URL = "https://wallhaven.cc/api/v1/w/%s"

logger = logging.getLogger("variety")

random.seed()


class BadApiKeyException(Exception):
    pass


class WallhavenDownloader(DefaultDownloader):
    def __init__(self, source, location, api_key):
        DefaultDownloader.__init__(self, source=source, config=location)
        self.api_key = api_key
        self.legacy_downloader = WallhavenLegacyDownloader(source, location)
        self.parse_location()

    def get_folder_name(self):
        """
        Override to exclude global exclusion terms from folder name.
        Exclusion terms are part of the search query but should not affect
        the folder name, so 'hdr -"anime girls" -nsfw' uses folder 'wallhaven_hdr'.
        """
        from variety.Util import Util

        if self.config:
            if self.config.startswith(("http://", "https://")):
                # URL-based config - use as-is (no exclusions appended)
                return self.get_source_type() + "_" + Util.convert_to_filename(self.config)
            else:
                # Keyword-based config - strip exclusion terms for folder name
                # Get the actual exclusion terms from options to handle multi-word exclusions
                # Multi-word terms are quoted: -"anime girls", single words: -nsfw
                base_query = self.config
                try:
                    exclusions = self.source.variety.options.get_wallhaven_exclusions()
                    for enabled, term in exclusions:
                        if enabled:
                            # Remove both quoted and unquoted exclusion patterns
                            # Quoted: -"anime girls", Unquoted: -anime
                            if " " in term:
                                base_query = base_query.replace(f'-"{term}"', "")
                            else:
                                base_query = base_query.replace(f"-{term}", "")
                except Exception:
                    # Fallback: strip quoted phrases and single terms starting with '-'
                    import re
                    # Remove -"quoted phrases"
                    base_query = re.sub(r'-"[^"]+"', "", base_query)
                    # Remove -single_terms
                    base_query = " ".join(
                        term for term in base_query.split() if not term.startswith("-")
                    )
                # Clean up extra whitespace
                base_query = " ".join(base_query.split())
                return self.get_source_type() + "_" + Util.convert_to_filename(base_query)
        else:
            return self.get_source_name()

    def update_download_folder(self, global_download_folder):
        target_folder = super().update_download_folder(global_download_folder)
        self.legacy_downloader.target_folder = target_folder
        self.legacy_downloader.state = self.state
        return target_folder

    def parse_location(self):
        if not self.config.startswith(("http://", "https://")):
            # interpret location as keywords
            self.api_url = API_SAFE_SEARCH_URL % self.config
        else:
            # location is an URL, use it
            url = self.config.replace("http://", "https://")

            # Use Wallhaven API
            if url.startswith(API_SEARCH):
                self.api_url = url
            elif url.startswith(WEB_DOMAIN_SEARCH):
                self.api_url = url.replace(WEB_DOMAIN_SEARCH, API_SEARCH)
            elif url.startswith("https://wallhaven.cc/tag"):
                self.api_url = url.replace(
                    "https://wallhaven.cc/tag/", "https://wallhaven.cc/api/v1/search?q=id:"
                )
            else:
                # we'll fallback to WallhavenLegacyDownloader
                self.api_url = None

        # make sure we use the API key, if provided
        if self.api_url and self.api_key and "&apikey=" not in self.api_url:
            self.api_url += "&apikey=" + self.api_key

    def search(self, page=None):
        if not self.api_url:
            return self.legacy_downloader.search(page)

        url = self.api_url
        if page:
            url = url + ("&" if "?" in self.api_url else "?") + "page=" + str(page)
        logger.info(lambda: "Performing wallhaven search: url=%s" % url)
        response = Util.fetch_json(url)
        count = response["meta"]["total"]
        return response, count

    @staticmethod
    def validate(location, api_key):
        logger.info(lambda: "Validating Wallhaven location " + location)
        try:
            _, count = WallhavenDownloader(None, location, api_key).search()
            return count > 0
        except requests.HTTPError as e:
            if api_key and e.response.status_code == 401:
                raise BadApiKeyException()
        except Exception:
            pass

        try:
            return WallhavenLegacyDownloader.validate(location)
        except:
            logger.exception(lambda: "Error while validating Wallhaven search")
            return False

    def download_queue_item(self, queue_item):
        if not self.api_url:
            return self.legacy_downloader.download_queue_item(queue_item)

        wallpaper_url = queue_item["url"]
        logger.info(lambda: "Wallpaper URL: " + wallpaper_url)

        src_url = queue_item["path"]
        logger.info(lambda: "Image src URL: " + src_url)

        extra_metadata = {}

        # Fetch detailed wallpaper info from API
        wallpaper_info = None
        try:
            wallpaper_info = Util.fetch_json(
                WALLPAPER_INFO_URL % urllib.parse.quote(queue_item["id"])
            )
            data = wallpaper_info["data"]

            # Extract tag names for XMP keywords (backwards compatible)
            extra_metadata["keywords"] = [tag["name"] for tag in data.get("tags", [])]

            # Parse created_at to Unix timestamp
            uploaded_at = None
            created_at = data.get("created_at")
            if created_at:
                try:
                    from datetime import datetime
                    # Wallhaven format: "2023-01-15 12:34:56"
                    dt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
                    uploaded_at = int(dt.timestamp())
                except (ValueError, TypeError):
                    pass

            # Store rich metadata in extraData for JSON serialization
            # This gets properly serialized to XMP and can be read back
            uploader = data.get("uploader", {})
            extra_metadata["extraData"] = {
                "wallhaven": {
                    # Full tag data (id, name, alias, category, purity)
                    "tags": [
                        {
                            "tag_id": tag["id"],
                            "name": tag["name"],
                            "alias": tag.get("alias"),
                            "category": tag.get("category"),
                            "purity": tag.get("purity"),
                        }
                        for tag in data.get("tags", [])
                    ],
                    # Source-provided color palette
                    "colors": data.get("colors", []),
                    # Content classification
                    "category": data.get("category"),  # general/anime/people
                    "purity": data.get("purity"),  # sfw/sketchy/nsfw
                    # Attribution
                    "uploader": uploader.get("username"),
                    "source": data.get("source"),  # Original source URL
                    # Popularity metrics
                    "views": data.get("views"),
                    "favorites": data.get("favorites"),
                    # Timestamp
                    "uploaded_at": uploaded_at,
                }
            }

        except Exception as e:
            logger.warning(lambda: f"Failed to fetch Wallhaven metadata: {e}")

        # Handle purity/SFW rating
        try:
            purity = queue_item.get("purity") or (wallpaper_info["data"]["purity"] if wallpaper_info else None)
            if purity:
                sfw_rating = {"sfw": 100, "sketchy": 50, "nsfw": 0}.get(purity, 50)
                extra_metadata["sfwRating"] = sfw_rating

                if self.is_safe_mode_enabled() and sfw_rating < 100:
                    logger.info(
                        lambda: "Skipping non-safe download from Wallhaven. "
                        "Is the source %s suitable for Safe mode?" % self.config
                    )
                    return None
        except Exception:
            pass

        return self.save_locally(wallpaper_url, src_url, extra_metadata=extra_metadata)

    def fill_queue(self):
        if not self.api_url:
            return self.legacy_downloader.fill_queue()

        queue = []

        not_random = "sorting=random" not in self.api_url
        if not_random:
            s, count = self.search()
            pages = min(count, 1000) // int(s["meta"]["per_page"]) + 1
            page = random.randint(1, pages)
            logger.info(lambda: "%s wallpapers in result, using page %s" % (count, page))
            s, _ = self.search(page=page)
        else:
            s, _ = self.search()

        results = s["data"]
        for result in results:
            try:
                p = result["resolution"].split("x")
                width = p[0]
                height = p[1]
                if self.is_size_inadequate(width, height):
                    continue
            except Exception:
                # missing or unparseable resolution - consider ok
                pass

            queue.append(result)

        random.shuffle(queue)

        if not_random and len(queue) >= 20:
            queue = queue[: len(queue) // 2]
            # only use randomly half the images from the page -
            # if we ever hit that same page again, we'll still have what to download

        return queue
