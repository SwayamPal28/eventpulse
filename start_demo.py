"""
EventPulse - Quick Demo Launcher
Starts the Unified Gateway & Microservices Engine with Interactive Web Dashboard on port 8000.
"""

import sys
import os
import webbrowser
import uvicorn

# Ensure repository root and parent are on sys.path
REPO_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(REPO_DIR)
for path in (REPO_DIR, PARENT_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

def main():
    print("=" * 75)
    print("⚡ EventPulse: High-Concurrency Distributed Ticketing & Flash-Sale Engine")
    print("=" * 75)
    print("\n[+] Starting Microservices & Event Choreography Engine...")
    print("[+] Redis Lua Atomic Seat Locking Engine: ACTIVE")
    print("[+] CQRS Read Projection (Catalog Service): ACTIVE")
    print("[+] Relational Transactional Outbox (PostgreSQL / SQLite): ACTIVE")
    print("[+] Cassandra Telemetry & Audit Stream: ACTIVE")
    print("[+] S3 Digital QR Ticket Pass Generator: ACTIVE")
    print("\n🌐 Interactive Web Dashboard: http://localhost:8000")
    print("📖 OpenAPI 3.0 Swagger Documentation: http://localhost:8000/docs")
    print("-" * 75)
    print("Press Ctrl+C to terminate the testbed.\n")

    try:
        webbrowser.open("http://localhost:8000")
    except Exception:
        pass

    uvicorn.run("eventpulse.services.gateway_service.src.main:app", host="0.0.0.0", port=8000, reload=False)

if __name__ == "__main__":
    main()
