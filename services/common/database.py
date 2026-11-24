import sqlite3
import json
import uuid
import datetime
import threading
import logging
from typing import Dict, Any, Optional, List, Tuple
from eventpulse.services.common.event_bus import event_bus

logger = logging.getLogger("EventPulse.Database")

class TransactionalDatabase:
    """
    Relational Database implementation with ACID Transactional Outbox Pattern.
    Prevents Dual-Write bugs by saving Order record and Outbound Event in the same atomic transaction.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(TransactionalDatabase, cls).__new__(cls)
                    cls._instance._init_db()
        return cls._instance

    def _init_db(self):
        self.db_path = "eventpulse_orders.db"
        self._lock = threading.Lock()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Orders table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                reservation_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                seat_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                amount REAL NOT NULL,
                payment_method TEXT NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """)
            # Outbox table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS outbox (
                id TEXT PRIMARY KEY,
                aggregate_type TEXT NOT NULL,
                aggregate_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                created_at TEXT NOT NULL
            );
            """)
            # Reservations table for relational persistence
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                reservation_id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                seat_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """)
            conn.commit()

        # Start background outbox publisher relay
        self.running = True
        self.relay_thread = threading.Thread(target=self._outbox_relay_worker, daemon=True)
        self.relay_thread.start()

    def _get_connection(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def save_reservation(self, reservation_id: str, event_id: str, seat_id: str, user_id: str):
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
                cursor.execute("""
                INSERT OR REPLACE INTO reservations (reservation_id, event_id, seat_id, user_id, status, created_at)
                VALUES (?, ?, ?, ?, 'HELD', ?)
                """, (reservation_id, event_id, seat_id, user_id, now_str))
                conn.commit()

    def create_order_with_outbox(
        self,
        reservation_id: str,
        event_id: str,
        seat_id: str,
        user_id: str,
        amount: float,
        payment_method: str,
        idempotency_key: str
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Executes ACID transaction inserting into orders AND outbox atomically.
        Guarantees idempotency via UNIQUE constraint on idempotency_key.
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # 1. Check idempotency key first
                cursor.execute("SELECT order_id, reservation_id, status, amount, created_at FROM orders WHERE idempotency_key = ?", (idempotency_key,))
                existing = cursor.fetchone()
                if existing:
                    logger.info(f"Duplicate checkout caught by Idempotency-Key {idempotency_key}. Returning cached order.")
                    return True, {
                        "order_id": existing[0],
                        "reservation_id": existing[1],
                        "status": existing[2],
                        "amount": existing[3],
                        "idempotency_key": idempotency_key,
                        "created_at": existing[4],
                        "idempotent_replay": True
                    }

                order_id = f"ord_{uuid.uuid4().hex[:10]}"
                outbox_id = f"out_{uuid.uuid4().hex[:10]}"
                now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

                payload = {
                    "event_type": "PaymentCompletedEvent",
                    "order_id": order_id,
                    "reservation_id": reservation_id,
                    "event_id": event_id,
                    "seat_id": seat_id,
                    "user_id": user_id,
                    "amount": amount,
                    "idempotency_key": idempotency_key,
                    "timestamp": now_str
                }

                try:
                    # Begin atomic transaction
                    cursor.execute("BEGIN TRANSACTION;")
                    # Insert order
                    cursor.execute("""
                    INSERT INTO orders (order_id, reservation_id, event_id, seat_id, user_id, amount, payment_method, idempotency_key, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'CONFIRMED', ?)
                    """, (order_id, reservation_id, event_id, seat_id, user_id, amount, payment_method, idempotency_key, now_str))

                    # Insert outbox entry
                    cursor.execute("""
                    INSERT INTO outbox (id, aggregate_type, aggregate_id, event_type, payload, status, created_at)
                    VALUES (?, 'Order', ?, 'PaymentCompletedEvent', ?, 'PENDING', ?)
                    """, (outbox_id, order_id, json.dumps(payload), now_str))

                    # Update reservation state
                    cursor.execute("""
                    UPDATE reservations SET status = 'CONFIRMED' WHERE reservation_id = ?
                    """, (reservation_id,))

                    conn.commit()
                    logger.info(f"[Outbox Pattern] Committed Order {order_id} and Outbox record {outbox_id} atomically.")
                    return True, {
                        "order_id": order_id,
                        "reservation_id": reservation_id,
                        "status": "CONFIRMED",
                        "amount": amount,
                        "idempotency_key": idempotency_key,
                        "created_at": now_str,
                        "idempotent_replay": False
                    }
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Transaction failed during order checkout: {e}")
                    return False, {"error": str(e)}

    def _outbox_relay_worker(self):
        """
        Outbox Relay Process (Transactional Outbox Pattern).
        Pulls PENDING events from outbox table and publishes to event bus.
        Guarantees at-least-once delivery without distributed 2PC locking.
        """
        while self.running:
            import time
            time.sleep(0.3)
            with self._lock:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT id, event_type, payload FROM outbox WHERE status = 'PENDING' LIMIT 10")
                    rows = cursor.fetchall()
                    if rows:
                        for row in rows:
                            outbox_id, event_type, payload_str = row
                            try:
                                payload = json.loads(payload_str)
                                event_bus.publish(event_type, payload)
                                cursor.execute("UPDATE outbox SET status = 'PROCESSED' WHERE id = ?", (outbox_id,))
                                conn.commit()
                                logger.info(f"[Outbox Relay] Dispatched event {event_type} for outbox {outbox_id}")
                            except Exception as e:
                                logger.error(f"Error relaying outbox message {outbox_id}: {e}")

db = TransactionalDatabase()
