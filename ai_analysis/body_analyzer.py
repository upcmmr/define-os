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


async def detect_body_template(body_image_path: Path, body_html_path: Path, url: str = "") -> Dict[str, Any]:
    """
    Detect what template type the body content represents using AI analysis.
    
    Args:
        body_image_path: Path to the body image file
        body_html_path: Path to the body HTML file
        url: URL of the page for context
        
    Returns:
        Dictionary containing template detection results with confidence score
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required")
    
    client = OpenAI(api_key=api_key)
    
    # Load and encode the body image
    print("    > Loading body image for template detection...", file=sys.stderr)
    body_b64 = _encode_image_to_base64(body_image_path)
    
    # Load and preprocess HTML content
    print("    > Processing body HTML content for template detection...", file=sys.stderr)
    html_content = _load_html_content(body_html_path)
    processed_html = _preprocess_body_html_for_analysis(html_content, url)
    
    # Extract page title from HTML if available
    page_title = ""
    try:
        import re
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html_content, re.IGNORECASE | re.DOTALL)
        if title_match:
            page_title = title_match.group(1).strip()
    except:
        pass
    
    print("    > Sending request to GPT-5 for template detection...", file=sys.stderr)
    try:
        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert web template analyst. Analyze the provided body image, HTML content, "
                        "URL, and page title to determine what type of ecommerce page template this represents. "
                        "Consider the layout, content structure, and URL patterns to make your determination. "
                        "Respond with valid JSON only."
                    )
                },
                {
                    "role": "user", 
                    "content": [
                        {
                            "type": "text",
                            "text": f"""
Please analyze this website body content and determine what template type it represents.

Website URL: {url}
Page Title: {page_title}

Body HTML Content:
{processed_html}

Available template types (use exact names):
- Homepage
- Category Page  
- Search Results
- Product Detail
- Cart
- Checkout
- My Account
- Wishlist
- Comparison Page
- Store Locator
- Contact Us
- Gift Registry
- Content

CONFIDENCE SCORING:
- 0: No confidence - Cannot determine template type
- 1: Low confidence - Some indicators but unclear
- 2: Medium confidence - Clear indicators present
- 3: High confidence - Very clear indicators (e.g., URL is domain root = Homepage)

ANALYSIS CRITERIA:
- URL patterns (e.g., "/" = Homepage, "/category/" = Category Page, "/product/" = Product Detail)
- Page title content
- Visual layout and structure from image
- HTML content structure and elements
- Presence of specific UI components

Return your analysis as a JSON object with this structure:
{{
  "template_name": "Template name from the list above",
  "confidence_score": 0-3,
  "justification": "One sentence explaining why you chose this template and confidence level",
  "url_indicators": "URL patterns that influenced the decision",
  "content_indicators": "Content/layout elements that influenced the decision"
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
        
        print("    > Processing template detection response...", file=sys.stderr)
        # Extract JSON response
        try:
            detection_data, raw_text = _extract_json_from_response(response)
        except Exception as e:
            print(f"      > Error extracting response: {str(e)}", file=sys.stderr)
            raise Exception(f"Failed to extract AI response: {str(e)}")
        
        if detection_data:
            template_name = detection_data.get('template_name', 'Unknown')
            confidence = detection_data.get('confidence_score', 0)
            justification = detection_data.get('justification', 'No justification provided')
            
            # Validate confidence score
            try:
                confidence = int(confidence)
                if confidence < 0 or confidence > 3:
                    print(f"    > Warning: Invalid confidence score {confidence}, defaulting to 0", file=sys.stderr)
                    confidence = 0
            except (ValueError, TypeError):
                print(f"    > Warning: Non-numeric confidence score '{confidence}', defaulting to 0", file=sys.stderr)
                confidence = 0
            
            print(f"    > Template detection complete: {template_name} (confidence: {confidence}/3)", file=sys.stderr)
            print(f"      > Justification: {justification}", file=sys.stderr)
            
            return {
                "success": True,
                "template_name": template_name,
                "confidence_score": confidence,
                "justification": justification,
                "url_indicators": detection_data.get('url_indicators', ''),
                "content_indicators": detection_data.get('content_indicators', ''),
                "raw_response": raw_text,
                "image_path": str(body_image_path),
                "html_path": str(body_html_path),
                "url": url,
                "page_title": page_title
            }
        else:
            print("    > ERROR: Template detection failed to extract structured data", file=sys.stderr)
            raise Exception(f"Failed to extract valid JSON from AI response. Raw response: {raw_text[:500]}")
            
    except Exception as e:
        return {
            "success": False,
            "error": f"Template detection failed: {str(e)}",
            "image_path": str(body_image_path),
            "html_path": str(body_html_path),
            "url": url
        }


async def analyze_template_features(body_image_path: Path, body_html_path: Path, template_name: str, url: str = "") -> Dict[str, Any]:
    """
    Analyze body content against a specific template to identify features.
    
    Args:
        body_image_path: Path to the body image file
        body_html_path: Path to the body HTML file
        template_name: Name of the template to analyze against
        url: Base URL for context
        
    Returns:
        Dictionary containing template feature analysis results
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required")
    
    client = OpenAI(api_key=api_key)
    
    # Load the ecommerce dictionary to get template features
    print(f"    > Loading template features for {template_name}...", file=sys.stderr)
    try:
        script_dir = Path(__file__).parent
        dict_path = script_dir / "ecommerce_dictionary.json"
        
        with open(dict_path, 'r', encoding='utf-8') as f:
            ecommerce_dict = json.load(f)
        
        # Find the template with robust matching
        template_data = None
        templates = ecommerce_dict.get('templates', [])
        
        # First try exact match (case insensitive)
        for template in templates:
            if template.get('name', '').lower() == template_name.lower():
                template_data = template
                break
        
        # If no exact match, try partial matching (for robustness)
        if not template_data:
            for template in templates:
                template_name_clean = template.get('name', '').lower().replace(' template', '')
                if template_name_clean == template_name.lower():
                    template_data = template
                    break
        
        # If still no match, try fuzzy matching on key words
        if not template_data:
            template_name_words = set(template_name.lower().split())
            best_match = None
            best_score = 0
            
            for template in templates:
                template_words = set(template.get('name', '').lower().replace(' template', '').split())
                common_words = template_name_words.intersection(template_words)
                if len(common_words) > best_score:
                    best_score = len(common_words)
                    best_match = template
            
            if best_match and best_score > 0:
                template_data = best_match
                print(f"    > Using fuzzy match: '{template_name}' -> '{template_data.get('name')}'", file=sys.stderr)
        
        if not template_data:
            raise Exception(f"Template '{template_name}' not found in ecommerce dictionary. Available templates: {[t.get('name') for t in templates]}")
            
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to load template: {str(e)}",
            "template_name": template_name
        }
    
    # Load and encode the body image
    print("    > Loading body image for feature analysis...", file=sys.stderr)
    body_b64 = _encode_image_to_base64(body_image_path)
    
    # Load and preprocess HTML content
    print("    > Processing body HTML content for feature analysis...", file=sys.stderr)
    html_content = _load_html_content(body_html_path)
    processed_html = _preprocess_body_html_for_analysis(html_content, url)
    
    # Build feature list for analysis
    features_text = ""
    for i, feature in enumerate(template_data.get('features', []), 1):
        features_text += f"{i}. {feature.get('name', 'Unknown')}: {feature.get('description', 'No description')}\n"
    
    print(f"    > Sending request to GPT-5 for {template_name} feature analysis...", file=sys.stderr)
    try:
        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are an expert web UI analyst specializing in {template_name} pages. "
                        "Analyze the provided image and HTML to determine which template features are present. "
                        "Look carefully at both the visual elements in the image and the HTML structure. "
                        "Respond with valid JSON only."
                    )
                },
                {
                    "role": "user", 
                    "content": [
                        {
                            "type": "text",
                            "text": f"""
Please analyze this {template_name} page and determine which features are present.

Website URL: {url}

HTML Content:
{processed_html}

Template Features to Check:
{features_text}

INSTRUCTIONS:
1. Look at the body image to identify visual elements
2. Cross-reference with the HTML code provided
3. For each feature listed above, determine if it's present ("yes") or not present ("no")
4. Base your decision on both visual evidence from the image AND HTML structure
5. Be thorough but conservative - only mark "yes" if you can clearly see evidence

Return your analysis as a JSON object with this structure:
{{
  "name": "{template_name}",
  "description": "{template_data.get('description', '')}",
  "features": [
    {{
      "name": "Feature Name",
      "description": "Feature Description", 
      "found": "yes" or "no"
    }}
  ]
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
        
        print("    > Processing feature analysis response...", file=sys.stderr)
        # Extract JSON response
        try:
            analysis_data, raw_text = _extract_json_from_response(response)
        except Exception as e:
            print(f"      > Error extracting response: {str(e)}", file=sys.stderr)
            raise Exception(f"Failed to extract AI response: {str(e)}")
        
        if analysis_data:
            features = analysis_data.get('features', [])
            found_count = sum(1 for f in features if f.get('found') == 'yes')
            total_count = len(features)
            
            print(f"    > {template_name} feature analysis complete: {found_count}/{total_count} features found", file=sys.stderr)
            
            return {
                "success": True,
                "template_analysis": analysis_data,
                "image_path": str(body_image_path),
                "html_path": str(body_html_path),
                "url": url,
                "raw_response": raw_text
            }
        else:
            print("    > ERROR: Feature analysis failed to extract structured data", file=sys.stderr)
            raise Exception(f"Failed to extract valid JSON from AI response. Raw response: {raw_text[:500]}")
            
    except Exception as e:
        return {
            "success": False,
            "error": f"Template feature analysis failed: {str(e)}",
            "template_name": template_name,
            "image_path": str(body_image_path),
            "html_path": str(body_html_path),
            "url": url
        }


async def analyze_body_elements(body_image_path: Path, body_html_path: Path, url: str = "") -> Dict[str, Any]:
    """
    Analyze body image and HTML with template detection and feature analysis.
    
    Args:
        body_image_path: Path to the body image file
        body_html_path: Path to the body HTML file
        url: Base URL for converting relative links to absolute
        
    Returns:
        Dictionary containing analysis results with template detection and features
    """
    try:
        # Step 1: Detect template type
        print("  > Step 1: Detecting template type...", file=sys.stderr)
        template_detection = await detect_body_template(body_image_path, body_html_path, url)
        
        if not template_detection.get("success", False):
            return {
                "success": False,
                "error": f"Template detection failed: {template_detection.get('error', 'Unknown error')}",
                "image_path": str(body_image_path),
                "html_path": str(body_html_path),
                "url": url
            }
        
        template_name = template_detection.get("template_name", "Unknown")
        confidence_score = template_detection.get("confidence_score", 0)
        justification = template_detection.get("justification", "No justification provided")
        
        # Step 2: Check confidence level
        if confidence_score <= 1:
            print(f"  > Low confidence ({confidence_score}/3) - returning template not known", file=sys.stderr)
            return {
                "success": True,
                "template_detection": template_detection,
                "template_not_known": True,
                "template_name": template_name,
                "confidence_score": confidence_score,
                "justification": justification,
                "image_path": str(body_image_path),
                "html_path": str(body_html_path),
                "url": url
            }
        
        # Step 3: Perform template-specific feature analysis
        print(f"  > Step 2: Analyzing {template_name} features (confidence: {confidence_score}/3)...", file=sys.stderr)
        feature_analysis = await analyze_template_features(body_image_path, body_html_path, template_name, url)
        
        if not feature_analysis.get("success", False):
            return {
                "success": False,
                "error": f"Feature analysis failed: {feature_analysis.get('error', 'Unknown error')}",
                "template_detection": template_detection,
                "image_path": str(body_image_path),
                "html_path": str(body_html_path),
                "url": url
            }
        
        # Combine results
        return {
            "success": True,
            "template_detection": template_detection,
            "template_analysis": feature_analysis.get("template_analysis"),
            "template_name": template_name,
            "confidence_score": confidence_score,
            "justification": justification,
            "image_path": str(body_image_path),
            "html_path": str(body_html_path),
            "url": url,
            "raw_response": feature_analysis.get("raw_response", "")
        }
            
    except Exception as e:
        return {
            "success": False,
            "error": f"Body analysis failed: {str(e)}",
            "image_path": str(body_image_path),
            "html_path": str(body_html_path),
            "url": url
        }
