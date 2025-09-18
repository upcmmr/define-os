"""
Header Interaction Analysis Module

This module analyzes interactive elements in website headers, specifically:
- Dropdown menus (on hover and click)
- Navigation menu interactions
- Search box interactions
- Button hover effects
- Modal triggers
- Any significant UI changes in the header region

When interactions are detected, screenshots are captured to document the changes.
"""

import asyncio
import sys
import os
import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from urllib.parse import urlparse
from playwright.async_api import async_playwright
from PIL import Image
import json


class HeaderInteractionAnalyzer:
    """
    Analyzes interactive elements in website headers and captures screenshots
    of any detected UI changes.
    """
    
    def __init__(self, output_dir: Optional[Path] = None):
        """
        Initialize the Header Interaction Analyzer.
        
        Args:
            output_dir: Directory to save screenshots and analysis results.
                       If None, creates an 'interaction_output' directory.
        """
        self.output_dir = output_dir or Path("interaction_output")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Common header selectors to analyze
        self.header_selectors = [
            "header", "nav", ".header", ".navigation", ".navbar", 
            ".nav-bar", ".site-header", ".main-header", ".top-nav",
            "[role='banner']", ".masthead", ".header-container"
        ]
        
        # Interactive elements to test
        self.interactive_selectors = [
            # Navigation and menu items
            "nav a", "nav button", ".nav-item", ".menu-item", ".nav-link",
            ".dropdown", ".dropdown-toggle", ".menu-toggle",
            
            # Search elements
            ".search", ".search-box", ".search-input", ".search-button",
            "[type='search']", ".search-form",
            
            # Buttons and interactive elements
            "button", ".btn", ".button", "[role='button']",
            ".toggle", ".hamburger", ".menu-button",
            
            # Account/user elements
            ".account", ".user", ".login", ".profile", ".user-menu",
            
            # Shopping cart elements
            ".cart", ".shopping-cart", ".basket", ".bag",
            
            # Language/region selectors
            ".language", ".locale", ".region", ".country-selector"
        ]

    async def analyze_header_interactions(self, url: str) -> Dict[str, Any]:
        """
        Analyze header interactions for a given URL.
        
        Args:
            url: The URL to analyze
            
        Returns:
            Dictionary containing analysis results and screenshot paths
        """
        print(f"\n--- Analyzing Header Interactions for {url} ---")
        
        # Setup output directory for this URL
        sanitized_url = "".join(c if c.isalnum() else "_" for c in urlparse(url).netloc)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        url_output_dir = self.output_dir / f"{sanitized_url}_{timestamp}"
        url_output_dir.mkdir(parents=True, exist_ok=True)
        
        results = {
            "url": url,
            "timestamp": timestamp,
            "output_directory": str(url_output_dir),
            "interactions_found": [],
            "screenshots": [],
            "errors": []
        }
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-web-security'
                ]
            )
            
            try:
                page = await self._create_page(browser)
                await self._load_page(page, url)
                
                # Find header element
                header_element = await self._find_header_element(page)
                if not header_element:
                    results["errors"].append("No header element found on the page")
                    return results
                
                # Take initial screenshot of header
                initial_screenshot = await self._capture_header_screenshot(
                    page, header_element, url_output_dir, "initial"
                )
                results["screenshots"].append({
                    "type": "initial",
                    "path": str(initial_screenshot),
                    "description": "Initial header state"
                })
                
                # Find interactive elements in header
                interactive_elements = await self._find_interactive_elements(page, header_element)
                print(f"  > Found {len(interactive_elements)} interactive elements in header")
                
                # Test each interactive element
                for i, element_info in enumerate(interactive_elements):
                    try:
                        interaction_result = await self._test_element_interaction(
                            page, element_info, header_element, url_output_dir, i
                        )
                        if interaction_result:
                            results["interactions_found"].append(interaction_result)
                            if "screenshot_path" in interaction_result:
                                results["screenshots"].append({
                                    "type": "interaction",
                                    "path": interaction_result["screenshot_path"],
                                    "description": interaction_result["description"]
                                })
                    except Exception as e:
                        error_msg = f"Error testing element {i}: {str(e)}"
                        print(f"    > {error_msg}", file=sys.stderr)
                        results["errors"].append(error_msg)
                
                # Save analysis results to JSON
                results_file = url_output_dir / "interaction_analysis.json"
                with open(results_file, 'w', encoding='utf-8') as f:
                    json.dump(results, f, indent=2, ensure_ascii=False)
                
                print(f"  > Analysis complete. Found {len(results['interactions_found'])} interactions")
                print(f"  > Results saved to: {results_file}")
                
            except Exception as e:
                error_msg = f"Critical error during analysis: {str(e)}"
                print(f"  > {error_msg}", file=sys.stderr)
                results["errors"].append(error_msg)
            finally:
                await browser.close()
        
        return results

    async def _create_page(self, browser):
        """Create a page with proper viewport and user agent."""
        page = await browser.new_page(
            viewport={'width': 1280, 'height': 1024},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        await page.set_extra_http_headers({
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
        })
        
        return page

    async def _load_page(self, page, url: str):
        """Load page with multi-stage strategy."""
        print("  > Loading page...")
        await page.goto(url, wait_until="domcontentloaded", timeout=90000)
        
        try:
            await page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            await page.wait_for_load_state("load", timeout=30000)
        
        await page.wait_for_timeout(2000)  # Allow time for any animations
        print("  > Page loaded successfully")

    async def _find_header_element(self, page):
        """Find the header element using multiple selectors."""
        print("  > Locating header element...")
        
        for selector in self.header_selectors:
            try:
                elements = await page.query_selector_all(selector)
                for element in elements:
                    if (await element.is_visible() and 
                        await element.bounding_box() is not None):
                        bounding_box = await element.bounding_box()
                        if bounding_box and bounding_box['height'] > 0:
                            print(f"    > Header found using selector: {selector}")
                            return element
            except Exception:
                continue
        
        print("  > Warning: No header element found", file=sys.stderr)
        return None

    async def _find_interactive_elements(self, page, header_element) -> List[Dict[str, Any]]:
        """Find interactive elements within the header."""
        interactive_elements = []
        
        for selector in self.interactive_selectors:
            try:
                # Find elements within the header
                elements = await header_element.query_selector_all(selector)
                
                for element in elements:
                    if await element.is_visible():
                        bounding_box = await element.bounding_box()
                        if bounding_box and bounding_box['width'] > 0 and bounding_box['height'] > 0:
                            # Get element information
                            tag_name = await element.evaluate('el => el.tagName.toLowerCase()')
                            element_text = await element.text_content() or ""
                            element_classes = await element.get_attribute('class') or ""
                            element_id = await element.get_attribute('id') or ""
                            
                            interactive_elements.append({
                                "element": element,
                                "selector": selector,
                                "tag_name": tag_name,
                                "text": element_text.strip()[:100],  # Limit text length
                                "classes": element_classes,
                                "id": element_id,
                                "bounding_box": bounding_box
                            })
            except Exception as e:
                print(f"    > Warning: Error finding elements with selector '{selector}': {str(e)}", file=sys.stderr)
        
        return interactive_elements

    async def _test_element_interaction(self, page, element_info: Dict[str, Any], 
                                      header_element, output_dir: Path, element_index: int) -> Optional[Dict[str, Any]]:
        """Test an interactive element for hover and click effects."""
        element = element_info["element"]
        
        try:
            # Take screenshot before interaction
            before_screenshot = await self._capture_header_screenshot(
                page, header_element, output_dir, f"before_element_{element_index}"
            )
            
            interaction_detected = False
            interaction_type = None
            screenshot_path = None
            
            # Test hover interaction
            print(f"    > Testing hover on element: {element_info['text'][:50]}...")
            await element.hover()
            await page.wait_for_timeout(1000)  # Wait for hover effects
            
            # Check if anything changed
            hover_changed = await self._detect_visual_changes(page, header_element, before_screenshot)
            if hover_changed:
                interaction_detected = True
                interaction_type = "hover"
                screenshot_path = await self._capture_header_screenshot(
                    page, header_element, output_dir, f"hover_element_{element_index}"
                )
                print(f"      > Hover interaction detected!")
            
            # Reset hover state by moving mouse away
            await page.mouse.move(0, 0)
            await page.wait_for_timeout(500)
            
            # Test click interaction (only if hover didn't already detect changes)
            if not interaction_detected:
                print(f"    > Testing click on element: {element_info['text'][:50]}...")
                
                # Check if element is still attached and clickable
                try:
                    await element.click(timeout=5000)
                    await page.wait_for_timeout(1500)  # Wait for click effects
                    
                    click_changed = await self._detect_visual_changes(page, header_element, before_screenshot)
                    if click_changed:
                        interaction_detected = True
                        interaction_type = "click"
                        screenshot_path = await self._capture_header_screenshot(
                            page, header_element, output_dir, f"click_element_{element_index}"
                        )
                        print(f"      > Click interaction detected!")
                        
                        # Try to close any opened dropdowns/modals by pressing Escape
                        await page.keyboard.press('Escape')
                        await page.wait_for_timeout(500)
                        
                except Exception as click_error:
                    print(f"      > Could not click element: {str(click_error)}", file=sys.stderr)
            
            # Clean up temporary screenshot
            if before_screenshot.exists():
                before_screenshot.unlink()
            
            if interaction_detected:
                return {
                    "element_index": element_index,
                    "selector": element_info["selector"],
                    "tag_name": element_info["tag_name"],
                    "text": element_info["text"],
                    "classes": element_info["classes"],
                    "id": element_info["id"],
                    "interaction_type": interaction_type,
                    "screenshot_path": str(screenshot_path) if screenshot_path else None,
                    "description": f"{interaction_type.title()} interaction on {element_info['tag_name']} element: {element_info['text'][:50]}"
                }
            
        except Exception as e:
            print(f"    > Error testing element interaction: {str(e)}", file=sys.stderr)
        
        return None

    async def _capture_header_screenshot(self, page, header_element, output_dir: Path, suffix: str) -> Path:
        """Capture a screenshot of just the header region."""
        bounding_box = await header_element.bounding_box()
        
        screenshot_path = output_dir / f"header_{suffix}.png"
        await page.screenshot(
            path=screenshot_path,
            clip={
                'x': bounding_box['x'],
                'y': bounding_box['y'],
                'width': bounding_box['width'],
                'height': bounding_box['height']
            }
        )
        
        return screenshot_path

    async def _detect_visual_changes(self, page, header_element, reference_screenshot: Path) -> bool:
        """
        Detect if there are visual changes in the header by comparing screenshots.
        
        Args:
            page: Playwright page object
            header_element: Header element to screenshot
            reference_screenshot: Path to reference screenshot for comparison
            
        Returns:
            True if changes detected, False otherwise
        """
        try:
            # Take current screenshot
            current_screenshot = reference_screenshot.parent / f"temp_current_{reference_screenshot.stem}.png"
            await self._capture_header_screenshot(page, header_element, 
                                                reference_screenshot.parent, 
                                                f"temp_current_{reference_screenshot.stem}")
            
            # Compare images using PIL
            with Image.open(reference_screenshot) as ref_img, Image.open(current_screenshot) as curr_img:
                # Convert to same mode if different
                if ref_img.mode != curr_img.mode:
                    curr_img = curr_img.convert(ref_img.mode)
                
                # Resize if dimensions are different (shouldn't happen, but safety check)
                if ref_img.size != curr_img.size:
                    curr_img = curr_img.resize(ref_img.size)
                
                # Compare pixel by pixel (simple approach)
                # For production, you might want to use more sophisticated image comparison
                ref_pixels = list(ref_img.getdata())
                curr_pixels = list(curr_img.getdata())
                
                # Count different pixels
                different_pixels = sum(1 for r, c in zip(ref_pixels, curr_pixels) if r != c)
                total_pixels = len(ref_pixels)
                
                # Consider it changed if more than 0.1% of pixels are different
                change_threshold = total_pixels * 0.001
                changed = different_pixels > change_threshold
                
                # Clean up temporary screenshot
                if current_screenshot.exists():
                    current_screenshot.unlink()
                
                return changed
                
        except Exception as e:
            print(f"      > Error detecting visual changes: {str(e)}", file=sys.stderr)
            return False

    def print_analysis_summary(self, results: Dict[str, Any]) -> None:
        """Print a formatted summary of the analysis results."""
        print(f"\n🎯 Header Interaction Analysis Summary")
        print(f"🌐 URL: {results['url']}")
        print(f"📁 Output Directory: {results['output_directory']}")
        print(f"🔍 Interactions Found: {len(results['interactions_found'])}")
        print(f"📸 Screenshots Captured: {len(results['screenshots'])}")
        
        if results['errors']:
            print(f"⚠️  Errors: {len(results['errors'])}")
            for error in results['errors']:
                print(f"  • {error}")
        
        if results['interactions_found']:
            print(f"\n✅ **Detected Interactions:**")
            for interaction in results['interactions_found']:
                print(f"  • {interaction['interaction_type'].upper()}: {interaction['description']}")
                if interaction.get('screenshot_path'):
                    print(f"    📸 Screenshot: {Path(interaction['screenshot_path']).name}")
        else:
            print(f"\n❌ **No interactions detected in header region**")


# For command line testing
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python header_interaction_analyzer.py <url>")
        print("Example: python header_interaction_analyzer.py https://example.com")
        sys.exit(1)
    
    url = sys.argv[1]
    
    async def main():
        analyzer = HeaderInteractionAnalyzer()
        results = await analyzer.analyze_header_interactions(url)
        analyzer.print_analysis_summary(results)
        
        # Print full results as JSON
        print(f"\n📋 Full Results:")
        print(json.dumps(results, indent=2, default=str))
    
    asyncio.run(main())
