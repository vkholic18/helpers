import json
import os
import tempfile
from unittest.mock import MagicMock
from unittest.mock import patch
import pytest
import requests
from ic4v_vmc_cli.commands.release_ips import create_release_ips_command_with
from tests.clirunner import CliRunner


@pytest.mark.unit
class TestReleaseIpsCommand:
    """
    Tests the JSON file-based IP release.
    Each test tries to release IPs and see how response status code is returned.
    """
    
    runner = CliRunner()

    @patch("ic4v_vmc_cli.commands.release_ips.requests.post")
    def test_it_accepts_valid_json_file_and_releases_single_host(
        self, mock_post: MagicMock
    ) -> None:
        host_data = {
            "ip": "172.19.1.18",
            "hostname": "hostname5.domain5",
            "serial_number": "072728a0-223jwd-dwdthw"
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
            json.dump(host_data, temp_file)
            temp_file_path = temp_file.name

        try:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "body": {
                    "status": "success",
                    "message": "Successfully released 1 host(s)"
                }
            }
            mock_post.return_value = mock_response
            
            cmd = create_release_ips_command_with()
            result = self.runner.invoke_command(cmd, ["-f", temp_file_path])
            
            assert result.exit_code == 0
            assert "[SUCCESS] Successfully released 1 host(s)" in result.stdout
        finally:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)

    @patch("ic4v_vmc_cli.commands.release_ips.requests.post")
    def test_it_accepts_valid_json_file_and_releases_multiple_hosts(
        self, mock_post: MagicMock
    ) -> None:
        hosts_data = [
            {
                "ip": "172.19.1.18",
                "hostname": "hostname5.domain5",
                "serial_number": "072728a0-223jwd-dwdthw"
            },
            {
                "ip": "172.19.1.19",
                "hostname": "hostname6.domain5",
                "serial_number": "072728a0-223jwd-dwdthx"
            }
        ]
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
            json.dump(hosts_data, temp_file)
            temp_file_path = temp_file.name

        try:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "body": {
                    "status": "success",
                    "message": "Successfully released 2 host(s)"
                }
            }
            mock_post.return_value = mock_response
            
            cmd = create_release_ips_command_with()
            result = self.runner.invoke_command(cmd, ["-f", temp_file_path])
            
            assert result.exit_code == 0
            assert "[SUCCESS] Successfully released 2 host(s)" in result.stdout
        finally:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)

    @patch("ic4v_vmc_cli.commands.release_ips.requests.post")
    def test_it_throws_error_if_host_release_api_returns_bad_statuscode(
        self, mock_post: MagicMock
    ) -> None:
        host_data = {
            "ip": "172.19.1.18",
            "hostname": "hostname5.domain5",
            "serial_number": "072728a0-223jwd-dwdthw"
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
            json.dump(host_data, temp_file)
            temp_file_path = temp_file.name

        try:
            mock_response = MagicMock()
            mock_response.status_code = 403
            mock_response.json.return_value = {
                "message": "Host is owned by another user"
            }
            mock_post.return_value = mock_response
            
            cmd = create_release_ips_command_with()
            result = self.runner.invoke_command(cmd, ["-f", temp_file_path])
            
            assert result.exit_code == 1
            assert "[ERROR 403]: Host is owned by another user" in result.stdout
        finally:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)

    @patch("ic4v_vmc_cli.commands.release_ips.requests.post")
    def test_it_throws_error_if_api_returns_success_with_error_status(
        self, mock_post: MagicMock
    ) -> None:
        host_data = {
            "ip": "172.19.1.18",
            "hostname": "hostname5.domain5",
            "serial_number": "072728a0-223jwd-dwdthw"
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
            json.dump(host_data, temp_file)
            temp_file_path = temp_file.name

        try:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "body": {
                    "status": "error",
                    "message": "Host not found in registry"
                }
            }
            mock_post.return_value = mock_response
            
            cmd = create_release_ips_command_with()
            result = self.runner.invoke_command(cmd, ["-f", temp_file_path])
            
            assert result.exit_code == 1
            assert "[ERROR]: Host not found in registry" in result.stdout
        finally:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)

    def test_it_throws_error_for_missing_file_argument(self) -> None:
        cmd = create_release_ips_command_with()
        result = self.runner.invoke_command(cmd, [])
        
        assert result.exit_code == 1

    def test_it_throws_error_for_invalid_json_format(self) -> None:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
            temp_file.write("invalid json content")
            temp_file_path = temp_file.name

        try:
            cmd = create_release_ips_command_with()
            result = self.runner.invoke_command(cmd, ["-f", temp_file_path])
            
            assert result.exit_code == 1
            assert "Invalid JSON format in file:" in result.stdout
        finally:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)

    def test_it_throws_error_for_missing_required_fields(self) -> None:
        host_data = {
            "ip": "172.19.1.18",
            "hostname": "hostname5.domain5"
            # missing serial_number
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
            json.dump(host_data, temp_file)
            temp_file_path = temp_file.name

        try:
            cmd = create_release_ips_command_with()
            result = self.runner.invoke_command(cmd, ["-f", temp_file_path])
            
            assert result.exit_code == 1
            assert "Missing required fields in host entry: ['serial_number']" in result.stdout
        finally:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)

    def test_it_throws_error_for_empty_hosts_list(self) -> None:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
            json.dump([], temp_file)
            temp_file_path = temp_file.name

        try:
            cmd = create_release_ips_command_with()
            result = self.runner.invoke_command(cmd, ["-f", temp_file_path])
            
            assert result.exit_code == 1
            assert "No valid host entries to be released" in result.stdout
        finally:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)

    @patch("ic4v_vmc_cli.commands.release_ips.requests.post")
    def test_it_rejects_release_ips_if_api_returns_RequestException(
        self, mock_post: MagicMock
    ) -> None:
        host_data = {
            "ip": "172.19.1.18",
            "hostname": "hostname5.domain5",
            "serial_number": "072728a0-223jwd-dwdthw"
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
            json.dump(host_data, temp_file)
            temp_file_path = temp_file.name

        try:
            mock_post.side_effect = requests.RequestException("Connection error")
            
            cmd = create_release_ips_command_with()
            result = self.runner.invoke_command(cmd, ["-f", temp_file_path])
            
            assert result.exit_code == 1
            assert (
                "[ERROR]: Host deregistration API request could not be sent, please try again."
                in result.stdout
            )
        finally:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)

    @patch("ic4v_vmc_cli.commands.release_ips.requests.post")
    def test_it_rejects_release_ips_if_api_returns_invalid_api_json_response(
        self, mock_post: MagicMock
    ) -> None:
        host_data = {
            "ip": "172.19.1.18",
            "hostname": "hostname5.domain5",
            "serial_number": "072728a0-223jwd-dwdthw"
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
            json.dump(host_data, temp_file)
            temp_file_path = temp_file.name

        try:
            mock_response = MagicMock()
            mock_response.json.side_effect = json.JSONDecodeError(
                "Invalid Json", doc="", pos=0
            )
            mock_post.return_value = mock_response
            
            cmd = create_release_ips_command_with()
            result = self.runner.invoke_command(cmd, ["-f", temp_file_path])
            
            assert result.exit_code == 1
            assert (
                "[ERROR]: Host deregistration API request returned invalid response."
                in result.stdout
            )
        finally:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
