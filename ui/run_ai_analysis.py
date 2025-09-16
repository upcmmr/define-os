#!/usr/bin/env python3
"""
Standalone script to run AI analysis and return JSON output.
Used by the Express server to get AI analysis results.
"""

import sys
import json
import asyncio
from pathlib import Path

# Add parent directory to path to import ai_analysis module
sys.path.append(str(Path(__file__).parent.parent))

from ai_analysis.header_analyzer import analyze_header_elements

async def main():
    if len(sys.argv) != 3:
        print(json.dumps({"success": False, "error": "Usage: python run_ai_analysis.py <header_image_path> <html_path>"}))
        sys.exit(1)
    
    header_image_path = Path(sys.argv[1])
    html_path = Path(sys.argv[2])
    
    # Extract URL from directory name if possible
    output_dir = header_image_path.parent
    dir_parts = output_dir.name.split("_")
    if len(dir_parts) >= 3:
        domain_parts = []
        for part in dir_parts:
            if part.isdigit() and len(part) == 8:  # Date part
                break
            domain_parts.append(part)
        url = f"https://{'.'.join(domain_parts)}"
    else:
        url = "Unknown URL"
    
    try:
        result = await analyze_header_elements(header_image_path, html_path, url)
        print(json.dumps(result))
    except Exception as e:
        error_result = {
            "success": False,
            "error": f"AI analysis failed: {str(e)}",
            "image_path": str(header_image_path),
            "html_path": str(html_path),
            "url": url
        }
        print(json.dumps(error_result))

if __name__ == "__main__":
    asyncio.run(main())
