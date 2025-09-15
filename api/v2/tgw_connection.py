
import os
from typing import Any, Dict, List
import requests
from datetime import datetime

IAM_URL = "https://iam.cloud.ibm.com/identity/token"
TGW_API = "https://transit.cloud.ibm.com/v1"

VMCA_DEV_API_KEY = os.getenv("VMCA_DEV_API_KEY")
VMCA_VPC_API_KEY = os.getenv("VMCA_VPC_API_KEY") 
VMCA_TGW_ID = os.getenv("VMCA_TGW_ID")
TGW_API_VERSION = os.getenv("TGW_API_VERSION") or "2025-08-27"

IAM_TOKEN = ""  # nosec


def _get_iam_token(api_key: str) -> str:
    """Get IAM token from IBM Cloud"""
    if not api_key:
        raise Exception("Environment variable for API Key not declared in system.")

    resp = requests.post(
        IAM_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
            "apikey": api_key,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _list_tgw_connections() -> List[Dict[str, Any]]:
    global IAM_TOKEN
    if not IAM_TOKEN:
        IAM_TOKEN = _get_iam_token(VMCA_DEV_API_KEY)
    url = f"{TGW_API}/transit_gateways/{VMCA_TGW_ID}/connections"
    params = {"version": TGW_API_VERSION}
    headers = {"Authorization": f"Bearer {IAM_TOKEN}"}
    response = requests.get(url, params=params, headers=headers, timeout=15)

    response.raise_for_status()
    return response.json()["connections"]


def _delete_connection(connection_id: str):
    global IAM_TOKEN
    if not IAM_TOKEN:
        IAM_TOKEN = _get_iam_token(VMCA_DEV_API_KEY)
    url = f"{TGW_API}/transit_gateways/{VMCA_TGW_ID}/connections/{connection_id}"
    params = {"version": TGW_API_VERSION}
    headers = {"Authorization": f"Bearer {IAM_TOKEN}"}
    response = requests.delete(url, params=params, headers=headers, timeout=15)
    response.raise_for_status()


def generate_name() -> str:
    """Generate unique TGW connection name"""
    return "tgw-" + datetime.utcnow().strftime("%Y%m%d%H%M%S")


def approve_connection(connection_id: str) -> dict:
    """Approve a TGW connection using Account 2"""
    try:
        iam_token = _get_iam_token(VMCA_VPC_API_KEY)
    except Exception as e:
        return {
            "body": {"message": f"Failed to get IAM token for approval: {str(e)}"},
            "statusCode": 500,
        }

    url = f"{TGW_API}/transit_gateways/{VMCA_TGW_ID}/connections/{connection_id}/actions"
    params = {"version": TGW_API_VERSION}
    headers = {
        "Authorization": f"Bearer {iam_token}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(url, params=params, json={"action": "approve"}, timeout=15)
    except Exception as e:
        return {
            "body": {"message": f"Approval request failed: {str(e)}"},
            "statusCode": 500,
        }

    if resp.status_code != 200:
        return {"body": {"message": resp.text}, "statusCode": resp.status_code}

    return {"body": {"message": "Connection approved"}, "statusCode": 200}


def create_and_approve_connection(vpc_crn: str) -> dict:
    """Create a TGW connection (Account 1) and approve it (Account 2)"""
    payload = {
        "network_type": "vpc",
        "network_id": vpc_crn,
        "name": generate_name(),
    }

    # Step 1: Create connection using Account 1
    try:
        iam_token = _get_iam_token(VMCA_DEV_API_KEY)
    except Exception as e:
        return {
            "body": {"message": f"Failed to get IAM token for creation: {str(e)}"},
            "statusCode": 500,
        }

    url = f"{TGW_API}/transit_gateways/{VMCA_TGW_ID}/connections"
    params = {"version": TGW_API_VERSION}
    headers = {
        "Authorization": f"Bearer {iam_token}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(url, params=params, json=payload, timeout=15)
    except Exception as e:
        return {
            "body": {"message": f"Connection creation request failed: {str(e)}"},
            "statusCode": 500,
        }

    if resp.status_code != 201:
        return {"body": {"message": resp.text}, "statusCode": resp.status_code}

    conn = resp.json()
    connection_id = conn.get("id")
    if not connection_id:
        return {
            "body": {"message": "Connection created but no ID returned"},
            "statusCode": 500,
        }

    # Step 2: Approve connection using Account 2
    approval_result = approve_connection(connection_id)

    if approval_result["statusCode"] == 200:
        return {"body": {"message": "Connection created and approved"}, "statusCode": 200}
    else:
        return {
            "body": {
                "message": "Connection created but approval failed",
                "approval_details": approval_result["body"],
            },
            "statusCode": 206,
        }


def create_tgw_connection(vpc_crn: str):
    """(Existing placeholder) Create TGW connection for given VPC CRN"""
    return create_and_approve_connection(vpc_crn)


def delete_tgw_connection(vpc_crn: str):
    """Delete TGW connection for given VPC CRN"""
    tgw_connections = _list_tgw_connections()
    connection_id = ""
    for connection in tgw_connections:
        if connection["network_id"] == vpc_crn:
            connection_id = connection["id"]

    if not connection_id:
        return {
            "statusCode": 404,
            "body": {
                "status": "warning",
                "message": f'Connection to VPC with CRN "{vpc_crn}" was not found.',
            },
        }

    print(f"[INFO] Found connection that matched VPC CRN. Connection id: {connection_id}")

    try:
        _delete_connection(connection_id)
    except Exception as delete_exception:
        print(
            f'An exception was raised when attempting to delete the connection to the VPC with CRN "{vpc_crn}". Exception: {str(delete_exception)}'
        )
        if isinstance(delete_exception, requests.HTTPError):
            print(
                f"Request to delete VPC connection failed. "
                f"Status code: {delete_exception.response.status_code}. "
                f"Response: {delete_exception.response.text}"
            )
        return {
            "statusCode": 500,
            "body": {
                "status": "error",
                "message": f'Error occurred when attempting to delete the connection to the VPC with CRN "{vpc_crn}".',
            },
        }

    return {
        "statusCode": 200,
        "body": {
            "status": "success",
            "message": f'Connection to VPC with CRN "{vpc_crn}" was successfully deleted.',
        },
    }
