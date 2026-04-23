"""
queuepool — waiting-room / queue detection for Camoufox.

Detects when a page is a known queue system (Queue-it, Akamai, Fastly/Shopify,
Nike SNKRS, Cloudflare waiting room, DataDome challenge), polls the user's
position, and fires a callback when the user is close to the front.

Public API:
    detect_queue(url, html=None) -> Optional[QueueState]
    QueueState                      (dataclass: kind, position, queue_size, ...)
    QueueKind                       (enum of supported systems)
    QueueMonitor(poll_interval, front_threshold).monitor(page, on_change, on_front)
    KNOWN_QUEUES                    (per-kind selector / URL-pattern config)
"""

from queuepool.detectors import (
    KNOWN_QUEUES,
    QueueKind,
    QueueState,
    detect_queue,
)
from queuepool.monitor import QueueMonitor

__all__ = [
    "KNOWN_QUEUES",
    "QueueKind",
    "QueueMonitor",
    "QueueState",
    "detect_queue",
]

__version__ = "0.1.0"
