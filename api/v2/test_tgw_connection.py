
import unittest
from requests import HTTPError, Response
from api.v1.tgw_connection import delete_tgw_connection, create_and_approve_connection
from unittest.mock import patch, Mock


class TestTGWConnections(unittest.TestCase):
    @patch("api.v1.tgw_connection._get_iam_token")
    @patch("api.v1.tgw_connection._list_tgw_connections")
    @patch("api.v1.tgw_connection._delete_connection")
    def test_delete_tgw_connection_succeeds(self, delete_connection, list_connections, iam_token_func):
        vpc_crn = "crn:v1:bluemix:public:is:region-a:a/account_id::vpc:vpc_id"
        # mock functions
        iam_token_func.return_value = "iam_token"
        list_connections.return_value = [
            {"network_id": "network_id", "id": "id_1"},
            {"network_id": vpc_crn, "id": "id_2"},
        ]
        result = delete_tgw_connection(vpc_crn)
        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(result["body"]["status"], "success")

    @patch("api.v1.tgw_connection._get_iam_token")
    @patch("api.v1.tgw_connection._list_tgw_connections")
    def test_delete_tgw_connection_fails_if_connection_is_not_found(
        self, list_connections, iam_token_func
    ):
        vpc_crn = "crn:v1:bluemix:public:is:region-a:a/account_id::vpc:vpc_id"
        # mock functions
        iam_token_func.return_value = "iam_token"
        list_connections.return_value = [{"network_id": "network_id", "id": "id_1"}]
        result = delete_tgw_connection(vpc_crn)
        self.assertEqual(result["statusCode"], 404)
        self.assertEqual(result["body"]["status"], "warning")

    @patch("api.v1.tgw_connection._get_iam_token")
    @patch("api.v1.tgw_connection._list_tgw_connections")
    @patch("api.v1.tgw_connection._delete_connection")
    def test_delete_tgw_connection_fails_if_connection_is_not_deleted(
        self, delete_connection, list_connections, iam_token_func
    ):
        vpc_crn = "crn:v1:bluemix:public:is:region-a:a/account_id::vpc:vpc_id"
        # mock functions
        iam_token_func.return_value = "iam_token"
        list_connections.return_value = [{"network_id": vpc_crn, "id": "id_2"}]
        error = HTTPError()
        error.response = Response()
        error.response.status_code = 500
        delete_connection.side_effect = error
        result = delete_tgw_connection(vpc_crn)
        self.assertEqual(result["statusCode"], 500)
        self.assertEqual(result["body"]["status"], "error")

    # New tests for create_and_approve_connection
    @patch("api.v1.tgw_connection.requests.post")
    @patch("api.v1.tgw_connection._get_iam_token")
    def test_create_and_approve_connection_succeeds(self, iam_token_func, mock_post):
        vpc_crn = "crn:v1:bluemix:public:is:region-a:a/account_id::vpc:vpc_id"
        
        # Mock IAM token calls (called twice - once for create, once for approve)
        iam_token_func.side_effect = ["create_token", "approve_token"]
        
        # Mock successful creation response
        create_response = Mock()
        create_response.status_code = 201
        create_response.json.return_value = {"id": "connection_123"}
        
        # Mock successful approval response
        approve_response = Mock()
        approve_response.status_code = 200
        
        # Configure mock_post to return different responses for create vs approve
        mock_post.side_effect = [create_response, approve_response]
        
        result = create_and_approve_connection(vpc_crn)
        
        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(result["body"]["message"], "Connection created and approved")
        self.assertEqual(mock_post.call_count, 2)

    @patch("api.v1.tgw_connection._get_iam_token")
    def test_create_and_approve_connection_fails_on_create_token_error(self, iam_token_func):
        vpc_crn = "crn:v1:bluemix:public:is:region-a:a/account_id::vpc:vpc_id"
        
        # Mock IAM token failure for creation
        iam_token_func.side_effect = Exception("Token fetch failed")
        
        result = create_and_approve_connection(vpc_crn)
        
        self.assertEqual(result["statusCode"], 500)
        self.assertIn("Failed to get IAM token for creation", result["body"]["message"])

    @patch("api.v1.tgw_connection.requests.post")
    @patch("api.v1.tgw_connection._get_iam_token")
    def test_create_and_approve_connection_fails_on_create_request_error(self, iam_token_func, mock_post):
        vpc_crn = "crn:v1:bluemix:public:is:region-a:a/account_id::vpc:vpc_id"
        
        iam_token_func.return_value = "create_token"
        
        # Mock request exception during creation
        mock_post.side_effect = Exception("Network error")
        
        result = create_and_approve_connection(vpc_crn)
        
        self.assertEqual(result["statusCode"], 500)
        self.assertIn("Connection creation request failed", result["body"]["message"])

    @patch("api.v1.tgw_connection.requests.post")
    @patch("api.v1.tgw_connection._get_iam_token")
    def test_create_and_approve_connection_fails_on_create_http_error(self, iam_token_func, mock_post):
        vpc_crn = "crn:v1:bluemix:public:is:region-a:a/account_id::vpc:vpc_id"
        
        iam_token_func.return_value = "create_token"
        
        # Mock failed creation response
        create_response = Mock()
        create_response.status_code = 400
        create_response.text = "Bad request"
        
        mock_post.return_value = create_response
        
        result = create_and_approve_connection(vpc_crn)
        
        self.assertEqual(result["statusCode"], 400)
        self.assertEqual(result["body"]["message"], "Bad request")

    @patch("api.v1.tgw_connection.requests.post")
    @patch("api.v1.tgw_connection._get_iam_token")
    def test_create_and_approve_connection_fails_when_no_connection_id_returned(self, iam_token_func, mock_post):
        vpc_crn = "crn:v1:bluemix:public:is:region-a:a/account_id::vpc:vpc_id"
        
        iam_token_func.return_value = "create_token"
        
        # Mock creation response without ID
        create_response = Mock()
        create_response.status_code = 201
        create_response.json.return_value = {}  # No ID in response
        
        mock_post.return_value = create_response
        
        result = create_and_approve_connection(vpc_crn)
        
        self.assertEqual(result["statusCode"], 500)
        self.assertEqual(result["body"]["message"], "Connection created but no ID returned")

    @patch("api.v1.tgw_connection.requests.post")
    @patch("api.v1.tgw_connection._get_iam_token")
    def test_create_and_approve_connection_succeeds_create_but_fails_approval(self, iam_token_func, mock_post):
        vpc_crn = "crn:v1:bluemix:public:is:region-a:a/account_id::vpc:vpc_id"
        
        # Mock IAM token calls - first succeeds, second fails
        iam_token_func.side_effect = ["create_token", Exception("Approval token failed")]
        
        # Mock successful creation response
        create_response = Mock()
        create_response.status_code = 201
        create_response.json.return_value = {"id": "connection_123"}
        
        mock_post.return_value = create_response
        
        result = create_and_approve_connection(vpc_crn)
        
        self.assertEqual(result["statusCode"], 206)
        self.assertEqual(result["body"]["message"], "Connection created but approval failed")
        self.assertIn("approval_details", result["body"])

    @patch("api.v1.tgw_connection.requests.post")
    @patch("api.v1.tgw_connection._get_iam_token")
    def test_create_and_approve_connection_succeeds_create_but_approval_request_fails(self, iam_token_func, mock_post):
        vpc_crn = "crn:v1:bluemix:public:is:region-a:a/account_id::vpc:vpc_id"
        
        # Mock IAM token calls
        iam_token_func.side_effect = ["create_token", "approve_token"]
        
        # Mock successful creation response, then approval request failure
        create_response = Mock()
        create_response.status_code = 201
        create_response.json.return_value = {"id": "connection_123"}
        
        mock_post.side_effect = [create_response, Exception("Approval request failed")]
        
        result = create_and_approve_connection(vpc_crn)
        
        self.assertEqual(result["statusCode"], 206)
        self.assertEqual(result["body"]["message"], "Connection created but approval failed")

    @patch("api.v1.tgw_connection.requests.post")
    @patch("api.v1.tgw_connection._get_iam_token")
    def test_create_and_approve_connection_succeeds_create_but_approval_http_error(self, iam_token_func, mock_post):
        vpc_crn = "crn:v1:bluemix:public:is:region-a:a/account_id::vpc:vpc_id"
        
        # Mock IAM token calls
        iam_token_func.side_effect = ["create_token", "approve_token"]
        
        # Mock successful creation response
        create_response = Mock()
        create_response.status_code = 201
        create_response.json.return_value = {"id": "connection_123"}
        
        # Mock failed approval response
        approve_response = Mock()
        approve_response.status_code = 403
        approve_response.text = "Forbidden"
        
        mock_post.side_effect = [create_response, approve_response]
        
        result = create_and_approve_connection(vpc_crn)
        
        self.assertEqual(result["statusCode"], 206)
        self.assertEqual(result["body"]["message"], "Connection created but approval failed")
        self.assertEqual(result["body"]["approval_details"]["message"], "Forbidden")
