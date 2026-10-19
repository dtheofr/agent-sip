from abc import ABC, abstractmethod

from .call import Call


class CallHandler(ABC):
    """Application behaviour. Subclass this; the SIP package never changes.

    ``on_call`` runs once per established call (concurrently for several calls).
    It is cancelled when the remote hangs up, and the call is hung up when it
    returns.
    """

    @abstractmethod
    async def on_call(self, call: Call) -> None: ...

    async def on_call_end(self, call: Call) -> None:
        """Always called after ``on_call`` finished or was cancelled."""
