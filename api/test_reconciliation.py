import unittest
from unittest.mock import patch, Mock
from sqlalchemy.orm import Session
from api.v1 import reconciliation
from api.v1.reconciliation import BoxAuthenticationError, InventoryFileNotFoundError


class TestReconciliation(unittest.TestCase):

    # ---------------- box_auth ----------------
    @patch("api.v1.reconciliation.BoxClient")
    @patch("api.v1.reconciliation.BoxCCGAuth")
    @patch("api.v1.reconciliation.CCGConfig")
    def test_box_auth_succeeds(self, mock_cfg, mock_auth, mock_client):
        client_instance = Mock()
        mock_client.return_value = client_instance
        result = reconciliation.box_auth("id", "secret", "ent")
        self.assertEqual(result, client_instance)

    def test_box_auth_missing_credentials(self):
        with self.assertRaises(BoxAuthenticationError):
            reconciliation.box_auth("", "secret", "ent")

    @patch("api.v1.reconciliation.BoxClient", side_effect=Exception("bad"))
    @patch("api.v1.reconciliation.BoxCCGAuth")
    @patch("api.v1.reconciliation.CCGConfig")
    def test_box_auth_failure_raises(self, mock_cfg, mock_auth, mock_client):
        with self.assertRaises(BoxAuthenticationError):
            reconciliation.box_auth("id", "secret", "ent")

    # ---------------- get_vm_inventory_from_box ----------------
    @patch("api.v1.reconciliation.download_file_from_box")
    @patch("api.v1.reconciliation.list_files_in_folder")
    @patch("api.v1.reconciliation.box_auth")
    def test_get_vm_inventory_from_box_success(self, mock_auth, mock_list, mock_download):
        with patch("api.v1.reconciliation.BOX_FOLDER_DALST", "dalst"), \
             patch("api.v1.reconciliation.BOX_CLIENT_ID", "id"), \
             patch("api.v1.reconciliation.BOX_CLIENT_SECRET", "secret"), \
             patch("api.v1.reconciliation.ENTERPRISE_ID", "ent"):

            mock_auth.return_value = Mock()
            mock_list.return_value = ["09-29-25_vCD_Inventory.csv"]
            mock_download.return_value = "IP,vCD,Org,Name\n10.0.0.1,vc1,org1,host1"

            vms = reconciliation.get_vm_inventory_from_box()
            expected = [{"IP": "10.0.0.1", "vCD": "vc1", "Org": "org1", "Name": "host1"}]
            # Use assertCountEqual to ignore order issues
            self.assertCountEqual(vms, expected)

    @patch("api.v1.reconciliation.box_auth", side_effect=BoxAuthenticationError("fail"))
    def test_get_vm_inventory_from_box_auth_error(self, *_):
        with self.assertRaises(BoxAuthenticationError):
            reconciliation.get_vm_inventory_from_box()

    @patch("api.v1.reconciliation.list_files_in_folder", return_value=[])
    @patch("api.v1.reconciliation.box_auth", return_value=Mock())
    def test_get_vm_inventory_from_box_no_files(self, *_):
        with self.assertRaises(Exception) as context:
            reconciliation.get_vm_inventory_from_box()
        self.assertIn("Error when trying to retrieve inventory reports", str(context.exception))

    # ---------------- list_all_hosts_for_reconciliation ----------------
    def test_list_all_hosts_for_reconciliation(self):
        mock_session = Mock(spec=Session)
        mock_host = Mock(
            ip_address="10.0.0.1",
            hostname="host1",
            workload_domain="vc1",
            user="user1",
            vcd_org="org1"
        )
        # Ensure query().all() returns a list
        mock_session.query.return_value.all.return_value = [mock_host]

        hosts = reconciliation.list_all_hosts_for_reconciliation(mock_session)
        self.assertEqual(hosts[0]["hostname"], "host1")
        self.assertEqual(hosts[0]["vcd_org"], "org1")

    # ---------------- perform_inventory_reconciliation ----------------
    @patch("api.v1.reconciliation.get_vm_inventory_from_box")
    @patch("api.v1.reconciliation.list_all_hosts_for_reconciliation")
    def test_perform_inventory_reconciliation_matched(self, mock_hosts, mock_vms):
        mock_hosts.return_value = [{"ip_address": "10.0.0.1", "hostname": "h1", "workload_domain": "vc", "vcd_org": "org1"}]
        mock_vms.return_value = [{"IP": "10.0.0.1", "vCD": "vc", "Org": "org1", "Name": "host1"}]

        result = reconciliation.perform_inventory_reconciliation(Mock())
        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(result["body"]["reconciliation_summary"]["matched_hosts"], 1)

    @patch("api.v1.reconciliation.get_vm_inventory_from_box", side_effect=InventoryFileNotFoundError("nofile"))
    @patch("api.v1.reconciliation.list_all_hosts_for_reconciliation", return_value=[])
    def test_perform_inventory_reconciliation_inventory_not_found(self, *_):
        result = reconciliation.perform_inventory_reconciliation(Mock())
        self.assertEqual(result["statusCode"], 404)

    @patch("api.v1.reconciliation.get_vm_inventory_from_box", side_effect=BoxAuthenticationError("authfail"))
    @patch("api.v1.reconciliation.list_all_hosts_for_reconciliation", return_value=[])
    def test_perform_inventory_reconciliation_auth_fail(self, *_):
        result = reconciliation.perform_inventory_reconciliation(Mock())
        self.assertEqual(result["statusCode"], 401)

    @patch("api.v1.reconciliation.list_all_hosts_for_reconciliation", side_effect=Exception("dbfail"))
    def test_perform_inventory_reconciliation_db_fail(self, *_):
        result = reconciliation.perform_inventory_reconciliation(Mock())
        self.assertEqual(result["statusCode"], 500)

    # ---------------- reconciliation_endpoint ----------------
    @patch("api.v1.reconciliation.perform_inventory_reconciliation", return_value={"statusCode": 200, "body": {}})
    def test_reconciliation_endpoint(self, mock_perform):
        result = reconciliation.reconciliation_endpoint(Mock())
        self.assertEqual(result["statusCode"], 200)


if __name__ == "__main__":
    unittest.main()
