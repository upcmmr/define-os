import asyncio
import sys
import os
import base64
import json
from playwright.async_api import async_playwright
from typing import Optional, Tuple
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()

async def _find_robust_element(page, selectors_string: str, max_height: int = None):
    """
    Find an element using multiple selectors with validation.
    
    Args:
        page: Playwright page object
        selectors_string: Comma-separated CSS selectors
        max_height: Optional maximum height limit for header/footer elements
        
    Returns:
        First valid element found, or None
    """
    selectors = [s.strip() for s in selectors_string.split(',')]
    
    for selector in selectors:
        try:
            elements = await page.query_selector_all(selector)
            for element in elements:
                # Check if element is visible and has meaningful dimensions
                if (await element.is_visible() and 
                    await element.bounding_box() is not None):
                    bounding_box = await element.bounding_box()
                    if bounding_box and bounding_box['height'] > 0 and bounding_box['width'] > 0:
                        # Add height validation for header/footer elements
                        if max_height and bounding_box['height'] > max_height:
                            print(f"    > Skipping {selector} element: too tall ({bounding_box['height']}px > {max_height}px limit)")
                            continue
                        return element
        except Exception:
            continue  # Try next selector if this one fails
    
    return None

async def _create_robust_browser():
    """Create a browser instance with anti-detection measures."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor'
            ]
        )
        return browser, p

async def _create_robust_page(browser):
    """Create a page with proper viewport and user agent."""
    page = await browser.new_page(
        viewport={'width': 1280, 'height': 1024},
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )
    
    # Set additional headers to appear more like a real browser
    await page.set_extra_http_headers({
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
    })
    
    return page

async def _multi_stage_load(page, url: str):
    """Load page using multi-stage strategy for better compatibility."""
    # Stage 1: Initial load
    print("    > Loading page structure...")
    await page.goto(url, wait_until="domcontentloaded", timeout=90000)
    
    # Stage 2: Wait for network to settle
    print("    > Waiting for network activity to settle...")
    try:
        await page.wait_for_load_state("networkidle", timeout=30000)
    except Exception:
        # If networkidle fails, wait for complete state
        await page.wait_for_load_state("load", timeout=30000)
    
    # Stage 3: Wait for document ready
    try:
        await page.wait_for_function("document.readyState === 'complete'", timeout=15000)
    except Exception:
        pass  # Continue if this fails
    
    # Stage 4: Small delay for any remaining async operations
    await page.wait_for_timeout(1500)
    print("    > Page loading complete")

async def extract_header_footer_body_html(url: str, header_selector: str, footer_selector: str) -> Tuple[str, str, str]:
    """
    Navigate to a URL and extract HTML content from header, footer, and body elements.
    
    Args:
        url: The URL to navigate to
        header_selector: CSS selector(s) for header element (comma-separated)
        footer_selector: CSS selector(s) for footer element (comma-separated)
        
    Returns:
        Tuple of (header_html, footer_html, body_html) strings
    """
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
            page = await _create_robust_page(browser)
            await _multi_stage_load(page, url)
            
            # Extract header HTML
            print("    > Extracting header HTML content...")
            header_html = ""
            try:
                header_element = await _find_robust_element(page, header_selector, max_height=1000)
                if header_element:
                    header_html = await header_element.inner_html()
                    print(f"    > Header HTML extracted: {len(header_html)} characters")
                else:
                    print("    > Warning: No header element found for HTML extraction", file=sys.stderr)
            except Exception as e:
                print(f"    > Warning: Could not extract header HTML: {str(e)}", file=sys.stderr)
            
            # Trigger lazy loading for footer
            print("    > Triggering lazy-loaded content for footer...")
            await _trigger_lazy_loading(page)
            
            # Extract footer HTML
            print("    > Extracting footer HTML content...")
            footer_html = ""
            try:
                footer_element = await _find_robust_element(page, footer_selector, max_height=1500)
                if footer_element:
                    footer_html = await footer_element.inner_html()
                    print(f"    > Footer HTML extracted: {len(footer_html)} characters")
                else:
                    print("    > Warning: No footer element found for HTML extraction", file=sys.stderr)
            except Exception as e:
                print(f"    > Warning: Could not extract footer HTML: {str(e)}", file=sys.stderr)
            
            # Extract body HTML (everything except header and footer)
            print("    > Extracting body HTML content...")
            body_html = ""
            try:
                # Get the body element content only (not the full document)
                body_element = await page.query_selector('body')
                if body_element:
                    body_html = await body_element.inner_html()
                    
                    # If we found header element, remove it from body HTML
                    if header_html:
                        header_element = await _find_robust_element(page, header_selector, max_height=1000)
                        if header_element:
                            header_outer_html = await header_element.evaluate('el => el.outerHTML')
                            body_html = body_html.replace(header_outer_html, '', 1)
                    
                    # If we found footer element, remove it from body HTML
                    if footer_html:
                        footer_element = await _find_robust_element(page, footer_selector, max_height=1500)
                        if footer_element:
                            footer_outer_html = await footer_element.evaluate('el => el.outerHTML')
                            body_html = body_html.replace(footer_outer_html, '', 1)
                    
                    print(f"    > Body HTML extracted: {len(body_html)} characters")
                else:
                    print("    > Warning: No body element found", file=sys.stderr)
                    # Fallback: get full page content if no body element
                    body_html = await page.content()
            except Exception as e:
                print(f"    > Warning: Could not extract body HTML: {str(e)}", file=sys.stderr)
                # Fallback: use full page HTML if body extraction fails
                body_html = await page.content()
            
            return header_html, footer_html, body_html
        finally:
            await browser.close()

async def _ai_measure_header_height(page, url: str) -> int:
    """
    Use AI to visually measure header height from full page screenshot.
    This is for diagnostic purposes only - results are printed but not used in detection logic.
    
    Args:
        page: Playwright page object
        url: URL being analyzed for context
        
    Returns:
        AI-determined header height in pixels, or 0 if measurement fails
    """
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("    > Warning: No OpenAI API key found, skipping AI measurement", file=sys.stderr)
            return 0
        
        client = OpenAI(api_key=api_key)
        
        # Take full page screenshot
        page_height = await page.evaluate("document.body.scrollHeight")
        viewport_width = await page.evaluate("window.innerWidth")
        
        # Capture top portion of page (first 800px should cover most headers)
        screenshot_height = min(800, page_height)
        full_screenshot = await page.screenshot(
            clip={
                'x': 0,
                'y': 0,
                'width': viewport_width,
                'height': screenshot_height
            }
        )
        
        # Encode screenshot to base64
        screenshot_b64 = base64.b64encode(full_screenshot).decode('utf-8')
        
        print(f"    > AI measuring header height from full screenshot ({screenshot_height}px capture)...")
        
        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert web UI analyst. Analyze screenshots to precisely measure header heights. "
                        "A complete header includes promotional banners, logo/brand, main navigation, and any utility elements (search, cart, account). "
                        "Respond with valid JSON only."
                    )
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"""
Analyze this website screenshot from {url}.

TASK: Determine the exact pixel height from the very top of the page to the bottom of the complete header area.

HEADER COMPONENTS TO INCLUDE:
1. Any promotional/announcement banners at the top
2. Logo/brand identity 
3. Main navigation menu (Home, Shop, About, etc.)
4. Search bars, account icons, shopping cart icons
5. Any other elements that are clearly part of the header region

MEASUREMENT INSTRUCTIONS:
- Start from pixel 0 (very top of the page)
- Find the bottom edge of the lowest header component
- Return the total pixel distance
- Be precise - this measurement will be used for image cropping

Return your measurement as JSON:
{{
  "header_height_pixels": 123,
  "confidence": 0.95,
  "reasoning": "Header includes promo banner (0-40px) and main nav with logo (40-123px)",
  "components_found": ["promotional banner", "logo", "main navigation", "utility icons"]
}}

Be as accurate as possible with the pixel measurement.
"""
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{screenshot_b64}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ]
        )
        
        # Parse AI response
        try:
            raw_text = response.choices[0].message.content.strip()
            # Extract JSON from response
            if raw_text.startswith('{'):
                result = json.loads(raw_text)
            else:
                # Look for JSON in code blocks or other formats
                import re
                json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_text, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group(1))
                else:
                    json_match = re.search(r'(\{.*\})', raw_text, re.DOTALL)
                    if json_match:
                        result = json.loads(json_match.group(1))
                    else:
                        raise ValueError("No JSON found in response")
            
            ai_height = result.get('header_height_pixels', 0)
            confidence = result.get('confidence', 0.0)
            reasoning = result.get('reasoning', 'No reasoning provided')
            components = result.get('components_found', [])
            
            print(f"    > *** AI VISUAL MEASUREMENT: {ai_height}px header height (confidence: {confidence:.2f}) ***")
            print(f"    > *** AI reasoning: {reasoning} ***")
            print(f"    > *** Components found: {', '.join(components)} ***")
            
            return ai_height
            
        except Exception as e:
            print(f"    > Warning: Could not parse AI measurement response: {str(e)}", file=sys.stderr)
            return 0
            
    except Exception as e:
        print(f"    > Warning: AI header measurement failed: {str(e)}", file=sys.stderr)
        return 0


async def _validate_header_with_ai(screenshot_data: bytes, detected_height: int, page_height: int, url: str) -> bool:
    """
    Use AI to validate if the detected header looks complete with navigation bar.
    
    Args:
        screenshot_data: Screenshot bytes of the detected header area
        detected_height: Height of the detected header in pixels
        page_height: Total page height for context
        url: URL being analyzed for context
        
    Returns:
        True if header looks complete, False otherwise
    """
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("    > Warning: No OpenAI API key found, skipping AI validation", file=sys.stderr)
            return True  # Default to accepting if no API key
        
        client = OpenAI(api_key=api_key)
        
        # Encode screenshot to base64
        header_b64 = base64.b64encode(screenshot_data).decode('utf-8')
        
        print(f"    > Validating header completeness with AI ({detected_height}px of {page_height}px total)...")
        
        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert web UI analyst. Analyze header screenshots to determine if they contain a complete header with navigation. "
                        "A complete header typically includes: logo/brand, main navigation menu, and may include promotional banners, search, account/cart icons. "
                        "Respond with valid JSON only."
                    )
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"""
Analyze this header screenshot from {url}.

Detected header area: 0px to {detected_height}px (includes everything from page top)
Total page height: {page_height}px
Header percentage: {(detected_height/page_height*100):.1f}%

Does this look like a COMPLETE header that includes:
1. Logo/brand identity
2. Main navigation menu (Home, Shop, About, etc.)
3. Any promotional banners or top bars

Return JSON with your assessment:
{{
  "is_complete": true/false,
  "confidence": 0.0-1.0,
  "missing_elements": ["list of missing key elements"],
  "reasoning": "brief explanation"
}}

Be strict - only return true if you can clearly see both logo AND navigation elements."""
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{header_b64}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ]
        )
        
        # Parse AI response
        try:
            raw_text = response.choices[0].message.content.strip()
            # Try to extract JSON from response
            if raw_text.startswith('{'):
                result = json.loads(raw_text)
            else:
                # Look for JSON in code blocks
                import re
                json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_text, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group(1))
                else:
                    # Look for any JSON-like structure
                    json_match = re.search(r'(\{.*\})', raw_text, re.DOTALL)
                    if json_match:
                        result = json.loads(json_match.group(1))
                    else:
                        raise ValueError("No JSON found in response")
            
            is_complete = result.get('is_complete', False)
            confidence = result.get('confidence', 0.0)
            reasoning = result.get('reasoning', 'No reasoning provided')
            
            print(f"    > AI validation result: {'COMPLETE' if is_complete else 'INCOMPLETE'} (confidence: {confidence:.2f})")
            print(f"    > AI reasoning: {reasoning}")
            
            return is_complete and confidence > 0.6  # Require high confidence
            
        except Exception as e:
            print(f"    > Warning: Could not parse AI response: {str(e)}", file=sys.stderr)
            return True  # Default to accepting if parsing fails
            
    except Exception as e:
        print(f"    > Warning: AI validation failed: {str(e)}", file=sys.stderr)
        return True  # Default to accepting if AI call fails


async def _find_multi_element_header(page, selectors: str) -> Optional[Tuple[int, int]]:
    """
    Find header by detecting multiple related elements and combining their bounding boxes.
    
    Args:
        page: Playwright page object
        selectors: CSS selectors string
        
    Returns:
        Tuple of (top_y, bottom_y) coordinates, or None if not found
    """
    print("    > Attempting multi-element header detection...")
    
    # Look for common header-related elements
    header_elements = []
    
    # Promotional banners (often at the very top)
    promo_selectors = [
        ".promo-bar", ".announcement-bar", ".top-bar", ".banner", 
        "[class*='promo']", "[class*='announcement']", "[class*='sale']"
    ]
    
    # Main navigation elements
    nav_selectors = [
        "nav", ".navigation", ".navbar", ".nav-bar", ".main-nav",
        "[role='navigation']", ".menu", ".nav-menu"
    ]
    
    # Logo/brand elements
    logo_selectors = [
        ".logo", "[class*='logo']", ".brand", "[class*='brand']",
        "h1 a", ".site-title", ".site-name"
    ]
    
    all_selectors = promo_selectors + nav_selectors + logo_selectors
    
    for selector in all_selectors:
        try:
            elements = await page.query_selector_all(selector)
            for element in elements:
                if await element.is_visible():
                    bbox = await element.bounding_box()
                    if bbox and bbox['y'] < 300:  # Only consider elements in top 300px
                        header_elements.append({
                            'element': element,
                            'bbox': bbox,
                            'selector': selector
                        })
        except Exception:
            continue
    
    if not header_elements:
        print("    > No header elements found in multi-element detection")
        return None
    
    # Sort by Y position (top to bottom)
    header_elements.sort(key=lambda x: x['bbox']['y'])
    
    # Find the top and bottom boundaries
    top_y = min(elem['bbox']['y'] for elem in header_elements)
    bottom_y = max(elem['bbox']['y'] + elem['bbox']['height'] for elem in header_elements)
    
    # Validate the detected area makes sense
    header_height = bottom_y - top_y
    if header_height < 50:  # Too small
        print(f"    > Multi-element header too small: {header_height}px")
        return None
    if header_height > 1000:  # Too large
        print(f"    > Multi-element header too large: {header_height}px")
        return None
    
    print(f"    > Multi-element detection found header: {top_y}px to {bottom_y}px ({header_height}px tall)")
    print(f"    > Found {len(header_elements)} header-related elements:")
    for i, elem in enumerate(header_elements):
        bbox = elem['bbox']
        print(f"      Element {i+1}: {elem['selector']} at y={bbox['y']:.1f}px, height={bbox['height']:.1f}px (bottom: {bbox['y'] + bbox['height']:.1f}px)")
    print(f"    > Will crop from page top (0px) to header bottom ({bottom_y}px)")
    
    return (int(top_y), int(bottom_y))


async def get_element_height(url: str, selector: str) -> int:
    """
    Navigate to a URL and measure the height of a header using enhanced detection with AI validation.
    
    Flow:
    1. Try standard element detection with 1000px limit
    2. Use AI to validate if header looks complete
    3. If not complete, try multi-element detection
    4. Validate multi-element result with AI
    5. If still not complete, fall back to 20% of page height
    
    Args:
        url: The URL to navigate to
        selector: CSS selector(s) for the element to measure (comma-separated)
        
    Returns:
        Height of the element in pixels, or 0 if not found
    """
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
            page = await _create_robust_page(browser)
            await _multi_stage_load(page, url)
            
            # Get page dimensions for context
            page_height = await page.evaluate("document.body.scrollHeight")
            viewport_height = await page.evaluate("window.innerHeight")
            
            print(f"    > Page dimensions: {page_height}px total, {viewport_height}px viewport")
            
            # DIAGNOSTIC: AI visual measurement (for comparison only)
            print("    > DIAGNOSTIC: AI visual header measurement...")
            ai_measured_height = await _ai_measure_header_height(page, url)
            
            # STEP 1: Try standard element detection with increased height limit
            print("    > Step 1: Standard header element detection...")
            element = await _find_robust_element(page, selector, max_height=1000)
            
            detected_height = 0
            if element:
                bounding_box = await element.bounding_box()
                if bounding_box:
                    detected_height = int(bounding_box['height'])
                    print(f"    > Standard detection found header: {detected_height}px")
                    
                    # STEP 2: AI validation of standard detection
                    print("    > Step 2: AI validation of detected header...")
                    try:
                        # Take screenshot of detected header area
                        header_screenshot = await page.screenshot(
                            clip={
                                'x': 0,
                                'y': 0,
                                'width': bounding_box['width'],
                                'height': bounding_box['height']
                            }
                        )
                        
                        is_complete = await _validate_header_with_ai(
                            header_screenshot, detected_height, page_height, url
                        )
                        
                        if is_complete:
                            print(f"    > AI validation passed - using standard detection: {detected_height}px")
                            return detected_height
                        else:
                            print("    > AI validation failed - header appears incomplete")
                    except Exception as e:
                        print(f"    > Warning: AI validation error: {str(e)}", file=sys.stderr)
                        # Continue to multi-element detection
            else:
                print("    > No element found with standard detection")
            
            # STEP 3: Multi-element detection
            print("    > Step 3: Multi-element header detection...")
            multi_result = await _find_multi_element_header(page, selector)
            
            if multi_result:
                top_y, bottom_y = multi_result
                # Use bottom_y as the height to include everything from page top to header bottom
                multi_height = int(bottom_y)
                
                # STEP 4: AI validation of multi-element detection
                print("    > Step 4: AI validation of multi-element header...")
                try:
                    # Take screenshot of multi-element header area (from page top to header bottom)
                    viewport_width = await page.evaluate("window.innerWidth")
                    header_screenshot = await page.screenshot(
                        clip={
                            'x': 0,
                            'y': 0,
                            'width': viewport_width,
                            'height': multi_height
                        }
                    )
                    
                    is_complete = await _validate_header_with_ai(
                        header_screenshot, multi_height, page_height, url
                    )
                    
                    if is_complete:
                        print(f"    > AI validation passed - using multi-element detection: {multi_height}px")
                        return multi_height
                    else:
                        print("    > AI validation failed - multi-element header appears incomplete")
                except Exception as e:
                    print(f"    > Warning: Multi-element AI validation error: {str(e)}", file=sys.stderr)
                    # Continue to fallback
            
            # STEP 5: Percentage-based fallback
            print("    > Step 5: Falling back to percentage-based detection (20% of page)...")
            fallback_height = int(page_height * 0.20)  # 20% of page height
            
            # Ensure reasonable bounds
            fallback_height = max(100, min(fallback_height, 800))  # Between 100px and 800px
            
            print(f"    > Fallback detection: {fallback_height}px (20% of {page_height}px page)")
            return fallback_height
            
        finally:
            await browser.close()

async def get_footer_height_after_scroll(url: str, selector: str) -> int:
    """
    Navigate to a URL, scroll to trigger lazy-loaded content, and measure footer height using robust detection.
    
    Args:
        url: The URL to navigate to
        selector: CSS selector(s) for the footer element (comma-separated)
        
    Returns:
        Height of the footer in pixels after scrolling, or 0 if not found
    """
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
            page = await _create_robust_page(browser)
            await _multi_stage_load(page, url)

            # Enhanced scrolling strategy for lazy-loaded content
            print("    > Triggering lazy-loaded content...")
            await _trigger_lazy_loading(page)
            
            print("    > Searching for footer element...")
            # Set reasonable height limit for footers (1500px max)
            footer = await _find_robust_element(page, selector, max_height=1500)
            if not footer:
                # Try again without height limit as fallback
                print("    > No footer found within height limit, trying without limit...")
                footer = await _find_robust_element(page, selector)
                if not footer:
                    raise Exception(f"Could not find visible footer element with any of these selectors: {selector}. Tried scrolling and waiting for lazy-loaded content. Check if the page has a footer or if different selectors are needed.")
            
            print("    > Measuring footer dimensions...")
            bounding_box = await footer.bounding_box()
            if not bounding_box:
                return 0
            height = int(bounding_box['height'])
            print(f"    > Footer measurement complete: {height}px")
            return height
            
        finally:
            await browser.close()

async def _trigger_lazy_loading(page):
    """Enhanced lazy-loading trigger strategy."""
    # Stage 1: Scroll to bottom
    print("      > Scrolling to trigger footer content...")
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await page.wait_for_timeout(1500)
    
    # Stage 2: Scroll up slightly and back down (triggers some lazy loaders)
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight - 100)")
    await page.wait_for_timeout(800)
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    
    # Stage 3: Wait for network to settle after scrolling
    print("      > Waiting for lazy content to load...")
    try:
        await page.wait_for_load_state("networkidle", timeout=30000)
    except Exception:
        pass  # Continue if networkidle fails
    
    # Stage 4: Wait for lazy-loaded content
    await page.wait_for_timeout(6000)
    
    # Stage 5: Final scroll to ensure everything is loaded
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await page.wait_for_timeout(1500)
    print("      > Lazy loading complete")
