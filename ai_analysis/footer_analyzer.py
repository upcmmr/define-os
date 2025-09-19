"""
Footer Analysis Module - Template-Based Approach

Uses GPT-4 to analyze footer images and HTML against the ecommerce dictionary
template to identify which features are present or absent.
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


def load_footer_template() -> dict:
    """Load the Footer Template section from ecommerce_dictionary.json"""
    try:
        dict_path = Path(__file__).parent / "ecommerce_dictionary.json"
        with open(dict_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Find the Footer Template
        for template in data.get("templates", []):
            if template.get("name") == "Footer Template":
                return template
        
        raise ValueError("Footer Template not found in ecommerce_dictionary.json")
    except Exception as e:
        raise Exception(f"Failed to load footer template: {str(e)}")


async def detect_custom_features(footer_image_path: Path, footer_html_path: Path, standard_features: List[Dict], url: str = "") -> Dict[str, Any]:
    """
    Second AI call to identify custom features not in the standard footer template.
    
    Args:
        footer_image_path: Path to the footer image file
        footer_html_path: Path to the footer HTML file
        standard_features: List of already identified standard features
        url: Base URL for context
        
    Returns:
        Dictionary containing custom features analysis results
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required")
    
    client = OpenAI(api_key=api_key)
    
    # Encode image
    try:
        footer_b64 = _encode_image_to_base64(footer_image_path)
    except Exception as e:
        raise Exception(f"Failed to encode footer image: {str(e)}")
    
    # Read HTML content
    try:
        with open(footer_html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        processed_html = html_content[:32000]  # Adaptive limit for footer custom features
    except Exception as e:
        raise Exception(f"Failed to read footer HTML: {str(e)}")
    
    # Format standard features for the prompt
    found_features = [f"- {f['name']}: {f['description']}" for f in standard_features if f.get('found') == 'yes']
    standard_features_text = "\n".join(found_features) if found_features else "None detected"
    
    print(f"    > Sending request to GPT-5-mini for custom footer features detection...", file=sys.stderr)
    try:
        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert web UI analyst specializing in identifying unique custom features in website footers. "
                        "Your task is to find additional functionality that goes beyond standard footer template features. "
                        "Focus on unique widgets, custom sections, special tools, or innovative UI elements in the footer area. "
                        "Respond with valid JSON only."
                    )
                },
                {
                    "role": "user", 
                    "content": [
                        {
                            "type": "text",
                            "text": f"""
Please analyze this website footer and identify CUSTOM features that are NOT in the standard footer template.

Website URL: {url}

HTML Content:
{processed_html}

STANDARD FOOTER FEATURES ALREADY IDENTIFIED:
{standard_features_text}

INSTRUCTIONS:
1. Look at the footer screenshot and HTML for additional functionality beyond the standard features listed above
2. Identify unique/custom elements specific to this footer or site
3. Focus on features that provide special functionality, custom widgets, unique sections, or innovative UI elements
4. Examples might include: Custom newsletter signup forms, special social media integrations, unique contact widgets, custom maps, interactive elements, special promotional sections, etc.
5. Only return features that are clearly visible and functional in the screenshot/HTML
6. Return 2-4 most significant custom footer features (if any exist)
7. If no significant custom features are found, return an empty array

NAMING REQUIREMENTS:
- **Name**: Keep it SHORT (2-4 words max) - concise feature identifier
- **Description**: Keep it BRIEF (1-2 sentences max) - what it does, not why it's unique

Return your analysis as a JSON object with this structure:
{{
  "custom_features": [
    {{
      "name": "Newsletter Signup",
      "description": "Email subscription form with promotional offers and updates."
    }},
    {{
      "name": "Store Locator",
      "description": "Interactive map showing nearby physical store locations."
    }}
  ]
}}
"""
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{footer_b64}"
                            }
                        }
                    ]
                }
            ]
        )
        
        print("    > Processing custom footer features detection response...", file=sys.stderr)
        # Extract JSON response
        try:
            analysis_data, raw_text = _extract_json_from_response(response)
        except Exception as e:
            print(f"      > Error extracting response: {str(e)}", file=sys.stderr)
            raise Exception(f"Failed to extract AI response: {str(e)}")
        
        if analysis_data:
            custom_features = analysis_data.get('custom_features', [])
            features_count = len(custom_features)
            
            print(f"    > Custom footer features detection complete: {features_count} custom features found", file=sys.stderr)
            
            return {
                "success": True,
                "custom_features": custom_features,
                "image_path": str(footer_image_path),
                "html_path": str(footer_html_path),
                "url": url,
                "raw_response": raw_text
            }
        else:
            print("    > ERROR: Custom footer features detection failed to extract structured data", file=sys.stderr)
            raise Exception(f"Failed to extract valid JSON from AI response. Raw response: {raw_text[:500]}")
            
    except Exception as e:
        return {
            "success": False,
            "error": f"Custom footer features detection failed: {str(e)}",
            "image_path": str(footer_image_path),
            "html_path": str(footer_html_path),
            "url": url
        }


async def analyze_footer_elements(footer_image_path: Path, footer_html_path: Path, url: str = "") -> Dict[str, Any]:
    """
    Analyze footer image and HTML against ecommerce template to identify features.
    
    Args:
        footer_image_path: Path to the footer screenshot
        footer_html_path: Path to the footer-specific HTML file
        url: Base URL for context
        
    Returns:
        Dictionary containing template-based feature analysis results
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required")
    
    client = OpenAI(api_key=api_key)
    
    # Load the footer template from ecommerce dictionary
    print("    > Loading footer template...", file=sys.stderr)
    try:
        footer_template = load_footer_template()
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to load footer template: {str(e)}",
            "image_path": str(footer_image_path),
            "html_path": str(footer_html_path),
            "url": url
        }
    
    # Load and encode the footer image
    print("    > Loading footer image...", file=sys.stderr)
    footer_b64 = _encode_image_to_base64(footer_image_path)
    
    # Load footer HTML content
    print("    > Processing footer HTML content...", file=sys.stderr)
    html_content = _load_html_content(footer_html_path)
    # Adaptive HTML size limit for footers (32KB to cover all experienced files)
    html_content = html_content[:32000]
    
    print("    > Sending request to GPT-4...", file=sys.stderr)
    try:
        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert ecommerce UI analyst. You will be given a footer image, "
                        "footer HTML, and a template of ecommerce features to look for. "
                        "Your job is to determine which features from the template are present "
                        "in this footer by analyzing both the visual image and the HTML code. "
                        "Respond with valid JSON only."
                    )
                },
                {
                    "role": "user", 
                    "content": [
                        {
                            "type": "text",
                            "text": f"""
Please analyze this website footer against the provided ecommerce template.

**Website URL:** {url}

**Footer Template to Check:**
{json.dumps(footer_template, indent=2)}

**Footer HTML Content:**
```html
{html_content}
```

**Instructions:**
1. Review each feature in the template's "features" array
2. Look at both the footer image and HTML to determine if each feature is present
3. Return the EXACT same JSON structure as the template, but add a "found" field to each feature
4. Set "found": "yes" if the feature is clearly present, "found": "no" if it's not present

**Return Format:**
Return the template JSON with each feature having an additional "found" field:
```json
{{
    "name": "Footer Template",
    "description": "...",
    "features": [
        {{
            "name": "Footer Navigation Links",
            "description": "...",
            "found": "yes"
        }},
        {{
            "name": "Social Media Links", 
            "description": "...",
            "found": "no"
        }}
    ]
}}
```

Be thorough but conservative - only mark "found": "yes" if you can clearly identify the feature in either the image or HTML.
"""
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
        
        print("    > Processing GPT-4 response...", file=sys.stderr)
        analysis_data, raw_response = _extract_json_from_response(response)
        
        if analysis_data:
            print("    > Footer template analysis completed successfully", file=sys.stderr)
            
            # Step 2: Detect custom features not in the standard template
            print("    > Detecting custom footer features...", file=sys.stderr)
            standard_features = analysis_data.get("features", [])
            custom_features_analysis = await detect_custom_features(footer_image_path, footer_html_path, standard_features, url)
            
            # Combine results (include custom features even if detection failed)
            result = {
                "success": True,
                "template_analysis": analysis_data,
                "image_path": str(footer_image_path),
                "html_path": str(footer_html_path),
                "url": url,
                "raw_response": raw_response
            }
            
            # Add custom features if detection was successful
            if custom_features_analysis.get("success", False):
                result["custom_features"] = custom_features_analysis.get("custom_features", [])
                print(f"    > Custom footer features integrated: {len(result['custom_features'])} features", file=sys.stderr)
            else:
                result["custom_features"] = []
                print(f"    > Custom footer features detection failed: {custom_features_analysis.get('error', 'Unknown error')}", file=sys.stderr)
            
            return result
        else:
            print("    > Failed to parse JSON from GPT-4 response", file=sys.stderr)
            return {
                "success": False,
                "error": "Failed to parse JSON from AI response",
                "image_path": str(footer_image_path),
                "html_path": str(footer_html_path),
                "url": url,
                "raw_response": raw_response
            }
            
    except Exception as e:
        print(f"    > Error during footer analysis: {str(e)}", file=sys.stderr)
        return {
            "success": False,
            "error": f"Footer AI analysis failed: {str(e)}",
            "image_path": str(footer_image_path),
            "html_path": str(footer_html_path),
            "url": url
        }


def print_analysis_results(analysis: Dict[str, Any]) -> None:
    """
    Print analysis results in a formatted way for command line output.
    """
    if not analysis.get("success", False):
        print(f"❌ Analysis failed: {analysis.get('error', 'Unknown error')}")
        return
    
    template_data = analysis.get("template_analysis", {})
    features = template_data.get("features", [])
    
    print(f"\n🎯 Footer Template Analysis Results")
    print(f"📄 Template: {template_data.get('name', 'Unknown')}")
    print(f"🌐 URL: {analysis.get('url', 'Unknown')}")
    print(f"📊 Features Found: {sum(1 for f in features if f.get('found') == 'yes')}/{len(features)}")
    
    print(f"\n✅ **Features Present:**")
    for feature in features:
        if feature.get("found") == "yes":
            print(f"  • {feature.get('name', 'Unknown')}")
    
    print(f"\n❌ **Features Not Found:**")
    for feature in features:
        if feature.get("found") == "no":
            print(f"  • {feature.get('name', 'Unknown')}")


# For command line testing
if __name__ == "__main__":
    import asyncio
    
    if len(sys.argv) != 4:
        print("Usage: python footer_analyzer_new.py <footer_image_path> <footer_html_path> <url>")
        sys.exit(1)
    
    footer_image_path = Path(sys.argv[1])
    footer_html_path = Path(sys.argv[2])
    url = sys.argv[3]
    
    async def main():
        result = await analyze_footer_elements(footer_image_path, footer_html_path, url)
        print_analysis_results(result)
        print(f"\nFull result: {json.dumps(result, indent=2)}")
    
    asyncio.run(main())
