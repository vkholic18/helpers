import os
import requests
from datetime import datetime

IAM_URL = "https://iam.cloud.ibm.com/identity/token"
TGW_API = "https://transit.cloud.ibm.com/v1"

VMCA_DEV_API_KEY = os.getenv("VMCA_DEV_API_KEY")
VMCA_VPC_API_KEY = os.getenv("VMCA_VPC_API_KEY")

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

def generate_name():
    # Format: tgw-YYYYMMDDHHMMSS
    return "tgw-" + datetime.utcnow().strftime("%Y%m%d%H%M%S")


def approve_connection(connection_id: str, transit_gateway_id: str) -> dict:
    """Approve a TGW connection using Account 2"""
    try:
        iam_token = get_iam_token(VMCA_VPC_API_KEY)
transit_gateway_id}/connections/"
        f"{connection_id}/actions?version=2021-05-01"
vpc_crn: str, transit_gateway_id: str) -> dict:
        "network_id": vpc_crn,
    }

    # Step 1: Create connection using Account 1
    try:
        iam_token = get_iam_token(VMCA_DEV_API_KEY)

    except Exception as e:
        return {
            "body": {"message": f"Failed to get IAM token for creation: {str(e)}"},
            "statusCode": 500,
        }

    url = f"{TGW_API}/transit_gateways/{transit_gateway_id}/connections?version=2021-05-01"
    headers = {
        "Authorization": f"Bearer {iam_token}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
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
    approval_result = approve_connection(connection_id, transit_gateway_id)

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
