import json
import pytest
from unittest.mock import patch, MagicMock

from ic4v_vmc_cli.commands.list_hosts import list_hosts_cmdb_only


@pytest.mark.unit
class TestListHostsCmdbOnly:

    @patch("ic4v_vmc_cli.commands.list_hosts.CMDBClient")
    def test_returns_success_with_hosts(self, mock_cmdb_client):
        # Arrange
        mock_client_instance = MagicMock()
        mock_client_instance.fetch_cmdb_server_list_paginated.return_value = [
            {"hostname": "host1", "ip": "10.0.0.1"},
            {"hostname": "host2", "ip": "10.0.0.2"},
        ]
        mock_cmdb_client.return_value = mock_client_instance

        # Act
        response = list_hosts_cmdb_only("IC4VMWS", offset=0, limit=2)
        body = json.loads(response["body"])

        # Assert
        assert response["statusCode"] == 200
        assert body["status"] == "success"
        assert body["count"] == 2
        assert body["offset"] == 0
        assert body["limit"] == 2
        assert len(body["data"]) == 2


    @patch("ic4v_vmc_cli.commands.list_hosts.CMDBClient")
    def test_returns_success_with_empty_list(self, mock_cmdb_client):
        # Arrange
        mock_client_instance = MagicMock()
        mock_client_instance.fetch_cmdb_server_list_paginated.return_value = []
        mock_cmdb_client.return_value = mock_client_instance

        # Act
        response = list_hosts_cmdb_only("IC4VMWS")
        body = json.loads(response["body"])

        # Assert
        assert response["statusCode"] == 200
        assert body["status"] == "success"
        assert body["count"] == 0
        assert body["data"] == []


    @patch("ic4v_vmc_cli.commands.list_hosts.CMDBClient")
    def test_returns_500_if_cmdb_throws_exception(self, mock_cmdb_client):
        # Arrange
        mock_client_instance = MagicMock()
        mock_client_instance.fetch_cmdb_server_list_paginated.side_effect = Exception("CMDB failure")
        mock_cmdb_client.return_value = mock_client_instance

        # Act
        response = list_hosts_cmdb_only("IC4VMWS")
        body = json.loads(response["body"])

        # Assert
        assert response["statusCode"] == 500
        assert body["status"] == "error"
        assert "CMDB failure" in body["message"]


    @patch("ic4v_vmc_cli.commands.list_hosts.CMDBClient")
    def test_offset_and_limit_are_converted_to_int(self, mock_cmdb_client):
        # Arrange
        mock_client_instance = MagicMock()
        mock_client_instance.fetch_cmdb_server_list_paginated.return_value = []
        mock_cmdb_client.return_value = mock_client_instance

        # Act
        response = list_hosts_cmdb_only("IC4VMWS", offset="10", limit="20")

        # Assert CMDB call received integers
        mock_client_instance.fetch_cmdb_server_list_paginated.assert_called_once_with(
            c_code="IC4VMWS",
            offset=10,
            limit=20,
        )

        assert response["statusCode"] == 200
