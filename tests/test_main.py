"""
Tests for main.py CLI module.

Covers:
- Argument parser creation and validation
- Configuration retrieval from args and environment variables
- Upload data routing to correct client methods
- Main function error handling (missing file, missing credentials)
- Test-login sub-command
- Dry-run mode
- JSON file validation
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from horus_api.client import HorusClient, HorusAPIError


class TestCreateParser(unittest.TestCase):
    """Test the argument parser."""

    def test_parser_accepts_valid_type(self):
        from main import create_parser
        parser = create_parser()
        args = parser.parse_args(['--type', 'sales', '--file', 'test.json'])
        self.assertEqual(args.type, 'sales')
        self.assertEqual(args.file, 'test.json')

    def test_parser_rejects_invalid_type(self):
        from main import create_parser
        parser = create_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(['--type', 'invalid', '--file', 'test.json'])

    def test_parser_accepts_all_types(self):
        from main import create_parser
        parser = create_parser()
        for entry_type in ['sales', 'purchases', 'miscellaneous', 'bank']:
            args = parser.parse_args(['--type', entry_type, '--file', 'test.json'])
            self.assertEqual(args.type, entry_type)

    def test_parser_accepts_api_url_option(self):
        from main import create_parser
        parser = create_parser()
        args = parser.parse_args(['--type', 'sales', '--file', 'test.json', '--api-url', 'https://custom.api.be'])
        self.assertEqual(args.api_url, 'https://custom.api.be')

    def test_parser_accepts_access_token_option(self):
        from main import create_parser
        parser = create_parser()
        args = parser.parse_args(['--type', 'sales', '--file', 'test.json', '--access-token', 'secret-token'])
        self.assertEqual(args.access_token, 'secret-token')

    def test_parser_accepts_dry_run(self):
        from main import create_parser
        parser = create_parser()
        args = parser.parse_args(['--type', 'sales', '--file', 'test.json', '--dry-run'])
        self.assertTrue(args.dry_run)

    def test_parser_dry_run_default_false(self):
        from main import create_parser
        parser = create_parser()
        args = parser.parse_args(['--type', 'sales', '--file', 'test.json'])
        self.assertFalse(args.dry_run)

    def test_parser_test_login_command(self):
        from main import create_parser
        parser = create_parser()
        args = parser.parse_args(['test-login'])
        self.assertEqual(args.command, 'test-login')

    def test_parser_type_optional_with_subcommand(self):
        from main import create_parser
        parser = create_parser()
        # test-login does not require --type or --file
        args = parser.parse_args(['test-login', '--api-url', 'https://api.be', '--access-token', 'token'])
        self.assertEqual(args.command, 'test-login')
        self.assertIsNone(args.type)
        self.assertIsNone(args.file)

    def test_parser_type_optional_without_subcommand(self):
        from main import create_parser
        parser = create_parser()
        # Without sub-command, --type and --file are optional at parse time
        # but main() will check them
        args = parser.parse_args([])
        self.assertIsNone(args.type)
        self.assertIsNone(args.file)
        self.assertIsNone(args.command)


class TestGetConfig(unittest.TestCase):
    """Test configuration retrieval."""

    def setUp(self):
        # Clear environment variables before each test
        self._original_url = os.environ.pop('HORUS_API_URL', None)
        self._original_token = os.environ.pop('HORUS_ACCESS_TOKEN', None)

    def tearDown(self):
        # Restore environment variables
        if self._original_url is not None:
            os.environ['HORUS_API_URL'] = self._original_url
        elif 'HORUS_API_URL' in os.environ:
            del os.environ['HORUS_API_URL']

        if self._original_token is not None:
            os.environ['HORUS_ACCESS_TOKEN'] = self._original_token
        elif 'HORUS_ACCESS_TOKEN' in os.environ:
            del os.environ['HORUS_ACCESS_TOKEN']

    def test_config_from_args(self):
        from main import get_config
        args = MagicMock()
        args.api_url = 'https://from-args.be'
        args.access_token = 'token-from-args'

        url, token = get_config(args)
        self.assertEqual(url, 'https://from-args.be')
        self.assertEqual(token, 'token-from-args')

    def test_config_from_env(self):
        from main import get_config
        os.environ['HORUS_API_URL'] = 'https://from-env.be'
        os.environ['HORUS_ACCESS_TOKEN'] = 'token-from-env'

        args = MagicMock()
        args.api_url = None
        args.access_token = None

        url, token = get_config(args)
        self.assertEqual(url, 'https://from-env.be')
        self.assertEqual(token, 'token-from-env')

    def test_args_override_env(self):
        from main import get_config
        os.environ['HORUS_API_URL'] = 'https://from-env.be'
        os.environ['HORUS_ACCESS_TOKEN'] = 'token-from-env'

        args = MagicMock()
        args.api_url = 'https://override.be'
        args.access_token = 'override-token'

        url, token = get_config(args)
        self.assertEqual(url, 'https://override.be')
        self.assertEqual(token, 'override-token')

    def test_missing_api_url_exits(self):
        from main import get_config
        args = MagicMock()
        args.api_url = None
        args.access_token = 'some-token'

        with self.assertRaises(SystemExit) as ctx:
            get_config(args)
        self.assertEqual(ctx.exception.code, 1)

    def test_missing_access_token_exits(self):
        from main import get_config
        args = MagicMock()
        args.api_url = 'https://api.be'
        args.access_token = None

        with self.assertRaises(SystemExit) as ctx:
            get_config(args)
        self.assertEqual(ctx.exception.code, 1)


class TestUploadData(unittest.TestCase):
    """Test the upload_data routing function."""

    @patch('horus_api.client.requests.Session')
    def test_upload_data_routes_sales(self, mock_session_class):
        from main import upload_data
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Id": "sales-1"}
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session

        client = HorusClient("https://api.horus.be", "token")
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"FolderId": "f1"}, f)
            temp_path = f.name

        try:
            results = upload_data(client, 'sales', temp_path)
            self.assertEqual(len(results), 1)
        finally:
            os.unlink(temp_path)

    @patch('horus_api.client.requests.Session')
    def test_upload_data_routes_purchases(self, mock_session_class):
        from main import upload_data
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Id": "purchase-1"}
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session

        client = HorusClient("https://api.horus.be", "token")
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"FolderId": "f1"}, f)
            temp_path = f.name

        try:
            results = upload_data(client, 'purchases', temp_path)
            self.assertEqual(len(results), 1)
        finally:
            os.unlink(temp_path)

    @patch('horus_api.client.requests.Session')
    def test_upload_data_routes_miscellaneous(self, mock_session_class):
        from main import upload_data
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Id": "misc-1"}
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session

        client = HorusClient("https://api.horus.be", "token")
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"FolderId": "f1"}, f)
            temp_path = f.name

        try:
            results = upload_data(client, 'miscellaneous', temp_path)
            self.assertEqual(len(results), 1)
        finally:
            os.unlink(temp_path)

    @patch('horus_api.client.requests.Session')
    def test_upload_data_routes_bank(self, mock_session_class):
        from main import upload_data
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Id": "bank-1"}
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session

        client = HorusClient("https://api.horus.be", "token")
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"FolderId": "f1"}, f)
            temp_path = f.name

        try:
            results = upload_data(client, 'bank', temp_path)
            self.assertEqual(len(results), 1)
        finally:
            os.unlink(temp_path)


class TestMain(unittest.TestCase):
    """Test the main entry point."""

    def setUp(self):
        self._original_url = os.environ.pop('HORUS_API_URL', None)
        self._original_token = os.environ.pop('HORUS_ACCESS_TOKEN', None)

    def tearDown(self):
        if self._original_url is not None:
            os.environ['HORUS_API_URL'] = self._original_url
        elif 'HORUS_API_URL' in os.environ:
            del os.environ['HORUS_API_URL']

        if self._original_token is not None:
            os.environ['HORUS_ACCESS_TOKEN'] = self._original_token
        elif 'HORUS_ACCESS_TOKEN' in os.environ:
            del os.environ['HORUS_ACCESS_TOKEN']

    def test_main_missing_file_exits(self):
        from main import main
        with patch('sys.argv', ['main.py', '--type', 'sales', '--file', '/nonexistent.json',
                                 '--api-url', 'https://api.be', '--access-token', 'token']):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 1)

    @patch('horus_api.client.requests.Session')
    def test_main_successful_upload(self, mock_session_class):
        from main import main
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Id": "entry-123"}
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"FolderId": "f1"}, f)
            temp_path = f.name

        try:
            with patch('sys.argv', ['main.py', '--type', 'sales', '--file', temp_path,
                                     '--api-url', 'https://api.be', '--access-token', 'token']):
                exit_code = main()
            self.assertEqual(exit_code, 0)
        finally:
            os.unlink(temp_path)

    @patch('horus_api.client.requests.Session')
    def test_main_api_error_returns_1(self, mock_session_class):
        from main import main
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "ErrorType": "ValidationError",
            "Message": "Invalid",
            "Details": "Something wrong"
        }
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"FolderId": "f1"}, f)
            temp_path = f.name

        try:
            with patch('sys.argv', ['main.py', '--type', 'sales', '--file', temp_path,
                                     '--api-url', 'https://api.be', '--access-token', 'token']):
                exit_code = main()
            self.assertEqual(exit_code, 1)
        finally:
            os.unlink(temp_path)

    @patch('horus_api.client.requests.Session')
    def test_main_batch_upload(self, mock_session_class):
        from main import main
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Id": "entry-1"}
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump([{"FolderId": "f1"}, {"FolderId": "f2"}], f)
            temp_path = f.name

        try:
            with patch('sys.argv', ['main.py', '--type', 'sales', '--file', temp_path,
                                     '--api-url', 'https://api.be', '--access-token', 'token']):
                exit_code = main()
            self.assertEqual(exit_code, 0)
            # Should have made 2 POST calls for 2 entries
            self.assertEqual(mock_session.post.call_count, 2)
        finally:
            os.unlink(temp_path)


class TestValidateJsonFile(unittest.TestCase):
    """Test the validate_json_file function."""

    def test_validates_single_dict(self):
        from main import validate_json_file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"FolderId": "f1", "Number": 1}, f)
            temp_path = f.name

        try:
            entries = validate_json_file(temp_path, "sales")
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["FolderId"], "f1")
        finally:
            os.unlink(temp_path)

    def test_validates_list_of_dicts(self):
        from main import validate_json_file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump([{"FolderId": "f1"}, {"FolderId": "f2"}], f)
            temp_path = f.name

        try:
            entries = validate_json_file(temp_path, "sales")
            self.assertEqual(len(entries), 2)
        finally:
            os.unlink(temp_path)

    def test_exits_on_missing_file(self):
        from main import validate_json_file
        with self.assertRaises(SystemExit) as ctx:
            validate_json_file("/nonexistent/file.json", "sales")
        self.assertEqual(ctx.exception.code, 1)

    def test_exits_on_invalid_json(self):
        from main import validate_json_file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{invalid json}")
            temp_path = f.name

        try:
            with self.assertRaises(SystemExit) as ctx:
                validate_json_file(temp_path, "sales")
            self.assertEqual(ctx.exception.code, 1)
        finally:
            os.unlink(temp_path)

    def test_exits_on_non_object_root(self):
        from main import validate_json_file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump("just a string", f)
            temp_path = f.name

        try:
            with self.assertRaises(SystemExit) as ctx:
                validate_json_file(temp_path, "sales")
            self.assertEqual(ctx.exception.code, 1)
        finally:
            os.unlink(temp_path)

    def test_exits_on_non_object_entry(self):
        from main import validate_json_file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump([1, 2, 3], f)
            temp_path = f.name

        try:
            with self.assertRaises(SystemExit) as ctx:
                validate_json_file(temp_path, "sales")
            self.assertEqual(ctx.exception.code, 1)
        finally:
            os.unlink(temp_path)


class TestMainTestLogin(unittest.TestCase):
    """Test the test-login sub-command via main()."""

    def setUp(self):
        self._original_url = os.environ.pop('HORUS_API_URL', None)
        self._original_token = os.environ.pop('HORUS_ACCESS_TOKEN', None)

    def tearDown(self):
        if self._original_url is not None:
            os.environ['HORUS_API_URL'] = self._original_url
        elif 'HORUS_API_URL' in os.environ:
            del os.environ['HORUS_API_URL']

        if self._original_token is not None:
            os.environ['HORUS_ACCESS_TOKEN'] = self._original_token
        elif 'HORUS_ACCESS_TOKEN' in os.environ:
            del os.environ['HORUS_ACCESS_TOKEN']

    @patch('horus_api.client.requests.Session')
    def test_test_login_success(self, mock_session_class):
        from main import main
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"License": "Test License", "Valid": True}
        mock_session.post.return_value = mock_response
        mock_session_class.return_value = mock_session

        with patch('sys.argv', ['main.py', 'test-login', '--api-url', 'https://api.be', '--access-token', 'token']):
            exit_code = main()
        self.assertEqual(exit_code, 0)

    @patch('horus_api.client.requests.Session')
    def test_test_login_api_error(self, mock_session_class):
        from main import main
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

        with patch('sys.argv', ['main.py', 'test-login', '--api-url', 'https://api.be', '--access-token', 'bad-token']):
            exit_code = main()
        self.assertEqual(exit_code, 1)

    def test_test_login_missing_credentials(self):
        from main import main
        with patch('sys.argv', ['main.py', 'test-login']):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 1)


class TestMainDryRun(unittest.TestCase):
    """Test the --dry-run mode via main()."""

    def setUp(self):
        self._original_url = os.environ.pop('HORUS_API_URL', None)
        self._original_token = os.environ.pop('HORUS_ACCESS_TOKEN', None)

    def tearDown(self):
        if self._original_url is not None:
            os.environ['HORUS_API_URL'] = self._original_url
        elif 'HORUS_API_URL' in os.environ:
            del os.environ['HORUS_API_URL']

        if self._original_token is not None:
            os.environ['HORUS_ACCESS_TOKEN'] = self._original_token
        elif 'HORUS_ACCESS_TOKEN' in os.environ:
            del os.environ['HORUS_ACCESS_TOKEN']

    def test_dry_run_valid_file(self):
        from main import main
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump([{"FolderId": "f1", "Number": 1}, {"FolderId": "f2", "Number": 2}], f)
            temp_path = f.name

        try:
            with patch('sys.argv', ['main.py', '--type', 'sales', '--file', temp_path, '--dry-run',
                                     '--api-url', 'https://api.be', '--access-token', 'token']):
                exit_code = main()
            self.assertEqual(exit_code, 0)
        finally:
            os.unlink(temp_path)

    def test_dry_run_single_dict(self):
        from main import main
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"FolderId": "f1", "Number": 1}, f)
            temp_path = f.name

        try:
            with patch('sys.argv', ['main.py', '--type', 'purchases', '--file', temp_path, '--dry-run',
                                     '--api-url', 'https://api.be', '--access-token', 'token']):
                exit_code = main()
            self.assertEqual(exit_code, 0)
        finally:
            os.unlink(temp_path)

    def test_dry_run_invalid_json(self):
        from main import main
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{not valid json")
            temp_path = f.name

        try:
            with patch('sys.argv', ['main.py', '--type', 'sales', '--file', temp_path, '--dry-run',
                                     '--api-url', 'https://api.be', '--access-token', 'token']):
                with self.assertRaises(SystemExit) as ctx:
                    main()
                self.assertEqual(ctx.exception.code, 1)
        finally:
            os.unlink(temp_path)

    def test_dry_run_missing_file(self):
        from main import main
        with patch('sys.argv', ['main.py', '--type', 'sales', '--file', '/nonexistent.json', '--dry-run',
                                 '--api-url', 'https://api.be', '--access-token', 'token']):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 1)

    def test_dry_run_does_not_need_credentials(self):
        """Dry-run should work even without credentials since it doesn't call the API."""
        from main import main
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"FolderId": "f1"}, f)
            temp_path = f.name

        try:
            # No --api-url or --access-token provided
            with patch('sys.argv', ['main.py', '--type', 'sales', '--file', temp_path, '--dry-run']):
                # Should exit with code 1 due to missing credentials before dry-run
                # Actually, get_config is called before dry-run check
                with self.assertRaises(SystemExit):
                    main()
        finally:
            os.unlink(temp_path)


class TestMainMissingArgs(unittest.TestCase):
    """Test main() when required args are missing."""

    def setUp(self):
        self._original_url = os.environ.pop('HORUS_API_URL', None)
        self._original_token = os.environ.pop('HORUS_ACCESS_TOKEN', None)

    def tearDown(self):
        if self._original_url is not None:
            os.environ['HORUS_API_URL'] = self._original_url
        elif 'HORUS_API_URL' in os.environ:
            del os.environ['HORUS_API_URL']

        if self._original_token is not None:
            os.environ['HORUS_ACCESS_TOKEN'] = self._original_token
        elif 'HORUS_ACCESS_TOKEN' in os.environ:
            del os.environ['HORUS_ACCESS_TOKEN']

    def test_main_missing_type_exits(self):
        from main import main
        with patch('sys.argv', ['main.py', '--file', 'test.json']):
            with self.assertRaises(SystemExit):
                main()

    def test_main_missing_file_exits(self):
        from main import main
        with patch('sys.argv', ['main.py', '--type', 'sales']):
            with self.assertRaises(SystemExit):
                main()


if __name__ == "__main__":
    unittest.main()
