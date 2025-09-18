"""
Configuration management for Define-OS application.
Centralizes all configuration values and eliminates hardcoded constants.
"""

import os
from pathlib import Path

class Config:
    """Application configuration class."""
    
    # Server Configuration
    SERVER_PORT = int(os.getenv('SERVER_PORT', 3000))
    SERVER_HOST = os.getenv('SERVER_HOST', 'localhost')
    
    # Python Process Configuration
    PYTHON_TIMEOUT_MS = int(os.getenv('PYTHON_TIMEOUT_MS', 300000))  # 5 minutes
    PYTHON_PATH = os.getenv('PYTHON_PATH', 'venv2/Scripts/python.exe')
    
    # AI Configuration
    AI_MODEL = os.getenv('AI_MODEL', 'gpt-5-mini')
    AI_MAX_TOKENS = int(os.getenv('AI_MAX_TOKENS', 4000))
    AI_TEMPERATURE = float(os.getenv('AI_TEMPERATURE', 0.1))
    
    # UI Configuration
    UI_UPDATE_DELAY_MS = int(os.getenv('UI_UPDATE_DELAY_MS', 100))
    
    # Screenshot Configuration
    SCREENSHOT_MAX_HEADER_HEIGHT = int(os.getenv('MAX_HEADER_HEIGHT', 500))
    SCREENSHOT_MAX_FOOTER_HEIGHT = int(os.getenv('MAX_FOOTER_HEIGHT', 800))
    SCREENSHOT_OUTPUT_DIR = Path(os.getenv('SCREENSHOT_OUTPUT_DIR', 'screenshot_urlbox/output'))
    
    # File Paths
    BASE_DIR = Path(__file__).parent
    AI_ANALYSIS_DIR = BASE_DIR / 'ai_analysis'
    UI_DIR = BASE_DIR / 'ui'
    VENV_DIR = BASE_DIR / 'venv2'
    
    # API Configuration
    API_RATE_LIMIT_WINDOW_MS = int(os.getenv('RATE_LIMIT_WINDOW_MS', 900000))  # 15 minutes
    API_RATE_LIMIT_MAX_REQUESTS = int(os.getenv('RATE_LIMIT_MAX_REQUESTS', 100))
    
    # Development Configuration
    DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    
    @classmethod
    def get_python_path(cls) -> Path:
        """Get the full path to Python executable."""
        return cls.BASE_DIR / cls.PYTHON_PATH
    
    @classmethod
    def get_screenshot_output_dir(cls) -> Path:
        """Get the screenshot output directory path."""
        return cls.SCREENSHOT_OUTPUT_DIR
    
    @classmethod
    def validate_config(cls):
        """Validate configuration values."""
        errors = []
        
        if not cls.get_python_path().exists():
            errors.append(f"Python path does not exist: {cls.get_python_path()}")
        
        if cls.PYTHON_TIMEOUT_MS <= 0:
            errors.append("Python timeout must be positive")
        
        if cls.SERVER_PORT <= 0 or cls.SERVER_PORT > 65535:
            errors.append("Server port must be between 1 and 65535")
        
        if errors:
            raise ValueError(f"Configuration errors: {'; '.join(errors)}")
        
        return True


# Create global config instance
config = Config()

# Validate configuration on import
if __name__ != '__main__':
    config.validate_config()
