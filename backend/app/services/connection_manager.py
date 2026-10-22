import asyncio
import json
from typing import Set
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    In-memory asynchronous pub-sub connection manager for Server-Sent Events (SSE).
    Distributes live telemetry events to all active subscriber queues.
    """

    def __init__(self):
        self._subscribers: Set[asyncio.Queue] = set()
        self._activity_changed = asyncio.Event()

    async def connect(self) -> asyncio.Queue:
        """Register a new client subscriber queue."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.add(queue)
        self._activity_changed.set()
        logger.info(f"SSE client connected. Active subscribers: {len(self._subscribers)}")
        return queue

    def disconnect(self, queue: asyncio.Queue) -> None:
        """Unregister a client subscriber queue."""
        self._subscribers.discard(queue)
        self._activity_changed.set()
        logger.info(f"SSE client disconnected. Active subscribers: {len(self._subscribers)}")

    async def broadcast(self, event_type: str, data: dict) -> None:
        """Broadcast an SSE event payload to all connected subscriber queues."""
        if not self._subscribers:
            return

        payload = {
            "type": event_type,
            "data": data,
        }

        # Put message into each subscriber queue without blocking
        dead_queues = set()
        for queue in list(self._subscribers):
            try:
                if queue.full():
                    # Drop oldest if queue is full to prevent memory buildup
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                queue.put_nowait(payload)
            except Exception as e:
                logger.warning(f"Failed to push event to subscriber: {e}")
                dead_queues.add(queue)

        for dead_queue in dead_queues:
            self._subscribers.discard(dead_queue)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    async def wait_for_activity_change(self, timeout: float | None = None) -> None:
        """Wait until a viewer connects/disconnects, or until the caller's deadline."""
        self._activity_changed.clear()
        try:
            await asyncio.wait_for(self._activity_changed.wait(), timeout)
        except asyncio.TimeoutError:
            pass


# Global singleton instance
connection_manager = ConnectionManager()
