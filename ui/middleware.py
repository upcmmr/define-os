#!/usr/bin/env python3
"""
Standalone script to run both header and footer AI analysis and return JSON output.
Used by the Express server to get comprehensive analysis results.
"""

import sys
import json
import asyncio
from pathlib import Path

# Add parent directory to path to import ai_analysis module
sys.path.append(str(Path(__file__).parent.parent))

from ai_analysis.header_analyzer import analyze_header_elements
from ai_analysis.footer_analyzer import analyze_footer_elements
from ai_analysis.body_analyzer import analyze_body_elements

async def main():
    if len(sys.argv) != 4:
        print(json.dumps({"success": False, "error": "Usage: python run_header_footer_analysis.py <output_directory> <url> <analysis_type>"}))
        sys.exit(1)
    
    output_dir = Path(sys.argv[1])
    url = sys.argv[2]
    analysis_type = sys.argv[3]  # "header" or "footer" or "body" or "both" or "all"
    
    # Define file paths
    header_image_path = output_dir / "header.png"
    footer_image_path = output_dir / "footer.png"
    body_image_path = output_dir / "body.png"
    header_html_path = output_dir / "header.html"
    footer_html_path = output_dir / "footer.html"
    body_html_path = output_dir / "body.html"
    
    try:
        results = {}
        
        if analysis_type in ["header", "both", "all"]:
            if header_image_path.exists() and header_html_path.exists():
                print("Running header analysis...", file=sys.stderr)
                header_result = await analyze_header_elements(header_image_path, header_html_path, url)
                results["header"] = header_result
            else:
                results["header"] = {"success": False, "error": "Header image or HTML file not found"}
        
        if analysis_type in ["footer", "both", "all"]:
            if footer_image_path.exists() and footer_html_path.exists():
                print("Running footer analysis...", file=sys.stderr)
                footer_result = await analyze_footer_elements(footer_image_path, footer_html_path, url)
                results["footer"] = footer_result
            else:
                results["footer"] = {"success": False, "error": "Footer image or HTML file not found"}
        
        if analysis_type in ["body", "all"]:
            if body_image_path.exists() and body_html_path.exists():
                print("Running body analysis...", file=sys.stderr)
                body_result = await analyze_body_elements(body_image_path, body_html_path, url)
                results["body"] = body_result
            else:
                results["body"] = {"success": False, "error": "Body image or HTML file not found"}
        
        # Return combined results
        combined_result = {
            "success": True,
            "analysis_type": analysis_type,
            "results": results,
            "url": url
        }
        
        print(json.dumps(combined_result))
        
    except Exception as e:
        error_result = {
            "success": False,
            "error": f"AI analysis failed: {str(e)}",
            "analysis_type": analysis_type,
            "url": url
        }
        print(json.dumps(error_result))

if __name__ == "__main__":
    asyncio.run(main())

