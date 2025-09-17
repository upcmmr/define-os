"""
Body Analysis Module

Uses GPT-5 to analyze body images and associated HTML to extract
links, UI elements, and interactive components from website body content.
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
from urllib.parse import urljoin, urlparse

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
            
            # Remove leading > characters that might be from markdown quotes
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
                        # Clean up common JSON issues
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
        return base64.b64encode(image_file.read()).decode('utf-8')


def _load_html_content(html_path: Path) -> str:
    """Load HTML content from file."""
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()


def _preprocess_body_html_for_analysis(html_content: str, base_url: str = "") -> str:
    """
    Preprocess body HTML to convert relative URLs to absolute URLs and extract main content.
    This helps the AI find actual URLs from the body content.
    """
    from urllib.parse import urljoin, urlparse
    
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
    
    # Create processed HTML with absolute URLs
    processed_html = html_content
    
    # Replace relative URLs with absolute URLs in the HTML
    if base_url:
        for i, original_link in enumerate(href_links):
            if i < len(absolute_links) and original_link != absolute_links[i]:
                processed_html = processed_html.replace(f'href="{original_link}"', f'href="{absolute_links[i]}"')
    
    return processed_html


async def analyze_body_elements(body_image_path: Path, body_html_path: Path, url: str = "") -> Dict[str, Any]:
    """
    Analyze body image and HTML to extract links and UI elements.
    
    Args:
        body_image_path: Path to the body image file
        body_html_path: Path to the body HTML file
        url: Base URL for converting relative links to absolute
        
    Returns:
        Dictionary containing analysis results with categorized body elements
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required")
    
    client = OpenAI(api_key=api_key)
    
    # Load and encode the body image
    print("    > Loading body image...", file=sys.stderr)
    body_b64 = _encode_image_to_base64(body_image_path)
    
    # Load and preprocess HTML content
    print("    > Processing body HTML content...", file=sys.stderr)
    html_content = _load_html_content(body_html_path)
    processed_html = _preprocess_body_html_for_analysis(html_content, url)
    
    print("    > Sending request to GPT-5 for body analysis...", file=sys.stderr)
    try:
        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert web UI analyst. Analyze the provided body image and HTML "
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
Please analyze this website body content and provide a comprehensive breakdown of all interactive elements.

Website URL: {url}

Body HTML Content:
{processed_html}

CRITICAL INSTRUCTIONS:
1. Look at the body image to identify visual elements
2. Match those visual elements to the HTML code provided
3. Extract ACTUAL URLs from href attributes in the HTML - USE ABSOLUTE URLS (full URLs starting with http/https)
4. Convert any relative URLs (starting with /) to absolute URLs using the base domain
5. For each visual element you see, find its corresponding HTML tag and extract:
   - href attributes for links (convert to absolute URLs)
   - class and id attributes for CSS selectors
   - data-* attributes for JavaScript interactions

Please identify and extract:
1. All content links with their ACTUAL URLs from HTML href attributes, categorized as follows:
   - PRODUCT CATEGORIES: Links to product collections, categories, or shopping sections (e.g., "Men's", "Women's", "Electronics", "Clothing", "Sale")
   - CONTENT: Informational links (e.g., "About Us", "Blog", "Help", "FAQ", "Store Locator", "Contact", "Careers")
   - TRANSACTIONAL: Account and commerce-related links (e.g., "Login", "Sign Up", "My Account", "Cart", "Checkout", "Wishlist", "Order Status")
   - SOCIAL: Social media links (e.g., "Facebook", "Twitter", "Instagram", "YouTube")
   - OTHER: Links that don't fit the above categories
2. Buttons and their purposes with any associated actions/links
3. Interactive elements (forms, search boxes, carousels, etc.) with their HTML attributes
4. Call-to-action elements with their actual links
5. Any other clickable or interactive components in the main content area

Return your analysis as a JSON object with this structure:
{{
  "navigation_links": {{
    "product_categories": [
      {{
        "text": "Link text visible in image",
        "url": "ACTUAL URL from href attribute",
        "css_selector": "CSS selector or class from HTML",
        "position": "Description of position in body",
        "category_type": "Description of product category (e.g., 'Men's Clothing', 'Electronics', etc.)"
      }}
    ],
    "content": [
      {{
        "text": "Link text visible in image",
        "url": "ACTUAL URL from href attribute",
        "css_selector": "CSS selector or class from HTML",
        "position": "Description of position in body",
        "content_type": "Type of content (e.g., 'About Us', 'Blog', 'Help', 'Store Locator', etc.)"
      }}
    ],
    "transactional": [
      {{
        "text": "Link text visible in image",
        "url": "ACTUAL URL from href attribute",
        "css_selector": "CSS selector or class from HTML",
        "position": "Description of position in body",
        "transaction_type": "Type of transaction (e.g., 'Account', 'Cart', 'Checkout', 'Wishlist', 'Login', etc.)"
      }}
    ],
    "social": [
      {{
        "text": "Link text visible in image",
        "url": "ACTUAL URL from href attribute",
        "css_selector": "CSS selector or class from HTML",
        "position": "Description of position in body",
        "social_platform": "Social media platform (e.g., 'Facebook', 'Twitter', 'Instagram', etc.)"
      }}
    ],
    "other": [
      {{
        "text": "Link text visible in image",
        "url": "ACTUAL URL from href attribute",
        "css_selector": "CSS selector or class from HTML",
        "position": "Description of position in body",
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
      "position": "Description of position in body",
      "functionality": "Functionality description"
    }}
  ],
  "interactive_elements": [
    {{
      "type": "Element type (form, carousel, search, etc.)",
      "description": "What this element does",
      "url": "URL if applicable",
      "css_selector": "CSS selector if found",
      "position": "Description of position in body",
      "functionality": "Functionality description"
    }}
  ],
  "call_to_action": [
    {{
      "type": "CTA type (e.g., banner, hero section, promotional)",
      "description": "Description of call-to-action element",
      "url": "URL if CTA links somewhere",
      "css_selector": "CSS selector if found",
      "position": "Description of position in body",
      "functionality": "Functionality description"
    }}
  ],
  "summary": {{
    "total_interactive_elements": 0,
    "navigation_breakdown": {{
      "product_categories_count": 0,
      "content_links_count": 0,
      "transactional_links_count": 0,
      "social_links_count": 0,
      "other_links_count": 0
    }},
    "has_forms": false,
    "has_search": false,
    "has_carousel_or_slider": false,
    "layout_style": "Description of body layout and main content structure"
  }}
}}
"""
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{body_b64}"
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
            raise Exception(f"Failed to extract AI response: {str(e)}")
        
        if analysis_data:
            # Count navigation links by category
            nav_links = analysis_data.get('navigation_links', {})
            product_cat_count = len(nav_links.get('product_categories', []))
            content_count = len(nav_links.get('content', []))
            transactional_count = len(nav_links.get('transactional', []))
            social_count = len(nav_links.get('social', []))
            other_count = len(nav_links.get('other', []))
            total_nav_count = product_cat_count + content_count + transactional_count + social_count + other_count
            
            button_count = len(analysis_data.get('buttons', []))
            interactive_count = len(analysis_data.get('interactive_elements', []))
            cta_count = len(analysis_data.get('call_to_action', []))
            total_elements = total_nav_count + button_count + interactive_count + cta_count
            
            print(f"    > Body AI analysis complete: {total_elements} elements found", file=sys.stderr)
            print(f"      > Navigation: {product_cat_count} product categories, {content_count} content, {transactional_count} transactional, {social_count} social, {other_count} other", file=sys.stderr)
            print(f"      > Other: {button_count} buttons, {interactive_count} interactive elements, {cta_count} call-to-action elements", file=sys.stderr)
            
            return {
                "success": True,
                "analysis": analysis_data,
                "raw_response": raw_text,
                "image_path": str(body_image_path),
                "html_path": str(body_html_path),
                "url": url
            }
        else:
            print("    > ERROR: Body AI analysis failed to extract structured data", file=sys.stderr)
            print(f"      > Raw AI response preview: {raw_text[:300]}...", file=sys.stderr)
            raise Exception(f"Failed to extract valid JSON from AI response. AI returned malformed data. Raw response: {raw_text[:500]}")
            
    except Exception as e:
        return {
            "success": False,
            "error": f"Body AI analysis failed: {str(e)}",
            "image_path": str(body_image_path),
            "html_path": str(body_html_path),
            "url": url
        }
