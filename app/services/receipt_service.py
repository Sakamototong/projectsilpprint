import os
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from typing import Dict, Any

from ..devices.printer_tcp import TcpPrinterAdapter

TMP_DIR = os.path.join(os.getcwd(), "tmp")
os.makedirs(TMP_DIR, exist_ok=True)

DEFAULT_PRINTER_HOST = os.getenv("PRINTER_HOST", "127.0.0.1")
DEFAULT_PRINTER_PORT = int(os.getenv("PRINTER_PORT", "9100"))


class ReceiptService:
    @staticmethod
    def render_and_save(transaction_id: int, tx_payload: Dict[str, Any]) -> str:
        """Render a minimal receipt as PDF and return path."""
        path = os.path.join(TMP_DIR, f"receipt_{transaction_id}.pdf")
        c = canvas.Canvas(path, pagesize=A4)
        x = 40
        y = 800
        c.setFont("Helvetica-Bold", 12)
        c.drawString(x, y, f"Receipt for transaction {transaction_id}")
        y -= 30
        c.setFont("Helvetica", 10)
        c.drawString(x, y, f"Total: {tx_payload.get('total', '')}")
        y -= 20
        c.drawString(x, y, f"Payment method: {tx_payload.get('payment_method', '')}")
        y -= 30
        c.drawString(x, y, "Items:")
        y -= 20
        for it in tx_payload.get("items", []):
            c.drawString(x + 10, y, f"- {it.get('name')} x{it.get('qty')} {it.get('price')}")
            y -= 15
            if y < 60:
                c.showPage()
                y = 800
        c.showPage()
        c.save()
        return path

    @staticmethod
    def print_to_tcp(transaction_id: int, tx_payload: Dict[str, Any], host: str = None, port: int = None):
        """Send a simple ESC/POS-like text receipt to a TCP printer/simulator."""
        host = host or DEFAULT_PRINTER_HOST
        port = port or DEFAULT_PRINTER_PORT
        adapter = TcpPrinterAdapter(host=host, port=port)
        try:
            adapter.connect()
            lines = []
            lines.append(f"Receipt #{transaction_id}")
            lines.append(f"Total: {tx_payload.get('total', '')}")
            lines.append(f"Payment: {tx_payload.get('payment_method', '')}")
            lines.append("")
            lines.append("Items:")
            for it in tx_payload.get("items", []):
                lines.append(f"{it.get('name')} x{it.get('qty')} {it.get('price')}")
            lines.append("\n\n")
            text = "\n".join(lines)
            data = b"\x1b\x40" + text.encode("utf-8") + b"\n\x1dV\x00"
            adapter.send(data)
        finally:
            adapter.disconnect()
