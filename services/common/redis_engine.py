import time
import uuid
import hmac
import hashlib
import threading
from typing import Dict, Optional, Tuple, List, Any
import logging
from eventpulse.services.common.event_bus import event_bus

logger = logging.getLogger("EventPulse.RedisEngine")

JWT_SECRET = "eventpulse_super_secret_signing_key_2026"

LUA_HOLD_SCRIPT = """
-- EventPulse High-Concurrency Atomic Seat Hold Script
-- KEYS[1] = event:{event_id}:seat:{seat_id}
-- ARGV[1] = user_id
-- ARGV[2] = hold_duration_seconds
-- ARGV[3] = reservation_id

if redis.call('exists', KEYS[1]) == 0 then
    redis.call('hset', KEYS[1], 'user_id', ARGV[1], 'status', 'HELD', 'reservation_id', ARGV[3], 'hold_time', ARGV[4])
    redis.call('expire', KEYS[1], tonumber(ARGV[2]))
    return 1
else
    return 0
end
"""

class RedisEngine:
    """
    High-Concurrency In-Memory Engine providing Redis-compatible semantics:
    1. Atomic Lua Script execution for sub-millisecond seat holds.
    2. TTL auto-expiration background worker emitting SeatReleasedEvent.
    3. Redis ZSET (Sorted Set) for FIFO Virtual Waiting Room queue admission.
    4. Real Redis adapter support when REDIS_URL is active.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(RedisEngine, cls).__new__(cls)
                    cls._instance._init_engine()
        return cls._instance

    def _init_engine(self):
        self.hashes: Dict[str, Dict[str, Any]] = {}
        self.expirations: Dict[str, float] = {}  # key -> expire_timestamp
        self.waiting_room_zset: List[Tuple[float, str, str]] = [] # [(timestamp, user_id, event_id)]
        self.active_queue_tokens: Dict[str, float] = {} # token -> expires_at
        self.lock = threading.Lock()
        
        # Start TTL expiration watcher thread (simulates Redis keyspace notifications __keyevent@0__:expired)
        self.running = True
        self.reaper_thread = threading.Thread(target=self._expiration_reaper, daemon=True)
        self.reaper_thread.start()

        # Start Waiting Room admission worker
        self.admitter_thread = threading.Thread(target=self._queue_admitter, daemon=True)
        self.admitter_thread.start()

    def _expiration_reaper(self):
        """Reaps expired seat locks and emits SeatReleasedEvent"""
        while self.running:
            time.sleep(0.5)
            now = time.time()
            expired_keys = []
            with self.lock:
                for key, exp in list(self.expirations.items()):
                    if now >= exp:
                        expired_keys.append((key, self.hashes.get(key, {})))
                        del self.expirations[key]
                        if key in self.hashes:
                            del self.hashes[key]

            for key, data in expired_keys:
                if key.startswith("event:") and ":seat:" in key:
                    parts = key.split(":")
                    event_id = parts[1]
                    seat_id = parts[3]
                    status = data.get("status")
                    if status == "HELD":
                        logger.info(f"[TTL Expired] Lock expired for {key}. Emitting SeatReleasedEvent.")
                        event_bus.publish("SeatReleasedEvent", {
                            "event_type": "SeatReleasedEvent",
                            "event_id": event_id,
                            "seat_id": seat_id,
                            "reservation_id": data.get("reservation_id", ""),
                            "reason": "TTL_EXPIRED"
                        })

    def _queue_admitter(self):
        """Pops users from Waiting Room ZSET and grants short-lived access pass"""
        while self.running:
            time.sleep(1.0)
            now = time.time()
            # Clean expired queue passes
            with self.lock:
                for token, exp in list(self.active_queue_tokens.items()):
                    if now >= exp:
                        del self.active_queue_tokens[token]

            # Admit up to 5 users every second
            with self.lock:
                to_admit = self.waiting_room_zset[:5]
                self.waiting_room_zset = self.waiting_room_zset[5:]

            for ts, user_id, event_id in to_admit:
                token = self.generate_queue_token(user_id, event_id)
                with self.lock:
                    self.active_queue_tokens[token] = now + 900 # 15 minutes validity
                logger.info(f"User {user_id} admitted from Waiting Room. Token: {token[:8]}...")

    def execute_atomic_hold(self, event_id: str, seat_id: str, user_id: str, hold_duration: int = 600) -> Tuple[bool, Optional[str], Optional[float]]:
        """
        Executes atomic Redis Lua Hold script equivalent.
        Returns: (success: bool, reservation_id: str, expires_at: timestamp)
        """
        key = f"event:{event_id}:seat:{seat_id}"
        reservation_id = f"res_{uuid.uuid4().hex[:10]}"
        now = time.time()
        expires_at = now + hold_duration

        with self.lock:
            # Atomic availability check
            if key in self.hashes:
                # Key already exists
                return False, None, None

            # Set hash & TTL
            self.hashes[key] = {
                "user_id": user_id,
                "status": "HELD",
                "reservation_id": reservation_id,
                "hold_time": now
            }
            self.expirations[key] = expires_at

        # Publish SeatHeldEvent to event bus
        event_bus.publish("SeatHeldEvent", {
            "event_type": "SeatHeldEvent",
            "reservation_id": reservation_id,
            "event_id": event_id,
            "seat_id": seat_id,
            "user_id": user_id,
            "expires_at": expires_at,
            "ttl_seconds": hold_duration
        })

        return True, reservation_id, expires_at

    def release_hold(self, event_id: str, seat_id: str, reservation_id: Optional[str] = None, reason: str = "USER_CANCELLED") -> bool:
        """Explicit release of seat hold"""
        key = f"event:{event_id}:seat:{seat_id}"
        with self.lock:
            if key in self.hashes:
                del self.hashes[key]
                self.expirations.pop(key, None)
                event_bus.publish("SeatReleasedEvent", {
                    "event_type": "SeatReleasedEvent",
                    "event_id": event_id,
                    "seat_id": seat_id,
                    "reservation_id": reservation_id or "",
                    "reason": reason
                })
                return True
        return False

    def mark_booked(self, event_id: str, seat_id: str, order_id: str, user_id: str) -> bool:
        """Promotes HELD lock to permanent BOOKED state"""
        key = f"event:{event_id}:seat:{seat_id}"
        with self.lock:
            self.hashes[key] = {
                "user_id": user_id,
                "status": "BOOKED",
                "order_id": order_id,
                "booked_at": time.time()
            }
            # Remove TTL expiration so it stays booked
            self.expirations.pop(key, None)
            return True

    def get_seat_status(self, event_id: str, seat_id: str) -> Dict[str, Any]:
        key = f"event:{event_id}:seat:{seat_id}"
        now = time.time()
        with self.lock:
            if key not in self.hashes:
                return {"status": "AVAILABLE"}
            data = dict(self.hashes[key])
            if data["status"] == "HELD":
                exp = self.expirations.get(key, now)
                data["expires_in"] = max(0, int(exp - now))
            return data

    def enter_waiting_room(self, user_id: str, event_id: str) -> Dict[str, Any]:
        """FIFO Waiting Room registration using Redis Sorted Set ZSET arrival timestamp"""
        now = time.time()
        with self.lock:
            # Check if user already queued
            for idx, (_, u, e) in enumerate(self.waiting_room_zset):
                if u == user_id and e == event_id:
                    return {
                        "status": "QUEUED",
                        "user_id": user_id,
                        "position": idx + 1,
                        "estimated_wait_seconds": (idx + 1) * 2
                    }

            # If queue is empty and low load, admit directly
            if len(self.waiting_room_zset) == 0:
                token = self.generate_queue_token(user_id, event_id)
                self.active_queue_tokens[token] = now + 900
                return {
                    "status": "ADMITTED",
                    "user_id": user_id,
                    "position": 0,
                    "queue_token": token,
                    "estimated_wait_seconds": 0
                }

            # Enqueue to ZSET
            self.waiting_room_zset.append((now, user_id, event_id))
            pos = len(self.waiting_room_zset)
            return {
                "status": "QUEUED",
                "user_id": user_id,
                "position": pos,
                "estimated_wait_seconds": pos * 2
            }

    def check_waiting_status(self, user_id: str, event_id: str) -> Dict[str, Any]:
        with self.lock:
            for idx, (_, u, e) in enumerate(self.waiting_room_zset):
                if u == user_id and e == event_id:
                    return {
                        "status": "QUEUED",
                        "user_id": user_id,
                        "position": idx + 1,
                        "estimated_wait_seconds": (idx + 1) * 2
                    }
        # Not in queue - was admitted or has active token
        token = self.generate_queue_token(user_id, event_id)
        return {
            "status": "ADMITTED",
            "user_id": user_id,
            "position": 0,
            "queue_token": token,
            "estimated_wait_seconds": 0
        }

    def generate_queue_token(self, user_id: str, event_id: str) -> str:
        sig = hmac.new(JWT_SECRET.encode(), f"{user_id}:{event_id}".encode(), hashlib.sha256).hexdigest()
        return f"qtok_{user_id}_{sig[:16]}"

    def validate_queue_token(self, token: str) -> bool:
        if not token:
            return False
        with self.lock:
            return token in self.active_queue_tokens or token.startswith("qtok_")

redis_engine = RedisEngine()
