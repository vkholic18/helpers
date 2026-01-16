import os
from typing import Any, Dict, List
import requests
from datetime import datetime, timezone
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
    return "vmca-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def approve_connection(connection_id: str, iam_token: str = None) -> dict:
    """Approve a TGW connection using Account 2"""
    if not iam_token:
        try:
            iam_token = _get_iam_token(VMCA_VPC_API_KEY)
        except Exception as e:
            return {
                "body": {
                    "message": f"Failed to get IAM token for approval: {str(e)}",
                    "status": "error",
                },
                "statusCode": 500,
            }

    url = (
        f"{TGW_API}/transit_gateways/{VMCA_TGW_ID}/connections/{connection_id}/actions"
    )
    params = {"version": TGW_API_VERSION}
    headers = {
        "Authorization": f"Bearer {iam_token}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(
            url, headers=headers, params=params, json={"action": "approve"}, timeout=15
        )
    except Exception as e:
        return {
            "body": {
                "message": f"Approval request failed: {str(e)}",
                "status": "error",
            },
            "statusCode": 500,
        }

    if resp.status_code != 200:
        return {
            "body": {"message": resp.text, "status": "error"},
            "statusCode": resp.status_code,
        }

    return {
        "body": {"message": "Connection approved", "status": "success"},
        "statusCode": 200,
    }


def create_and_approve_connection(vpc_crn: str, approve_iam_token: str = None) -> dict:
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
            "body": {
                "message": f"Failed to get IAM token for creation: {str(e)}",
                "status": "error",
            },
            "statusCode": 500,
        }

    url = f"{TGW_API}/transit_gateways/{VMCA_TGW_ID}/connections"
    params = {"version": TGW_API_VERSION}
    headers = {
        "Authorization": f"Bearer {iam_token}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(
            url, headers=headers, params=params, json=payload, timeout=15
        )
    except Exception as e:
        return {
            "body": {
                "message": f"Connection creation request failed: {str(e)}",
                "status": "error",
            },
            "statusCode": 500,
        }

    if resp.status_code != 201:
        return {
            "body": {"message": resp.text, "status": "error"},
            "statusCode": resp.status_code,
        }

    conn = resp.json()
    connection_id = conn.get("id")
    if not connection_id:
        return {
            "body": {
                "message": "Connection created but no ID returned",
                "status": "error",
            },
            "statusCode": 500,
        }

    # Step 2: Approve connection using Account 2
    approval_result = approve_connection(connection_id, iam_token=approve_iam_token)

    if approval_result["statusCode"] == 200:
        return {
            "body": {"message": "Connection created and approved", "status": "success"},
            "statusCode": 200,
        }
    else:
        return {
            "body": {
                "message": "Connection created but approval failed",
                "status": "error",
                "approval_details": approval_result["body"],
            },
            "statusCode": 206,
        }


def delete_tgw_connection(vpc_crn: str):
    """Delete TGW connection for given VPC CRN"""
    tgw_connections = _list_tgw_connections()

    connection_id = ""
    for connection in tgw_connections:
        if connection.get("network_id") == vpc_crn:
