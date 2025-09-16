"""
Screenshot URLBox Module

A hybrid screenshot capture system that combines URLBox API for high-quality screenshots
with Playwright for accurate DOM element analysis and local image cropping.

Key Features:
- Full-page screenshot capture with modal/banner dismissal
- Accurate header and footer height measurement using browser automation
- Local image cropping into header, body, and footer sections
- Configurable CSS selectors for different website layouts

Usage:
    from screenshot_urlbox import ScreenshotProcessor
    
    processor = ScreenshotProcessor(config_path)
    await processor.process_url(url, output_dir)
"""

from .processor import ScreenshotProcessor
from .analyzer import get_element_height, get_footer_height_after_scroll

__all__ = ['ScreenshotProcessor', 'get_element_height', 'get_footer_height_after_scroll']
