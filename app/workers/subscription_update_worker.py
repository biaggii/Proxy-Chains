"""Background subscription download and parse worker."""

from PySide6.QtCore import QThread, Signal

from models.subscription import Subscription
from parsers.subscription_fetcher import fetch_and_parse


class SubscriptionUpdateWorker(QThread):
    completed = Signal(str, object, object, object)

    def __init__(self, subscription: Subscription, parent=None):
        super().__init__(parent)
        self.snapshot = Subscription.from_dict(subscription.to_dict())

    def run(self) -> None:
        nodes, errors = fetch_and_parse(self.snapshot)
        self.completed.emit(
            self.snapshot.sub_id,
            nodes,
            errors,
            self.snapshot.to_dict(),
        )
