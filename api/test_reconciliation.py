import unittest
from unittest.mock import patch, Mock, MagicMock
from sqlalchemy.orm import Session

from api.v1 import reconciliation


class TestReconciliation(unittest.TestCase):

    # ---------------- box_auth ----------------
    @patch("reconciliation.BoxClient")
    @patch("reconciliation.BoxCCGAuth")
    @patch("reconciliation.CCGConfig")
    def test_box_auth_succeeds(self, mock_cfg, mock_auth, mock_client):
        client = Mock()
        mock_client.return_value = client
        result = box_auth("id", "secret", "ent")
        self.assertEqual(result, client)

    def test_box_auth_missing_credentials(self):
        with self.assertRaises(BoxAuthenticationError):
            box_auth("", "secret", "ent")

    @patch("reconciliation.BoxClient", side_effect=Exception("bad"))
    @patch("reconciliation.BoxCCGAuth")
    @patch("reconciliation.CCGConfig")
    def test_box_auth_failure_raises(self, *_):
        with self.assertRaises(BoxAuthenticationError):
            box_auth("id", "secret", "ent")

    # ---------------- list_files_in_folder ----------------
    def test_list_files_in_folder(self):
        client = Mock()
        folder = Mock()
        folder.entries = [Mock(type="file", name="a.csv"), Mock(type="folder", name="sub")]
        client.folders.get_folder_items.return_value = folder
        result = list_files_in_folder("folder_id", client)
        self.assertEqual(result, ["a.csv"])

    # ---------------- get_latest_inventory_file ----------------
    def test_get_latest_inventory_file_returns_latest(self):
        files = ["09-28-25_VM_Inventory.csv", "09-29-25_VM_Inventory.csv"]
        latest = get_latest_inventory_file(files)
        self.assertEqual(latest, "09-29-25_VM_Inventory.csv")

    def test_get_latest_inventory_file_none(self):
        self.assertIsNone(get_latest_inventory_file(["random.txt"]))

    def test_get_latest_inventory_file_bad_date(self):
        self.assertIsNone(get_latest_inventory_file(["bad_VM_Inventory.csv"]))

    # ---------------- download_file_from_box ----------------
    def test_download_file_from_box_success(self):
        client = Mock()
        folder = Mock()
        file_item = Mock()
        file_item.name = "test.csv"
        file_item.id = "123"
        folder.entries = [file_item]
        client.folders.get_folder_items.return_value = folder
        mock_file = Mock()
        mock_file.read.return_value = b"IP,vCenter\n10.0.0.1,vc1"
        client.downloads.download_file.return_value = mock_file

        content = download_file_from_box("test.csv", "fid", client)
        self.assertIn("10.0.0.1", content)

    def test_download_file_from_box_file_not_found(self):
        client = Mock()
        folder = Mock()
        folder.entries = []
        client.folders.get_folder_items.return_value = folder
        with self.assertRaises(InventoryFileNotFoundError):
            download_file_from_box("missing.csv", "fid", client)

    def test_download_file_from_box_error(self):
        client = Mock()
        client.folders.get_folder_items.side_effect = Exception("bad")
        with self.assertRaises(Exception):
            download_file_from_box("file.csv", "fid", client)

    # ---------------- get_vm_inventory_from_box ----------------
    @patch("reconciliation.download_file_from_box")
    @patch("reconciliation.list_files_in_folder")
    @patch("reconciliation.box_auth")
    @patch("reconciliation.BOX_FOLDER_DALST", "dalst")
    @patch("reconciliation.BOX_CLIENT_ID", "id")
    @patch("reconciliation.BOX_CLIENT_SECRET", "secret")
    @patch("reconciliation.ENTERPRISE_ID", "ent")
    def test_get_vm_inventory_from_box_success(
        self, mock_auth, mock_list, mock_download
    ):
        mock_auth.return_value = Mock()
        mock_list.return_value = ["09-29-25_VM_Inventory.csv"]
        mock_download.return_value = "IP,vCenter\n10.0.0.1,vc1"

        vms = get_vm_inventory_from_box()
        self.assertEqual(vms, [{"IP": "10.0.0.1", "vCenter": "vc1"}])

    @patch("reconciliation.box_auth", side_effect=BoxAuthenticationError("fail"))
    def test_get_vm_inventory_from_box_auth_error(self, *_):
        with self.assertRaises(BoxAuthenticationError):
            get_vm_inventory_from_box()

    @patch("reconciliation.list_files_in_folder", return_value=[])
    @patch("reconciliation.box_auth", return_value=Mock())
    def test_get_vm_inventory_from_box_no_files(self, *_):
        with self.assertRaises(InventoryFileNotFoundError):
            get_vm_inventory_from_box()

    # ---------------- list_all_hosts_for_reconciliation ----------------
    def test_list_all_hosts_for_reconciliation(self):
        mock_session = Mock(spec=Session)
        mock_session.query().all.return_value = [
            Mock(ip_address="10.0.0.1", hostname="host1", workload_domain="vc1")
        ]
        hosts = list_all_hosts_for_reconciliation(mock_session)
        self.assertEqual(hosts[0]["hostname"], "host1")

    # ---------------- perform_inventory_reconciliation ----------------
    @patch("reconciliation.get_vm_inventory_from_box")
    @patch("reconciliation.list_all_hosts_for_reconciliation")
    def test_perform_inventory_reconciliation_matched(self, mock_hosts, mock_vms):
        mock_hosts.return_value = [{"ip_address": "10.0.0.1", "hostname": "h1", "workload_domain": "vc"}]
        mock_vms.return_value = [{"IP": "10.0.0.1", "vCenter": "vc"}]

        result = perform_inventory_reconciliation(Mock())
        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(result["body"]["reconciliation_summary"]["matched_hosts"], 1)

    @patch("reconciliation.get_vm_inventory_from_box", side_effect=InventoryFileNotFoundError("nofile"))
    @patch("reconciliation.list_all_hosts_for_reconciliation", return_value=[])
    def test_perform_inventory_reconciliation_inventory_not_found(self, *_):
        result = perform_inventory_reconciliation(Mock())
        self.assertEqual(result["statusCode"], 404)

    @patch("reconciliation.get_vm_inventory_from_box", side_effect=BoxAuthenticationError("authfail"))
    @patch("reconciliation.list_all_hosts_for_reconciliation", return_value=[])
    def test_perform_inventory_reconciliation_auth_fail(self, *_):
        result = perform_inventory_reconciliation(Mock())
        self.assertEqual(result["statusCode"], 401)

    @patch("reconciliation.get_vm_inventory_from_box", side_effect=Exception("boxfail"))
    @patch("reconciliation.list_all_hosts_for_reconciliation", return_value=[])
    def test_perform_inventory_reconciliation_box_fail(self, *_):
        result = perform_inventory_reconciliation(Mock())
        self.assertEqual(result["statusCode"], 500)

    @patch("reconciliation.list_all_hosts_for_reconciliation", side_effect=Exception("dbfail"))
    def test_perform_inventory_reconciliation_db_fail(self, *_):
        result = perform_inventory_reconciliation(Mock())
        self.assertEqual(result["statusCode"], 500)

    # ---------------- reconciliation_endpoint ----------------
    @patch("reconciliation.perform_inventory_reconciliation", return_value={"statusCode": 200, "body": {}})
    def test_reconciliation_endpoint(self, mock_perform):
        result = reconciliation_endpoint(Mock())
        self.assertEqual(result["statusCode"], 200)


if __name__ == "__main__":
    unittest.main()
