#!/usr/bin/env python3
"""
Script to start the Django development server
"""

import os
import sys
import subprocess
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mmbackend.settings')
django.setup()

def start_server():
    """Start the Django development server"""
    print("Starting Django development server...")
    print("Server will be available at: http://localhost:8000")
    print("API endpoints will be available at: http://localhost:8000/api/")
    print("\nPress Ctrl+C to stop the server")
    print("-" * 50)
    
    try:
        # Start the Django development server
        subprocess.run([
            sys.executable, 'manage.py', 'runserver', '0.0.0.0:8000'
        ], check=True)
    except KeyboardInterrupt:
        print("\nServer stopped by user")
    except subprocess.CalledProcessError as e:
        print(f"Error starting server: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    start_server() 