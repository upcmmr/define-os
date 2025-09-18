"""
Shared utilities for AI analysis modules.
Consolidates common functions to eliminate code duplication.
"""

import base64
import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()


def extract_json_from_response(resp) -> Tuple[Optional[dict], str]:
    """
    Extract JSON from GPT Chat Completions API output with robust error handling.
    
    Args:
        resp: OpenAI API response object
        
    Returns:
        Tuple of (parsed_json_dict, raw_text_response)
    """
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


def encode_image_to_base64(image_path: Path) -> str:
    """
    Encode an image file to base64 string for API transmission.
    
    Args:
        image_path: Path to the image file
        
    Returns:
        Base64 encoded string of the image
        
    Raises:
        FileNotFoundError: If image file doesn't exist
        IOError: If image cannot be read
    """
    if not image_path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")
    
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except IOError as e:
        raise IOError(f"Failed to read image file {image_path}: {e}")


def load_html_content(html_path: Path) -> str:
    """
    Load HTML content from file with error handling.
    
    Args:
        html_path: Path to the HTML file
        
    Returns:
        HTML content as string
        
    Raises:
        FileNotFoundError: If HTML file doesn't exist
        IOError: If HTML cannot be read
    """
    if not html_path.exists():
        raise FileNotFoundError(f"HTML file not found: {html_path}")
    
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            return f.read()
    except IOError as e:
        raise IOError(f"Failed to read HTML file {html_path}: {e}")


def create_openai_client() -> OpenAI:
    """
    Create and return configured OpenAI client.
    
    Returns:
        Configured OpenAI client instance
    """
    return OpenAI()


def create_standard_error_response(error_msg: str, **additional_fields) -> Dict[str, Any]:
    """
    Create standardized error response dictionary.
    
    Args:
        error_msg: Error message
        **additional_fields: Additional fields to include in response
        
    Returns:
        Standardized error response dictionary
    """
    response = {
        "success": False,
        "error": error_msg,
        **additional_fields
    }
    return response


def create_standard_success_response(data: Dict[str, Any], **additional_fields) -> Dict[str, Any]:
    """
    Create standardized success response dictionary.
    
    Args:
        data: Main response data
        **additional_fields: Additional fields to include in response
        
    Returns:
        Standardized success response dictionary
    """
    response = {
        "success": True,
        **data,
        **additional_fields
    }
    return response
