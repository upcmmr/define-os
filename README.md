# Define-OS

A web application that analyzes ecommerce websites using AI to identify template features and extract site links.

## How to Start the App

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   cd ui && npm install
   ```

2. **Set Environment Variable**
   ```bash
   set OPENAI_API_KEY=your_openai_api_key_here
   ```

3. **Start the Server**
   ```bash
   cd ui
   node server.js
   ```

4. **Open Browser**
   - Navigate to `http://localhost:3000`
   - Enter a website URL and click Submit

## Process Functions

- **Screenshot Capture** - Takes full page, header, body, and footer screenshots
- **Template Detection** - AI identifies page template type (Homepage, Product Detail, etc.)
- **Feature Analysis** - Analyzes header/footer/body against ecommerce feature templates
- **Site Links Extraction** - Extracts and categorizes all navigation links
- **Interactive UI** - Displays results with editable checkboxes for feature validation
- **Multi-page Analysis** - Provides separate views for different page sections
