#!/usr/bin/env python3
"""
Horus Office API Upload Tool

Command-line tool to upload accounting data to Horus Office via the API.
Supports uploading:
- Inbound invoices (purchases)
- Outbound invoices (sales)
- Miscellaneous operations (OD)
- Bank extracts

Usage:
    python main.py --type sales --file invoices.json
    python main.py --type purchases --file invoices.json
    python main.py --type miscellaneous --file operations.json
    python main.py --type bank --file bank_extract.json
    python main.py test-login

Environment variables:
    HORUS_API_URL     The license-specific API URL from OAuth 2 authorization
    HORUS_ACCESS_TOKEN The OAuth 2 bearer access token
"""

import argparse
import json
import sys
import os

from horus_api.client import HorusClient, HorusAPIError


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        description="Upload accounting data to Horus Office API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --type sales --file outbound.json
  %(prog)s --type purchases --file inbound.json
  %(prog)s --type miscellaneous --file operations.json
  %(prog)s --type bank --file bank_extract.json
  %(prog)s test-login

Environment variables:
  HORUS_API_URL       License-specific API URL (required)
  HORUS_ACCESS_TOKEN  OAuth 2 access token (required)
        """,
    )

    # Common options for all commands
    parser.add_argument(
        "--api-url",
        default=None,
        help="Horus API URL (overrides HORUS_API_URL environment variable)",
    )
    parser.add_argument(
        "--access-token",
        default=None,
        help="Horus access token (overrides HORUS_ACCESS_TOKEN environment variable)",
    )

    # Sub-commands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # test-login sub-command
    test_login_parser = subparsers.add_parser(
        "test-login",
        help="Test API connection and verify the access token",
    )
    test_login_parser.add_argument(
        "--api-url",
        default=None,
        help="Horus API URL (overrides HORUS_API_URL environment variable)",
    )
    test_login_parser.add_argument(
        "--access-token",
        default=None,
        help="Horus access token (overrides HORUS_ACCESS_TOKEN environment variable)",
    )

    # Default upload command arguments (positional-like, but optional when using sub-commands)
    parser.add_argument(
        "--type",
        choices=["sales", "purchases", "miscellaneous", "bank"],
        help="Type of data to upload: sales (outbound invoices), "
             "purchases (inbound invoices), miscellaneous (OD), or bank (bank extracts)",
    )
    parser.add_argument(
        "--file",
        help="Path to the JSON file containing the data to upload",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the JSON file without uploading to the API",
    )

    return parser


def get_config(args) -> tuple:
    """
    Get API URL and access token from args or environment variables.

    Returns:
        Tuple of (api_url, access_token)
    """
    api_url = args.api_url or os.environ.get("HORUS_API_URL", "")
    access_token = args.access_token or os.environ.get("HORUS_ACCESS_TOKEN", "")

    if not api_url:
        print("Error: HORUS_API_URL is required. Set it via --api-url or the HORUS_API_URL environment variable.", file=sys.stderr)
        sys.exit(1)

    if not access_token:
        print("Error: HORUS_ACCESS_TOKEN is required. Set it via --access-token or the HORUS_ACCESS_TOKEN environment variable.", file=sys.stderr)
        sys.exit(1)

    return api_url, access_token


def upload_data(client: HorusClient, entry_type: str, file_path: str) -> list:
    """
    Upload data based on the entry type.

    Args:
        client: HorusClient instance
        entry_type: One of 'sales', 'purchases', 'miscellaneous', 'bank'
        file_path: Path to the JSON file

    Returns:
        List of API responses
    """
    uploaders = {
        "sales": client.upload_sales_invoice_from_file,
        "purchases": client.upload_purchase_invoice_from_file,
        "miscellaneous": client.upload_miscellaneous_operation_from_file,
        "bank": client.upload_bank_entry_from_file,
    }

    uploader = uploaders[entry_type]
    return uploader(file_path)


def validate_json_file(file_path: str, entry_type: str) -> list:
    """
    Validate a JSON file and return the parsed entries.

    Args:
        file_path: Path to the JSON file.
        entry_type: Type of entries for labeling.

    Returns:
        List of entry dictionaries.

    Raises:
        SystemExit: If the file is invalid.
    """
    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {file_path}: {e}", file=sys.stderr)
        sys.exit(1)

    # Ensure it's a list of dicts
    if isinstance(data, dict):
        entries = [data]
    elif isinstance(data, list):
        entries = data
    else:
        print(f"Error: Expected a JSON object or array in {file_path}", file=sys.stderr)
        sys.exit(1)

    # Validate each entry is a dict
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            print(f"Error: Entry {i} in {file_path} is not a JSON object", file=sys.stderr)
            sys.exit(1)

    return entries


def main():
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Handle test-login sub-command
    if args.command == "test-login":
        api_url, access_token = get_config(args)
        print(f"Testing connection to {api_url}...")
        client = HorusClient(api_url=api_url, access_token=access_token)
        try:
            info = client.test_connection()
            print("Connection successful! Token is valid.")
            print(f"License info: {json.dumps(info, indent=2)}")
            return 0
        except HorusAPIError as e:
            print(f"Connection failed: {e}", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"Connection failed: {e}", file=sys.stderr)
            return 1

    # Upload command: --type and --file are required
    if not args.type:
        parser.print_help()
        print("\nError: --type is required for upload.", file=sys.stderr)
        sys.exit(1)

    if not args.file:
        parser.print_help()
        print("\nError: --file is required for upload.", file=sys.stderr)
        sys.exit(1)

    api_url, access_token = get_config(args)

    # Handle dry-run mode
    if args.dry_run:
        print(f"Validating JSON file: {args.file} (dry-run mode, no upload)...")
        entries = validate_json_file(args.file, args.type)
        count = len(entries)

        type_labels = {
            "sales": "outbound invoice(s)",
            "purchases": "inbound invoice(s)",
            "miscellaneous": "miscellaneous operation(s)",
            "bank": "bank extract entr(y/ies)",
        }
        label = type_labels[args.type]
        print(f"Valid JSON: {count} {label} found in {args.file}")

        for i, entry in enumerate(entries, 1):
            print(f"\n  Entry [{i}]:")
            for key, value in entry.items():
                if isinstance(value, list):
                    print(f"    {key}: [{len(value)} items]")
                else:
                    print(f"    {key}: {value}")

        print(f"\nValidation complete. {count} {label} ready to upload.")
        return 0

    # Normal upload mode
    # Validate file exists
    if not os.path.exists(args.file):
        print(f"Error: File not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    # Preview the data
    with open(args.file, "r", encoding="utf-8") as f:
        data = json.load(f)

    count = len(data) if isinstance(data, list) else 1
    type_labels = {
        "sales": "outbound invoice(s)",
        "purchases": "inbound invoice(s)",
        "miscellaneous": "miscellaneous operation(s)",
        "bank": "bank extract entr(y/ies)",
    }
    label = type_labels[args.type]
    print(f"Uploading {count} {label} from {args.file}...")

    # Create client and upload
    client = HorusClient(api_url=api_url, access_token=access_token)

    try:
        results = upload_data(client, args.type, args.file)

        print(f"\nSuccessfully uploaded {len(results)} entr(y/ies):")
        for i, result in enumerate(results, 1):
            entry_id = result.get("Id", "unknown")
            print(f"  [{i}] Book Entry ID: {entry_id}")

        return 0

    except HorusAPIError as e:
        print(f"\nAPI Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\nUnexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
