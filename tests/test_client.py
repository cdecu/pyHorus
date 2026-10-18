"""
Tests for horus_api.client module.

Covers:
- HorusClient initialization and headers
- All 4 upload methods (sales, purchases, miscellaneous, bank)
- File-based batch uploads (single dict and list)
- Error handling (API errors, non-JSON errors, file not found)
- Helper methods (_ensure_list, _load_json_file)
"""

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from horus_api.client import HorusClient, HorusAPIError


class TestHorusClientInit(unittest.TestCase):
    """Test HorusClient initialization."""

    def test_init_sets_api_url_without_trailing_slash(self):
        client = HorusClient("https://api.horus.be/", "token123")
        self.assertEqual(client.api_url, "https://api.horus.be")

    def test_init_sets_api_url_without_adding_slash(self):
        client = HorusClient("https://api.horus.be", "token123")
        self.assertEqual(client.api_url, "https://api.horus.be")

    def test_init_sets_access_token(self):
        client = HorusClient("https://api.horus.be", "my-secret-token")
        self.assertEqual(client.access_token, "my-secret-token")

    def test_init_sets_authorization_header(self):
        client = HorusClient("https://api.horus.be", "token123")
        self.assertEqual(client.session.headers["Authorization"], "Bearer token123")

    def test_init_sets_content_type_header(self):
        client = HorusClient("https://api.horus.be", "token123")
        self.assertEqual(client.session.headers["Content-Type"], "application/json")


class TestHorusClientPost(unittest.TestCase):
    """Test the _post method."""

    def setUp(self):
        self.client = HorusClient("https://api.horus.be", "token123")

    @patch.object(HorusClient, '_post', return_value={"Id": "generated-id-123"})
    def test_post_returns_json(self, mock_post):
        result = self.client._post("/test", {"key": "value"})
        self.assertEqual(result, {"Id": "generated-id-123"})

    @patch('horus_api.client.requests.Session')
    def test_post_sends_correct_url(self, mock_session_class):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Id": "123"}
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session

        client = HorusClient("https://api.horus.be", "token123")
        client._post("/invoices.sales.new", {"FolderId": "abc"})

        mock_session.post.assert_called_once_with(
            "https://api.horus.be/invoices.sales.new",
            json={"FolderId": "abc"}
        )

    @patch('horus_api.client.requests.Session')
    def test_post_raises_on_4xx_error(self, mock_session_class):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "ErrorType": "ValidationError",
            "Message": "Invalid input",
            "Details": "Field 'FolderId' is required"
        }
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session

        client = HorusClient("https://api.horus.be", "token123")
        with self.assertRaises(HorusAPIError) as ctx:
            client._post("/test", {})

        self.assertEqual(ctx.exception.error_type, "ValidationError")
        self.assertEqual(ctx.exception.message, "Invalid input")
        self.assertEqual(ctx.exception.status_code, 400)

    @patch('horus_api.client.requests.Session')
    def test_post_raises_on_5xx_error(self, mock_session_class):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {
            "ErrorType": "ServerError",
            "Message": "Internal error",
            "Details": "Something went wrong"
        }
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session

        client = HorusClient("https://api.horus.be", "token123")
        with self.assertRaises(HorusAPIError) as ctx:
            client._post("/test", {})

        self.assertEqual(ctx.exception.status_code, 500)

    @patch('horus_api.client.requests.Session')
    def test_post_handles_non_json_error_response(self, mock_session_class):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 502
        mock_response.text = "Bad Gateway"
        mock_response.json.side_effect = json.JSONDecodeError("Expecting value", "doc", 0)
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session

        client = HorusClient("https://api.horus.be", "token123")
        with self.assertRaises(HorusAPIError) as ctx:
            client._post("/test", {})

        self.assertEqual(ctx.exception.error_type, "http_error")
        self.assertEqual(ctx.exception.status_code, 502)


class TestTestConnection(unittest.TestCase):
    """Test the test_connection method."""

    @patch('horus_api.client.requests.Session')
    def test_test_connection_calls_licenses_me(self, mock_session_class):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"License": "Test", "Valid": True}
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session

        client = HorusClient("https://api.horus.be", "token123")
        result = client.test_connection()

        call_args = mock_session.post.call_args
        self.assertEqual(call_args[0][0], "https://api.horus.be/licenses.me")
        self.assertEqual(result, {"License": "Test", "Valid": True})

    @patch('horus_api.client.requests.Session')
    def test_test_connection_raises_on_invalid_token(self, mock_session_class):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {
            "ErrorType": "Unauthorized",
            "Message": "Invalid token",
            "Details": "Token expired"
        }
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session

        client = HorusClient("https://api.horus.be", "bad-token")
        with self.assertRaises(HorusAPIError) as ctx:
            client.test_connection()
        self.assertEqual(ctx.exception.status_code, 401)


class TestUploadSalesInvoice(unittest.TestCase):
    """Test upload_sales_invoice method."""

    @patch('horus_api.client.requests.Session')
    def test_upload_sales_invoice_calls_correct_endpoint(self, mock_session_class):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Id": "sales-123"}
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session

        client = HorusClient("https://api.horus.be", "token123")
        invoice = {
            "FolderId": "folder-1",
            "DaybookId": "daybook-1",
            "Type": 0,
            "Number": 1001,
            "Date": "2024-10-01T00:00:00+00:00",
            "DueDate": "2024-10-31T00:00:00+00:00",
            "CompanyId": "company-1",
            "TotalAmount": 2420.00,
            "BaseAmount": 2000.00,
            "TaxAmount": 420.00,
            "InvoiceLines": []
        }
        result = client.upload_sales_invoice(invoice)

        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        self.assertEqual(call_args[0][0], "https://api.horus.be/invoices.sales.new")
        self.assertEqual(result, {"Id": "sales-123"})


class TestUploadPurchaseInvoice(unittest.TestCase):
    """Test upload_purchase_invoice method."""

    @patch('horus_api.client.requests.Session')
    def test_upload_purchase_invoice_calls_correct_endpoint(self, mock_session_class):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Id": "purchase-456"}
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session

        client = HorusClient("https://api.horus.be", "token123")
        invoice = {
            "FolderId": "folder-1",
            "DaybookId": "daybook-1",
            "Type": 0,
            "Date": "2024-10-01T00:00:00+00:00",
            "DueDate": "2024-10-31T00:00:00+00:00",
            "CompanyId": "company-1",
            "TotalAmount": 1815.00,
            "BaseAmount": 1500.00,
            "TaxAmount": 315.00,
            "InvoiceLines": []
        }
        result = client.upload_purchase_invoice(invoice)

        call_args = mock_session.post.call_args
        self.assertEqual(call_args[0][0], "https://api.horus.be/invoices.purchases.new")
        self.assertEqual(result, {"Id": "purchase-456"})


class TestUploadMiscellaneousOperation(unittest.TestCase):
    """Test upload_miscellaneous_operation method."""

    @patch('horus_api.client.requests.Session')
    def test_upload_miscellaneous_calls_correct_endpoint(self, mock_session_class):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Id": "misc-789"}
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session

        client = HorusClient("https://api.horus.be", "token123")
        operation = {
            "FolderId": "folder-1",
            "DaybookId": "daybook-1",
            "Number": 5001,
            "Date": "2024-10-01T00:00:00+00:00",
            "Lines": [
                {"Type": 0, "Account": "400000", "Debit": 100.00, "Credit": 0.00},
                {"Type": 0, "Account": "410000", "Debit": 0.00, "Credit": 100.00},
            ]
        }
        result = client.upload_miscellaneous_operation(operation)

        call_args = mock_session.post.call_args
        self.assertEqual(call_args[0][0], "https://api.horus.be/book-entries.miscellaneous-operations.new")
        self.assertEqual(result, {"Id": "misc-789"})


class TestUploadBankEntry(unittest.TestCase):
    """Test upload_bank_entry method."""

    @patch('horus_api.client.requests.Session')
    def test_upload_bank_entry_calls_correct_endpoint(self, mock_session_class):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Id": "bank-012"}
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session

        client = HorusClient("https://api.horus.be", "token123")
        bank_entry = {
            "FolderId": "folder-1",
            "DaybookId": "bank-daybook-1",
            "Number": 3001,
            "Date": "2024-10-01T00:00:00+00:00",
            "Lines": [
                {"Type": 0, "Account": "410000", "Amount": 500.00, "Date": "2024-10-01T00:00:00+00:00", "CompanyId": "company-1"}
            ]
        }
        result = client.upload_bank_entry(bank_entry)

        call_args = mock_session.post.call_args
        self.assertEqual(call_args[0][0], "https://api.horus.be/book-entries.banks.new")
        self.assertEqual(result, {"Id": "bank-012"})


class TestFileUploads(unittest.TestCase):
    """Test file-based batch upload methods."""

    def setUp(self):
        self.client = HorusClient("https://api.horus.be", "token123")

    @patch.object(HorusClient, 'upload_sales_invoice')
    def test_upload_sales_from_file_single_dict(self, mock_upload):
        mock_upload.return_value = {"Id": "sales-1"}
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"FolderId": "f1", "DaybookId": "d1"}, f)
            temp_path = f.name

        try:
            results = self.client.upload_sales_invoice_from_file(temp_path)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0], {"Id": "sales-1"})
            mock_upload.assert_called_once_with({"FolderId": "f1", "DaybookId": "d1"})
        finally:
            os.unlink(temp_path)

    @patch.object(HorusClient, 'upload_sales_invoice')
    def test_upload_sales_from_file_list(self, mock_upload):
        mock_upload.return_value = {"Id": "sales-1"}
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump([
                {"FolderId": "f1"},
                {"FolderId": "f2"},
                {"FolderId": "f3"},
            ], f)
            temp_path = f.name

        try:
            results = self.client.upload_sales_invoice_from_file(temp_path)
            self.assertEqual(len(results), 3)
            self.assertEqual(mock_upload.call_count, 3)
        finally:
            os.unlink(temp_path)

    @patch.object(HorusClient, 'upload_purchase_invoice')
    def test_upload_purchase_from_file(self, mock_upload):
        mock_upload.return_value = {"Id": "purchase-1"}
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"FolderId": "f1"}, f)
            temp_path = f.name

        try:
            results = self.client.upload_purchase_invoice_from_file(temp_path)
            self.assertEqual(len(results), 1)
        finally:
            os.unlink(temp_path)

    @patch.object(HorusClient, 'upload_miscellaneous_operation')
    def test_upload_miscellaneous_from_file(self, mock_upload):
        mock_upload.return_value = {"Id": "misc-1"}
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump([{"FolderId": "f1"}, {"FolderId": "f2"}], f)
            temp_path = f.name

        try:
            results = self.client.upload_miscellaneous_operation_from_file(temp_path)
            self.assertEqual(len(results), 2)
        finally:
            os.unlink(temp_path)

    @patch.object(HorusClient, 'upload_bank_entry')
    def test_upload_bank_from_file(self, mock_upload):
        mock_upload.return_value = {"Id": "bank-1"}
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"FolderId": "f1"}, f)
            temp_path = f.name

        try:
            results = self.client.upload_bank_entry_from_file(temp_path)
            self.assertEqual(len(results), 1)
        finally:
            os.unlink(temp_path)

    def test_upload_from_nonexistent_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.client.upload_sales_invoice_from_file("/nonexistent/path.json")


class TestEnsureList(unittest.TestCase):
    """Test the _ensure_list helper."""

    def test_list_returns_as_is(self):
        data = [{"a": 1}, {"a": 2}]
        result = HorusClient._ensure_list(data)
        self.assertEqual(result, data)

    def test_dict_wrapped_in_list(self):
        data = {"a": 1}
        result = HorusClient._ensure_list(data)
        self.assertEqual(result, [data])

    def test_empty_list_returns_empty(self):
        result = HorusClient._ensure_list([])
        self.assertEqual(result, [])

    def test_invalid_type_raises(self):
        with self.assertRaises(ValueError) as ctx:
            HorusClient._ensure_list("not a dict or list")
        self.assertIn("str", str(ctx.exception))

    def test_integer_raises(self):
        with self.assertRaises(ValueError):
            HorusClient._ensure_list(42)


class TestLoadJsonFile(unittest.TestCase):
    """Test the _load_json_file helper."""

    def test_load_valid_json(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"key": "value", "num": 42}, f)
            temp_path = f.name

        try:
            result = HorusClient._load_json_file(temp_path)
            self.assertEqual(result, {"key": "value", "num": 42})
        finally:
            os.unlink(temp_path)

    def test_load_json_array(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump([1, 2, 3], f)
            temp_path = f.name

        try:
            result = HorusClient._load_json_file(temp_path)
            self.assertEqual(result, [1, 2, 3])
        finally:
            os.unlink(temp_path)

    def test_load_nonexistent_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            HorusClient._load_json_file("/does/not/exist.json")


class TestHorusAPIError(unittest.TestCase):
    """Test the HorusAPIError exception."""

    def test_error_attributes(self):
        error = HorusAPIError(
            error_type="ValidationError",
            message="Invalid field",
            details="Field X is required",
            status_code=400
        )
        self.assertEqual(error.error_type, "ValidationError")
        self.assertEqual(error.message, "Invalid field")
        self.assertEqual(error.details, "Field X is required")
        self.assertEqual(error.status_code, 400)

    def test_error_string_representation(self):
        error = HorusAPIError("TypeError", "Bad value", "Details here", 422)
        self.assertIn("TypeError", str(error))
        self.assertIn("Bad value", str(error))
        self.assertIn("Details here", str(error))

    def test_error_default_status_code(self):
        error = HorusAPIError("Unknown", "Msg", "Details")
        self.assertEqual(error.status_code, 0)


if __name__ == "__main__":
    unittest.main()
