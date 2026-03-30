from abc import ABC, abstractmethod


class DeviceAdapter(ABC):
    @abstractmethod
    def connect(self):
        pass

    @abstractmethod
    def disconnect(self):
        pass

    @abstractmethod
    def send(self, data: bytes):
        pass

    @abstractmethod
    def status(self) -> dict:
        pass
