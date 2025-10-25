# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Multi-app Python portal hosting AI-powered applications in an iframe-based architecture. The portal dynamically discovers and mounts Flask applications as sub-paths.

## Running the Portal

```bash
# Development mode (with reloader and debugger)
python run_dev.py

# Production mode
python wsgi.py
```

Portal runs on **http://localhost:8000**

## Architecture

### Portal System (wsgi.py)

Uses Flask + Werkzeug's DispatcherMiddleware to dynamically mount sub-applications:

- **Main portal**: Serves index.html at `/` with iframe navigation
- **Sub-apps**: Auto-discovered and mounted (e.g., `/verificador_de_fraudes`)
- **Static files**: Served with `conditional=False, max_age=0` to prevent 304 caching issues

**Auto-discovery logic**:
1. Checks environment variables: `VERIFICADOR_APP_FILE` or `VERIFICADOR_APP_ROOT`
2. Scans subdirectories for Python files containing `app = Flask(...)` or `application = Flask(...)`
3. Prioritizes app.py > wsgi.py > main.py, favoring shallower directory depths

### Sub-Application Structure

Each app lives in its own directory with:
- **app.py**: Flask application exposing `app` or `application` variable
- **requirements.txt**: App-specific dependencies
- **.venv**: Isolated virtual environment (not shared with portal)
- **static/**, **templates/**: Standard Flask directories

## Sub-Applications

### Verificador de Fraudes

AI-powered fraud detection using OCR, heuristics, and LLM analysis.

**Setup**:
```bash
cd "Verificador de Fraudes"
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.sample .env
# Edit .env: add OPENAI_API_KEY
```

**Prerequisites**:
- Tesseract OCR installed (`apt-get install tesseract-ocr` on Ubuntu/Debian)
- Redis server running

**Run standalone**:
```bash
flask --app app.py run --host=0.0.0.0 --port=8000
```

**Run with Docker Compose** (includes Redis):
```bash
docker compose up --build
```

**Architecture layers**:
1. **Input**: URLs, images (OCR), .eml files
2. **Extraction** (extractors.py): BeautifulSoup for URLs, Tesseract+OpenCV for images, email parser
3. **Analysis**:
   - heuristics.py: Rule-based fraud scoring
   - brand_guard.py: Brand impersonation detection
   - llm_client.py: OpenAI GPT analysis
4. **Scoring** (scoring.py): Combines signals into fraud probability
5. **Caching**: In-memory TTL cache by content hash (OCR, URL parse, LLM responses)

**Key environment variables**:
- `OPENAI_API_KEY`: Required
- `REDIS_URL`: Default redis://localhost:6379/0
- `MAX_CONTENT_LENGTH_MB`: Upload limit (default: 10)
- `OCR_LANG`: Tesseract language (default: por+eng)
- `DEV_NO_CACHE`: Disable browser caching

### E2E Runner

LLM-driven Playwright test automation using GPT-5.

**Setup**:
```bash
cd "E2E Runner"
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install
# Edit .env: add OPENAI_API_KEY
```

**Run scenarios**:
```bash
python e2e.py scenarios.json
```

**How it works**:
- Scenarios defined in scenarios.json with natural language steps
- LLM generates Playwright actions (navigate, click, type, wait_for_selector, assert_text, assert_url_contains, press, done)
- Avoids element.fill(), uses focus() + keyboard.type() for reliability
- Keeps Playwright instance alive to avoid "event loop closed" errors
- Fallback to dummy model if OpenAI not configured

**Environment variables**:
- `OPENAI_API_KEY`: OpenAI API key
- `OPENAI_MODEL`: Model name (default: gpt-5)
- `HEADLESS`: Browser mode (default: 1)
- `MAX_TURNS_PER_STEP`: Max LLM iterations (default: 6)
- `NAV_TIMEOUT_MS`: Navigation timeout (default: 15000)

### Heatmap

Interactive heat map visualization of Recife neighborhoods with demographic data and points of interest.

**Setup**:
```bash
cd Heatmap
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**Run standalone**:
```bash
python app.py
```

Runs on **http://localhost:8002** (when standalone)

**Features**:
- Choropleth heat map based on demographic density
- Interactive tooltips on hover showing quick stats
- Detailed popups on click with full neighborhood information
- Color-coded density visualization (lighter = less dense, darker = more dense)
- Points of interest counts: pharmacies, shopping malls, gas stations, supermarkets, schools

**Data**:
- GeoJSON with neighborhood polygons in `data/recife_bairros.json`
- Each neighborhood includes: population, area, density, and POI counts
- Sample data covers 12 major Recife neighborhoods

**Technology**:
- Folium for interactive Leaflet.js maps
- Branca for color mapping
- Full-screen plugin for better visualization

## Adding New Apps

1. Create subdirectory in portal root
2. Create app.py with `app = Flask(...)` or `application = Flask(...)`
3. Update index.html:
   - Add tab button: `<button class="tab" data-app="app_name">Display Name</button>`
   - Add route mapping: `const routes = { app_name: "/app_name" };`
4. Portal auto-discovers the Flask app on startup

Alternatively, set environment variable pointing to the app:
- `<APPNAME>_APP_FILE`: Direct path to app.py
- `<APPNAME>_APP_ROOT`: Directory to search

## Python Environments

Portal uses isolated virtual environments:
- **Root .venv/**: Portal dependencies (Flask>=2.3, Werkzeug>=3.0)
- **Each app .venv/**: App-specific dependencies

## Important Implementation Details

- Portal uses DispatcherMiddleware for prefix-based routing to sub-apps
- Static file route for sub-apps mounted at `/verificador_de_fraudes/static` with no-cache headers
- wsgi.py temporarily modifies sys.path when importing sub-apps
- Verificador de Fraudes caches by content hash to avoid redundant OCR/LLM calls
- E2E Runner system prompt constrains LLM output to specific JSON action schema
