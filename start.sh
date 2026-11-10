#!/bin/bash
set -e

# Generate the clinic database if it doesn't exist (Render's disk resets on restart)
if [ ! -f "${DB_PATH:-clinic.db}" ]; then
    echo "Initializing database..."
    python setup_database.py
    echo "Seeding agent memory..."
    python seed_memory.py
fi

# Start the server
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
