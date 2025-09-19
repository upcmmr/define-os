"""
Site Links Analysis Module

Uses GPT-4 to analyze header and footer images and HTML to extract all links
(both text and image/icon links) and return them as a simple bullet list.
Now includes template categorization functionality.
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
    """Extract JSON from GPT-4 Chat Completions API output with robust error handling."""
    data = None
    
    # Extract text from chat completions response
    try:
        raw_text = resp.choices[0].message.content.strip()
    except (AttributeError, IndexError):
        raw_text = str(resp)
    
    # Try to extract JSON from the response
    try:
        # First, try to parse the entire response as JSON
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        # If that fails, try to find JSON within code blocks
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # If still no luck, try to find any JSON-like structure
        if data is None:
            json_match = re.search(r'(\{.*\})', raw_text, re.DOTALL)
            if json_match:
                try:
                    data = json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    pass
    
    return data, raw_text


def _encode_image_to_base64(image_path: Path) -> str:
    """Encode an image file to base64 string."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def _chunk_html_content(html_content: str, chunk_size: int = 48000) -> List[str]:
    """
    Split HTML content into chunks of specified size while trying to preserve structure.
    
    Args:
        html_content: The HTML content to chunk
        chunk_size: Maximum size of each chunk in characters
        
    Returns:
        List of HTML chunks
    """
    if len(html_content) <= chunk_size:
        return [html_content]
    
    chunks = []
    current_pos = 0
    
    while current_pos < len(html_content):
        # Calculate end position for this chunk
        end_pos = min(current_pos + chunk_size, len(html_content))
        
        # If we're not at the end of the content, try to find a good break point
        if end_pos < len(html_content):
            # Look for tag boundaries within the last 1000 characters
            search_start = max(end_pos - 1000, current_pos)
            
            # Try to find closing tags as good break points
            break_points = []
            for tag in ['</div>', '</section>', '</nav>', '</ul>', '</ol>', '</li>', '</a>']:
                pos = html_content.rfind(tag, search_start, end_pos)
                if pos > search_start:
                    break_points.append(pos + len(tag))
            
            # Use the latest break point if found
            if break_points:
                end_pos = max(break_points)
        
        # Extract chunk
        chunk = html_content[current_pos:end_pos]
        if chunk.strip():  # Only add non-empty chunks
            chunks.append(chunk)
        
        current_pos = end_pos
    
    return chunks


def _load_html_content(html_path: Path) -> str:
    """Load HTML content from file."""
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()


def load_template_names() -> List[str]:
    """Load template names from ecommerce_dictionary.json (excluding feature elements and header/footer templates)"""
    try:
        dict_path = Path(__file__).parent / "ecommerce_dictionary.json"
        with open(dict_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        template_names = []
        excluded_templates = {"Header Template", "Footer Template"}
        
        for template in data.get("templates", []):
            template_name = template.get("name", "")
            if template_name and template_name not in excluded_templates:
                template_names.append(template_name)
        
        return template_names
    except Exception as e:
        print(f"    > Warning: Failed to load template names: {str(e)}", file=sys.stderr)
        return []


def extract_brand_name_from_url(url: str) -> str:
    """Extract a clean brand name from the URL domain."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        # Remove common prefixes
        if domain.startswith('www.'):
            domain = domain[4:]
        
        # Remove common TLD extensions
        domain_parts = domain.split('.')
        if len(domain_parts) > 1:
            # Take the main domain name (before the TLD)
            brand_name = domain_parts[0]
        else:
            brand_name = domain
        
        # Clean up the brand name - capitalize first letter of each word
        brand_name = brand_name.replace('-', ' ').replace('_', ' ')
        brand_name = ' '.join(word.capitalize() for word in brand_name.split())
        
        return brand_name
    except Exception as e:
        print(f"    > Warning: Could not extract brand name from URL {url}: {str(e)}", file=sys.stderr)
        return "Homepage"


def is_homepage_url(link_url: str, base_url: str) -> bool:
    """Check if a link URL points to the homepage."""
    try:
        from urllib.parse import urlparse, urljoin
        
        # Normalize URLs
        base_parsed = urlparse(base_url)
        link_parsed = urlparse(link_url)
        
        # If different domains, not homepage
        if link_parsed.netloc and link_parsed.netloc != base_parsed.netloc:
            return False
        
        # Check common homepage patterns
        path = link_parsed.path.lower().rstrip('/')
        return path in ['', '/', '/index.html', '/index.php', '/home']
        
    except Exception:
        return False


def process_homepage_links(links: List[Dict[str, str]], base_url: str) -> List[Dict[str, str]]:
    """Process links to handle homepage special case - ensure only one homepage link with brand name."""
    if not links:
        return links
    
    brand_name = extract_brand_name_from_url(base_url)
    homepage_link = None
    other_links = []
    
    # Find homepage links and separate them
    for link in links:
        if is_homepage_url(link.get('url', ''), base_url):
            if not homepage_link:  # Keep only the first homepage link found
                homepage_link = {
                    'text': brand_name,  # Use clean brand name
                    'url': link['url']
                }
        else:
            other_links.append(link)
    
    # Construct final list with homepage first (if found)
    result = []
    if homepage_link:
        result.append(homepage_link)
    result.extend(other_links)
    
    return result


async def categorize_links_by_template(links: List[Dict[str, str]], template_names: List[str]) -> Dict[str, Any]:
    """
    Use AI to categorize links by template type.
    
    Args:
        links: List of links with 'text' and 'url' keys
        template_names: List of template names from the dictionary
        
    Returns:
        Dictionary with categorized links
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required")
    
    client = OpenAI(api_key=api_key)
    
    # Prepare links text for AI analysis
    links_text = ""
    for i, link in enumerate(links, 1):
        links_text += f"{i}. {link.get('text', 'Untitled')} → {link.get('url', 'No URL')}\n"
    
    # Prepare template names text
    templates_text = "\n".join([f"- {name}" for name in template_names])
    
    print("    > Categorizing links by template...", file=sys.stderr)
    try:
        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert web analyst. Your job is to categorize website links "
                        "by the template/page type they POINT TO (their destination). Analyze each link's "
                        "text and URL to determine what type of page the user will land on when they click it. "
                        "Focus on the destination page type, not where the link is located on the current page. "
                        "If a link doesn't clearly fit any template, categorize it as 'Unknown'."
                    )
                },
                {
                    "role": "user",
                    "content": f"""
Please categorize the following links by template type.

**Available Templates:**
{templates_text}

**Links to Categorize:**
{links_text}

**Instructions:**
1. Analyze each link's text and URL to determine what type of page it leads to
2. Match each link to the template category that represents its DESTINATION page type
3. If a link doesn't clearly fit any template, put it in "Unknown"
4. Focus on where the link takes the user, not where the link is found on the current page

**Return Format:**
Return a JSON object with template names as keys and arrays of link objects as values:
```json
{{
    "Header Template": [
        {{"text": "Link name", "url": "https://example.com/path"}}
    ],
    "Homepage": [
        {{"text": "Link name", "url": "https://example.com/path"}}
    ],
    "Unknown": [
        {{"text": "Link name", "url": "https://example.com/path"}}
    ]
}}
```

Be thorough and logical in your categorization based on DESTINATION page type:
- Links to product categories → Category Page
- Links to individual products → Product Detail
- Links to shopping cart → Cart
- Links to checkout process → Checkout
- Links to user account/login → My Account
- Links to wishlist/favorites → Wishlist
- Links to search results → Search Results
- Links to store locations → Store Locator
- Links to contact forms/info → Contact Us
- Links to homepage/brand → Homepage
- Links to policies/help/about → Content
- Links to product comparison → Comparison Page
- Links to gift registries → Gift Registry
- External social media links → Content (if they're just social links)
- Links that don't fit above categories → Unknown
"""
                }
            ]
        )
        
        print("    > Processing categorization response...", file=sys.stderr)
        categorization_data, raw_response = _extract_json_from_response(response)
        
        if categorization_data:
            # Ensure template categories are in the correct order from the dictionary
            result = {}
            for template_name in template_names:
                template_links = categorization_data.get(template_name, [])
                # Only include template categories that have links
                if template_links:
                    result[template_name] = template_links
            
            # Add Unknown category if it has links
            unknown_links = categorization_data.get("Unknown", [])
            if unknown_links:
                result["Unknown"] = unknown_links
            
            print(f"    > Link categorization completed successfully", file=sys.stderr)
            return {
                "success": True,
                "categorized_links": result,
                "template_order": template_names,  # Preserve original order
                "raw_response": raw_response
            }
        else:
            print("    > Failed to parse categorization from AI response", file=sys.stderr)
            return {
                "success": False,
                "error": "Failed to parse categorization from AI response",
                "raw_response": raw_response
            }
            
    except Exception as e:
        print(f"    > Error during link categorization: {str(e)}", file=sys.stderr)
        return {
            "success": False,
            "error": f"Link categorization failed: {str(e)}"
        }


async def analyze_site_links(header_image_path: Path, header_html_path: Path, 
                           footer_image_path: Path, footer_html_path: Path, 
                           url: str = "") -> Dict[str, Any]:
    """
    Analyze header and footer images and HTML to extract all links.
    
    Args:
        header_image_path: Path to the header screenshot
        header_html_path: Path to the header HTML file
        footer_image_path: Path to the footer screenshot
        footer_html_path: Path to the footer HTML file
        url: Base URL for context
        
    Returns:
        Dictionary containing all discovered links
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required")
    
    client = OpenAI(api_key=api_key)
    
    # Load and encode images
    print("    > Loading header and footer images...", file=sys.stderr)
    header_b64 = _encode_image_to_base64(header_image_path)
    footer_b64 = _encode_image_to_base64(footer_image_path)
    
    # Load HTML content with chunking
    print("    > Loading header and footer HTML content...", file=sys.stderr)
    header_html_full = _load_html_content(header_html_path)
    footer_html_full = _load_html_content(footer_html_path)
    
    # Use chunking for large HTML content (48KB chunks)
    header_chunks = _chunk_html_content(header_html_full, 48000)
    footer_chunks = _chunk_html_content(footer_html_full, 48000)
    
    print(f"    > Header split into {len(header_chunks)} chunks, Footer split into {len(footer_chunks)} chunks", file=sys.stderr)
    
    # Use the first chunk of each for link analysis (contains most navigation)
    header_html = header_chunks[0] if header_chunks else ""
    footer_html = footer_chunks[0] if footer_chunks else ""
    
    print("    > Sending request to GPT-5-mini...", file=sys.stderr)
    try:
        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert web analyst. Your job is to extract ALL links from "
                        "the provided header and footer images and HTML. Include both text links "
                        "and image/icon links. Return only a simple JSON list of links with "
                        "their names and URLs. Be thorough and include every clickable element."
                    )
                },
                {
                    "role": "user", 
                    "content": [
                        {
                            "type": "text",
                            "text": f"""
Please analyze the header and footer images and HTML to extract ALL links.

**Website URL:** {url}
**Brand Name:** {extract_brand_name_from_url(url)}

**Header HTML:**
```html
{header_html}
```

**Footer HTML:**
```html
{footer_html}
```

**Instructions:**
1. Look at both header and footer images to identify all clickable elements
2. Match visual elements to HTML href attributes
3. Include both text links and image/icon links (logos, social media icons, etc.)
4. Extract the actual URLs from href attributes
5. Convert relative URLs to absolute URLs using the base domain
6. Include ALL links - navigation, utility, social, legal, etc.

**SPECIAL HOMEPAGE HANDLING:**
- If you find a logo or main brand link that goes to the homepage (/, /index.html, or the root domain), name it EXACTLY as the brand name only
- For example: "Marine Layer" NOT "Marine Layer Logo" or "Marine Layer Home"
- There should be only ONE homepage link with the clean brand name
- Remove any duplicate homepage links

**Return Format:**
Return a simple JSON object with an array of links:
```json
{{
    "links": [
        {{
            "text": "Link name or description",
            "url": "https://full-url.com/path"
        }}
    ]
}}
```

**Examples:**
- Homepage logo: "{extract_brand_name_from_url(url)}" → "{url if url.endswith('/') else url + '/'}"
- Text links: "Women's Clothing" → "https://example.com/women"
- Social icons: "Facebook Icon" → "https://facebook.com/company"
- Utility links: "My Account" → "https://example.com/account"

Be comprehensive - include every single clickable link you can find in both sections.
"""
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{header_b64}",
                                "detail": "high"
                            }
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{footer_b64}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ]
        )
        
        print("    > Processing GPT-5-mini response...", file=sys.stderr)
        analysis_data, raw_response = _extract_json_from_response(response)
        
        if analysis_data and 'links' in analysis_data:
            links = analysis_data['links']
            
            # Process homepage links to ensure proper naming and ordering
            print(f"    > Processing homepage links...", file=sys.stderr)
            links = process_homepage_links(links, url)
            
            link_count = len(links)
            print(f"    > Site links analysis completed successfully - found {link_count} links", file=sys.stderr)
            
            # Load template names and categorize links
            template_names = load_template_names()
            print(f"    > Loaded {len(template_names)} template names", file=sys.stderr)
            categorization_result = None
            
            if template_names and links:
                print(f"    > Starting categorization of {len(links)} links...", file=sys.stderr)
                categorization_result = await categorize_links_by_template(links, template_names)
                print(f"    > Categorization completed", file=sys.stderr)
            else:
                print(f"    > Skipping categorization - templates: {len(template_names)}, links: {len(links)}", file=sys.stderr)
            
            return {
                "success": True,
                "links": links,
                "categorization": categorization_result,
                "header_image_path": str(header_image_path),
                "header_html_path": str(header_html_path),
                "footer_image_path": str(footer_image_path),
                "footer_html_path": str(footer_html_path),
                "url": url,
                "raw_response": raw_response
            }
        else:
            print("    > Failed to parse links from GPT-4 response", file=sys.stderr)
            return {
                "success": False,
                "error": "Failed to parse links from AI response",
                "header_image_path": str(header_image_path),
                "header_html_path": str(header_html_path),
                "footer_image_path": str(footer_image_path),
                "footer_html_path": str(footer_html_path),
                "url": url,
                "raw_response": raw_response
            }
            
    except Exception as e:
        print(f"    > Error during site links analysis: {str(e)}", file=sys.stderr)
        return {
            "success": False,
            "error": f"Site links AI analysis failed: {str(e)}",
            "header_image_path": str(header_image_path),
            "header_html_path": str(header_html_path),
            "footer_image_path": str(footer_image_path),
            "footer_html_path": str(footer_html_path),
            "url": url
        }


def print_analysis_results(analysis: Dict[str, Any]) -> None:
    """
    Print analysis results in a formatted way for command line output.
    """
    if not analysis.get("success", False):
        print(f"Analysis failed: {analysis.get('error', 'Unknown error')}", file=sys.stderr)
        return
    
    links = analysis.get("links", [])
    
    print(f"\nSite Links Analysis Results", file=sys.stderr)
    print(f"URL: {analysis.get('url', 'Unknown')}", file=sys.stderr)
    print(f"Total Links Found: {len(links)}", file=sys.stderr)
    
    print(f"\nAll Links:", file=sys.stderr)
    for i, link in enumerate(links, 1):
        print(f"  {i}. {link.get('text', 'Untitled')} -> {link.get('url', 'No URL')}", file=sys.stderr)


# For command line testing
if __name__ == "__main__":
    import asyncio
    
    if len(sys.argv) != 6:
        print("Usage: python site_links_analyzer.py <header_image> <header_html> <footer_image> <footer_html> <url>", file=sys.stderr)
        sys.exit(1)
    
    header_image_path = Path(sys.argv[1])
    header_html_path = Path(sys.argv[2])
    footer_image_path = Path(sys.argv[3])
    footer_html_path = Path(sys.argv[4])
    url = sys.argv[5]
    
    async def main():
        result = await analyze_site_links(header_image_path, header_html_path, 
                                        footer_image_path, footer_html_path, url)
        # For command line usage, print human-readable results to stderr
        # and JSON to stdout for programmatic use
        print_analysis_results(result)
        # Output JSON to stdout for the backend to parse
        print(f"    > Outputting JSON result to stdout", file=sys.stderr)
        print(json.dumps(result))
    
    asyncio.run(main())
