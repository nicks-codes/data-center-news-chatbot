#!/usr/bin/env python
"""
Simple script to run the FastAPI application
"""
import uvicorn
import sys
import os

# Add the parent directory to the path so we can import backend as a package
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

if __name__ == "__main__":
    # Run the application as a module
    uvicorn.run(
        "backend.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 8000)),
        reload=True
    )
