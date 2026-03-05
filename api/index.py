"""
Vercel serverless function entry point.
Wraps the Flask application for deployment on Vercel.
"""

import os
import sys

# Add the project root to sys.path so that the web package can be imported.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web.app import app
