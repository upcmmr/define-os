#!/usr/bin/env python3
"""
Test script for header analysis functionality.

This script finds existing screenshot outputs and runs AI analysis
on the header images and HTML files.
"""

import asyncio
import sys
from pathlib import Path
from header_analyzer import analyze_header_elements, print_analysis_results


async def test_header_analysis():
    """Test header analysis on existing screenshot outputs."""
    
    # Find screenshot output directories
    screenshot_output_dir = Path(__file__).parent.parent / "screenshot_urlbox" / "output"
    
    if not screenshot_output_dir.exists():
        print("❌ No screenshot output directory found. Run screenshot_urlbox first.")
        return
    
    # Find all output directories
    output_dirs = [d for d in screenshot_output_dir.iterdir() if d.is_dir()]
    
    if not output_dirs:
        print("❌ No screenshot output directories found. Run screenshot_urlbox first.")
        return
    
    print(f"🔍 Found {len(output_dirs)} screenshot output directories")
    
    for output_dir in output_dirs:
        print(f"\n{'='*60}")
        print(f"🔬 Analyzing: {output_dir.name}")
        
        # Look for required files
        header_image = output_dir / "header.png"
        html_file = output_dir / "page.html"
        
        if not header_image.exists():
            print(f"❌ Header image not found: {header_image}")
            continue
            
        if not html_file.exists():
            print(f"❌ HTML file not found: {html_file}")
            continue
        
        # Extract URL from directory name (rough approximation)
        dir_parts = output_dir.name.split("_")
        if len(dir_parts) >= 3:
            # Reconstruct URL from directory name
            domain_parts = []
            for part in dir_parts:
                if part.isdigit() and len(part) == 8:  # Date part
                    break
                domain_parts.append(part)
            url = f"https://{'.'.join(domain_parts)}"
        else:
            url = "Unknown URL"
        
        print(f"🌐 Inferred URL: {url}")
        print(f"📸 Header Image: {header_image.name}")
        print(f"📄 HTML File: {html_file.name}")
        
        # Run AI analysis
        try:
            analysis = await analyze_header_elements(header_image, html_file, url)
            print_analysis_results(analysis)
            
        except Exception as e:
            print(f"❌ Analysis failed for {output_dir.name}: {str(e)}")
            continue


async def test_specific_sites(site_names: list):
    """Test header analysis on specific sites."""
    
    screenshot_output_dir = Path(__file__).parent.parent / "screenshot_urlbox" / "output"
    
    for site_name in site_names:
        print(f"\n{'='*60}")
        print(f"🔍 Looking for {site_name} outputs...")
        
        # Find directories containing the site name
        matching_dirs = [d for d in screenshot_output_dir.iterdir() 
                        if d.is_dir() and site_name.lower() in d.name.lower()]
        
        if not matching_dirs:
            print(f"❌ No outputs found for {site_name}")
            continue
        
        # Use the most recent directory
        latest_dir = max(matching_dirs, key=lambda d: d.stat().st_mtime)
        
        print(f"🔬 Analyzing latest {site_name} output: {latest_dir.name}")
        
        header_image = latest_dir / "header.png"
        html_file = latest_dir / "page.html"
        
        if not header_image.exists() or not html_file.exists():
            print(f"❌ Required files missing in {latest_dir.name}")
            continue
        
        # Reconstruct URL
        url = f"https://www.{site_name.lower()}.com"
        
        try:
            analysis = await analyze_header_elements(header_image, html_file, url)
            print_analysis_results(analysis)
            
        except Exception as e:
            print(f"❌ Analysis failed for {site_name}: {str(e)}")


async def main():
    """Main entry point."""
    
    if len(sys.argv) > 1:
        # Test specific sites provided as arguments
        site_names = sys.argv[1:]
        await test_specific_sites(site_names)
    else:
        # Test all available outputs
        await test_header_analysis()


if __name__ == "__main__":
    asyncio.run(main())
