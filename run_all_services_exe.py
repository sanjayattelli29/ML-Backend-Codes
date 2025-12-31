#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DataVizAI Services Launcher - Executable Version
Launches all DataVizAI services in a single process for distribution
"""

import subprocess
import os
import time
import signal
import sys
import codecs
import threading
import multiprocessing
import requests
from pathlib import Path

# Try importing streamlit for the Status Page
try:
    import streamlit as st
    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False

# Import Tornado for Proxying (Streamlit uses Tornado under the hood)
try:
    import tornado.web
    import tornado.httputil
    HAS_TORNADO = True
except ImportError:
    HAS_TORNADO = False

# Handle PyInstaller bundled app
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    BASE_DIR = sys._MEIPASS
    EXECUTABLE_MODE = True
    
    # Set environment variables for frozen app to find libraries
    os.environ['PATH'] = f"{sys._MEIPASS};{os.environ['PATH']}"
    os.environ['PYTHONPATH'] = sys._MEIPASS
    
    # Ensure temp folder exists and is writable
    try:
        temp_dir = os.path.join(os.environ.get('TEMP', os.path.expanduser('~')), 'DataVizAI_Temp')
        os.makedirs(temp_dir, exist_ok=True)
        os.environ['TEMP'] = temp_dir
        os.environ['TMP'] = temp_dir
    except:
        pass
else:
    # Running as script
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    EXECUTABLE_MODE = False

# Set UTF-8 encoding for output
if sys.stdout.encoding != 'utf-8':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
if sys.stderr.encoding != 'utf-8':
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Store subprocesses and threads for cleanup
processes = []
service_threads = []

# --- PROXY LOGIC ---
if HAS_TORNADO and HAS_STREAMLIT:
    class ProxyHandler(tornado.web.RequestHandler):
        def initialize(self, target_url):
            self.target_url = target_url

        async def prepare(self):
            # Capture request body explicitly for forwarding
            pass

        async def get(self):
            await self.proxy_request('GET')

        async def post(self):
            await self.proxy_request('POST')

        async def put(self):
            await self.proxy_request('PUT')

        async def delete(self):
            await self.proxy_request('DELETE')
            
        async def options(self):
            # Handle CORS preflight options request
            self.set_header("Access-Control-Allow-Origin", "*")
            self.set_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
            self.set_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.set_status(204)
            self.finish()

        async def proxy_request(self, method):
            try:
                # Prepare headers
                headers = {k: v for k, v in self.request.headers.get_all()}
                # Remove Host header to avoid confusion
                if 'Host' in headers:
                    del headers['Host']
                
                # Forward the request
                response = requests.request(
                    method=method,
                    url=self.target_url,
                    headers=headers,
                    data=self.request.body,
                    params=self.request.arguments,
                    timeout=300 # Long timeout for ML tasks
                )
                
                # Relay status code
                self.set_status(response.status_code)
                
                # Relay headers
                for key, value in response.headers.items():
                    if key.lower() not in ['content-encoding', 'transfer-encoding', 'content-length', 'connection']:
                        self.set_header(key, value)
                
                # Setup CORS headers for the response
                self.set_header("Access-Control-Allow-Origin", "*")
                
                # Relay body
                self.write(response.content)
                self.finish()
                
            except Exception as e:
                self.set_status(500)
                self.write({"error": f"Proxy Error: {str(e)}"})
                self.finish()

    def mount_proxy_routes():
        """
        Injects proxy routes into the underlying Streamlit Tornado server.
        This allows mapping specific public paths (e.g. /analyze) to local services (e.g. localhost:1289).
        """
        import gc
        from streamlit.web.server.server import Server

        # Find the Tornado Application instance using multiple strategies
        app = None
        
        # Strategy 1: Search for the Tornado Application object directly
        # This is the most consistent way effectively
        from tornado.web import Application
        for obj in gc.get_objects():
            if isinstance(obj, Application):
                app = obj
                break
        
        if not app:
            print("❌ Could not find Tornado Application instance to mount proxies.")
            return

        # Define the routes to proxy
        # Format: (Public Path, Target Local URL)
        # Note: /analyze maps to Data Quality Service
        routes = [
            (r"/analyze", "http://127.0.0.1:1289/analyze"),
            (r"/train", "http://127.0.0.1:5000/train"),
            (r"/predict", "http://127.0.0.1:5000/predict"),
            (r"/models", "http://127.0.0.1:5000/models"),
            (r"/health", "http://127.0.0.1:5000/health"), 
            # Add more routes as needed (regex matching can be used for more complex paths)
        ]

        # app = server_instance._tornado_app  <-- Removed, we already have app from GC lookup
        
        # We need to insert these handlers BEFORE the default Streamlit catch-all
        # Tornado processes handlers in order.
        
        existing_handlers = app.handlers[0][1] # Host pattern ".*"
        
        # Check if we already mounted handlers to avoid duplicate mounting on reruns
        if getattr(app, "_proxy_mounted", False):
            return

        print("🔧 Injecting Proxy Routes for API access...")
        
        new_handlers = []
        for path, target in routes:
            # Create a specific handler for this route
            handler = tornado.web.URLSpec(path, ProxyHandler, dict(target_url=target))
            new_handlers.append(handler)
            print(f"   Mapped {path} -> {target}")
            
        # Also map wildcard routes for sub-resources if needed, e.g. /models/.*
        # This requires more careful regex
        new_handlers.append(tornado.web.URLSpec(r"/models/(.*)", ProxyHandlerMapModels, dict(base_url="http://127.0.0.1:5000/models/")))

        # Insert at the beginning
        # app.add_handlersOr similar... but we want them robustly locally
        # The easiest way with the Server instance is usually direct manipulation
        
        # Prepend our handlers to the list
        app.handlers[0][1][:0] = new_handlers
        
        app._proxy_mounted = True
        print("✅ Proxy Routes Mounted Successfully!")

    class ProxyHandlerMapModels(tornado.web.RequestHandler):
        """Special handler for dynamic paths like /models/<id>"""
        def initialize(self, base_url):
            self.base_url = base_url

        async def get(self, path_arg):
            await self.proxy_request('GET', path_arg)
        async def post(self, path_arg):
            await self.proxy_request('POST', path_arg)
        async def delete(self, path_arg):
            await self.proxy_request('DELETE', path_arg)
        async def options(self, path_arg):
            self.set_header("Access-Control-Allow-Origin", "*")
            self.set_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
            self.set_header("Access-Control-Allow-Headers", "*")
            self.set_status(204)
            self.finish()

        async def proxy_request(self, method, path_arg):
            target_url = self.base_url + path_arg
            # Copy-paste logic from ProxyHandler (refactor ideally, but keeping self-contained here)
            try:
                headers = {k: v for k, v in self.request.headers.get_all()}
                if 'Host' in headers: del headers['Host']
                response = requests.request(
                    method=method, url=target_url, headers=headers,
                    data=self.request.body, params=self.request.arguments,
                    timeout=300
                )
                self.set_status(response.status_code)
                for k, v in response.headers.items():
                    if k.lower() not in ['content-encoding', 'transfer-encoding', 'content-length', 'connection']:
                        self.set_header(k, v)
                self.set_header("Access-Control-Allow-Origin", "*")
                self.write(response.content)
                self.finish()
            except Exception as e:
                self.set_status(500)
                self.write({"error": str(e)})
                self.finish()

# --- SERVICE LOGIC ---

def run_service_in_process(service_name, module_path, port):
    """Run a service in a separate process (for executable mode)"""
    try:
        if service_name == "ML Backend":
            from ml_backend.app import app
            app.run(debug=False, host='0.0.0.0', port=port, use_reloader=False, threaded=True)
        elif service_name == "Data Quality":
            metric_quality_path = os.path.join(BASE_DIR, 'metric-quality')
            sys.path.insert(0, BASE_DIR)
            import importlib.util
            spec = importlib.util.spec_from_file_location("app", os.path.join(metric_quality_path, "app.py"))
            metric_quality_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(metric_quality_module)
            metric_quality_module.app.run(debug=False, host='0.0.0.0', port=port, use_reloader=False, threaded=True)
        elif service_name == "Data Preprocessing":
            preprocessing_path = os.path.join(BASE_DIR, 'pre-processing')
            sys.path.insert(0, BASE_DIR)
            import importlib.util
            spec = importlib.util.spec_from_file_location("preprocessing_api", os.path.join(preprocessing_path, "preprocessing_api.py"))
            preprocessing_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(preprocessing_module)
            preprocessing_module.app.run(debug=False, host='0.0.0.0', port=port, use_reloader=False, threaded=True)
        elif service_name == "GANs Service":
            sys.path.insert(0, os.path.join(BASE_DIR, 'gans'))
            import gans
            gans.app.run(debug=False, host='0.0.0.0', port=port, use_reloader=False, threaded=True)
    except Exception as e:
        print(f"❌ {service_name} failed to start: {e}")

def launch_service_executable(name, module_path, port):
    print(f"🔄 {name} starting on port {port}...")
    thread = threading.Thread(
        target=run_service_in_process,
        args=(name, module_path, port),
        daemon=True
    )
    thread.start()
    service_threads.append((name, thread))
    time.sleep(2)
    print(f"✅ {name}: RUNNING")

def launch_service_development(name, rel_path, port):
    """Launch service in development mode using subprocess"""
    full_path = os.path.join(BASE_DIR, rel_path)
    service_dir = os.path.dirname(full_path)
    service_file = os.path.basename(full_path)
    
    print(f"🔄 {name} starting on port {port}...")
    print(f"   📂 Directory: {service_dir}")
    print(f"   📄 File: {service_file}")

    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONLEGACYWINDOWSSTDIO'] = '0'
    env['PYTHONUTF8'] = '1'
    
    # CRITICAL: Add project root to PYTHONPATH
    current_pythonpath = env.get('PYTHONPATH', '')
    env['PYTHONPATH'] = f"{BASE_DIR};{current_pythonpath}" if sys.platform == 'win32' else f"{BASE_DIR}:{current_pythonpath}"

    process = subprocess.Popen(
        [sys.executable, "-u", service_file],
        cwd=service_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding='utf-8',
        env=env
    )
    processes.append((name, process))

    time.sleep(5)
    
    if process.poll() is None:
        print(f"✅ {name}: HEALTHY (running)")
    else:
        print(f"❌ {name} failed to start (PID: {process.pid})")
        stdout, stderr = process.communicate()
        print("📄 STDOUT:")
        print(stdout if stdout else "No output")
        print("⚠️  STDERR:")
        print(stderr if stderr else "No errors")

def start_all_services():
    if EXECUTABLE_MODE:
        print("🔧 Running in executable mode with multi-threading")
        launch_service_executable("ML Backend", "ml_backend.app", 5000)
        launch_service_executable("Data Quality", "metric-quality.app", 1289)
        launch_service_executable("Data Preprocessing", "pre-processing.preprocessing_api", 1290)
        launch_service_executable("GANs Service", "gans.gans", 4321)
    else:
        print("🔧 Running in development mode with subprocesses")
        launch_service_development("ML Backend", "ml_backend/app.py", 5000)
        launch_service_development("Data Quality", "metric-quality/app.py", 1289)
        launch_service_development("Data Preprocessing", "pre-processing/preprocessing_api.py", 1290)
        launch_service_development("GANs Service", "gans/gans.py", 4321)

if HAS_STREAMLIT:
    @st.cache_resource
    def ensure_services_started():
        start_all_services()
        # Mount proxies after services started
        if HAS_TORNADO:
            mount_proxy_routes()
        return True

def stop_all_services():
    print("\n🛑 Stopping all services...")
    if EXECUTABLE_MODE:
        pass
    else:
        print("🔄 Terminating service processes...")
        for name, process in processes:
            try:
                process.terminate()
                print(f"✅ {name} terminated.")
            except:
                print(f"⚠️  Failed to terminate {name}")
    print("👋 All services stopped. Goodbye!")

def main():
    try:
        is_streamlit = False
        if HAS_STREAMLIT and st.runtime.exists():
            is_streamlit = True
        
        if is_streamlit:
            # --- STREAMLIT UI MODE ---
            st.set_page_config(page_title="DataVizAI Backend API", page_icon="🔗", layout="wide")
            
            st.title("🔗 DataVizAI Backend Gateway")
            
            with st.sidebar:
                st.header("Service Status")
                st.success("System Online")
                st.markdown(f"**Working Directory:** `{BASE_DIR}`")
            
            st.info("Initializing services and API Gateway...")
            
            ensure_services_started()
            
            st.success("✅ API Gateway Active")
            
            st.markdown("### 🌐 Public API Endpoints")
            st.markdown("Use these endpoints for your frontend application:")
            
            st.code(f"""
POST /analyze  --> Proxies to Data Quality Service
POST /train    --> Proxies to ML Backend
POST /predict  --> Proxies to ML Backend
GET  /models   --> Proxies to ML Backend
            """, language="text")
            
            st.divider()
            
            # Simple health check visual
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("#### 🟢 Services Running")
                st.json({
                    "ML Backend": "Active",
                    "Data Quality": "Active",
                    "Preprocessing": "Active"
                })
            
        else:
            # --- CLI MODE ---
            print("🚀 DataVizAI Combined Services Launcher")
            start_all_services()
            # Keep script running
            while True:
                time.sleep(1)

    except KeyboardInterrupt:
        stop_all_services()
        sys.exit(0)
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
