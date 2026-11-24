import os
import sys
import logging
from typing import Optional

# Ensure project root is in sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from fastapi import FastAPI, HTTPException, Header, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Import domain components
from eventpulse.services.common.models import (
    SeatHoldRequest, SeatHoldResponse,
    ConfirmOrderRequest, ConfirmOrderResponse,
    WaitingRoomEnterRequest, WaitingRoomResponse,
    SeatmapProjection, TicketPass
)
from eventpulse.services.common.redis_engine import redis_engine
from eventpulse.services.common.database import db
from eventpulse.services.common.telemetry import telemetry_store
from eventpulse.services.common.event_bus import event_bus

# Initialize workers
import eventpulse.services.ticket_worker.src.worker as ticket_worker
import eventpulse.services.ledger_worker.src.worker as ledger_worker
import eventpulse.services.catalog_service.src.main as catalog_app_module
import eventpulse.services.reservation_service.src.main as reservation_app_module

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("EventPulse.Gateway")

app = FastAPI(
    title="EventPulse: High-Concurrency Distributed Ticketing & Flash-Sale Engine",
    description="Unified API Gateway routing to Reservation Command Service, CQRS Catalog Read Service, and Workers.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Route to Reservation Service
@app.post("/api/v1/waiting-room/enter", response_model=WaitingRoomResponse, tags=["Waiting Room"])
def enter_waiting_room(req: WaitingRoomEnterRequest):
    return reservation_app_module.enter_waiting_room(req)

@app.get("/api/v1/waiting-room/status/{user_id}", response_model=WaitingRoomResponse, tags=["Waiting Room"])
def get_waiting_status(user_id: str, event_id: str = "fest_rvce_2026"):
    return reservation_app_module.get_waiting_status(user_id, event_id)

@app.post("/api/v1/reservations/hold", status_code=status.HTTP_201_CREATED, response_model=SeatHoldResponse, tags=["Reservation Commands"])
def hold_seat(req: SeatHoldRequest, response: Response, queue_token: Optional[str] = Header(None, alias="X-Queue-Token")):
    return reservation_app_module.hold_seat(req, response, queue_token)

@app.post("/api/v1/reservations/{reservation_id}/confirm", response_model=ConfirmOrderResponse, tags=["Reservation Commands"])
def confirm_reservation(reservation_id: str, req: ConfirmOrderRequest, idempotency_key: str = Header(..., alias="Idempotency-Key")):
    return reservation_app_module.confirm_reservation(reservation_id, req, idempotency_key)

# Route to Catalog Service (CQRS Read Path)
@app.get("/api/v1/events/{event_id}/seatmap", response_model=SeatmapProjection, tags=["Catalog Query (CQRS)"])
def get_seatmap(event_id: str):
    return catalog_app_module.get_live_seatmap(event_id)

@app.get("/api/v1/dora/metrics", tags=["DevOps DORA Metrics"])
def get_dora_metrics():
    return catalog_app_module.get_dora_metrics()

# Route to Ticket & Telemetry
@app.get("/api/v1/tickets/{ticket_id}", tags=["Tickets & Passes"])
def get_ticket(ticket_id: str):
    tkt = ticket_worker.ISSUED_TICKETS.get(ticket_id)
    if not tkt:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return tkt

@app.get("/api/v1/audit/logs", tags=["Cassandra Telemetry"])
def get_audit_logs(limit: int = 50, event_id: Optional[str] = None):
    return {
        "storage_engine": "Apache Cassandra (Clustering Key: timestamp DESC)",
        "logs": telemetry_store.get_logs(limit, event_id),
        "metrics": telemetry_store.get_metrics_summary()
    }

@app.get("/api/v1/events/reset", tags=["Admin"])
def reset_demo():
    """Resets seat statuses and clears holds for fresh demo runs"""
    catalog_app_module.initialize_event_seatmap()
    with redis_engine.lock:
        redis_engine.hashes.clear()
        redis_engine.expirations.clear()
        redis_engine.waiting_room_zset.clear()
    reservation_app_module.active_reservations.clear()
    ticket_worker.ISSUED_TICKETS.clear()
    return {"status": "SUCCESS", "message": "EventPulse testbed state reset successfully."}

# Static Files for Frontend
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if os.path.exists(os.path.join(PROJECT_ROOT, "frontend")):
    FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")
else:
    FRONTEND_DIR = os.path.join(BASE_DIR, "eventpulse", "frontend")

if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

@app.get("/")
def serve_index():
    index_file = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "EventPulse API Gateway is live. Visit /docs for OpenAPI swagger UI."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("eventpulse.services.gateway_service.src.main:app", host="0.0.0.0", port=8000, reload=False)
