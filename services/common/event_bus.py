import asyncio
import json
import logging
import threading
from typing import Callable, Dict, List, Any

logger = logging.getLogger("EventPulse.EventBus")

class EventBus:
    """
    CQRS / Event Choreography Event Bus.
    Supports asynchronous publish-subscribe between microservices:
    Reservation Service -> Message Broker -> Catalog Service / Ledger Worker / Ticket Worker.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(EventBus, cls).__new__(cls)
                    cls._instance._subscribers = {}
                    cls._instance._history = []
                    cls._instance._history_lock = threading.Lock()
        return cls._instance

    def subscribe(self, event_type: str, callback: Callable[[Dict[str, Any]], None]):
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)
        logger.info(f"Subscribed handler to event type: {event_type}")

    def publish(self, event_type: str, payload: Dict[str, Any]):
        """Publish domain event to subscribers and event ledger"""
        message = {
            "event_type": event_type,
            "payload": payload
        }
        with self._history_lock:
            self._history.append(message)
            if len(self._history) > 1000:
                self._history.pop(0)

        # Dispatch to registered consumers
        handlers = self._subscribers.get(event_type, [])
        handlers += self._subscribers.get("*", [])

        for handler in handlers:
            try:
                # If running within asyncio loop
                if asyncio.iscoroutinefunction(handler):
                    asyncio.create_task(handler(payload))
                else:
                    threading.Thread(target=handler, args=(payload,), daemon=True).start()
            except Exception as e:
                logger.error(f"Error executing event handler for {event_type}: {e}")

    def get_event_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._history_lock:
            return list(reversed(self._history[-limit:]))

# Global singleton
event_bus = EventBus()
