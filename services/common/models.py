import datetime
import uuid
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

class SeatHoldRequest(BaseModel):
    event_id: str
    seat_id: str
    user_id: str
    hold_duration_seconds: int = 600

class SeatHoldResponse(BaseModel):
    reservation_id: str
    event_id: str
    seat_id: str
    user_id: str
    status: str = "HELD"
    expires_at: str
    ttl_seconds: int

class ConfirmOrderRequest(BaseModel):
    payment_method: str = "UPI"
    amount: float = 499.0

class ConfirmOrderResponse(BaseModel):
    order_id: str
    reservation_id: str
    ticket_id: str
    status: str = "CONFIRMED"
    amount: float
    idempotency_key: str
    issued_at: str

class WaitingRoomEnterRequest(BaseModel):
    user_id: str
    event_id: str

class WaitingRoomResponse(BaseModel):
    status: str  # QUEUED or ADMITTED
    user_id: str
    position: int
    queue_token: Optional[str] = None
    estimated_wait_seconds: int = 0

class SeatItem(BaseModel):
    seat_id: str
    tier: str
    row: str
    number: int
    price: float
    status: str  # AVAILABLE, HELD, BOOKED
    held_by: Optional[str] = None
    expires_in: Optional[int] = None

class SeatmapProjection(BaseModel):
    event_id: str
    event_name: str
    total_seats: int
    available_count: int
    held_count: int
    booked_count: int
    seats: List[SeatItem]

class TicketPass(BaseModel):
    ticket_id: str
    order_id: str
    reservation_id: str
    event_id: str
    seat_id: str
    attendee_id: str
    amount: float
    qr_signature: str
    qr_code_svg: Optional[str] = None
    s3_key: str
    s3_url: str
    issued_at: str

class TelemetryRecord(BaseModel):
    log_id: str
    event_id: str
    seat_id: str
    user_id: str
    attempt_type: str  # HOLD_ATTEMPT, CONFLICT, CHECKOUT, CANCEL, EXPIRE
    outcome: str       # SUCCESS, FAILED, TIMEOUT
    latency_ms: float
    timestamp: str
    ip_address: str
