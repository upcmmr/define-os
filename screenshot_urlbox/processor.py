import os
import asyncio
import datetime
import yaml
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv
from urlbox import UrlboxClient
from PIL import Image

from .analyzer import get_element_height, get_footer_height_after_scroll

# --- Initialization ---
load_dotenv()

class ScreenshotProcessor:
    """
    A robust hybrid class to capture and crop website screenshots.
    - Uses URLBox for high-fidelity full-page screenshots.
    - Uses Playwright for accurate element height analysis.
    """
    def __init__(self, config_path: Path):
        """Initialize the processor with configuration and URLBox client."""
        self.config = self._load_config(config_path)
        
        api_key = os.environ.get("URLBOX_API_KEY")
        api_secret = os.environ.get("URLBOX_API_SECRET")
        if not api_key or not api_secret:
            raise ValueError("URLBOX_API_KEY and URLBOX_API_SECRET must be set in your .env file")
        self.urlbox_client = UrlboxClient(api_key=api_key, api_secret=api_secret)

    def _load_config(self, config_path: Path) -> dict:
        """Load configuration from YAML file."""
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found at {config_path}")
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)

    async def process_url(self, url: str, base_output_dir: Path):
        """
        Process a single URL: analyze elements, capture screenshot, and crop sections.
        
        Args:
            url: The URL to process
            base_output_dir: Directory where output folders will be created
        """
        print(f"\n--- Processing {url} ---")
        
        # Setup output directory
        sanitized_url = "".join(c if c.isalnum() else "_" for c in urlparse(url).netloc)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = base_output_dir / f"{sanitized_url}_{timestamp}"
        output_path.mkdir(parents=True, exist_ok=True)
        
        # --- Phase 1: Analyze heights with Playwright ---
        print("  > Phase 1: Analyzing element heights with Playwright...")
        header_selectors = ",".join(self.config['header_selectors'])
        footer_selectors = ",".join(self.config['footer_selectors'])

        header_height = await get_element_height(url, header_selectors)
        footer_height = await get_footer_height_after_scroll(url, footer_selectors)
        
        if header_height == 0:
             print("  > WARNING: Header height is 0. Header crop may be blank.")
        if footer_height == 0:
             print("  > WARNING: Footer height is 0. Footer crop may be blank.")
        print(f"    > Measured Header Height: {header_height}px")
        print(f"    > Measured Footer Height: {footer_height}px")

        # --- Phase 2: Capture screenshot and HTML with URLBox ---
        print("  > Phase 2: Capturing screenshot and HTML with URLBox...")
        fullpage_path, html_path = await self._capture_full_page(url, output_path)
        print(f"    > Screenshot saved: {fullpage_path.name}")
        print(f"    > HTML saved: {html_path.name}")
        
        # --- Phase 3: Crop sections locally ---
        print("  > Phase 3: Cropping sections locally...")
        self._crop_sections(fullpage_path, header_height, footer_height, output_path)
        
        print(f"--- Successfully processed {url} ---")
        print(f"   > Output saved in: {output_path}")

    async def _capture_full_page(self, url: str, output_path: Path) -> tuple[Path, Path]:
        """Capture both full-page screenshot and HTML using URLBox API."""
        # Capture screenshot
        screenshot_options = {
            "url": url,
            "full_page": True,
            "format": "png",
            "click": ",".join(self.config['modal_close_selectors']),
            **self.config['screenshot_options']
        }
        
        screenshot_response = self.urlbox_client.get(screenshot_options)
        if screenshot_response.status_code != 200:
            raise Exception(f"URLBox failed to capture screenshot: {screenshot_response.text}")
            
        screenshot_path = output_path / "full_page.png"
        with open(screenshot_path, "wb") as f:
            f.write(screenshot_response.content)
        
        # Capture HTML
        html_options = {
            "url": url,
            "format": "html",
            "click": ",".join(self.config['modal_close_selectors']),
            **self.config['screenshot_options']
        }
        
        html_response = self.urlbox_client.get(html_options)
        if html_response.status_code != 200:
            raise Exception(f"URLBox failed to capture HTML: {html_response.text}")
            
        html_path = output_path / "page.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_response.text)
        
        return screenshot_path, html_path

    def _crop_sections(self, fullpage_path: Path, header_height: int, footer_height: int, output_path: Path):
        """Crop the full-page screenshot into header, body, and footer sections."""
        with Image.open(fullpage_path) as img_full:
            full_width, full_height = img_full.size
            footer_top = full_height - footer_height
            
            if header_height >= footer_top:
                raise ValueError(f"Invalid dimensions: header ({header_height}px) overlaps footer ({footer_top}px).")

            # Crop Header
            header_img = img_full.crop((0, 0, full_width, header_height))
            header_img.save(output_path / "header.png")

            # Crop Body
            body_img = img_full.crop((0, header_height, full_width, footer_top))
            body_img.save(output_path / "body.png")

            # Crop Footer
            footer_img = img_full.crop((0, footer_top, full_width, full_height))
            footer_img.save(output_path / "footer.png")
        print("    > Header, Body, and Footer saved.")


async def main():
    """
    Main entry point for the script.
    
    This is primarily for testing purposes. In production, import and use
    the ScreenshotProcessor class directly.
    """
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python -m screenshot_urlbox.processor <url1> [url2] ...")
        print("Example: python -m screenshot_urlbox.processor https://example.com")
        return
    
    CONFIG_PATH = Path(__file__).parent / "config.yaml"
    BASE_OUTPUT_DIR = Path(__file__).parent / "output"
    
    TARGET_URLS = sys.argv[1:]
    
    try:
        processor = ScreenshotProcessor(CONFIG_PATH)
        for url in TARGET_URLS:
            try:
                await processor.process_url(url, BASE_OUTPUT_DIR)
            except Exception as e:
                print(f"--- FAILED to process {url}: {e} ---")
                
    except Exception as e:
        print(f"An error occurred during initialization: {e}")

if __name__ == "__main__":
    asyncio.run(main())
