import os
import sys
import time
import json
import uuid
import hmac
import hashlib
import io
import base64
import logging
from typing import Dict, Any

# Ensure project root is in sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from eventpulse.services.common.event_bus import event_bus
from eventpulse.services.common.models import TicketPass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("EventPulse.TicketWorker")

QR_SECRET = "eventpulse_qr_hmac_secret_2026"
ISSUED_TICKETS: Dict[str, Dict[str, Any]] = {}

# S3 storage mock directory
S3_BUCKET_DIR = os.path.join(BASE_DIR, "eventpulse", "data", "s3_tickets")
os.makedirs(S3_BUCKET_DIR, exist_ok=True)

def generate_qr_svg(data_payload: str) -> str:
    """Generates an embedded QR code as base64 data URI using qrcode package"""
    try:
        import qrcode
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=6,
            border=2,
        )
        qr.add_data(data_payload)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#1e1b4b", back_color="white")
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{img_str}"
    except Exception as e:
        logger.warning(f"qrcode library generation fallback: {e}")
        return ""

def process_payment_completed(payload: Dict[str, Any]):
    """
    Async Ticket Pipeline:
    1. Consumes PaymentCompletedEvent from Outbox relay / Broker fan-out.
    2. Signs payload with cryptographic HMAC-SHA256.
    3. Generates QR Pass.
    4. Uploads to S3 bucket (or LocalStack S3).
    5. Publishes TicketIssuedEvent for notification fan-out.
    """
    order_id = payload.get("order_id")
    reservation_id = payload.get("reservation_id")
    event_id = payload.get("event_id")
    seat_id = payload.get("seat_id")
    user_id = payload.get("user_id")
    amount = payload.get("amount")

    ticket_id = f"tkt_{order_id[4:] if order_id else uuid.uuid4().hex[:8]}"

    # 1. Cryptographic HMAC-SHA256 signature
    sign_payload = f"{ticket_id}:{order_id}:{event_id}:{seat_id}:{user_id}:{amount}"
    qr_sig = hmac.new(QR_SECRET.encode(), sign_payload.encode(), hashlib.sha256).hexdigest()

    # 2. QR pass metadata
    qr_data = json.dumps({
        "tkt": ticket_id,
        "event": event_id,
        "seat": seat_id,
        "user": user_id,
        "sig": qr_sig[:16]
    })
    qr_image = generate_qr_svg(qr_data)

    # 3. Save ticket to S3 mock directory
    s3_key = f"tickets/{event_id}/{ticket_id}.json"
    s3_path = os.path.join(S3_BUCKET_DIR, f"{ticket_id}.json")
    ticket_record = {
        "ticket_id": ticket_id,
        "order_id": order_id,
        "reservation_id": reservation_id,
        "event_id": event_id,
        "seat_id": seat_id,
        "attendee_id": user_id,
        "amount": amount,
        "qr_signature": qr_sig,
        "qr_code_svg": qr_image,
        "s3_key": s3_key,
        "s3_url": f"https://s3.localstack.eventpulse.local/eventpulse-tickets/{s3_key}",
        "issued_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }

    with open(s3_path, "w") as f:
        json.dump(ticket_record, f, indent=2)

    ISSUED_TICKETS[ticket_id] = ticket_record
    logger.info(f"[Ticket Worker] Generated Ticket Pass {ticket_id} for Seat {seat_id}. Uploaded to S3.")

    # 4. Publish TicketIssuedEvent
    event_bus.publish("TicketIssuedEvent", {
        "event_type": "TicketIssuedEvent",
        "ticket_id": ticket_id,
        "order_id": order_id,
        "s3_url": ticket_record["s3_url"],
        "qr_signature": qr_sig
    })

def start_ticket_worker():
    event_bus.subscribe("PaymentCompletedEvent", process_payment_completed)
    logger.info("Ticket Generation Worker subscribed to PaymentCompletedEvent.")

start_ticket_worker()
