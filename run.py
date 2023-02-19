#!/usr/bin/env python3
"""
Run Blackbird Search Engine

Simple script to run the server without installing as a package.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Run the server
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "blackbird.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
