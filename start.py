"""Render startup wrapper — catches and logs import/startup errors."""
import os
import sys
import traceback

try:
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend.server:app", host="0.0.0.0", port=port)
except Exception:
    traceback.print_exc()
    sys.exit(1)
