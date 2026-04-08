"""
Server entry point for OpenEnv deployment.

The validator expects:
  - A main() function that starts the server
  - if __name__ == '__main__' block
"""

import uvicorn

from app.server import app


def main():
    """Start the FastAPI server."""
    uvicorn.run(app, host="0.0.0.0", port=7860)


if __name__ == "__main__":
    main()