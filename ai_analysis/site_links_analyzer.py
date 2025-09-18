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


def _load_html_content(html_path: Path) -> str:
    """Load HTML content from file."""
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()


def load_template_names() -> List[str]:
    """Load template names from ecommerce_dictionary.json (excluding feature elements)"""
    try:
        dict_path = Path(__file__).parent / "ecommerce_dictionary.json"
        with open(dict_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        template_names = []
        for template in data.get("templates", []):
            template_name = template.get("name", "")
            if template_name:
                template_names.append(template_name)
        
        return template_names
    except Exception as e:
        print(f"    > Warning: Failed to load template names: {str(e)}", file=sys.stderr)
        return []


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
                        "by the template/page type they most likely belong to. Analyze each link's "
                        "text and URL to determine which template category it fits best. If a link "
                        "doesn't clearly fit any template, categorize it as 'Unknown'."
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
1. Analyze each link's text and URL to determine its purpose
2. Match each link to the most appropriate template category
3. If a link doesn't clearly fit any template, put it in "Unknown"
4. Consider the typical content and functionality of each template type

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

Be thorough and logical in your categorization. Consider:
- Navigation links → Header Template
- Product category links → Category Page or Header Template
- Account/login links → My Account or Header Template  
- Shopping cart links → Cart or Header Template
- Social media links → Footer Template
- Legal/policy links → Footer Template or Content
- Search functionality → Header Template or Search Results
- Contact information → Contact Us or Footer Template
"""
                }
            ]
        )
        
        print("    > Processing categorization response...", file=sys.stderr)
        categorization_data, raw_response = _extract_json_from_response(response)
        
        if categorization_data:
            # Ensure all template categories exist, even if empty
            result = {}
            for template_name in template_names:
                result[template_name] = categorization_data.get(template_name, [])
            
            # Add Unknown category
            result["Unknown"] = categorization_data.get("Unknown", [])
            
            print(f"    > Link categorization completed successfully", file=sys.stderr)
            return {
                "success": True,
                "categorized_links": result,
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
    
    # Load HTML content
    print("    > Loading header and footer HTML content...", file=sys.stderr)
    header_html = _load_html_content(header_html_path)
    footer_html = _load_html_content(footer_html_path)
    
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
- Text links: "Women's Clothing" → "https://example.com/women"
- Logo links: "Company Logo" → "https://example.com/"
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
