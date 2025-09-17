import asyncio
import sys
from playwright.async_api import async_playwright
from typing import Optional, Tuple

async def _find_robust_element(page, selectors_string: str):
    """
    Find an element using multiple selectors with validation.
    
    Args:
        page: Playwright page object
        selectors_string: Comma-separated CSS selectors
        
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
                header_element = await _find_robust_element(page, header_selector)
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
                footer_element = await _find_robust_element(page, footer_selector)
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
                        header_element = await _find_robust_element(page, header_selector)
                        if header_element:
                            header_outer_html = await header_element.evaluate('el => el.outerHTML')
                            body_html = body_html.replace(header_outer_html, '', 1)
                    
                    # If we found footer element, remove it from body HTML
                    if footer_html:
                        footer_element = await _find_robust_element(page, footer_selector)
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

async def get_element_height(url: str, selector: str) -> int:
    """
    Navigate to a URL and measure the height of an element using robust detection.
    
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
            
            print("    > Searching for header element...")
            element = await _find_robust_element(page, selector)
            if not element:
                raise Exception(f"Could not find visible header element with any of these selectors: {selector}. Check if the page loaded correctly and the selectors are appropriate for this website.")
            
            print("    > Measuring header dimensions...")
            bounding_box = await element.bounding_box()
            if not bounding_box:
                return 0
            height = int(bounding_box['height'])
            print(f"    > Header measurement complete: {height}px")
            return height
            
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
