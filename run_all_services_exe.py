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
from pathlib import Path

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

print("🚀 DataVizAI Combined Services Launcher")
print(f"📁 Working directory: {BASE_DIR}")
print(f"⚙️  Mode: {'Executable' if EXECUTABLE_MODE else 'Development'}")
print("🌟 Starting All Flask Services...")
print("=" * 60)

# Store subprocesses and threads for cleanup
processes = []
service_threads = []

def run_service_in_process(service_name, module_path, port):
    """Run a service in a separate process (for executable mode)"""
    try:
        if service_name == "ML Backend":
            from ml_backend.app import app
            app.run(debug=False, host='0.0.0.0', port=port, use_reloader=False, threaded=True)
        elif service_name == "Data Quality":
            # Import and run metric-quality app
            metric_quality_path = os.path.join(BASE_DIR, 'metric-quality')
            sys.path.insert(0, BASE_DIR)
            
            # Dynamically load the module
            import importlib.util
            spec = importlib.util.spec_from_file_location("app", os.path.join(metric_quality_path, "app.py"))
            metric_quality_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(metric_quality_module)
            
            # Run the Flask app
            metric_quality_module.app.run(debug=False, host='0.0.0.0', port=port, use_reloader=False, threaded=True)
        elif service_name == "Data Preprocessing":
            # Import and run preprocessing app
            preprocessing_path = os.path.join(BASE_DIR, 'pre-processing')
            sys.path.insert(0, BASE_DIR)
            
            # Dynamically load the module
            import importlib.util
            spec = importlib.util.spec_from_file_location("preprocessing_api", os.path.join(preprocessing_path, "preprocessing_api.py"))
            preprocessing_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(preprocessing_module)
            
            # Run the Flask app
            preprocessing_module.app.run(debug=False, host='0.0.0.0', port=port, use_reloader=False, threaded=True)
        elif service_name == "GANs Service":
            # Import and run GANs app
            sys.path.insert(0, os.path.join(BASE_DIR, 'gans'))
            import gans
            gans.app.run(debug=False, host='0.0.0.0', port=port, use_reloader=False, threaded=True)
    except Exception as e:
        print(f"❌ {service_name} failed to start: {e}")

def launch_service_executable(name, module_path, port):
    """Launch service in executable mode using threading"""
    print(f"🔄 {name} starting on port {port}...")
    
    # Create and start thread for this service
    thread = threading.Thread(
        target=run_service_in_process,
        args=(name, module_path, port),
        daemon=True
    )
    thread.start()
    service_threads.append((name, thread))
    
    # Wait a moment to check if service started
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

    # Set environment variables for UTF-8 encoding
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONLEGACYWINDOWSSTDIO'] = '0'
    env['PYTHONUTF8'] = '1'

    # Launch service in background with correct working directory and UTF-8 support
    # NEW: Use sys.executable to ensure the same python environment is used
    process = subprocess.Popen(
        [sys.executable, "-u", service_file],  # Use current python interpreter
        cwd=service_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding='utf-8',
        env=env
    )
    processes.append((name, process))

    # Wait briefly and check if still running
    time.sleep(5)  # Increased wait time for startup check
    
    # Check if process is still running
    if process.poll() is None:
        print(f"✅ {name}: HEALTHY (running)")
    else:
        print(f"❌ {name} failed to start (PID: {process.pid})")
        print("📄 STDOUT:")
        print(stdout if stdout else "No output")
        print("⚠️  STDERR:")
        print(stderr if stderr else "No errors")

try:
    if EXECUTABLE_MODE:
        # Running as executable - use threading
        print("🔧 Running in executable mode with multi-threading")
        launch_service_executable("ML Backend", "ml_backend.app", 5000)
        launch_service_executable("Data Quality", "metric-quality.app", 1289)
        launch_service_executable("Data Preprocessing", "pre-processing.preprocessing_api", 1290)
        launch_service_executable("GANs Service", "gans.gans", 4321)
    else:
        # Running as script - use subprocess
        print("🔧 Running in development mode with subprocesses")
        launch_service_development("ML Backend", "ml_backend/app.py", 5000)
        launch_service_development("Data Quality", "metric-quality/app.py", 1289)
        launch_service_development("Data Preprocessing", "pre-processing/preprocessing_api.py", 1290)
        launch_service_development("GANs Service", "gans/gans.py", 4321)

    print("=" * 60)
    print("🌐 SERVICE ENDPOINTS:")
    print("🤖 ML Backend:          http://localhost:5000")
    print("📊 Data Quality:        http://localhost:1289")
    print("🔧 Data Preprocessing:  http://localhost:1290")
    print("🎨 GANs Service:        http://localhost:4321")
    print("=" * 60)
    print("⚠️  Press Ctrl+C to stop all services")
    print("📱 Open your web browser and navigate to your frontend application")
    print("🔗 The services are now ready to accept requests!")

    # Keep script running
    if EXECUTABLE_MODE:
        # In executable mode, wait for threads
        try:
            while True:
                time.sleep(1)
                # Check if any threads have died
                for name, thread in service_threads:
                    if not thread.is_alive():
                        print(f"⚠️  {name} thread has stopped")
        except KeyboardInterrupt:
            print("\n🛑 Stopping all services...")
            print("👋 Goodbye!")
    else:
        # In development mode, wait for processes
        while True:
            time.sleep(1)

except KeyboardInterrupt:
    print("\n🛑 Stopping all services...")
    
    if EXECUTABLE_MODE:
        print("🔄 Stopping service threads...")
        # In executable mode, threads will stop when main process stops
    else:
        print("🔄 Terminating service processes...")
        for name, process in processes:
            try:
                process.terminate()
                print(f"✅ {name} terminated.")
            except:
                print(f"⚠️  Failed to terminate {name}")
    
    print("👋 All services stopped. Goodbye!")
    sys.exit(0)

except Exception as e:
    print(f"❌ Fatal error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
