"""
Interaction Analysis Module

This module provides tools for analyzing interactive elements on websites,
particularly focusing on detecting dropdowns, hover effects, and click-based
UI changes in different page regions (header, body, footer).
"""

from .header_interaction_analyzer import HeaderInteractionAnalyzer

__version__ = "1.0.0"
__all__ = ["HeaderInteractionAnalyzer"]
