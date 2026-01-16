from typing import List, Dict, Union, Optional, Tuple, Any
import datetime
import ipaddress

# ❌ VMCA DB imports – NOT needed for CMDB-only flow
# from sqlalchemy.orm import Session
# from common.db import Host, CIDR_BLOCK

from common.cmdb_client import CMDBClient
from common.constants import IBM_CLOUD_DATACENTER_LIST
from common.constants import IBM_CLOUD_ZONES_MAP

REQUIRED_FIELDS = [
    "ip_address",
    "fqdn",
    "environment",
    "platform",
    "datacenter",
    "serial_number",
    "host_type",
]

ALLOWED_HOST_TYPES = {"VCFaaS", "VCS", "VCFforVPC", "Other"}


def validate_input(data) -> str | None:
    for item in data:
        for field in REQUIRED_FIELDS:
            if field not in item:
                return f"Missing required field: {field} in item: {item}"

            field_value = item.get(field)
            if field_value is None or field_value == "":
                return (
                    f"Missing or empty field value for field: {field} in item: {item}"
                )

        # IP format validation
        ip_address = item.get("ip_address")
        try:
            ipaddress.ip_address(ip_address)
        except ValueError:
            return f"Invalid IP address format: {ip_address}, (e.g. 172.16.12.222)"

        # host_type validation
        host_type = item.get("host_type")
        if host_type not in ALLOWED_HOST_TYPES:
            return f"Invalid value for field 'host_type'={host_type}, allowed values={ALLOWED_HOST_TYPES}"

        # VCFaaS specific validation
        if host_type == "VCFaaS":
            if not item.get("workload_domain") or not item.get("vcd_org"):
                return (
                    f"'workload_domain' and 'vcd_org' cannot be empty "
                    f"for host with ip={ip_address} when host_type=VCFaaS"
                )

    return None


def extract_reserved_ips_details(
    json_data: List[Dict[str, Any]], user: str
) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
    """
    Extract hostname, domain and normalize datacenter.
    """
    ip_hostnames_list = []
    error = {}

    for item in json_data:
        fqdn = item["fqdn"]
        hostname, domain = (fqdn.split(".", 1) + [""])[:2]

        datacenter = item["datacenter"]

        if datacenter.upper() not in IBM_CLOUD_DATACENTER_LIST:
            zone = datacenter.lower()
            if zone not in IBM_CLOUD_ZONES_MAP:
                error = {
                    "statusCode": 400,
                    "body": {
                        "status": "error",
                        "message": f'Invalid datacenter: {datacenter} for host "{hostname}"',
                    },
                }
                break
            datacenter = IBM_CLOUD_ZONES_MAP[zone]["datacenter"]

        ip_hostnames_list.append(
            {
                "ip": item["ip_address"],
                "fqdn": fqdn,
                "hostname": hostname,
                "domain": domain,
                "platform": item.get("platform"),
                "environment": item.get("environment"),
                "datacenter": datacenter,
                "user_email": user,
                "serial_number": item.get("serial_number"),
                "host_type": item.get("host_type"),
                "workload_domain": item.get("workload_domain"),
                "vcd_org": item.get("vcd_org"),
            }
        )

    return ip_hostnames_list, error


# ❌ VMCA DB persistence – NOT required
# def upload_hosts_to_db(db_session, ip_hostnames_list):
#     pass


# ❌ CIDR validation – NOT required
# def validate_and_attach_cidr_block(ip_hostnames_list, db_session):
#     pass


# ❌ Serial number duplication check – NOT required
# def validate_duplicate_serial_numbers(data, db_session):
#     pass


def register_hosts_cmdb_only(data: List[Dict], user: str) -> dict:
    """
    CMDB-only host registration.
    No VMCA DB insert.
    No CIDR validation.
    """

    print("[INFO] Validating input for CMDB-only host registration")

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
                "message": "You can only import up to 100 hosts at once.",
            },
        }

    # 3. Extract host details
    ip_hostnames_list, error = extract_reserved_ips_details(data, user)
    if error:
        return error

    # 4. Upload directly to CMDB
    print("[INFO] Uploading hosts to CMDB inventory")
    try:
        cmdb_client = CMDBClient()
        cmdb_client.upload_ips_to_cmdb_inventory(ip_hostnames_list)
    except Exception as e:
        print(f"[ERROR] CMDB upload failed: {str(e)}")
        return {
            "statusCode": 500,
            "body": {
                "status": "error",
                "message": f"CMDB upload failed: {str(e)}",
            },
        }

    print("[INFO] CMDB host registration successful")
    return {
        "statusCode": 200,
        "body": {
            "status": "success",
            "message": f"{len(ip_hostnames_list)} host(s) uploaded to CMDB successfully.",
        },
    }
