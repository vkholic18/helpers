import os
import requests

IAM_URL = "https://iam.cloud.ibm.com/identity/token"
TGW_API = "https://transit.cloud.ibm.com/v1"

API_KEY_ACCOUNT_1 = os.getenv("API_KEY_1368749")
API_KEY_ACCOUNT_2 = os.getenv("API_KEY_2579380")
TRANSIT_GATEWAY_ID = os.getenv("TRANSIT_GATEWAY_ID")


def get_iam_token(api_key: str) -> str:
    """Get IAM token from IBM Cloud"""
    resp = requests.post(
        IAM_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
            "apikey": api_key,
        },
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def create_tgw_connection(vpc_crn: str):
    """Create a TGW connection for the given VPC CRN"""
    # Pick correct API key based on account in CRN
    if "1368749" in vpc_crn:
        api_key = API_KEY_ACCOUNT_1
    elif "2579380" in vpc_crn:
        api_key = API_KEY_ACCOUNT_2
    else:
        return {"body": "Unsupported account in VPC CRN", "statusCode": 400}

    if not api_key:
        return {"body": "API key missing for this account", "statusCode": 500}

    try:
        iam_token = get_iam_token(api_key)
    except Exception as e:
        return {"body": f"Failed to get IAM token: {str(e)}", "statusCode": 500}

    url = f"{TGW_API}/transit_gateways/{TRANSIT_GATEWAY_ID}/connections?version=2021-05-01"
    headers = {
        "Authorization": f"Bearer {iam_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "network_type": "vpc",
        "name": f"connection-to-{vpc_crn.split(':')[-1]}",
        "network_id": vpc_crn,
    }

    resp = requests.post(url, headers=headers, json=payload)

    if resp.status_code == 201:
        conn = resp.json()
        status = conn.get("status")
        if status == "approved":
            return {
                "body": {"message": "Connection established and approved"},
                "statusCode": 200,
            }
        else:
            return {
                "body": {"message": "Connection established but not approved"},
                "statusCode": 206,
            }
    else:
        return {"body": resp.text, "statusCode": resp.status_code}
