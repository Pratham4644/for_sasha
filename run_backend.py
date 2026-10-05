#!/usr/bin/env python3
import os
import sys

# Ensure production/ is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import uvicorn
from backend.app.config import settings

if __name__ == "__main__":
    print(f"Starting {settings.app_name} on {settings.app_host}:{settings.app_port}...")
    uvicorn.run(
        "backend.app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.debug,
    )
