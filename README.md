# pyHorus

Python client for the [Horus Office API](https://docs.horus-software.be/) to upload accounting data.

## Features

Upload the following types of accounting entries from JSON files:

| Type | Description | API Endpoint |
|------|-------------|--------------|
| `sales` | Outbound invoices (sales) | `POST /invoices.sales.new` |
| `purchases` | Inbound invoices (purchases) | `POST /invoices.purchases.new` |
| `miscellaneous` | Miscellaneous operations (OD) | `POST /book-entries.miscellaneous-operations.new` |
| `bank` | Bank extracts | `POST /book-entries.banks.new` |

## Project Structure

```
pyHorus/
├── main.py                      # CLI entry point
├── pdf_to_excel.py              # Journal PDF report to Excel converter
├── pdf_to_ubls.py               # Journal PDF report to UBL invoices converter
├── horus_api/
│   ├── __init__.py
│   └── client.py                # Horus API connector
├── examples/
│   ├── invoices_outbound.json   # Example: sales invoices
│   ├── invoices_inbound.json    # Example: purchase invoices
│   ├── miscellaneous_operations.json  # Example: OD entries
│   └── bank_extract.json        # Example: bank extract entries
├── requirements.txt
└── README.md
```

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

The API URL and access token can be provided via environment variables or command-line arguments:

| Variable | Description |
|----------|-------------|
| `HORUS_API_URL` | License-specific API URL from OAuth 2 authorization |
| `HORUS_ACCESS_TOKEN` | OAuth 2 bearer access token |

## Usage

### Command Line

```bash
# Upload outbound (sales) invoices
python main.py --type sales --file examples/invoices_outbound.json

# Upload inbound (purchases) invoices
python main.py --type purchases --file examples/invoices_inbound.json

# Upload miscellaneous operations (OD)
python main.py --type miscellaneous --file examples/miscellaneous_operations.json

# Upload bank extracts
python main.py --type bank --file examples/bank_extract.json
```

You can also pass credentials directly:

```bash
python main.py --type sales --file invoices.json \
  --api-url https://your-api-url.horus-software.be \
  --access-token YOUR_TOKEN
```

### Python Library

```python
from horus_api.client import HorusClient

client = HorusClient(
    api_url="https://your-api-url.horus-software.be",
    access_token="YOUR_TOKEN"
)

# Upload a single invoice
result = client.upload_sales_invoice({
    "FolderId": "83f26e75-f474-4b09-a1d3-aa698e18fbf0",
    "DaybookId": "87f48c7e-54d1-48d2-aed7-447e6003bc67",
    "Type": 0,
    "Number": 202410001,
    "Date": "2024-10-01T00:00:00+00:00",
    "DueDate": "2024-10-31T00:00:00+00:00",
    "CompanyId": "32ebe925-23cc-4a3e-8b36-8b2b33780fc1",
    "TotalAmount": 1210.00,
    "BaseAmount": 1000.00,
    "TaxAmount": 210.00,
    "InvoiceLines": [
        {
            "Account": "700000",
            "BaseAmount": 1000.00,
            "TaxAmount": 210.00,
            "TaxRate": 21,
            "TaxOrigin": 0,
            "TaxType": 0,
        }
    ]
})
print(f"Book Entry ID: {result['Id']}")

# Upload from a JSON file (supports single object or array)
results = client.upload_purchase_invoice_from_file("invoices.json")
```

### PDF Journal to Excel

Convert the journal entries table (`DATE : PIECE : COMPTE : DEBIT : CREDIT : COMMENTAIRE`)
of a PDF report to an Excel file. The other sections of the report are ignored.

```bash
python pdf_to_excel.py docs/2025.05.FA.pdf                  # writes docs/2025.05.FA.xlsx
python pdf_to_excel.py docs/2025.05.FA.pdf -o journal.xlsx
```

Columns: `Date`, `Pièce`, `Type` (F/G...), `Compte`, `Libellé`, `Débit`, `Crédit`, `Commentaire`.

### PDF Journal to UBL invoices

Read the same journal table and write one UBL 2.1 invoice (Peppol BIS Billing 3.0) per document
in the given directory (`F1.xml`, `F2.xml`, ...). The supplier details are read from the third
parties file (`Tiers.xlsx`, column `Clé Fournisseur`); the buyer is CODOTRA (`BE0445314330`).

```bash
python pdf_to_ubls.py docs/2025.05.FA.pdf ubl/                       # uses docs/Tiers.xlsx
python pdf_to_ubls.py docs/2025.05.FA.pdf ubl/ --tiers other/Tiers.xlsx
```

VAT is deduced from the journal lines: `411xxx` only → standard rate (`S`), `411xxx` + `451xxx`
→ reverse charge (`K` for EU suppliers, `AE` otherwise), no VAT line → exempt (`E`).
A warning is printed for suppliers without VAT number or VAT amounts not matching a standard rate.

## JSON File Format

Each JSON file can contain a single entry object or an array of entry objects.

### Sales Invoice (Outbound)

```json
{
  "FolderId": "...",
  "DaybookId": "...",
  "Type": 0,
  "Number": 202410001,
  "Date": "2024-10-01T00:00:00+00:00",
  "DueDate": "2024-10-31T00:00:00+00:00",
  "CompanyId": "...",
  "TotalAmount": 1210.00,
  "BaseAmount": 1000.00,
  "TaxAmount": 210.00,
  "InvoiceLines": [
    {
      "Account": "700000",
      "BaseAmount": 1000.00,
      "TaxAmount": 210.00,
      "TaxRate": 21,
      "TaxOrigin": 0,
      "TaxType": 0
    }
  ]
}
```

### Purchase Invoice (Inbound)

Same as sales but with additional tax fields (`TaxKind`, `TaxCondition`, `TaxConditionValue`) and `VehicleId` support.

### Miscellaneous Operation (OD)

```json
{
  "FolderId": "...",
  "DaybookId": "...",
  "Number": 202410001,
  "Date": "2024-10-01T00:00:00+00:00",
  "Lines": [
    {
      "Type": 3,
      "Account": "499000",
      "Debit": 1000.00,
      "Credit": 0
    },
    {
      "Type": 3,
      "Account": "410000",
      "Debit": 0,
      "Credit": 1000.00
    }
  ]
}
```

> **Note:** The sum of Debit and Credit amounts must be balanced.

### Bank Extract

```json
{
  "FolderId": "...",
  "DaybookId": "...",
  "Number": 202410001,
  "Date": "2024-10-01T00:00:00+00:00",
  "Lines": [
    {
      "Type": 1,
      "Account": "400000",
      "Amount": 1210.00,
      "Date": "2024-10-01T00:00:00+00:00",
      "CompanyId": "..."
    }
  ]
}
```

> **Note:** `DaybookId` must be of type Bank (= 500).

## API Reference

For the full API specification, see the [Horus Software API Documentation](https://docs.horus-software.be/).
