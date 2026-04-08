"""
Server entry point for OpenEnv deployment.

The validator expects this file at server/app.py.
It imports the FastAPI app from our app package.
"""

from app.server import app

__all__ = ["app"]