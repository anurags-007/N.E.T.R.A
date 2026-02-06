#!/bin/bash

# Kill existing instance if any (to update changes)
echo "Stopping any running servers..."
fuser -k 8001/tcp || true

# Check/Create Virtual Environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment 'venv'..."
    python3 -m venv venv
    
    # If venv creation failed
    if [ ! -d "venv" ]; then
        echo "Error: Failed to create venv. Please install python3-venv."
        exit 1
    fi
fi

# Activate
source venv/bin/activate

# Install
echo "Installing dependencies..."
pip install -r requirements.txt

# Run
echo "Starting N.E.T.R.A. System..."
echo "Access at: http://localhost:8001/frontend/index.html"
uvicorn backend.main:app --port 8001 --reload
