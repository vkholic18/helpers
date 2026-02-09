from typing import List, Dict
from common.cmdb_client import CMDBClient
from concurrent.futures import ThreadPoolExecutor, as_completed

# CMDB graveyard API requires hostname + serial_number
REQUIRED_FIELDS = ["serial_number", "hostname"]


def validate_input(data) -> str | None:
    for item in data:
        for field in REQUIRED_FIELDS:
            if field not in item:
                return f"Missing required field: {field} in item: {item}"

            value = item[field]
            if not isinstance(value, str) or not value.strip():
                return f"Empty or invalid value for field: {field} in item: {item}"

    return None


def extract_hosts(data: List[Dict]) -> List[Dict]:
    """
    Prepare CMDB graveyard payload.
    CMDB client requires hostname and serial_number.
    """
    hosts = []

    for item in data:
        hostname = item["hostname"]

        hosts.append(
            {
                "hostname": hostname,
                "serial_number": item["serial_number"],
                "c_code": item["c_code"]
            }
        )

    return hosts


def deregister_hosts_cmdb_only(data: List[Dict], user: str) -> dict:
    print("[INFO] CMDB-only host deregistration started")

    # 1. Validate input
    error_msg = validate_input(data)
    if error_msg:
        return {
            "statusCode": 400,
            "body": {"status": "error", "message": error_msg},
        }

    # 2. Limit check
    if len(data) > 100:
        return {
            "statusCode": 413,
            "body": {
                "status": "error",
                "message": "You can only deregister up to 100 hosts at once.",
            },
        }

    # 3. Prepare CMDB payload
    extracted_hosts = extract_hosts(data)

    # 4. Graveyard hosts in CMDB
    batch_size = 25
    max_workers = 2

    try:
        cmdb_client = CMDBClient()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(
                    cmdb_client.remove_hosts_from_cmdb,
                    extracted_hosts[i : i + batch_size],
                )
                for i in range(0, len(extracted_hosts), batch_size)
            ]

            for future in as_completed(futures):
                response = future.result()
                if response is not None and isinstance(response, dict):
                    status = response.get("status")
                    if status and status.lower() not in ("success", "ok", "created"):
                        raise RuntimeError(
                            f"CMDB did not confirm  host graveyard: {response}"
                        )

    except Exception as e:
        print(f"[ERROR] CMDB deregistration failed: {str(e)}")
        return {
            "statusCode": 500,
            "body": {
                "status": "error",
                "message": f"CMDB deregistration failed: {str(e)}",
            },
        }

    print("[INFO] CMDB-only host deregistration successful")
    return {
        "statusCode": 200,
        "body": {
            "status": "success",
            "message": f"{len(extracted_hosts)} host(s) graveyarded in CMDB successfully.",
        },
    }
