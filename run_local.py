#!/usr/bin/env python3
"""
Run the Reddit Agent locally.
This script starts the FastAPI app with improved error handling and setup.
"""

import os
import sys
import webbrowser
import uvicorn
import time
import subprocess
import platform

# Default port
PORT = 8000

def check_dependencies():
    """Check if all required dependencies are installed"""
    try:
        import fastapi
        import asyncpraw
        import chromadb
        import sentence_transformers
        print("✅ All core dependencies are installed")
        return True
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("\nPlease install all dependencies with:")
        print("pip install -r requirements.txt")
        return False

def check_ollama():
    """Check if Ollama is running"""
    try:
        import requests
        response = requests.get("http://localhost:11434/api/version", timeout=2)
        if response.status_code == 200:
            print("✅ Ollama is running")
            return True
        else:
            print("⚠️ Ollama API returned unexpected status code")
            return False
    except Exception:
        print("⚠️ Ollama doesn't appear to be running")
        print("Please start Ollama before running this app")
        
        # Provide platform-specific instructions
        if platform.system() == "Darwin":  # macOS
            print("\nOn macOS, you can start Ollama by:")
            print("1. Open the Ollama app")
            print("2. Or run: open -a Ollama")
        elif platform.system() == "Linux":
            print("\nOn Linux, you can start Ollama by running:")
            print("ollama serve")
        elif platform.system() == "Windows":
            print("\nOn Windows, you can start Ollama by:")
            print("1. Open the Ollama app from the Start menu")
            print("2. Or run Ollama from the command line")
        
        return False

def check_port_available(port):
    """Check if the port is available"""
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    available = False
    try:
        sock.bind(("127.0.0.1", port))
        available = True
    except:
        pass
    finally:
        sock.close()
    return available

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🚀 Reddit Agent Setup")
    print("="*60)
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Check if Ollama is running
    if not check_ollama():
        user_input = input("\nDo you want to continue anyway? (y/n): ")
        if user_input.lower() != 'y':
            sys.exit(1)
    
    # Find an available port if the default is in use
    if not check_port_available(PORT):
        print(f"⚠️ Port {PORT} is already in use.")
        for test_port in range(8001, 8020):
            if check_port_available(test_port):
                PORT = test_port
                print(f"✅ Using alternative port: {PORT}")
                break
        else:
            print("❌ No available ports found in range 8000-8020. Please free up a port and try again.")
            sys.exit(1)
    
    # Print access information
    print("\n" + "="*60)
    print(f"🚀 Starting Reddit Agent on http://localhost:{PORT}")
    print("="*60)
    
    # Open browser after a short delay
    def open_browser():
        time.sleep(2)
        webbrowser.open(f"http://localhost:{PORT}")
    
    import threading
    browser_thread = threading.Thread(target=open_browser)
    browser_thread.daemon = True
    browser_thread.start()
    
    # Start the server
    try:
        uvicorn.run("app.main:app", host="127.0.0.1", port=PORT, reload=True)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down server...")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error starting server: {e}")
        print("\nTroubleshooting tips:")
        print("1. Check if another application is using port 8000")
        print("2. Make sure you have the required permissions")
        print("3. Check your firewall settings")
        sys.exit(1) 