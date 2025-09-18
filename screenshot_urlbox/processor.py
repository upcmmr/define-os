import os
import asyncio
import datetime
import yaml
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv
from urlbox import UrlboxClient
from PIL import Image

from .analyzer import get_element_height, get_footer_height_after_scroll, extract_header_footer_body_html
from .html_cleaner import clean_all_html_files

# --- Initialization ---
load_dotenv()

class ScreenshotProcessor:
    """
    A robust hybrid class to capture and crop website screenshots.
    - Uses URLBox for high-fidelity full-page screenshots.
    - Uses Playwright for accurate element height analysis and HTML extraction.
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

    async def process_url(self, url: str, base_output_dir: Path, header_height: int = None, footer_height: int = None):
        """
        Process a single URL: analyze elements, capture screenshot, and crop sections.
        
        Args:
            url: The URL to process
            base_output_dir: Directory where output folders will be created
            header_height: Optional predefined header height (skips detection if provided)
            footer_height: Optional predefined footer height (skips detection if provided)
        """
        print(f"\n--- Processing {url} ---")
        
        # Setup output directory
        sanitized_url = "".join(c if c.isalnum() else "_" for c in urlparse(url).netloc)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = base_output_dir / f"{sanitized_url}_{timestamp}"
        output_path.mkdir(parents=True, exist_ok=True)
        
        # --- Phase 1: Analyze heights and extract HTML with Playwright ---
        print("  > Phase 1: Analyzing element heights and extracting HTML with Playwright...")
        header_selectors = ",".join(self.config['header_selectors'])
        footer_selectors = ",".join(self.config['footer_selectors'])

        # Get element heights (use predefined if provided, otherwise detect)
        if header_height is not None:
            print(f"    > Using predefined header height: {header_height}px")
        else:
            header_height = await get_element_height(url, header_selectors)
            
        if footer_height is not None:
            print(f"    > Using predefined footer height: {footer_height}px")
        else:
            footer_height = await get_footer_height_after_scroll(url, footer_selectors)
        
        # Extract header, footer, and body HTML content
        print("  > Extracting header, footer, and body HTML content...")
        header_html, footer_html, body_html = await extract_header_footer_body_html(url, header_selectors, footer_selectors)
        
        # Save header, footer, and body HTML to separate files
        header_html_path = output_path / "header.html"
        footer_html_path = output_path / "footer.html"
        body_html_path = output_path / "body.html"
        
        with open(header_html_path, "w", encoding="utf-8") as f:
            f.write(header_html)
        print(f"    > Header HTML saved: {header_html_path.name}")
        
        with open(footer_html_path, "w", encoding="utf-8") as f:
            f.write(footer_html)
        print(f"    > Footer HTML saved: {footer_html_path.name}")
        
        with open(body_html_path, "w", encoding="utf-8") as f:
            f.write(body_html)
        print(f"    > Body HTML saved: {body_html_path.name}")
        
        # Clean HTML files for AI analysis
        print("  > Cleaning HTML files for AI analysis...")
        cleaning_results = clean_all_html_files(output_path)
        
        if header_height == 0:
             print("  > WARNING: Header height is 0. Header crop may be blank.")
        if footer_height == 0:
             print("  > WARNING: Footer height is 0. Footer crop may be blank.")
        print(f"    > Measured Header Height: {header_height}px")
        print(f"    > Measured Footer Height: {footer_height}px")

        # --- Phase 2: Capture screenshot with URLBox ---
        print("  > Phase 2: Capturing screenshot with URLBox...")
        fullpage_path = await self._capture_full_page(url, output_path)
        print(f"    > Screenshot saved: {fullpage_path.name}")
        
        # --- Phase 3: Crop sections locally ---
        print("  > Phase 3: Cropping sections locally...")
        self._crop_sections(fullpage_path, header_height, footer_height, output_path)
        
        print(f"--- Successfully processed {url} ---")
        print(f"Header height: {header_height}")
        print(f"Footer height: {footer_height}")
        print(f"   > Output saved in: {output_path}")

    async def _capture_full_page(self, url: str, output_path: Path) -> Path:
        """Capture full-page screenshot using URLBox API."""
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
        
        return screenshot_path

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
    import argparse
    
    parser = argparse.ArgumentParser(description='Process website screenshots')
    parser.add_argument('url', help='URL to process')
    parser.add_argument('--header-height', type=int, help='Predefined header height in pixels')
    parser.add_argument('--footer-height', type=int, help='Predefined footer height in pixels')
    
    # Handle both old and new argument formats
    if len(sys.argv) < 2:
        print("Usage: python -m screenshot_urlbox.processor <url> [--header-height HEIGHT] [--footer-height HEIGHT]")
        print("Example: python -m screenshot_urlbox.processor https://example.com")
        print("Example: python -m screenshot_urlbox.processor https://example.com --header-height 120 --footer-height 80")
        return
    
    # Parse arguments
    try:
        args = parser.parse_args()
    except SystemExit:
        # Fallback to old format for backward compatibility
        if len(sys.argv) >= 2 and not sys.argv[1].startswith('--'):
            args = type('Args', (), {
                'url': sys.argv[1],
                'header_height': None,
                'footer_height': None
            })()
        else:
            return
    
    CONFIG_PATH = Path(__file__).parent / "config.yaml"
    BASE_OUTPUT_DIR = Path(__file__).parent / "output"
    
    try:
        processor = ScreenshotProcessor(CONFIG_PATH)
        await processor.process_url(
            args.url, 
            BASE_OUTPUT_DIR, 
            header_height=args.header_height,
            footer_height=args.footer_height
        )
    except Exception as e:
        print(f"--- FAILED to process {args.url}: {e} ---")

if __name__ == "__main__":
    asyncio.run(main())
