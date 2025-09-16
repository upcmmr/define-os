"""
AI Analysis Module

Provides AI-powered analysis of website screenshots and HTML to extract
UI elements, links, and interactions using GPT-5.

Key Features:
- Header analysis to extract links and UI elements
- Image and HTML correlation analysis
- Structured output of interactive elements

Usage:
    from ai_analysis import analyze_header_elements
    
    result = await analyze_header_elements(header_image_path, html_path)
"""

from .header_analyzer import analyze_header_elements

__all__ = ['analyze_header_elements']
