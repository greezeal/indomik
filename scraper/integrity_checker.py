"""
Universal Chapter Integrity Checker
Specifically checks if chapters on disk match the live versions.
"""

import os
import json
from datetime import datetime
from typing import List

# Import from the main scraper script
from main_scraper import MainScraper, decode_url, DEFAULT_DATA_DIR


class IntegrityChecker(MainScraper):
    def __init__(self, data_dir: str = DEFAULT_DATA_DIR, delay: float = 1.0):
        print("=" * 50)
        print("INTEGRITY CHECKER - Mode: Check Existing Chapters")
        print("=" * 50)
        super().__init__(data_dir=data_dir, delay=delay, force=True)
        print("Integrity Checker ready.\n")

    def check_comic(self, slug: str):
        """Check all chapters of a specific comic for updates."""
        print(f"\n{'='*50}")
        print(f"CHECKING: {slug}")
        print(f"{'='*50}")
        
        metadata_path = os.path.join(self.comics_dir, slug, "metadata.json")
        if not os.path.exists(metadata_path):
            print(f"Error: Metadata not found for {slug}")
            return

        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
            # Decode b64 chapters
            chapters = metadata.get("chapters", [])
            for ch in chapters:
                ch["url"] = decode_url(ch["url"])

        chapters_dir = os.path.join(self.comics_dir, slug, "chapters")
        if not os.path.exists(chapters_dir):
            print(f"Error: Chapters directory not found for {slug}")
            return

        updated_count = 0
        total_checked = 0

        for ch in chapters:
            chapter_num = ch["chapter"]
            chapter_filename = f"chapter-{chapter_num.replace('.', '-')}.json"
            chapter_path = os.path.join(chapters_dir, chapter_filename)

            if not os.path.exists(chapter_path):
                print(f"  [?] Chapter {chapter_num} missing locally. Skipping.")
                continue

            total_checked += 1
            with open(chapter_path, "r", encoding="utf-8") as f:
                local_data = json.load(f)
                local_img_count = local_data.get("total_images", 0)
                if not local_img_count and "images" in local_data:
                    local_img_count = len(local_data["images"])

            # Fetch live image list
            print(f"  [*] Checking Chapter {chapter_num} (local: {local_img_count} images)...", end="\r")
            live_images = self.scrape_chapter_images(ch["url"])
            live_img_count = len(live_images)

            # Get local images for URL comparison
            local_images = local_data.get("images", [])
            
            # Check for URL changes (even if count is same)
            urls_changed = False
            changed_urls = []
            if live_img_count == local_img_count and live_img_count > 0:
                for i, (local_url, live_url) in enumerate(zip(local_images, live_images)):
                    if local_url != live_url:
                        urls_changed = True
                        changed_urls.append(i + 1)  # 1-indexed for display

            needs_update = False
            update_reason = ""

            if live_img_count > local_img_count:
                needs_update = True
                update_reason = f"MORE IMAGES (Local: {local_img_count} -> Live: {live_img_count})"
            elif urls_changed:
                needs_update = True
                if len(changed_urls) <= 5:
                    update_reason = f"URL CHANGED at position(s): {changed_urls}"
                else:
                    update_reason = f"URL CHANGED at {len(changed_urls)} position(s)"
            elif live_img_count < local_img_count and live_img_count > 0:
                print(f"  [W] Warning: Chapter {chapter_num} has fewer images live ({live_img_count}) than local ({local_img_count}). Skipping update.")

            if needs_update:
                print(f"  [!] UPDATE FOUND: Chapter {chapter_num} - {update_reason}")
                
                updated_data = {
                    "chapter": chapter_num,
                    "title": ch["title"],
                    "url": ch["url"],
                    "date": ch["date"],
                    "scraped_at": datetime.now().isoformat(),
                    "images": live_images,
                    "total_images": live_img_count,
                    "updated_via": "integrity_checker",
                    "update_reason": update_reason
                }
                self.save_chapter(slug, chapter_num, updated_data)
                updated_count += 1

        print(f"\nIntegrity check complete for {slug}.")
        print(f"Checked: {total_checked}, Updated: {updated_count}")

    def check_all(self):
        """Check all comics in the data directory."""
        comics = [d for d in os.listdir(self.comics_dir) if os.path.isdir(os.path.join(self.comics_dir, d))]
        print(f"Found {len(comics)} comics to check.")
        for slug in comics:
            self.check_comic(slug)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Chapter Integrity Checker")
    parser.add_argument("--comic", type=str, help="Slug of the comic to check")
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR, help="Directory where data is stored")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests")
    parser.add_argument("--all", action="store_true", help="Check all comics in data-dir")

    args = parser.parse_args()
    checker = IntegrityChecker(data_dir=args.data_dir, delay=args.delay)

    if args.comic:
        checker.check_comic(args.comic)
    elif args.all:
        checker.check_all()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
