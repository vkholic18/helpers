import os
import requests

IAM_URL = "https://iam.cloud.ibm.com/identity/token"
TGW_API = "https://transit.cloud.ibm.com/v1"

API_KEY_ACCOUNT_1 = os.getenv("API_KEY_1368749")
API_KEY_ACCOUNT_2 = os.getenv("API_KEY_2579380")
TRANSIT_GATEWAY_ID = "705a8bd3-1928-4b03-be80-f1618ac83a0e"


def get_iam_token(api_key: str) -> str:
    """Get IAM token from IBM Cloud"""
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


def approve_connection(connection_id: str) -> tuple[dict, int]:
    """Approve a TGW connection using Account 2"""
    try:
        iam_token = get_iam_token(API_KEY_ACCOUNT_2)
    except Exception as e:
        return {"message": f"Failed to get IAM token for approval: {str(e)}"}, 500

    url = f"{TGW_API}/transit_gateways/{TRANSIT_GATEWAY_ID}/connections/{connection_id}/actions?version=2021-05-01"
    headers = {
        "Authorization": f"Bearer {iam_token}",
        "Content-Type": "application/json",
    }
    payload = {"action": "approve"}

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
    except Exception as e:
        return {"message": f"Approval request failed: {str(e)}"}, 500

    if resp.status_code == 204:
        return {"message": "Connection approved"}, 200
    elif resp.status_code == 403:
        return {"message": "Not authorized to approve connection"}, 403
    elif resp.status_code == 404:
        return {"message": "Connection or TGW not found"}, 404
    elif resp.status_code == 409:
        return {"message": "Cannot approve classic_access VPC connection"}, 409
    else:
        return {"message": resp.text}, resp.status_code


def create_and_approve_connection(vpc_crn: str) -> dict:
    """Create TGW connection and attempt approval"""
    # Always use CRN as both name and network_id
    payload = {"network_type": "vpc", "name": vpc_crn, "network_id": vpc_crn}

    # Step 1: Create connection using Account 1
    try:
        iam_token = get_iam_token(API_KEY_ACCOUNT_1)
    except Exception as e:
        return {"body": f"Failed to get IAM token for creation: {str(e)}", "statusCode": 500}

    url = f"{TGW_API}/transit_gateways/{TRANSIT_GATEWAY_ID}/connections?version=2021-05-01"
    headers = {"Authorization": f"Bearer {iam_token}", "Content-Type": "application/json"}

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
    except Exception as e:
        return {"body": f"Connection creation request failed: {str(e)}", "statusCode": 500}

    if resp.status_code != 201:
        return {"body": resp.text, "statusCode": resp.status_code}

    conn = resp.json()
    connection_id = conn.get("id")
    if not connection_id:
        return {"body": "Connection created but no ID returned", "statusCode": 500}

    # Step 2: Approve connection using Account 2
    approval_result, approval_status = approve_connection(connection_id)

    if approval_status == 200:
        return {"body": {"message": "Connection created and approved"}, "statusCode": 200}
    elif approval_status == 206:
        return {"body": {"message": "Connection created but partially approved"}, "statusCode": 206}
    elif approval_status in (403, 404, 409):
        # Created but not approved
        return {"body": {"message": "Connection created but approval failed", "reason": approval_result}, "statusCode": 206}
    else:
        # Something else went wrong
        return {"body": {"message": "Connection created but approval request failed", "reason": approval_result}, "statusCode": 206}
