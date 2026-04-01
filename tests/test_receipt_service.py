"""Unit tests สำหรับ ReceiptService"""
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_app.db")

import pytest
from unittest.mock import patch, MagicMock

from app.services.receipt_service import ReceiptService


def _sample_payload(total=500.0, items=None):
    return {
        "total": total,
        "payment_method": "cash",
        "items": items or [{"name": "Fuel 95", "qty": 1, "price": total}],
    }


class TestRenderAndSave:
    def test_creates_pdf_file(self, tmp_path):
        with patch("app.services.receipt_service.TMP_DIR", str(tmp_path)):
            path = ReceiptService.render_and_save(1, _sample_payload())
            assert os.path.isfile(path)
            assert path.endswith(".pdf")

    def test_pdf_filename_contains_id(self, tmp_path):
        with patch("app.services.receipt_service.TMP_DIR", str(tmp_path)):
            path = ReceiptService.render_and_save(42, _sample_payload())
            assert "receipt_42" in os.path.basename(path)

    def test_handles_many_items(self, tmp_path):
        items = [{"name": f"Item{i}", "qty": 1, "price": 10.0} for i in range(100)]
        with patch("app.services.receipt_service.TMP_DIR", str(tmp_path)):
            path = ReceiptService.render_and_save(1, _sample_payload(items=items))
            assert os.path.isfile(path)

    def test_handles_empty_items(self, tmp_path):
        with patch("app.services.receipt_service.TMP_DIR", str(tmp_path)):
            path = ReceiptService.render_and_save(1, _sample_payload(items=[]))
            assert os.path.isfile(path)


class TestPrintToTcp:
    @patch("app.services.receipt_service.TcpPrinterAdapter")
    def test_sends_data_to_printer(self, MockAdapter):
        mock_instance = MagicMock()
        MockAdapter.return_value = mock_instance
        ReceiptService.print_to_tcp(1, _sample_payload())
        mock_instance.connect.assert_called_once()
        mock_instance.send.assert_called_once()
        mock_instance.disconnect.assert_called_once()

    @patch("app.services.receipt_service.TcpPrinterAdapter")
    def test_send_data_contains_esc_pos_init(self, MockAdapter):
        mock_instance = MagicMock()
        MockAdapter.return_value = mock_instance
        ReceiptService.print_to_tcp(1, _sample_payload())
        sent_data = mock_instance.send.call_args[0][0]
        assert sent_data.startswith(b"\x1b\x40")  # ESC/POS init

    @patch("app.services.receipt_service.TcpPrinterAdapter")
    def test_disconnect_called_on_error(self, MockAdapter):
        mock_instance = MagicMock()
        mock_instance.send.side_effect = IOError("network error")
        MockAdapter.return_value = mock_instance
        with pytest.raises(IOError):
            ReceiptService.print_to_tcp(1, _sample_payload())
        mock_instance.disconnect.assert_called_once()

    @patch("app.services.receipt_service.TcpPrinterAdapter")
    def test_custom_host_port(self, MockAdapter):
        mock_instance = MagicMock()
        MockAdapter.return_value = mock_instance
        ReceiptService.print_to_tcp(1, _sample_payload(), host="10.0.0.1", port=1234)
        MockAdapter.assert_called_once_with(host="10.0.0.1", port=1234)
