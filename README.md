# Define-OS

A web analysis tool that captures screenshots of websites and uses AI to identify e-commerce features and site navigation patterns. The system automatically detects headers, footers, and body content, then analyzes them against predefined templates to catalog standard and custom features.

## Quick Start

### Prerequisites
- Python 3.8+
- Node.js 14+
- OpenAI API key
- URLBox API credentials

### Setup
```powershell
# Clone and navigate to project
cd C:\dev\define-os

# Activate Python virtual environment
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
cd ui
npm install

# Set environment variables
$env:OPENAI_API_KEY = "your-openai-key"
$env:URLBOX_API_KEY = "your-urlbox-key"
$env:URLBOX_API_SECRET = "your-urlbox-secret"
```

### Run Application
```powershell
# Start the web interface
cd ui
node server.js

# Open browser to http://localhost:3000
```

### Usage
1. Enter a website URL in the web interface
2. Click "Discover Links" to analyze the site
3. View detected features, screenshots, and extracted links
4. Results are saved in `screenshot_urlbox/output/` directory

The system uses GPT-5-mini for AI analysis and URLBox for high-quality screenshots.
