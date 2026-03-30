import socket
import os
from typing import Dict

DEFAULT_HOST = os.getenv("PRINTER_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.getenv("PRINTER_PORT", "9100"))


class TcpPrinterAdapter:
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock = None

    def connect(self):
        self._sock = socket.create_connection((self.host, self.port), timeout=self.timeout)

    def disconnect(self):
        try:
            if self._sock:
                self._sock.close()
        finally:
            self._sock = None

    def send(self, data: bytes):
        if not self._sock:
            self.connect()
        self._sock.sendall(data)

    def status(self) -> Dict[str, str]:
        # Minimal status; real printers may support SNMP/vendor APIs
        return {"host": self.host, "port": str(self.port), "connected": str(self._sock is not None)}
