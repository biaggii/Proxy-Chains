"""
TCP latency test worker.

Runs TCP connect probes against proxy nodes in a thread pool.
Extracted from ``ui_pages_nodes.py`` for single-responsibility.
"""

import concurrent.futures
import socket
import time

from PySide6.QtCore import QThread, Signal


class TcpPingWorker(QThread):
    """Background worker that tests TCP connect latency for a batch of nodes."""

    progress = Signal(str, int)    # node_id, latency_ms (-1 for timeout)
    finished_ping = Signal()

    def __init__(self, nodes_to_ping: list[tuple[str, str, int]]):
        super().__init__()
        self.nodes = nodes_to_ping

    def run(self) -> None:
        def _ping_task(node_id: str, host: str, port: int) -> tuple[str, int]:
            latency = self._ping(host, int(port) if port else 80)
            return node_id, latency

        with concurrent.futures.ThreadPoolExecutor(max_workers=64) as executor:
            futures = {
                executor.submit(_ping_task, nid, host, port): nid
                for nid, host, port in self.nodes
            }
            for future in concurrent.futures.as_completed(futures):
                node_id, latency = future.result()
                self.progress.emit(node_id, latency)

        self.finished_ping.emit()

    @staticmethod
    def _ping(host: str, port: int) -> int:
        """Return round-trip time in ms, or -1 on failure."""
        try:
            start = time.time()
            with socket.create_connection((host, port), timeout=3.0):
                pass
            return int((time.time() - start) * 1000)
        except Exception:
            return -1
