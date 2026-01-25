"""
Universal Comic Scraper
Features:
- Scrapes all comics from manga list
- Gets comic metadata (title, author, genres, synopsis, etc.)
- Gets chapter list with URLs
- Gets chapter images
- Saves data in organized JSON structure
"""

import os
import json
import time
import re
import base64
from curl_cffi import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from datetime import datetime
from typing import Optional, Dict, List, Any


SENSITIVE_DOMAINS = [base64.b64decode("a29taWtpbmRv").decode()]


def encode_url(url: str) -> str:
    """Encode URL to base64 if it contains sensitive domain."""
    if not url:
        return url
    for domain in SENSITIVE_DOMAINS:
        if domain in url.lower():
            return "b64:" + base64.b64encode(url.encode()).decode()
    return url


def decode_url(encoded: str) -> str:
    """Decode base64 URL back to original."""
    if not encoded:
        return encoded
    if encoded.startswith("b64:"):
        return base64.b64decode(encoded[4:]).decode()
    return encoded


def encode_urls_in_data(data: any) -> any:
    """Recursively encode all URLs in a data structure."""
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            if key in ["url", "cover_url"] or key.endswith("_url"):
                result[key] = encode_url(value) if isinstance(value, str) else value
            else:
                result[key] = encode_urls_in_data(value)
        return result
    elif isinstance(data, list):
        return [encode_urls_in_data(item) for item in data]
    else:
        return data


# Calculate default data directory relative to script location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "data"))


class MainScraper:
    BASE_URL = base64.b64decode("aHR0cHM6Ly9rb21pa2luZG8uY2g=").decode()
    LIST_URL = f"{BASE_URL}/komik-terbaru/"
    
    def __init__(self, data_dir: str = DEFAULT_DATA_DIR, delay: float = 1.0, force: bool = False):
        """
        Initialize the scraper.
        """
        print(f"Initializing Scraper (data_dir: {data_dir})")
        self.data_dir = data_dir
        self.delay = delay
        self.force = force
        print("Configuring browser impersonation...")
        self.session = requests.Session(impersonate="chrome120")
        print("Scraper initialized successfully.")
        
        # We rely more on curl_cffi's impersonate than manual headers to avoid inconsistencies
        self.session.headers.update({
            "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.google.com/"
        })
        
        # Create directories
        self.comics_dir = os.path.join(data_dir, "comics")
        os.makedirs(self.comics_dir, exist_ok=True)
        
        # Load or create index
        self.index_path = os.path.join(data_dir, "index.json")
        self.index = self._load_index()
    
    def _load_index(self) -> Dict[str, Any]:
        """Load existing index or create new one."""
        if os.path.exists(self.index_path):
            with open(self.index_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {
            "last_updated": None,
            "total_comics": 0,
            "comics": []
        }
    
    def _save_index(self):
        """Save index to file."""
        self.index["last_updated"] = datetime.now().isoformat()
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(self.index, f, ensure_ascii=False, indent=2)

    def warm_up(self):
        """
        Perform a warm-up request to the home page to establish session/cookies.
        Includes retries and alternative impersonation if needed.
        """
        targets = [
            {"impersonate": "chrome120", "url": self.BASE_URL},
            {"impersonate": "safari15", "url": self.BASE_URL},
        ]
        
        for attempt, target in enumerate(targets, 1):
            print(f"Performing warm-up request (Attempt {attempt}, {target['impersonate']})...")
            try:
                self.session = requests.Session(impersonate=target['impersonate'])
                self.session.headers.update({
                    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Referer": "https://www.google.com/"
                })
                
                response = self.session.get(target['url'], timeout=30)
                
                if response.status_code == 200:
                    print("Warm-up successful.")
                    self.session.headers.update({"Referer": self.BASE_URL})
                    return True
                else:
                    print(f"Warm-up returned status: {response.status_code}")
                    if "Just a moment" in response.text:
                        print("Cloudflare 'Just a moment' challenge detected.")
                    
                time.sleep(self.delay * 2)
            except Exception as e:
                print(f"Warm-up attempt {attempt} failed: {e}")
                
        return False
    
    def _fetch(self, url: str) -> Optional[BeautifulSoup]:
        """Fetch a URL and return BeautifulSoup object."""
        try:
            time.sleep(self.delay)
            response = self.session.get(url, timeout=30)
            
            if response.status_code == 403:
                print(f"Access Denied (403) for {url}. The site may be blocking this server's IP.")
                # Log a snippet of the response to diagnose Cloudflare/blocking
                snippet = response.text[:500].replace('\n', ' ')
                print(f"Response snippet: {snippet}")
                return None
                
            response.raise_for_status()
            return BeautifulSoup(response.text, "html.parser")
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None
    
    def _slugify(self, text: str) -> str:
        """Convert text to slug format."""
        text = text.lower().strip()
        text = re.sub(r'[^\w\s-]', '', text)
        text = re.sub(r'[-\s]+', '-', text)
        return text
    
    def get_total_pages(self) -> int:
        """Get total number of pages in the manga list."""
        soup = self._fetch(self.LIST_URL)
        if not soup:
            return 1
        
        pagination = soup.select(".pagination a.page-numbers")
        if pagination:
            # Find the last page number (before "Berikutnya")
            page_nums = []
            for a in pagination:
                text = a.get_text().strip()
                if text.isdigit():
                    page_nums.append(int(text))
            return max(page_nums) if page_nums else 1
        return 1
    
    def scrape_comic_list(self, page: int = 1) -> List[Dict[str, Any]]:
        """
        Scrape comic list from a specific page.
        
        Args:
            page: Page number to scrape
            
        Returns:
            List of comic basic info (title, url, cover, type, rating)
        """
        url = f"{self.LIST_URL}page/{page}/" if page > 1 else self.LIST_URL
        soup = self._fetch(url)
        
        if not soup:
            return []
        
        comics = []
        posts = soup.select(".animepost")
        
        for post in posts:
            try:
                # Get link and title
                link_elem = post.select_one("a[href]")
                if not link_elem:
                    continue
                
                comic_url = link_elem.get("href", "")
                title = link_elem.get("title", "").replace("Komik ", "")
                
                # Get cover image
                img_elem = post.select_one("img")
                cover_url = img_elem.get("src", "") if img_elem else ""
                
                # Get type (Manga/Manhwa/Manhua)
                type_elem = post.select_one(".typeflag")
                comic_type = ""
                if type_elem:
                    classes = type_elem.get("class", [])
                    for cls in classes:
                        if cls in ["Manga", "Manhwa", "Manhua"]:
                            comic_type = cls
                            break
                
                # Check if colored
                is_colored = bool(post.select_one(".warnalabel"))
                
                # Get rating
                rating_elem = post.select_one(".rating i")
                rating = float(rating_elem.get_text().strip()) if rating_elem else 0.0
                
                # Extract slug from URL
                slug = comic_url.rstrip("/").split("/")[-1]
                
                comics.append({
                    "slug": slug,
                    "title": title,
                    "url": comic_url,
                    "cover_url": cover_url,
                    "type": comic_type,
                    "is_colored": is_colored,
                    "rating": rating
                })
                
            except Exception as e:
                print(f"Error parsing comic post: {e}")
                continue
        
        return comics
    
    def scrape_comic_detail(self, comic_url: str) -> Optional[Dict[str, Any]]:
        """
        Scrape detailed information about a comic.
        
        Args:
            comic_url: URL of the comic detail page
            
        Returns:
            Dictionary with comic metadata
        """
        soup = self._fetch(comic_url)
        if not soup:
            return None
        
        metadata = {
            "url": comic_url,
            "scraped_at": datetime.now().isoformat()
        }
        
        try:
            # Get title from page
            title_elem = soup.select_one(".entry-title")
            if title_elem:
                metadata["title"] = title_elem.get_text().strip().replace("Komik ", "")
            
            # Parse info section
            info_section = soup.select_one(".spe")
            if info_section:
                spans = info_section.select("span")
                for span in spans:
                    text = span.get_text().strip()
                    
                    if "Judul Alternatif:" in text:
                        metadata["alternative_titles"] = text.replace("Judul Alternatif:", "").strip()
                    elif "Status:" in text:
                        metadata["status"] = text.replace("Status:", "").strip()
                    elif "Pengarang:" in text:
                        metadata["author"] = text.replace("Pengarang:", "").strip()
                    elif "Ilustrator:" in text:
                        metadata["illustrator"] = text.replace("Ilustrator:", "").strip()
                    elif "Grafis:" in text:
                        link = span.select_one("a")
                        metadata["demographic"] = link.get_text().strip() if link else ""
                    elif "Tema:" in text:
                        themes = [a.get_text().strip() for a in span.select("a")]
                        metadata["themes"] = themes
                    elif "Jenis Komik:" in text:
                        link = span.select_one("a")
                        metadata["type"] = link.get_text().strip() if link else ""
            
            # Get genres
            genre_section = soup.select_one(".genre-info")
            if genre_section:
                genres = [a.get_text().strip() for a in genre_section.select("a")]
                metadata["genres"] = genres
            
            # Get cover
            thumb = soup.select_one(".thumb img")
            if thumb:
                metadata["cover_url"] = thumb.get("src", "")
            
            # Get rating
            rating_elem = soup.select_one(".ratingmanga i[itemprop='ratingValue']")
            if rating_elem:
                metadata["rating"] = float(rating_elem.get_text().strip())
            
            # Get synopsis
            synopsis_elem = soup.select_one(".entry-content-single p")
            if synopsis_elem:
                metadata["synopsis"] = synopsis_elem.get_text().strip()
            
            # Get chapters
            chapters = []
            chapter_list = soup.select(".eps_lst ul li")
            for li in chapter_list:
                link = li.select_one(".lchx a")
                date_elem = li.select_one(".dt a")
                
                if link:
                    chapter_num = ""
                    chapter_tag = link.select_one("chapter")
                    if chapter_tag:
                        chapter_num = chapter_tag.get_text().strip()
                    
                    chapters.append({
                        "chapter": chapter_num,
                        "title": link.get("title", ""),
                        "url": link.get("href", ""),
                        "date": date_elem.get_text().strip() if date_elem else ""
                    })
            
            metadata["chapters"] = chapters
            metadata["total_chapters"] = len(chapters)
            
        except Exception as e:
            print(f"Error parsing comic detail: {e}")
        
        return metadata
    
    def scrape_chapter_images(self, chapter_url: str) -> List[str]:
        """
        Scrape image URLs from a chapter page.
        
        Args:
            chapter_url: URL of the chapter page
            
        Returns:
            List of image URLs
        """
        soup = self._fetch(chapter_url)
        if not soup:
            return []
        
        images = []
        img_container = soup.select_one("#chimg-auh")
        
        if img_container:
            for img in img_container.select("img"):
                src = img.get("src", "")
                if src and src not in images:
                    images.append(src)
        
        return images
    
    def save_comic(self, comic_data: Dict[str, Any]):
        """Save comic data to file."""
        slug = comic_data.get("slug") or self._slugify(comic_data.get("title", "unknown"))
        comic_dir = os.path.join(self.comics_dir, slug)
        os.makedirs(comic_dir, exist_ok=True)
        
        # Encode sensitive URLs before saving
        encoded_data = encode_urls_in_data(comic_data)
        
        # Save metadata
        metadata_path = os.path.join(comic_dir, "metadata.json")
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(encoded_data, f, ensure_ascii=False, indent=2)
        
        # Create chapters directory
        chapters_dir = os.path.join(comic_dir, "chapters")
        os.makedirs(chapters_dir, exist_ok=True)
        
        return comic_dir
    
    def save_chapter(self, comic_slug: str, chapter_num: str, chapter_data: Dict[str, Any]):
        """Save chapter data to file."""
        chapters_dir = os.path.join(self.comics_dir, comic_slug, "chapters")
        os.makedirs(chapters_dir, exist_ok=True)
        
        # Normalize chapter number for filename
        chapter_filename = f"chapter-{chapter_num.replace('.', '-')}.json"
        chapter_path = os.path.join(chapters_dir, chapter_filename)
        
        # Encode sensitive URLs before saving
        encoded_data = encode_urls_in_data(chapter_data)
        
        with open(chapter_path, "w", encoding="utf-8") as f:
            json.dump(encoded_data, f, ensure_ascii=False, indent=2)
    
    def scrape_all(self, start_page: int = 1, end_page: Optional[int] = None, 
                   scrape_chapters: bool = False, scrape_images: bool = False):
        """
        Scrape all comics from the website.
        
        Args:
            start_page: Starting page number
            end_page: Ending page number (None for all pages)
            scrape_chapters: Whether to scrape individual chapters
            scrape_images: Whether to scrape chapter images (requires scrape_chapters=True)
        """
        # Get total pages if not specified
        if end_page is None:
            end_page = self.get_total_pages()
            print(f"Total pages found: {end_page}")
        
        # Perform session warm-up
        self.warm_up()
        
        all_comics = []
        
        for page in range(start_page, end_page + 1):
            print(f"\n--- Scraping page {page}/{end_page} ---")
            
            comics = self.scrape_comic_list(page)
            print(f"Found {len(comics)} comics on page {page}")
            
            for i, comic in enumerate(comics, 1):
                # Use existing metadata if it exists and not in force mode
                slug = comic["slug"]
                metadata_path = os.path.join(self.comics_dir, slug, "metadata.json")
                detail = None
                
                if not self.force and os.path.exists(metadata_path):
                    with open(metadata_path, "r", encoding="utf-8") as f:
                        saved_data = json.load(f)
                        detail = {k: decode_url(v) if isinstance(v, str) and k in ["url", "cover_url"] else v 
                                 for k, v in saved_data.items()}
                        # Deep decode for chapters
                        if "chapters" in detail:
                            for ch in detail["chapters"]:
                                if "url" in ch:
                                    ch["url"] = decode_url(ch["url"])
                    print(f"  [{i}/{len(comics)}] Using existing metadata for: {comic['title']}")
                else:
                    print(f"  [{i}/{len(comics)}] Processing: {comic['title']}")
                    detail = self.scrape_comic_detail(comic["url"])
                    if detail:
                        # Merge basic info with detail
                        comic.update(detail)
                    # Save comic
                    self.save_comic(comic)
                
                # Scrape chapters if requested
                if scrape_chapters and detail and "chapters" in detail:
                    for ch in detail["chapters"]:
                        chapter_num = ch["chapter"]
                        chapter_filename = f"chapter-{chapter_num.replace('.', '-')}.json"
                        chapter_path = os.path.join(self.comics_dir, slug, "chapters", chapter_filename)
                        
                        existing_chapter = None
                        if os.path.exists(chapter_path):
                            with open(chapter_path, "r", encoding="utf-8") as f:
                                existing_chapter = json.load(f)
                        
                        # Only scrape if forced OR doesn't exist OR need images but they are missing
                        if self.force or not existing_chapter or (scrape_images and "images" not in existing_chapter):
                            chapter_data = {
                                "chapter": ch["chapter"],
                                "title": ch["title"],
                                "url": ch["url"],
                                "date": ch["date"],
                                "scraped_at": datetime.now().isoformat()
                            }
                            
                            if scrape_images:
                                print(f"    - Scraping images for chapter {ch['chapter']}")
                                images = self.scrape_chapter_images(ch["url"])
                                chapter_data["images"] = images
                                chapter_data["total_images"] = len(images)
                            
                            self.save_chapter(slug, ch["chapter"], chapter_data)
                        else:
                            print(f"    - Skipping chapter {ch['chapter']} (already exists)")
                
                all_comics.append({
                    "slug": slug,
                    "title": comic.get("title", ""),
                    "type": comic.get("type", ""),
                    "status": comic.get("status", ""),
                    "rating": comic.get("rating", 0),
                    "total_chapters": comic.get("total_chapters", 0)
                })
        
        # Update index
        self.index["comics"] = all_comics
        self.index["total_comics"] = len(all_comics)
        self._save_index()
        
        print(f"\n=== Scraping complete! ===")
        print(f"Total comics scraped: {len(all_comics)}")
        print(f"Data saved to: {self.data_dir}")


def main():
    print("Scraper script started.")
    import argparse
    
    parser = argparse.ArgumentParser(description="Universal Comic Scraper")
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR, help="Directory to save data")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests in seconds")
    parser.add_argument("--start-page", type=int, default=1, help="Starting page number")
    parser.add_argument("--end-page", type=int, default=None, help="Ending page number (default: all)")
    parser.add_argument("--chapters", action="store_true", help="Also scrape chapter details")
    parser.add_argument("--images", action="store_true", help="Also scrape chapter images (requires --chapters)")
    parser.add_argument("--comic", type=str, default=None, help="Scrape a specific comic by URL or slug")
    parser.add_argument("--force", action="store_true", help="Force re-scrape even if data exists")
    
    args = parser.parse_args()
    
    scraper = MainScraper(data_dir=args.data_dir, delay=args.delay, force=args.force)
    
    if args.comic:
        # Perform session warm-up
        scraper.warm_up()
        
        # Scrape single comic
        if not args.comic.startswith("http"):
            comic_url = f"{MainScraper.BASE_URL}/komik/{args.comic}/"
        else:
            comic_url = args.comic
        
        # Extract slug from URL
        slug = comic_url.rstrip("/").split("/")[-1]
        metadata_path = os.path.join(scraper.comics_dir, slug, "metadata.json")
        
        detail = None
        if not args.force and os.path.exists(metadata_path):
            with open(metadata_path, "r", encoding="utf-8") as f:
                saved_data = json.load(f)
                detail = {k: decode_url(v) if isinstance(v, str) and k in ["url", "cover_url"] else v 
                         for k, v in saved_data.items()}
                # Deep decode for chapters
                if "chapters" in detail:
                    for ch in detail["chapters"]:
                        if "url" in ch:
                            ch["url"] = decode_url(ch["url"])
            print(f"Using existing metadata for: {slug}")
        else:
            print(f"Scraping single comic: {comic_url}")
            detail = scraper.scrape_comic_detail(comic_url)
            if detail:
                detail["slug"] = slug
                scraper.save_comic(detail)
        
        if detail:
            if args.chapters or args.images:
                for ch in detail.get("chapters", []):
                    # Get original URL (before it was encoded)
                    chapter_url = ch["url"]
                    chapter_num = ch["chapter"]
                    chapter_filename = f"chapter-{chapter_num.replace('.', '-')}.json"
                    chapter_path = os.path.join(scraper.comics_dir, slug, "chapters", chapter_filename)
                    
                    existing_chapter = None
                    if os.path.exists(chapter_path):
                        with open(chapter_path, "r", encoding="utf-8") as f:
                            existing_chapter = json.load(f)
                    
                    if args.force or not existing_chapter or (args.images and "images" not in existing_chapter):
                        chapter_data = {
                            "chapter": ch["chapter"],
                            "title": ch["title"],
                            "url": chapter_url,
                            "date": ch["date"],
                            "scraped_at": datetime.now().isoformat()
                        }
                        
                        if args.images:
                            print(f"  Scraping images for chapter {ch['chapter']}")
                            images = scraper.scrape_chapter_images(chapter_url)
                            chapter_data["images"] = images
                            chapter_data["total_images"] = len(images)
                        
                        scraper.save_chapter(slug, ch["chapter"], chapter_data)
                    else:
                        print(f"  Skipping chapter {ch['chapter']} (already exists)")
            
            print(f"Comic saved to: {scraper.comics_dir}/{slug}/")
        else:
            print("Failed to scrape comic")
    else:
        # Scrape all comics
        scraper.scrape_all(
            start_page=args.start_page,
            end_page=args.end_page,
            scrape_chapters=args.chapters,
            scrape_images=args.images
        )


if __name__ == "__main__":
    main()
