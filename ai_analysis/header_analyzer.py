"""
Header Analysis Module - Template-Based Approach

Uses GPT-5 to analyze header images and HTML against the ecommerce dictionary
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
    """Extract JSON from GPT-5 Chat Completions API output with robust error handling."""
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


def load_header_template() -> dict:
    """Load the Header Template section from ecommerce_dictionary.json"""
    try:
        dict_path = Path(__file__).parent / "ecommerce_dictionary.json"
        with open(dict_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Find the Header Template
        for template in data.get("templates", []):
            if template.get("name") == "Header Template":
                return template
        
        raise ValueError("Header Template not found in ecommerce_dictionary.json")
    except Exception as e:
        raise Exception(f"Failed to load header template: {str(e)}")


async def analyze_header_elements(header_image_path: Path, header_html_path: Path, url: str = "") -> Dict[str, Any]:
    """
    Analyze header image and HTML against ecommerce template to identify features.
    
    Args:
        header_image_path: Path to the header screenshot
        header_html_path: Path to the header-specific HTML file
        url: Base URL for context
        
    Returns:
        Dictionary containing template-based feature analysis results
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required")
    
    client = OpenAI(api_key=api_key)
    
    # Load the header template from ecommerce dictionary
    print("    > Loading header template...", file=sys.stderr)
    try:
        header_template = load_header_template()
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to load header template: {str(e)}",
            "image_path": str(header_image_path),
            "html_path": str(header_html_path),
            "url": url
        }
    
    # Load and encode the header image
    print("    > Loading header image...", file=sys.stderr)
    header_b64 = _encode_image_to_base64(header_image_path)
    
    # Load header HTML content
    print("    > Processing header HTML content...", file=sys.stderr)
    html_content = _load_html_content(header_html_path)
    
    print("    > Sending request to GPT-5...", file=sys.stderr)
    try:
        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert ecommerce UI analyst. You will be given a header image, "
                        "header HTML, and a template of ecommerce features to look for. "
                        "Your job is to determine which features from the template are present "
                        "in this header by analyzing both the visual image and the HTML code. "
                        "Respond with valid JSON only."
                    )
                },
                {
                    "role": "user", 
                    "content": [
                        {
                            "type": "text",
                            "text": f"""
Please analyze this website header against the provided ecommerce template.

**Website URL:** {url}

**Header Template to Check:**
{json.dumps(header_template, indent=2)}

**Header HTML Content:**
```html
{html_content}
```

**Instructions:**
1. Review each feature in the template's "features" array
2. Look at both the header image and HTML to determine if each feature is present
3. Return the EXACT same JSON structure as the template, but add a "found" field to each feature
4. Set "found": "yes" if the feature is clearly present, "found": "no" if it's not present

**Return Format:**
Return the template JSON with each feature having an additional "found" field:
```json
{{
    "name": "Header Template",
    "description": "...",
    "features": [
        {{
            "name": "Logo",
            "description": "...",
            "found": "yes"
        }},
        {{
            "name": "Search Box", 
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
                                "url": f"data:image/png;base64,{header_b64}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ]
        )
        
        print("    > Processing GPT-5 response...", file=sys.stderr)
        analysis_data, raw_response = _extract_json_from_response(response)
        
        if analysis_data:
            print("    > Header template analysis completed successfully", file=sys.stderr)
            return {
                "success": True,
                "template_analysis": analysis_data,
                "image_path": str(header_image_path),
                "html_path": str(header_html_path),
                "url": url,
                "raw_response": raw_response
            }
        else:
            print("    > Failed to parse JSON from GPT-5 response", file=sys.stderr)
            return {
                "success": False,
                "error": "Failed to parse JSON from AI response",
                "image_path": str(header_image_path),
                "html_path": str(header_html_path),
                "url": url,
                "raw_response": raw_response
            }
            
    except Exception as e:
        print(f"    > Error during header analysis: {str(e)}", file=sys.stderr)
        return {
            "success": False,
            "error": f"Header AI analysis failed: {str(e)}",
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
        return
    
    template_data = analysis.get("template_analysis", {})
    features = template_data.get("features", [])
    
    print(f"\n🎯 Header Template Analysis Results")
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
        print("Usage: python header_analyzer_new.py <header_image_path> <header_html_path> <url>")
        sys.exit(1)
    
    header_image_path = Path(sys.argv[1])
    header_html_path = Path(sys.argv[2])
    url = sys.argv[3]
    
    async def main():
        result = await analyze_header_elements(header_image_path, header_html_path, url)
        print_analysis_results(result)
        print(f"\nFull result: {json.dumps(result, indent=2)}")
    
    asyncio.run(main())
