"""
Header Analysis Module

Uses GPT-5 to analyze header images and associated HTML to extract
links, UI elements, and interactive components.
"""

import os
import sys
import base64
import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()


def _extract_json_from_response(resp) -> Tuple[Optional[dict], str]:
    """Extract JSON from GPT-5 Chat Completions API output with robust error handling."""
    data = None
    
    # Extract text from chat completions response
    try:
        raw_text = resp.choices[0].message.content.strip()
    except (AttributeError, IndexError):
        raw_text = str(resp)
    
    # If no structured JSON found, try to parse the raw text as JSON
    if data is None and raw_text:
        try:
            # Clean the text first - remove any markdown formatting and problematic characters
            cleaned_text = raw_text
            if cleaned_text.startswith('```json'):
                cleaned_text = cleaned_text[7:]
            if cleaned_text.endswith('```'):
                cleaned_text = cleaned_text[:-3]
            
            # Remove leading > characters that might be causing issues
            cleaned_text = re.sub(r'^>\s*', '', cleaned_text, flags=re.MULTILINE)
            cleaned_text = cleaned_text.strip()
            
            # Try to parse the cleaned text as JSON
            data = json.loads(cleaned_text)
            print(f"      > Successfully parsed JSON after cleaning", file=sys.stderr)
        except json.JSONDecodeError as e:
            print(f"      > JSON parse error: {str(e)}", file=sys.stderr)
            # Try to find JSON within the text using more robust pattern
            json_patterns = [
                r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}',  # Simple nested objects
                r'\{.*?"navigation_links".*?\}',      # Look for our expected structure
                r'\{.*?\}(?=\s*$)',                   # JSON at end of text
            ]
            
            for pattern in json_patterns:
                json_match = re.search(pattern, raw_text, re.DOTALL)
                if json_match:
                    try:
                        candidate_json = json_match.group()
                        # Clean up common issues
                        candidate_json = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', candidate_json)  # Remove control chars
                        candidate_json = re.sub(r',\s*}', '}', candidate_json)  # Remove trailing commas
                        candidate_json = re.sub(r',\s*]', ']', candidate_json)  # Remove trailing commas in arrays
                        
                        data = json.loads(candidate_json)
                        print(f"      > Successfully extracted JSON using pattern matching", file=sys.stderr)
                        break
                    except json.JSONDecodeError:
                        continue
            
            if data is None:
                print(f"      > Failed to extract valid JSON. Raw response preview: {raw_text[:200]}...", file=sys.stderr)
    
    return data, raw_text


def _encode_image_to_base64(image_path: Path) -> str:
    """Encode an image file to base64 string."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def _load_html_content(html_path: Path) -> str:
    """Load HTML content from file."""
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()


def _preprocess_html_for_analysis(html_content: str, base_url: str = "") -> str:
    """
    Preprocess HTML to extract key navigation and header elements.
    This helps the AI focus on relevant parts and find actual URLs.
    """
    from urllib.parse import urljoin, urlparse
    
    # Extract header/navigation related sections
    header_patterns = [
        r'<header[^>]*>.*?</header>',
        r'<nav[^>]*>.*?</nav>',
        r'<div[^>]*(?:header|navigation|nav|topbar|menu)[^>]*>.*?</div>',
        r'<ul[^>]*(?:nav|menu)[^>]*>.*?</ul>',
    ]
    
    extracted_sections = []
    
    # Find all href links in the HTML
    href_links = re.findall(r'href="([^"]*)"', html_content)
    
    # Convert relative URLs to absolute URLs
    absolute_links = []
    if base_url:
        for link in href_links:
            if link.startswith('http'):
                absolute_links.append(link)
            elif link.startswith('/'):
                # Relative to domain root
                parsed_base = urlparse(base_url)
                absolute_url = f"{parsed_base.scheme}://{parsed_base.netloc}{link}"
                absolute_links.append(absolute_url)
            elif link.startswith('#'):
                # Fragment/anchor link
                absolute_url = f"{base_url}{link}"
                absolute_links.append(absolute_url)
            else:
                # Relative path
                absolute_url = urljoin(base_url, link)
                absolute_links.append(absolute_url)
    else:
        absolute_links = href_links
    
    # Extract navigation sections
    for pattern in header_patterns:
        matches = re.findall(pattern, html_content, re.IGNORECASE | re.DOTALL)
        extracted_sections.extend(matches)
    
    # If we found specific sections, use those
    if extracted_sections:
        relevant_html = "\n\n".join(extracted_sections[:5])  # Limit to first 5 sections
    else:
        # Fallback: take first part of HTML
        relevant_html = html_content[:15000]
    
    # Add a summary of all found links (now absolute)
    if absolute_links:
        links_summary = "\n\n<!-- EXTRACTED ABSOLUTE LINKS -->\n"
        for i, link in enumerate(absolute_links[:20]):  # First 20 links
            links_summary += f"<!-- Link {i+1}: {link} -->\n"
        relevant_html += links_summary
    
    return relevant_html


async def analyze_header_elements(header_image_path: Path, header_html_path: Path, url: str = "") -> Dict[str, Any]:
    """
    Analyze header image and HTML to extract links and UI elements.
    
    Args:
        header_image_path: Path to the header screenshot
        header_html_path: Path to the header-specific HTML file
        url: Base URL for converting relative links to absolute
        
    Returns:
        Dictionary containing analysis results with categorized navigation links
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required")
    
    client = OpenAI(api_key=api_key)
    
    # Load and encode the header image
    print("    > Loading header image...", file=sys.stderr)
    header_b64 = _encode_image_to_base64(header_image_path)
    
    # Load and preprocess header HTML content
    print("    > Processing header HTML content...", file=sys.stderr)
    html_content = _load_html_content(header_html_path)
    processed_html = _preprocess_html_for_analysis(html_content, url)
    
    print("    > Sending request to GPT-5...", file=sys.stderr)
    try:
        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert web UI analyst. Analyze the provided header image and HTML "
                        "to extract all links, buttons, navigation elements, and interactive components. "
                        "Correlate visual elements in the image with their corresponding HTML elements. "
                        "Focus on extracting ACTUAL URLs from href attributes in the HTML. "
                        "Respond with valid JSON only containing your analysis."
                    )
                },
                {
                    "role": "user", 
                    "content": [
                        {
                            "type": "text",
                            "text": f"""
Please analyze this website header and provide a comprehensive breakdown of all interactive elements.

Website URL: {url}

HTML Content (preprocessed and focused on navigation):
{processed_html}

CRITICAL INSTRUCTIONS:
1. Look at the header image to identify visual elements
2. Match those visual elements to the HTML code provided
3. Extract ACTUAL URLs from href attributes in the HTML - USE ABSOLUTE URLS (full URLs starting with http/https)
4. Convert any relative URLs (starting with /) to absolute URLs using the base domain
5. For each visual element you see, find its corresponding HTML tag and extract:
   - href attributes for links (convert to absolute URLs)
   - class and id attributes for CSS selectors
   - data-* attributes for JavaScript interactions

Please identify and extract:
1. All navigation links with their ACTUAL URLs from HTML href attributes, categorized as follows:
   - PRODUCT CATEGORIES: Links to product collections, categories, or shopping sections (e.g., "Men's", "Women's", "Electronics", "Clothing", "Sale")
   - CONTENT: Informational links (e.g., "About Us", "Blog", "Help", "FAQ", "Store Locator", "Contact", "Careers")
   - TRANSACTIONAL: Account and commerce-related links (e.g., "Login", "Sign Up", "My Account", "Cart", "Checkout", "Wishlist", "Order Status")
   - OTHER: Links that don't fit the above categories
2. Buttons and their purposes with any associated actions/links
3. Interactive elements (dropdowns, search boxes, etc.) with their HTML attributes
4. Logo and branding elements with their actual links
5. Any other clickable or interactive components

Return your analysis as a JSON object with this structure:
{{
  "navigation_links": {{
    "product_categories": [
      {{
        "text": "Link text visible in image",
        "url": "ACTUAL URL from href attribute",
        "css_selector": "CSS selector or class from HTML",
        "position": "Description of position in header",
        "category_type": "Description of product category (e.g., 'Men's Clothing', 'Electronics', etc.)"
      }}
    ],
    "content": [
      {{
        "text": "Link text visible in image",
        "url": "ACTUAL URL from href attribute",
        "css_selector": "CSS selector or class from HTML",
        "position": "Description of position in header",
        "content_type": "Type of content (e.g., 'About Us', 'Blog', 'Help', 'Store Locator', etc.)"
      }}
    ],
    "transactional": [
      {{
        "text": "Link text visible in image",
        "url": "ACTUAL URL from href attribute",
        "css_selector": "CSS selector or class from HTML",
        "position": "Description of position in header",
        "transaction_type": "Type of transaction (e.g., 'Account', 'Cart', 'Checkout', 'Wishlist', 'Login', etc.)"
      }}
    ],
    "other": [
      {{
        "text": "Link text visible in image",
        "url": "ACTUAL URL from href attribute",
        "css_selector": "CSS selector or class from HTML",
        "position": "Description of position in header",
        "link_type": "Description of link purpose if not fitting other categories"
      }}
    ]
  }},
  "buttons": [
    {{
      "text": "Button text",
      "type": "Button type/purpose",
      "url": "URL if button links somewhere",
      "css_selector": "CSS selector if found",
      "position": "Description of position in header"
    }}
  ],
  "interactive_elements": [
    {{
      "type": "Element type (dropdown, search, etc.)",
      "description": "What this element does",
      "url": "URL if applicable",
      "css_selector": "CSS selector if found",
      "position": "Description of position in header"
    }}
  ],
  "branding": [
    {{
      "type": "logo/brand element",
      "description": "Description of branding element",
      "url": "URL if logo/brand links somewhere",
      "position": "Description of position in header"
    }}
  ],
  "summary": {{
    "total_interactive_elements": 0,
    "navigation_breakdown": {{
      "product_categories_count": 0,
      "content_links_count": 0,
      "transactional_links_count": 0,
      "other_links_count": 0
    }},
    "has_search": false,
    "has_user_account_features": false,
    "layout_style": "Description of header layout"
  }}
}}
"""
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{header_b64}"
                            }
                        }
                    ]
                }
            ]
        )
        
        print("    > Processing AI response...", file=sys.stderr)
        # Extract JSON response
        try:
            analysis_data, raw_text = _extract_json_from_response(response)
        except Exception as e:
            print(f"      > Error extracting response: {str(e)}", file=sys.stderr)
            return {
                "success": False,
                "error": f"Failed to extract AI response: {str(e)}",
                "image_path": str(header_image_path),
                "html_path": str(header_html_path),
                "url": url
            }
        
        if analysis_data:
            # Count navigation links by category
            nav_links = analysis_data.get('navigation_links', {})
            product_cat_count = len(nav_links.get('product_categories', []))
            content_count = len(nav_links.get('content', []))
            transactional_count = len(nav_links.get('transactional', []))
            other_count = len(nav_links.get('other', []))
            total_nav_count = product_cat_count + content_count + transactional_count + other_count
            
            button_count = len(analysis_data.get('buttons', []))
            interactive_count = len(analysis_data.get('interactive_elements', []))
            branding_count = len(analysis_data.get('branding', []))
            total_elements = total_nav_count + button_count + interactive_count + branding_count
            
            print(f"    > AI analysis complete: {total_elements} elements found", file=sys.stderr)
            print(f"      > Navigation: {product_cat_count} product categories, {content_count} content, {transactional_count} transactional, {other_count} other", file=sys.stderr)
            print(f"      > Other: {button_count} buttons, {interactive_count} interactive elements, {branding_count} branding elements", file=sys.stderr)
            
            return {
                "success": True,
                "analysis": analysis_data,
                "raw_response": raw_text,
                "image_path": str(header_image_path),
                "html_path": str(header_html_path),
                "url": url
            }
        else:
            print("    > ERROR: AI analysis failed to extract structured data", file=sys.stderr)
            print(f"      > Raw AI response preview: {raw_text[:300]}...", file=sys.stderr)
            return {
                "success": False,
                "error": f"Failed to extract valid JSON from AI response. AI returned malformed data. Raw response: {raw_text[:500]}",
                "raw_response": raw_text,
                "image_path": str(header_image_path),
                "html_path": str(header_html_path),
                "url": url
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": f"AI analysis failed: {str(e)}",
            "image_path": str(header_image_path),
            "html_path": str(header_html_path),
            "url": url
        }


def print_analysis_results(analysis: Dict[str, Any]) -> None:
    """
    Print analysis results in a formatted way for command line output.
    """
    if not analysis.get("success", False):
        print(f"❌ Analysis failed: {analysis.get('error', 'Unknown error')}")
        if analysis.get("raw_response"):
            print(f"Raw response: {analysis['raw_response'][:500]}...")
        return
    
    data = analysis.get("analysis", {})
    print(f"\n🎯 Header Analysis Results")
    print(f"📁 Image: {Path(analysis['image_path']).name}")
    print(f"📄 HTML: {Path(analysis['html_path']).name}")
    if analysis.get("url"):
        print(f"🌐 URL: {analysis['url']}")
    
    # Navigation Links by Category
    nav_links = data.get("navigation_links", {})
    if nav_links:
        print(f"\n🔗 Navigation Links:")
        
        # Product Categories
        product_cats = nav_links.get('product_categories', [])
        if product_cats:
            print(f"\n  🛍️  Product Categories ({len(product_cats)}):")
            for i, link in enumerate(product_cats, 1):
                url_display = link.get('url', 'N/A')
                if url_display and url_display != 'N/A' and url_display != 'None' and url_display != 'null':
                    print(f"    {i}. {link.get('text', 'N/A')} → {url_display}")
                else:
                    print(f"    {i}. {link.get('text', 'N/A')} → [No URL found]")
                if link.get('category_type'):
                    print(f"       Category: {link['category_type']}")
        
        # Content Links
        content_links = nav_links.get('content', [])
        if content_links:
            print(f"\n  📄 Content Links ({len(content_links)}):")
            for i, link in enumerate(content_links, 1):
                url_display = link.get('url', 'N/A')
                if url_display and url_display != 'N/A' and url_display != 'None' and url_display != 'null':
                    print(f"    {i}. {link.get('text', 'N/A')} → {url_display}")
                else:
                    print(f"    {i}. {link.get('text', 'N/A')} → [No URL found]")
                if link.get('content_type'):
                    print(f"       Type: {link['content_type']}")
        
        # Transactional Links
        transactional_links = nav_links.get('transactional', [])
        if transactional_links:
            print(f"\n  💳 Transactional Links ({len(transactional_links)}):")
            for i, link in enumerate(transactional_links, 1):
                url_display = link.get('url', 'N/A')
                if url_display and url_display != 'N/A' and url_display != 'None' and url_display != 'null':
                    print(f"    {i}. {link.get('text', 'N/A')} → {url_display}")
                else:
                    print(f"    {i}. {link.get('text', 'N/A')} → [No URL found]")
                if link.get('transaction_type'):
                    print(f"       Type: {link['transaction_type']}")
        
        # Other Links
        other_links = nav_links.get('other', [])
        if other_links:
            print(f"\n  🔗 Other Links ({len(other_links)}):")
            for i, link in enumerate(other_links, 1):
                url_display = link.get('url', 'N/A')
                if url_display and url_display != 'N/A' and url_display != 'None' and url_display != 'null':
                    print(f"    {i}. {link.get('text', 'N/A')} → {url_display}")
                else:
                    print(f"    {i}. {link.get('text', 'N/A')} → [No URL found]")
                if link.get('link_type'):
                    print(f"       Type: {link['link_type']}")
    
    # Buttons
    buttons = data.get("buttons", [])
    if buttons:
        print(f"\n🔘 Buttons ({len(buttons)}):")
        for i, button in enumerate(buttons, 1):
            print(f"  {i}. {button.get('text', 'N/A')} ({button.get('type', 'N/A')})")
            if button.get('url'):
                print(f"     URL: {button['url']}")
            if button.get('position'):
                print(f"     Position: {button['position']}")
            if button.get('css_selector'):
                print(f"     CSS: {button['css_selector']}")
    
    # Interactive Elements
    interactive = data.get("interactive_elements", [])
    if interactive:
        print(f"\n⚡ Interactive Elements ({len(interactive)}):")
        for i, element in enumerate(interactive, 1):
            print(f"  {i}. {element.get('type', 'N/A')}: {element.get('description', 'N/A')}")
            if element.get('url'):
                print(f"     URL: {element['url']}")
            if element.get('position'):
                print(f"     Position: {element['position']}")
            if element.get('css_selector'):
                print(f"     CSS: {element['css_selector']}")
    
    # Branding
    branding = data.get("branding", [])
    if branding:
        print(f"\n🏷️  Branding Elements ({len(branding)}):")
        for i, brand in enumerate(branding, 1):
            print(f"  {i}. {brand.get('type', 'N/A')}: {brand.get('description', 'N/A')}")
            if brand.get('url'):
                print(f"     URL: {brand['url']}")
    
    # Summary
    summary = data.get("summary", {})
    if summary:
        print(f"\n📊 Summary:")
        print(f"  • Total Interactive Elements: {summary.get('total_interactive_elements', 0)}")
        print(f"  • Main Navigation Count: {summary.get('main_navigation_count', 0)}")
        print(f"  • Has Search: {'Yes' if summary.get('has_search') else 'No'}")
        print(f"  • Has User Account Features: {'Yes' if summary.get('has_user_account_features') else 'No'}")
        if summary.get('layout_style'):
            print(f"  • Layout Style: {summary['layout_style']}")
    
    print("\n" + "="*60)