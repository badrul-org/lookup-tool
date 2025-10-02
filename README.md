# Property Lookup Tool Web Interface

A modern web interface for the Property Lookup Tool that automates property report searches and tax rate lookups using Playwright.

## Features

- **Dashboard**: Overview of lookup statistics and recent activity
- **Lookup Tool**: Interactive form to search for property reports
- **Real-time Progress**: Live updates during lookup process
- **Results Management**: Download and view property reports
- **Responsive Design**: Works on desktop and mobile devices

## Setup Instructions

### 1. Install Dependencies

```bash
# Install Python dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

### 2. Run the Application

```bash
# Start the Flask web server
python app.py
```

The application will be available at `http://localhost:5000`

### 3. Using the Web Interface

1. **Dashboard**: View statistics and recent lookups
2. **Lookup Tool**: 
   - Enter property address (required)
   - Select county (required)
   - Optionally add city and ZIP code
   - Click "Start Lookup" to begin the process
   - Monitor progress in real-time
   - Download results when complete

## File Structure

```
├── app.py                 # Flask web application
├── tools.py              # Original automation tool
├── requirements.txt      # Python dependencies
├── templates/            # HTML templates
│   ├── base.html        # Base template with navbar
│   ├── dashboard.html   # Dashboard page
│   └── lookup.html      # Lookup tool page
└── static/              # Static assets
    ├── css/
    │   └── style.css    # Custom styling
    └── js/
        └── main.js      # JavaScript functionality
```

## API Endpoints

- `GET /` - Dashboard page
- `GET /lookup` - Lookup tool page
- `POST /api/lookup` - Start new lookup
- `GET /api/lookup/<session_id>` - Get lookup status
- `POST /api/lookup/<session_id>/cancel` - Cancel lookup
- `GET /api/sessions` - Get all lookup sessions

## Browser Requirements

The automation tool requires:
- Chromium browser (installed via Playwright)
- Internet connection for web scraping
- Headless mode can be enabled/disabled in `tools.py`

## Troubleshooting

1. **Playwright Installation Issues**: Run `playwright install chromium`
2. **Port Already in Use**: Change port in `app.py` (line 210)
3. **Browser Launch Issues**: Check if Chromium is properly installed
4. **Lookup Failures**: Verify internet connection and target website availability

## Security Notes

- Change the secret key in `app.py` for production use
- Consider adding authentication for production deployment
- The application runs with browser automation capabilities

## Development

To modify the interface:
1. Edit templates in `templates/` directory
2. Update styling in `static/css/style.css`
3. Modify JavaScript in `static/js/main.js`
4. Update Flask routes in `app.py`

## License

This project is for internal use. Please ensure compliance with target website terms of service.
