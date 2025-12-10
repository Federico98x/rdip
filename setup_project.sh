#!/bin/bash
# RDIP v1.3.0 - Project Structure Setup Script
# Reddit Deep Intelligence Platform

set -e

echo "🚀 Creating RDIP v1.3.0 project structure..."

# Create main directories
mkdir -p app/core
mkdir -p app/services
mkdir -p app/api
mkdir -p ui
mkdir -p data
mkdir -p tests

# Create __init__.py files for Python packages
touch app/__init__.py
touch app/core/__init__.py
touch app/services/__init__.py
touch app/api/__init__.py
touch tests/__init__.py

# Create placeholder files
touch data/.gitkeep

echo "✅ Directory structure created successfully!"
echo ""
echo "📁 Project structure:"
echo "├── app/"
echo "│   ├── __init__.py"
echo "│   ├── main.py"
echo "│   ├── models.py"
echo "│   ├── core/"
echo "│   │   ├── __init__.py"
echo "│   │   ├── config.py"
echo "│   │   └── logging.py"
echo "│   └── services/"
echo "│       ├── __init__.py"
echo "│       ├── reddit_miner.py"
echo "│       ├── rate_limiter.py"
echo "│       ├── ai_orchestrator.py"
echo "│       ├── cache_manager.py"
echo "│       └── job_store.py"
echo "├── ui/"
echo "│   └── app.py"
echo "├── data/"
echo "├── tests/"
echo "├── .env.example"
echo "├── requirements.txt"
echo "└── Dockerfile"
echo ""
echo "📌 Next steps:"
echo "1. Copy .env.example to .env and fill in your API keys"
echo "2. Run: pip install -r requirements.txt"
echo "3. Start backend: uvicorn app.main:app --reload"
echo "4. Start frontend: streamlit run ui/app.py"
