import unittest
from unittest.mock import patch, Mock, MagicMock
from concurrent.futures import Future
from api.v1.deregister_hosts import deregister_hosts_cmdb_only


class TestDeregisterHosts(unittest.TestCase):
    
    def setUp(self):
        """Set up test data"""
        self.valid_host_data = [
            {
                "hostname": "server01.example.com",
                "serial_number": "SN12345",
                "c_code": "CC123",
            }
        ]

    @patch("api.v1.deregister_hosts.CMDBClient")
    def test_deregister_hosts_succeeds(self, mock_cmdb_client):
        """Test successful host deregistration"""
        # Mock CMDB client response
        mock_instance = Mock()
        mock_instance.remove_hosts_from_cmdb.return_value = {
            "status": "success"
        }
        mock_cmdb_client.return_value = mock_instance
        
        result = deregister_hosts_cmdb_only(self.valid_host_data, "test_user")
        
        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(result["body"]["status"], "success")
        self.assertIn("graveyarded in CMDB successfully", result["body"]["message"])

    def test_deregister_hosts_fails_missing_required_field(self):
        """Test validation failure for missing required field"""
        invalid_data = [
            {
                "hostname": "server01.example.com",
                # Missing serial_number
            }
        ]
        
        result = deregister_hosts_cmdb_only(invalid_data, "test_user")
        
        self.assertEqual(result["statusCode"], 400)
        self.assertEqual(result["body"]["status"], "error")
        self.assertIn("Missing required field", result["body"]["message"])

    def test_deregister_hosts_fails_empty_hostname(self):
        """Test validation failure for empty hostname"""
        invalid_data = [
            {
                "hostname": "",
                "serial_number": "SN12345",
            }
        ]
        
        result = deregister_hosts_cmdb_only(invalid_data, "test_user")
        
        self.assertEqual(result["statusCode"], 400)
        self.assertEqual(result["body"]["status"], "error")
        self.assertIn("Empty or invalid value", result["body"]["message"])

    def test_deregister_hosts_fails_empty_serial_number(self):
        """Test validation failure for empty serial_number"""
        invalid_data = [
            {
                "hostname": "server01.example.com",
                "serial_number": "   ",
            }
        ]
        
        result = deregister_hosts_cmdb_only(invalid_data, "test_user")
        
        self.assertEqual(result["statusCode"], 400)
        self.assertEqual(result["body"]["status"], "error")
        self.assertIn("Empty or invalid value", result["body"]["message"])

    def test_deregister_hosts_fails_invalid_field_type(self):
        """Test validation failure for non-string field value"""
        invalid_data = [
            {
                "hostname": "server01.example.com",
                "serial_number": 12345,  # Should be string
            }
        ]
        
        result = deregister_hosts_cmdb_only(invalid_data, "test_user")
        
        self.assertEqual(result["statusCode"], 400)
        self.assertEqual(result["body"]["status"], "error")
        self.assertIn("Empty or invalid value", result["body"]["message"])

    def test_deregister_hosts_fails_exceeds_max_hosts(self):
        """Test failure when exceeding max 100 hosts"""
        # Create 101 hosts
        too_many_hosts = [self.valid_host_data[0].copy() for _ in range(101)]
        
        result = deregister_hosts_cmdb_only(too_many_hosts, "test_user")
        
        self.assertEqual(result["statusCode"], 413)
        self.assertEqual(result["body"]["status"], "error")
        self.assertIn("100 hosts at once", result["body"]["message"])

    @patch("api.v1.deregister_hosts.CMDBClient")
    def test_deregister_hosts_fails_cmdb_exception(self, mock_cmdb_client):
        """Test failure when CMDB operation raises exception"""
        mock_instance = Mock()
        mock_instance.remove_hosts_from_cmdb.side_effect = Exception("Connection timeout")
        mock_cmdb_client.return_value = mock_instance
        
        result = deregister_hosts_cmdb_only(self.valid_host_data, "test_user")
        
        self.assertEqual(result["statusCode"], 500)
        self.assertEqual(result["body"]["status"], "error")
        self.assertIn("CMDB deregistration failed", result["body"]["message"])

    @patch("api.v1.deregister_hosts.CMDBClient")
    def test_deregister_hosts_fails_cmdb_response_not_success(self, mock_cmdb_client):
        """Test failure when CMDB returns non-success status"""
        mock_instance = Mock()
        mock_instance.remove_hosts_from_cmdb.return_value = {
            "status": "failed",
            "error": "Host not found"
        }
        mock_cmdb_client.return_value = mock_instance
        
        result = deregister_hosts_cmdb_only(self.valid_host_data, "test_user")
        
        self.assertEqual(result["statusCode"], 500)
        self.assertEqual(result["body"]["status"], "error")
        self.assertIn("CMDB did not confirm  host graveyard", result["body"]["message"])

    @patch("api.v1.deregister_hosts.CMDBClient")
    def test_deregister_hosts_succeeds_multiple_hosts(self, mock_cmdb_client):
        """Test successful deregistration with multiple hosts"""
        mock_instance = Mock()
        mock_instance.remove_hosts_from_cmdb.return_value = {
            "status": "success"
        }
        mock_cmdb_client.return_value = mock_instance
        
        multiple_hosts = [
            {
                "hostname": "server01.example.com",
                "serial_number": "SN12345",
                "c_code": "CC123",
            },
            {
                "hostname": "server02.example.com",
                "serial_number": "SN12346",
                "c_code": "CC124",
            },
            {
                "hostname": "server03.example.com",
                "serial_number": "SN12347",
                "c_code": "CC125",
            },
        ]
        
        result = deregister_hosts_cmdb_only(multiple_hosts, "test_user")
        
        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(result["body"]["status"], "success")
        self.assertIn("3 host(s)", result["body"]["message"])

    @patch("api.v1.deregister_hosts.ThreadPoolExecutor")
    @patch("api.v1.deregister_hosts.CMDBClient")
    def test_deregister_hosts_processes_batches(self, mock_cmdb_client, mock_executor):
        """Test that hosts are processed in batches"""
        mock_instance = Mock()
        mock_instance.remove_hosts_from_cmdb.return_value = {
            "status": "success"
        }
        mock_cmdb_client.return_value = mock_instance
        
        # Create mock future
        mock_future = Mock(spec=Future)
        mock_future.result.return_value = {"status": "success"}
        
        # Mock executor context manager
        mock_executor_instance = MagicMock()
        mock_executor_instance.submit.return_value = mock_future
        mock_executor_instance.__enter__.return_value = mock_executor_instance
        mock_executor_instance.__exit__.return_value = None
        mock_executor.return_value = mock_executor_instance
        
        # Create 30 hosts (should be split into 2 batches of 25 and 5)
        many_hosts = [
            {
                "hostname": f"server{i:02d}.example.com",
                "serial_number": f"SN{i:05d}",
                "c_code": "CC123",
            }
            for i in range(30)
        ]
        
        result = deregister_hosts_cmdb_only(many_hosts, "test_user")
        
        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(result["body"]["status"], "success")
        # Should have 2 batch submissions (25 + 5 hosts)
        self.assertEqual(mock_executor_instance.submit.call_count, 2)

    @patch("api.v1.deregister_hosts.CMDBClient")
    def test_deregister_hosts_succeeds_with_exactly_100_hosts(self, mock_cmdb_client):
        """Test successful deregistration with exactly 100 hosts (boundary case)"""
        mock_instance = Mock()
        mock_instance.remove_hosts_from_cmdb.return_value = {
            "status": "success"
        }
        mock_cmdb_client.return_value = mock_instance
        
        exactly_100_hosts = [
            {
                "hostname": f"server{i:03d}.example.com",
                "serial_number": f"SN{i:05d}",
                "c_code": "CC123",
            }
            for i in range(100)
        ]
        
        result = deregister_hosts_cmdb_only(exactly_100_hosts, "test_user")
        
        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(result["body"]["status"], "success")
        self.assertIn("100 host(s)", result["body"]["message"])

    @patch("api.v1.deregister_hosts.CMDBClient")
    def test_deregister_hosts_fails_cmdb_runtime_error(self, mock_cmdb_client):
        """Test failure when CMDB returns non-success status (RuntimeError path)"""
        mock_instance = Mock()
        mock_instance.remove_hosts_from_cmdb.return_value = {
            "status": "error",
            "message": "Database constraint violation"
        }
        mock_cmdb_client.return_value = mock_instance
        
        result = deregister_hosts_cmdb_only(self.valid_host_data, "test_user")
        
        self.assertEqual(result["statusCode"], 500)
        self.assertEqual(result["body"]["status"], "error")
        self.assertIn("CMDB deregistration failed", result["body"]["message"])


if __name__ == "__main__":
    unittest.main()
