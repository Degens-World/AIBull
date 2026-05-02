"""
AIBull desktop launcher.
Starts the FastAPI backend then opens a native window (or browser fallback).
"""
import sys
import os
import threading
import time
import subprocess
import uvicorn

PORT = int(os.getenv("PORT", "8421"))


def _free_port():
    """Kill any process already bound to PORT."""
    try:
        out = subprocess.check_output(
            f'netstat -ano | findstr ":{PORT} "',
            shell=True, text=True, stderr=subprocess.DEVNULL
        )
        pids = set()
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[-1].isdigit() and int(parts[-1]) > 0:
                pids.add(parts[-1])
        for pid in pids:
            subprocess.call(f"taskkill /PID {pid} /F", shell=True,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if pids:
            time.sleep(1)
    except Exception:
        pass


def start_backend():
    _free_port()
    uvicorn.run(
        "backend.main:app",
        host="127.0.0.1",
        port=PORT,
        log_level="info",
    )


def wait_for_backend(timeout: int = 20) -> bool:
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/settings", timeout=1)
            return True
        except Exception:
            time.sleep(0.4)
    return False


def open_browser():
    import webbrowser
    webbrowser.open(f"http://127.0.0.1:{PORT}")


def main():
    t = threading.Thread(target=start_backend, daemon=True)
    t.start()

    print("Starting AIBull backend…")
    if not wait_for_backend():
        print("ERROR: Backend failed to start within 20 seconds.")
        print("Check that all dependencies are installed: .venv\\Scripts\\pip install -r requirements.txt")
        input("Press Enter to exit.")
        sys.exit(1)

    print(f"Backend ready at http://127.0.0.1:{PORT}")

    # Try native window first, fall back to browser
    try:
        import webview
        print("Opening desktop window…")
        webview.create_window(
            title="AIBull — Automated Trading",
            url=f"http://127.0.0.1:{PORT}",
            width=1400,
            height=900,
            min_size=(1100, 700),
            background_color="#0d1117",
        )
        webview.start(debug=False)
    except Exception as e:
        print(f"pywebview unavailable ({e}), opening in browser instead.")
        open_browser()
        print(f"AIBull running at http://127.0.0.1:{PORT}")
        print("Press Ctrl+C to stop the server.")
        try:
            t.join()
        except KeyboardInterrupt:
            print("\nShutting down.")


if __name__ == "__main__":
    main()
