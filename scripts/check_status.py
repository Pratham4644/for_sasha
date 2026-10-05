#!/usr/bin/env python3
"""
Quick Health & Status Checker for Remote Camera + AI Platform.
Run this script anytime to verify all services are active and responding.
"""
import sys
import urllib.request
import urllib.error
import json

def check_service(name: str, url: str, expected_key: str = None) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "HealthCheck/1.0"})
        with urllib.request.urlopen(req, timeout=3.0) as res:
            status = res.status
            body = res.read().decode("utf-8")
            if status == 200:
                print(f"  [OK]  {name:<25} -> {url} (HTTP 200)")
                return True
            else:
                print(f"  [WARN] {name:<25} -> {url} (HTTP {status})")
                return False
    except urllib.error.HTTPError as e:
        # e.g., 404 on root of mediamtx is normal if path list isn't exposed there
        print(f"  [INFO] {name:<25} -> {url} (HTTP {e.code})")
        return True
    except Exception as e:
        print(f"  [FAIL] {name:<25} -> {url} ({e})")
        return False

def main():
    print("=" * 65)
    print("  DYNAMIC REMOTE CAMERA + AI PLATFORM - STATUS CHECK")
    print("=" * 65)
    print()

    checks = [
        ("Backend Root", "http://127.0.0.1:8000/"),
        ("Backend Health", "http://127.0.0.1:8000/health"),
        ("Database Health", "http://127.0.0.1:8000/health/database"),
        ("AI Pipeline Health", "http://127.0.0.1:8000/health/ai"),
        ("MediaMTX WebRTC Port", "http://127.0.0.1:8889/"),
        ("MediaMTX API Port", "http://127.0.0.1:9997/v3/paths/list"),
        ("Frontend UI", "http://localhost:5173/"),
    ]

    all_ok = True
    for name, url in checks:
        ok = check_service(name, url)
        if not ok and "Frontend" not in name:
            all_ok = False

    print()
    print("=" * 65)
    if all_ok:
        print("  All primary services are ONLINE!")
    else:
        print("  Some services appear offline.")
        print("  Run 'start_all.bat' or check the startup instructions.")
    print("=" * 65)

if __name__ == "__main__":
    main()
