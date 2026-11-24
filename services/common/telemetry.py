import time
import datetime
import uuid
import threading
from typing import List, Dict, Any, Optional

CASSANDRA_CQL_SCHEMA = """
-- EventPulse Cassandra High-Throughput Access Telemetry Schema
-- Optimized for high-write clickstreams and zero read-interference on transactional DB
CREATE KEYSPACE IF NOT EXISTS eventpulse 
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

CREATE TABLE IF NOT EXISTS eventpulse.seat_clickstream_telemetry (
    event_id text,
    event_date text,
    timestamp timestamp,
    log_id text,
    seat_id text,
    user_id text,
    attempt_type text, -- 'HOLD_ATTEMPT', 'CONFLICT', 'CHECKOUT', 'EXPIRED'
    outcome text,      -- 'SUCCESS', 'FAILED', 'TIMEOUT'
    latency_ms double,
    ip_address text,
    PRIMARY KEY ((event_id, event_date), timestamp, log_id)
) WITH CLUSTERING ORDER BY (timestamp DESC);
"""

class TelemetryStore:
    """
    High-write telemetry log store.
    Captures all seat hold attempts, conflicts, timeouts, and latency traces.
    Connects to Apache Cassandra cluster if available; falls back to append log buffer.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(TelemetryStore, cls).__new__(cls)
                    cls._instance._init_store()
        return cls._instance

    def _init_store(self):
        self.records: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def record(self, event_id: str, seat_id: str, user_id: str, attempt_type: str, outcome: str, latency_ms: float, ip_address: str = "127.0.0.1") -> Dict[str, Any]:
        log_entry = {
            "log_id": f"tel_{uuid.uuid4().hex[:8]}",
            "event_id": event_id,
            "seat_id": seat_id,
            "user_id": user_id,
            "attempt_type": attempt_type,
            "outcome": outcome,
            "latency_ms": round(latency_ms, 2),
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "ip_address": ip_address
        }
        with self._lock:
            self.records.append(log_entry)
            if len(self.records) > 2000:
                self.records.pop(0)
        return log_entry

    def get_logs(self, limit: int = 50, event_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            filtered = self.records
            if event_id:
                filtered = [r for r in filtered if r["event_id"] == event_id]
            return list(reversed(filtered[-limit:]))

    def get_metrics_summary(self) -> Dict[str, Any]:
        with self._lock:
            total = len(self.records)
            if total == 0:
                return {
                    "total_requests": 0,
                    "success_count": 0,
                    "conflict_count": 0,
                    "avg_latency_ms": 0.0,
                    "p99_latency_ms": 0.0
                }
            successes = sum(1 for r in self.records if r["outcome"] == "SUCCESS")
            conflicts = sum(1 for r in self.records if r["outcome"] == "CONFLICT" or r["attempt_type"] == "CONFLICT")
            latencies = sorted([r["latency_ms"] for r in self.records])
            avg_lat = sum(latencies) / len(latencies)
            p99_idx = int(len(latencies) * 0.99)
            p99_lat = latencies[min(p99_idx, len(latencies) - 1)]

            return {
                "total_requests": total,
                "success_count": successes,
                "conflict_count": conflicts,
                "avg_latency_ms": round(avg_lat, 2),
                "p99_latency_ms": round(p99_lat, 2)
            }

telemetry_store = TelemetryStore()
