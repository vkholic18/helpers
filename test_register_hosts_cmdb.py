import unittest
from unittest.mock import patch, Mock
from api.v1.register_hosts import register_hosts_cmdb_only


class TestRegisterHosts(unittest.TestCase):
    
    def setUp(self):
        """Set up test data"""
        self.valid_host_data = [
            {
                "ip_address": "192.168.1.10",
                "fqdn": "server01.example.com",
                "c_code": "CC123",
                "environment": "production",
                "platform": "linux",
                "datacenter": "DAL10",
                "serial_number": "SN12345",
                "domain": "example.com",
                "host_type": "VCFaaS",
            }
        ]

    @patch("api.v1.register_hosts.CMDBClient")
    def test_register_hosts_succeeds(self, mock_cmdb_client):
        """Test successful host registration"""
        # Mock CMDB client response
        mock_instance = Mock()
        mock_instance.upload_ips_to_cmdb_inventory.return_value = {
            "status": "success"
        }
        mock_cmdb_client.return_value = mock_instance
        
        result = register_hosts_cmdb_only(self.valid_host_data, "test_user")
        
        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(result["body"]["status"], "success")
        self.assertIn("uploaded to CMDB successfully", result["body"]["message"])

    def test_register_hosts_fails_missing_required_field(self):
        """Test validation failure for missing required field"""
        invalid_data = [
            {
                "ip_address": "192.168.1.10",
                "fqdn": "server01.example.com",
                # Missing c_code
                "environment": "production",
                "platform": "linux",
                "datacenter": "DAL10",
                "serial_number": "SN12345",
            }
        ]
        
        result = register_hosts_cmdb_only(invalid_data, "test_user")
        
        self.assertEqual(result["statusCode"], 400)
        self.assertEqual(result["body"]["status"], "error")
        self.assertIn("Missing or empty field", result["body"]["message"])

    def test_register_hosts_fails_invalid_ip_address(self):
        """Test validation failure for invalid IP address"""
        invalid_data = [
            {
                "ip_address": "999.999.999.999",
                "fqdn": "server01.example.com",
                "c_code": "CC123",
                "environment": "production",
                "platform": "linux",
                "datacenter": "DAL10",
                "serial_number": "SN12345",
            }
        ]
        
        result = register_hosts_cmdb_only(invalid_data, "test_user")
        
        self.assertEqual(result["statusCode"], 400)
        self.assertEqual(result["body"]["status"], "error")
        self.assertIn("Invalid IP address", result["body"]["message"])

    def test_register_hosts_fails_invalid_host_type(self):
        """Test validation failure for invalid host_type"""
        invalid_data = [
            {
                "ip_address": "192.168.1.10",
                "fqdn": "server01.example.com",
                "c_code": "CC123",
                "environment": "production",
                "platform": "linux",
                "datacenter": "DAL10",
                "serial_number": "SN12345",
                "host_type": "InvalidType",
            }
        ]
        
        result = register_hosts_cmdb_only(invalid_data, "test_user")
        
        self.assertEqual(result["statusCode"], 400)
        self.assertEqual(result["body"]["status"], "error")
        self.assertIn("Invalid host_type", result["body"]["message"])

    def test_register_hosts_fails_exceeds_max_hosts(self):
        """Test failure when exceeding max 100 hosts"""
        # Create 101 hosts
        too_many_hosts = [self.valid_host_data[0].copy() for _ in range(101)]
        
        result = register_hosts_cmdb_only(too_many_hosts, "test_user")
        
        self.assertEqual(result["statusCode"], 413)
        self.assertEqual(result["body"]["status"], "error")
        self.assertEqual(result["body"]["message"], "Max 100 hosts allowed")

    @patch("api.v1.register_hosts.IBM_CLOUD_ZONES_MAP", {"dal10-1": {"datacenter": "DAL10"}})
    @patch("api.v1.register_hosts.IBM_CLOUD_DATACENTER_LIST", [])
    @patch("api.v1.register_hosts.CMDBClient")
    def test_register_hosts_succeeds_with_zone_mapping(self, mock_cmdb_client):
        """Test successful registration with zone to datacenter mapping"""
        mock_instance = Mock()
        mock_instance.upload_ips_to_cmdb_inventory.return_value = {
            "status": "success"
        }
        mock_cmdb_client.return_value = mock_instance
        
        zone_data = [
            {
                "ip_address": "192.168.1.10",
                "fqdn": "server01.example.com",
                "c_code": "CC123",
                "environment": "production",
                "platform": "linux",
                "datacenter": "dal10-1",
                "serial_number": "SN12345",
                "domain": "example.com",
            }
        ]
        
        result = register_hosts_cmdb_only(zone_data, "test_user")
        
        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(result["body"]["status"], "success")

    @patch("api.v1.register_hosts.IBM_CLOUD_DATACENTER_LIST", [])
    @patch("api.v1.register_hosts.IBM_CLOUD_ZONES_MAP", {})
    def test_register_hosts_fails_invalid_datacenter(self):
        """Test failure for invalid datacenter/zone"""
        invalid_dc_data = [
            {
                "ip_address": "192.168.1.10",
                "fqdn": "server01.example.com",
                "c_code": "CC123",
                "environment": "production",
                "platform": "linux",
                "datacenter": "INVALID_DC",
                "serial_number": "SN12345",
                "domain": "example.com",
            }
        ]
        
        result = register_hosts_cmdb_only(invalid_dc_data, "test_user")
        
        self.assertEqual(result["statusCode"], 400)
        self.assertEqual(result["body"]["status"], "error")
        self.assertIn("Invalid datacenter", result["body"]["message"])

    @patch("api.v1.register_hosts.CMDBClient")
    def test_register_hosts_fails_cmdb_upload_exception(self, mock_cmdb_client):
        """Test failure when CMDB upload raises exception"""
        mock_instance = Mock()
        mock_instance.upload_ips_to_cmdb_inventory.side_effect = Exception("Connection failed")
        mock_cmdb_client.return_value = mock_instance
        
        result = register_hosts_cmdb_only(self.valid_host_data, "test_user")
        
        self.assertEqual(result["statusCode"], 500)
        self.assertEqual(result["body"]["status"], "error")
        self.assertIn("CMDB upload failed", result["body"]["message"])

    @patch("api.v1.register_hosts.CMDBClient")
    def test_register_hosts_fails_cmdb_response_not_success(self, mock_cmdb_client):
        """Test failure when CMDB returns non-success status"""
        mock_instance = Mock()
        mock_instance.upload_ips_to_cmdb_inventory.return_value = {
            "status": "failed",
            "error": "Database error"
        }
        mock_cmdb_client.return_value = mock_instance
        
        result = register_hosts_cmdb_only(self.valid_host_data, "test_user")
        
        self.assertEqual(result["statusCode"], 500)
        self.assertEqual(result["body"]["status"], "error")
        self.assertIn("CMDB did not confirm host creation", result["body"]["message"])

    @patch("api.v1.register_hosts.CMDBClient")
    def test_register_hosts_succeeds_with_optional_fields(self, mock_cmdb_client):
        """Test successful registration with optional fields"""
        mock_instance = Mock()
        mock_instance.upload_ips_to_cmdb_inventory.return_value = {
            "status": "success"
        }
        mock_cmdb_client.return_value = mock_instance
        
        data_with_optional = [
            {
                "ip_address": "192.168.1.10",
                "fqdn": "server01.example.com",
                "c_code": "CC123",
                "environment": "production",
                "platform": "linux",
                "datacenter": "DAL10",
                "serial_number": "SN12345",
                "domain": "example.com",
                "business_unit": "IT",
                "system_admin": "admin@example.com",
                "owned_by": "team_lead",
                "u_exclude_patching": True,
                "u_exclude_reason": "Critical system",
            }
        ]
        
        result = register_hosts_cmdb_only(data_with_optional, "test_user")
        
        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(result["body"]["status"], "success")


if __name__ == "__main__":
    unittest.main()
