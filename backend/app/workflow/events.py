import asyncio
from collections import defaultdict

from app.schemas.execution import ProgressEvent


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[ProgressEvent]]] = defaultdict(set)

    async def publish(self, event: ProgressEvent) -> None:
        for queue in tuple(self._subscribers.get(event.task_id, set())):
            await queue.put(event)

    def subscribe(self, task_id: str) -> asyncio.Queue[ProgressEvent]:
        queue: asyncio.Queue[ProgressEvent] = asyncio.Queue(maxsize=50)
        self._subscribers[task_id].add(queue)
        return queue

    def unsubscribe(self, task_id: str, queue: asyncio.Queue[ProgressEvent]) -> None:
        self._subscribers[task_id].discard(queue)
        if not self._subscribers[task_id]:
            self._subscribers.pop(task_id, None)


event_bus = EventBus()
