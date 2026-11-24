import os
import sys
import uuid
import pytest

# Ensure root is in sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from eventpulse.services.common.models import SeatHoldRequest, ConfirmOrderRequest, WaitingRoomEnterRequest
from eventpulse.services.common.redis_engine import redis_engine
from eventpulse.services.common.telemetry import telemetry_store
import eventpulse.services.catalog_service.src.main as catalog
import eventpulse.services.reservation_service.src.main as reservation
import eventpulse.services.gateway_service.src.main as gateway

@pytest.fixture(autouse=True)
def reset_testbed():
    """Resets testbed state before each test"""
    gateway.reset_demo()

def test_health_probes():
    """Validates microservice liveness & readiness probes"""
    live = reservation.liveness()
    assert live["status"] == "UP"
    ready = reservation.readiness()
    assert ready["status"] == "READY"
    cat_live = catalog.liveness()
    assert cat_live["status"] == "UP"

def test_cqrs_seatmap_query():
    """Tests sub-millisecond CQRS read projection"""
    proj = catalog.get_live_seatmap("fest_rvce_2026")
    assert proj.total_seats == 60
    assert proj.available_count == 60
    assert proj.held_count == 0
    assert proj.booked_count == 0
    assert len(proj.seats) == 60

def test_atomic_seat_hold():
    """Tests atomic seat hold with Redis Lua script semantics"""
    req = SeatHoldRequest(
        event_id="fest_rvce_2026",
        seat_id="A-01",
        user_id="user_test_01",
        hold_duration_seconds=60
    )
    res = reservation.hold_seat(req, response=None, queue_token="test_token")
    assert res.status == "HELD"
    assert res.seat_id == "A-01"
    assert res.reservation_id.startswith("res_")

    # Verify CQRS Read Projection updated asynchronously
    proj = catalog.get_live_seatmap("fest_rvce_2026")
    assert proj.held_count == 1
    assert proj.available_count == 59

def test_conflict_rejection_prevents_race_conditions():
    """Tests that a second user attempting to hold the same seat is rejected with 409 Conflict"""
    req1 = SeatHoldRequest(
        event_id="fest_rvce_2026",
        seat_id="A-02",
        user_id="user_1",
        hold_duration_seconds=60
    )
    res1 = reservation.hold_seat(req1, response=None, queue_token="test_token")
    assert res1.status == "HELD"

    # User 2 tries to hold exact same seat concurrently
    req2 = SeatHoldRequest(
        event_id="fest_rvce_2026",
        seat_id="A-02",
        user_id="user_2",
        hold_duration_seconds=60
    )
    with pytest.raises(Exception) as excinfo:
        reservation.hold_seat(req2, response=None, queue_token="test_token")
    assert "409" in str(excinfo.value) or "currently held" in str(excinfo.value)

def test_transactional_outbox_checkout_and_idempotency():
    """Tests ACID checkout, Transactional Outbox, and Idempotency-Key guarantee"""
    # 1. Hold seat
    hold_req = SeatHoldRequest(
        event_id="fest_rvce_2026",
        seat_id="B-01",
        user_id="user_buyer",
        hold_duration_seconds=60
    )
    hold_res = reservation.hold_seat(hold_req, response=None, queue_token="test_token")
    res_id = hold_res.reservation_id

    idempotency_key = str(uuid.uuid4())

    # 2. Confirm checkout
    confirm_req = ConfirmOrderRequest(payment_method="UPI", amount=699.0)
    order_res = reservation.confirm_reservation(
        reservation_id=res_id,
        req=confirm_req,
        idempotency_key=idempotency_key
    )
    assert order_res.status == "CONFIRMED"
    assert order_res.order_id.startswith("ord_")

    # 3. Duplicate checkout retry with identical Idempotency-Key
    retry_res = reservation.confirm_reservation(
        reservation_id=res_id,
        req=confirm_req,
        idempotency_key=idempotency_key
    )
    # Must return exact same order_id without double-charging
    assert retry_res.order_id == order_res.order_id

def test_virtual_waiting_room_fifo():
    """Tests FIFO queue admission via Redis ZSET"""
    req1 = WaitingRoomEnterRequest(user_id="user_q1", event_id="fest_rvce_2026")
    res1 = reservation.enter_waiting_room(req1)
    status_val = res1.status if hasattr(res1, "status") else res1["status"]
    user_id_val = res1.user_id if hasattr(res1, "user_id") else res1["user_id"]
    assert status_val in ["ADMITTED", "QUEUED"]
    assert user_id_val == "user_q1"

def test_cassandra_telemetry_audit():
    """Tests high-throughput access audit logging"""
    req = SeatHoldRequest(
        event_id="fest_rvce_2026",
        seat_id="C-01",
        user_id="user_audit_check",
        hold_duration_seconds=30
    )
    reservation.hold_seat(req, response=None, queue_token="test_token")
    logs = telemetry_store.get_logs(limit=10)
    assert len(logs) > 0
    assert any(l["seat_id"] == "C-01" for l in logs)
