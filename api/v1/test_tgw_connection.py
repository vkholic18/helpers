
import unittest
from unittest.mock import patch, MagicMock
from requests import exceptions

from api.v1 import tgw_connection


class TestTGWCreateConnection(unittest.TestCase):
    def setUp(self):
        self.vpc_crn = "crn:v1:bluemix:public:is:region-a:a/account_id::vpc:vpc_id"
        self.transit_gateway_id = "dummy-tgw-id"

    @patch("api.v1.tgw_connection.get_iam_token")
    @patch("api.v1.tgw_connection.requests.post")
    def test_create_and_approve_connection_success(self, mock_post, mock_token):
        mock_token.return_value = "iam_token"

        # First call: Create connection
        create_resp = MagicMock()
        create_resp.status_code = 201
        create_resp.json.return_value = {"id": "conn_123"}
        # Second call: Approve connection
        approve_resp = MagicMock()
        approve_resp.status_code = 204

        mock_post.side_effect = [create_resp, approve_resp]

        result = tgw_connection.create_and_approve_connection(
            self.vpc_crn, self.transit_gateway_id
        )

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(result["body"]["message"], "Connection created and approved")

    @patch("api.v1.tgw_connection.get_iam_token")
    @patch("api.v1.tgw_connection.requests.post")
    def test_create_connection_but_approval_fails(self, mock_post, mock_token):
        mock_token.return_value = "iam_token"

        # Create works
        create_resp = MagicMock()
        create_resp.status_code = 201
        create_resp.json.return_value = {"id": "conn_123"}
        # Approve fails
        approve_resp = MagicMock()
        approve_resp.status_code = 403
        approve_resp.text = "Forbidden"

        mock_post.side_effect = [create_resp, approve_resp]

        result = tgw_connection.create_and_approve_connection(
            self.vpc_crn, self.transit_gateway_id
        )

        self.assertEqual(result["statusCode"], 206)
        self.assertIn("approval failed", result["body"]["message"])

    @patch("api.v1.tgw_connection.get_iam_token")
    @patch("api.v1.tgw_connection.requests.post")
    def test_create_connection_fails(self, mock_post, mock_token):
        mock_token.return_value = "iam_token"

        # Create fails
        create_resp = MagicMock()
        create_resp.status_code = 400
        create_resp.text = "Bad Request"
        mock_post.return_value = create_resp

        result = tgw_connection.create_and_approve_connection(
            self.vpc_crn, self.transit_gateway_id
        )

        self.assertEqual(result["statusCode"], 400)
        self.assertEqual(result["body"]["message"], "Bad Request")

    @patch("api.v1.tgw_connection.get_iam_token")
    @patch("api.v1.tgw_connection.requests.post")
    def test_create_connection_no_id_returned(self, mock_post, mock_token):
        mock_token.return_value = "iam_token"

        # Create succeeds but no ID
        create_resp = MagicMock()
        create_resp.status_code = 201
        create_resp.json.return_value = {}
        mock_post.return_value = create_resp

        result = tgw_connection.create_and_approve_connection(
            self.vpc_crn, self.transit_gateway_id
        )

        self.assertEqual(result["statusCode"], 500)
        self.assertIn("no ID returned", result["body"]["message"])

    @patch("api.v1.tgw_connection.get_iam_token")
    def test_create_connection_token_failure(self, mock_token):
        mock_token.side_effect = Exception("IAM token failure")

        result = tgw_connection.create_and_approve_connection(
            self.vpc_crn, self.transit_gateway_id
        )

        self.assertEqual(result["statusCode"], 500)
        self.assertIn("Failed to get IAM token", result["body"]["message"])

    @patch("api.v1.tgw_connection.get_iam_token", return_value="iam_token")
    @patch("api.v1.tgw_connection.requests.post", side_effect=exceptions.RequestException("Network error"))
    def test_create_connection_network_exception(self, mock_post, mock_token):
        result = tgw_connection.create_and_approve_connection(
            self.vpc_crn, self.transit_gateway_id
        )

        self.assertEqual(result["statusCode"], 500)
        self.assertIn("Network error", result["body"]["message"])
