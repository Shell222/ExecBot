#!/bin/bash

# Stock Analysis Streamlit App Launcher
echo "🚀 Starting Stock Analysis Dashboard..."

# Check if .env file exists
if [ ! -f .env ]; then
    echo "❌ .env file not found. Please create one with CLAUDE_API_KEY."
    exit 1
fi

# Activate virtual environment and run Streamlit
# Redirect both stdout and stderr to log.txt (append mode) while also showing in terminal
source .venv/bin/activate
streamlit run streamlit_app.py 2>&1 | tee -a log.txt

echo "✨ Dashboard closed."