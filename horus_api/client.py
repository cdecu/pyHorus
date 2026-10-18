"""
Horus API Connector

Provides a client for interacting with the Horus Office API to upload:
- Inbound invoices (purchases)
- Outbound invoices (sales)
- Miscellaneous operations (OD)
- Bank extracts
"""

import json
import os
from typing import Any, Dict, List, Optional

import requests


class HorusAPIError(Exception):
    """Exception raised for Horus API errors."""

    def __init__(self, error_type: str, message: str, details: str, status_code: int = 0):
        self.error_type = error_type
        self.message = message
        self.details = details
        self.status_code = status_code
        super().__init__(f"[{error_type}] {message}: {details}")


class HorusClient:
    """
    Client for the Horus Office API.

    Args:
        api_url: The license-specific API URL returned during OAuth 2 authorization.
        access_token: The OAuth 2 bearer access token.
    """

    def __init__(self, api_url: str, access_token: str):
        self.api_url = api_url.rstrip("/")
        self.access_token = access_token
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        })

    def _post(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send a POST request to the given API endpoint with JSON data.

        Args:
            endpoint: The API endpoint path (e.g. "/invoices.sales.new").
            data: The JSON payload to send.

        Returns:
            The JSON response from the API.

        Raises:
            HorusAPIError: If the API returns an error response.
        """
        url = f"{self.api_url}{endpoint}"
        response = self.session.post(url, json=data)

        if response.status_code >= 400:
            try:
                error_data = response.json()
                raise HorusAPIError(
                    error_type=error_data.get("ErrorType", "unknown"),
                    message=error_data.get("Message", "Unknown error"),
                    details=error_data.get("Details", response.text),
                    status_code=response.status_code,
                )
            except json.JSONDecodeError:
                raise HorusAPIError(
                    error_type="http_error",
                    message=f"HTTP {response.status_code}",
                    details=response.text,
                    status_code=response.status_code,
                )

        return response.json()

    def test_connection(self) -> Dict[str, Any]:
        """
        Test the API connection by calling the licenses.me endpoint.

        This verifies that the access token is valid and the API URL is correct.

        Returns:
            Dictionary containing license information if the token is valid.

        Raises:
            HorusAPIError: If the token is invalid or the API is unreachable.
        """
        return self._post("/licenses.me", {})

    def upload_sales_invoice(self, invoice_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Upload an outbound (sales) invoice.

        The invoice will be converted into a book entry.

        Args:
            invoice_data: Dictionary matching the invoices.sales.new schema.
                Required fields:
                    - FolderId: str
                    - DaybookId: str
                    - Type: int (0 for invoice, 1 for credit note)
                    - Number: int
                    - Date: str (ISO 8601)
                    - DueDate: str (ISO 8601)
                    - CompanyId: str
                    - TotalAmount: float
                    - BaseAmount: float
                    - TaxAmount: float
                    - InvoiceLines: list of line dicts

        Returns:
            Dictionary containing the generated book entry ID: {"Id": "..."}.
        """
        return self._post("/invoices.sales.new", invoice_data)

    def upload_purchase_invoice(self, invoice_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Upload an inbound (purchases) invoice.

        The invoice will be converted into a book entry.

        Args:
            invoice_data: Dictionary matching the invoices.purchases.new schema.
                Required fields:
                    - FolderId: str
                    - DaybookId: str
                    - Type: int (0 for invoice, 1 for credit note)
                    - Date: str (ISO 8601)
                    - DueDate: str (ISO 8601)
                    - CompanyId: str
                    - TotalAmount: float
                    - BaseAmount: float
                    - TaxAmount: float
                    - InvoiceLines: list of line dicts

        Returns:
            Dictionary containing the generated book entry ID: {"Id": "..."}.
        """
        return self._post("/invoices.purchases.new", invoice_data)

    def upload_miscellaneous_operation(self, operation_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Upload a miscellaneous operation (OD - Opération Diverses).

        The sum of debit and credit amounts must be balanced.

        Args:
            operation_data: Dictionary matching the book-entries.miscellaneous-operations.new schema.
                Required fields:
                    - FolderId: str
                    - DaybookId: str
                    - Number: int
                    - Date: str (ISO 8601)
                    - Lines: list of line dicts with Type, Account, Debit, Credit

        Returns:
            Dictionary containing the generated book entry ID: {"Id": "..."}.
        """
        return self._post("/book-entries.miscellaneous-operations.new", operation_data)

    def upload_bank_entry(self, bank_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Upload a bank extract entry (bank operation).

        Args:
            bank_data: Dictionary matching the book-entries.banks.new schema.
                Required fields:
                    - FolderId: str
                    - DaybookId: str (must be of type Bank = 500)
                    - Number: int
                    - Date: str (ISO 8601)
                    - Lines: list of line dicts with Type, Account, Amount, Date, CompanyId

        Returns:
            Dictionary containing the generated book entry ID: {"Id": "..."}.
        """
        return self._post("/book-entries.banks.new", bank_data)

    def upload_sales_invoice_from_file(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Upload one or more sales invoices from a JSON file.

        The JSON file should contain either a single invoice dict or a list of invoice dicts.

        Args:
            file_path: Path to the JSON file.

        Returns:
            List of API responses, one per invoice uploaded.
        """
        data = self._load_json_file(file_path)
        invoices = self._ensure_list(data)
        results = []
        for invoice in invoices:
            result = self.upload_sales_invoice(invoice)
            results.append(result)
        return results

    def upload_purchase_invoice_from_file(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Upload one or more purchase invoices from a JSON file.

        The JSON file should contain either a single invoice dict or a list of invoice dicts.

        Args:
            file_path: Path to the JSON file.

        Returns:
            List of API responses, one per invoice uploaded.
        """
        data = self._load_json_file(file_path)
        invoices = self._ensure_list(data)
        results = []
        for invoice in invoices:
            result = self.upload_purchase_invoice(invoice)
            results.append(result)
        return results

    def upload_miscellaneous_operation_from_file(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Upload one or more miscellaneous operations from a JSON file.

        The JSON file should contain either a single operation dict or a list of operation dicts.

        Args:
            file_path: Path to the JSON file.

        Returns:
            List of API responses, one per operation uploaded.
        """
        data = self._load_json_file(file_path)
        operations = self._ensure_list(data)
        results = []
        for operation in operations:
            result = self.upload_miscellaneous_operation(operation)
            results.append(result)
        return results

    def upload_bank_entry_from_file(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Upload one or more bank entries from a JSON file.

        The JSON file should contain either a single bank entry dict or a list of bank entry dicts.

        Args:
            file_path: Path to the JSON file.

        Returns:
            List of API responses, one per bank entry uploaded.
        """
        data = self._load_json_file(file_path)
        entries = self._ensure_list(data)
        results = []
        for entry in entries:
            result = self.upload_bank_entry(entry)
            results.append(result)
        return results

    @staticmethod
    def _load_json_file(file_path: str) -> Any:
        """Load and parse a JSON file."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"JSON file not found: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _ensure_list(data: Any) -> List[Any]:
        """Ensure the data is a list; wrap a single dict in a list."""
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            return [data]
        else:
            raise ValueError(f"Expected a JSON object or array, got {type(data).__name__}")
