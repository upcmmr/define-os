"""
HTML Cleaner Module

This module provides functions to preprocess and clean HTML content
to reduce size and complexity for AI analysis while preserving
essential structural and interactive elements.
"""

import sys
from pathlib import Path
from bs4 import BeautifulSoup
from typing import Optional


def clean_html_for_ai(html_content: str, section_type: str) -> str:
    """
    Clean and preprocess HTML content to reduce size for AI analysis.
    
    This function removes or simplifies elements that add bulk without
    providing value for AI analysis of interactive elements and structure.
    
    Args:
        html_content: Raw HTML content to clean
        section_type: Type of section (header, footer, body) for logging
        
    Returns:
        Cleaned HTML with reduced size and complexity
    """
    if not html_content or not html_content.strip():
        return html_content
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        original_size = len(html_content)
        
        # Track what we're cleaning
        cleaning_stats = {
            'svg_count': 0,
            'script_count': 0,
            'style_count': 0,
            'comment_count': 0
        }
        
        # 1. Remove/simplify SVG content - this can be massive
        for svg in soup.find_all('svg'):
            cleaning_stats['svg_count'] += 1
            # Replace complex SVGs with simple placeholder
            svg.clear()
            svg.string = f"[{section_type.upper()}_SVG_{cleaning_stats['svg_count']}]"
        
        # 2. Remove script tags (not needed for AI analysis)
        for script in soup.find_all('script'):
            cleaning_stats['script_count'] += 1
            script.decompose()
        
        # 3. Remove style tags and inline styles (keep class names for structure)
        for style in soup.find_all('style'):
            cleaning_stats['style_count'] += 1
            style.decompose()
        
        # Remove inline styles but keep class attributes
        for tag in soup.find_all(style=True):
            del tag['style']
        
        # 4. Remove HTML comments
        for comment in soup.find_all(string=lambda text: isinstance(text, soup.__class__.__bases__[0])):
            if hasattr(comment, 'extract'):
                cleaning_stats['comment_count'] += 1
                comment.extract()
        
        cleaned_html = str(soup)
        cleaned_size = len(cleaned_html)
        reduction = original_size - cleaned_size
        reduction_percent = (reduction / original_size) * 100 if original_size > 0 else 0
        
        # Log cleaning results
        if any(cleaning_stats.values()):
            print(f"    > Cleaned {section_type}: {reduction:,} bytes ({reduction_percent:.1f}%) reduction", file=sys.stderr)
            if cleaning_stats['svg_count'] > 0:
                print(f"      - Simplified {cleaning_stats['svg_count']} SVG elements", file=sys.stderr)
            if cleaning_stats['script_count'] > 0:
                print(f"      - Removed {cleaning_stats['script_count']} script tags", file=sys.stderr)
            if cleaning_stats['style_count'] > 0:
                print(f"      - Removed {cleaning_stats['style_count']} style tags", file=sys.stderr)
        
        return cleaned_html
        
    except Exception as e:
        print(f"    > Warning: HTML cleaning failed for {section_type}: {str(e)}", file=sys.stderr)
        return html_content  # Return original if cleaning fails


def clean_html_file(file_path: Path, section_type: str) -> bool:
    """
    Clean an HTML file in-place.
    
    Args:
        file_path: Path to the HTML file to clean
        section_type: Type of section (header, footer, body) for logging
        
    Returns:
        True if cleaning was successful, False otherwise
    """
    if not file_path.exists():
        print(f"    > Warning: HTML file not found: {file_path}", file=sys.stderr)
        return False
    
    try:
        # Read original content
        with open(file_path, 'r', encoding='utf-8') as f:
            original_content = f.read()
        
        # Clean the content
        cleaned_content = clean_html_for_ai(original_content, section_type)
        
        # Write back cleaned content
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(cleaned_content)
        
        return True
        
    except Exception as e:
        print(f"    > Error cleaning HTML file {file_path}: {str(e)}", file=sys.stderr)
        return False


def clean_all_html_files(output_dir: Path) -> dict:
    """
    Clean all HTML files in an output directory.
    
    Args:
        output_dir: Directory containing HTML files to clean
        
    Returns:
        Dictionary with cleaning results for each file type
    """
    results = {}
    
    # Define the HTML files to clean
    html_files = [
        ('header.html', 'header'),
        ('footer.html', 'footer'),
        ('body.html', 'body')
    ]
    
    print("    > Cleaning HTML files for AI analysis...", file=sys.stderr)
    
    for filename, section_type in html_files:
        file_path = output_dir / filename
        success = clean_html_file(file_path, section_type)
        results[section_type] = {
            'file_path': file_path,
            'success': success,
            'exists': file_path.exists()
        }
    
    return results


def get_file_size_info(file_path: Path) -> dict:
    """
    Get size information for a file.
    
    Args:
        file_path: Path to the file
        
    Returns:
        Dictionary with size information
    """
    if not file_path.exists():
        return {'exists': False, 'size_bytes': 0, 'size_kb': 0}
    
    size_bytes = file_path.stat().st_size
    size_kb = size_bytes / 1024
    
    return {
        'exists': True,
        'size_bytes': size_bytes,
        'size_kb': size_kb
    }


if __name__ == "__main__":
    """
    Command-line interface for testing HTML cleaning.
    Usage: python html_cleaner.py <output_directory>
    """
    if len(sys.argv) != 2:
        print("Usage: python html_cleaner.py <output_directory>")
        sys.exit(1)
    
    output_dir = Path(sys.argv[1])
    if not output_dir.exists():
        print(f"Error: Directory {output_dir} does not exist")
        sys.exit(1)
    
    print(f"Cleaning HTML files in: {output_dir}")
    results = clean_all_html_files(output_dir)
    
    print("\nCleaning Results:")
    for section_type, result in results.items():
        if result['exists']:
            size_info = get_file_size_info(result['file_path'])
            status = "✅ Success" if result['success'] else "❌ Failed"
            print(f"  {section_type.title()}: {status} ({size_info['size_kb']:.1f} KB)")
        else:
            print(f"  {section_type.title()}: ⚠️  File not found")
