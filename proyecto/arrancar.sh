#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "=== Mercadona IT - Arch Linux Launcher ==="
echo

# Check if venv exists, if not create it
if [ ! -d "ai-service/.venv" ]; then
    echo "Setting up Python virtual environment..."
    cd ai-service
    python -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    
    # Copy .env if it doesn't exist
    if [ ! -f ".env" ]; then
        cp .env.example .env
    fi
    
    # Run seed to create database
    echo "Initializing database..."
    python -m app.data.seed
    cd ..
    echo "✓ AI service setup complete"
    echo
fi

echo "Starting services..."
echo

# Start AI service in background
cd ai-service
source .venv/bin/activate
python -m uvicorn app.main:app --port 8001 &
AI_PID=$!
cd ..

# Give AI service time to start
sleep 2

# Start backend in background
cd backend
./mvnw spring-boot:run &
BACKEND_PID=$!
cd ..

echo "✓ AI Service:  http://localhost:8001/docs (PID: $AI_PID)"
echo "✓ Backend:     http://localhost:8080 (PID: $BACKEND_PID)"
echo
echo "Press Ctrl+C to stop both services"
echo

# Wait for Ctrl+C and clean up
trap "echo 'Stopping services...'; kill $AI_PID $BACKEND_PID 2>/dev/null; wait 2>/dev/null; exit 0" SIGINT
wait