from typing import List, Dict
from common.cmdb_client import CMDBClient
from common.constants import IBM_CLOUD_DATACENTER_LIST, IBM_CLOUD_ZONES_MAP
import ipaddress

REQUIRED_FIELDS = [
    "ip_address",
    "fqdn",
    "c_code",
    "environment",
    "platform",
    "datacenter",
    "serial_number",
]

ALLOWED_HOST_TYPES = {"VCFaaS", "VCS", "VCFforVPC", "Other"}


def validate_input(data):
    for item in data:
        for field in REQUIRED_FIELDS:
            if not item.get(field):
                return f"Missing or empty field: {field}"

        try:
            ipaddress.ip_address(item["ip_address"])
        except ValueError:
            return f"Invalid IP address: {item['ip_address']}"

        # host_type OPTIONAL
        host_type = item.get("host_type", "Other")

        if host_type not in ALLOWED_HOST_TYPES:
            return f"Invalid host_type: {host_type}"

    return None


def extract_hosts(data, user):
    hosts = []

    for item in data:
        fqdn = item["fqdn"]
        hostname, domain = (fqdn.split(".", 1) + [""])[:2]

        datacenter = item["datacenter"]
        if datacenter.upper() not in IBM_CLOUD_DATACENTER_LIST:
            zone = datacenter.lower()
            if zone not in IBM_CLOUD_ZONES_MAP:
                return None, f"Invalid datacenter: {datacenter}"
            datacenter = IBM_CLOUD_ZONES_MAP[zone]["datacenter"]

        unique_hostname = f"{hostname}.{domain}" if domain else hostname

        hosts.append(
            {
                "ip": item["ip_address"],
                "fqdn": fqdn,
                "hostname": unique_hostname,
                "domain": item["domain"],
                "platform": item["platform"],
                "environment": item["environment"],
                "datacenter": datacenter,
                "serial_number": item["serial_number"],
                "host_type": item.get("host_type", "Other"),
                "c_code": item["c_code"],

                "business_unit": item.get("business_unit", ""),
                "system_admin": item.get("system_admin", ""),
                "owned_by": item.get("owned_by", ""),
                "additional_owners": item.get("additional_owner", ""),
                "emergency_contacts": item.get("emergency_contacts", ""),
                "role": item.get("role", ""),
                "app_name": item.get("app_name", ""),

                "u_exclude_patching": item.get("u_exclude_patching", False),
                "u_exclude_anti_virus": item.get("u_exclude_anti_virus", False),
                "u_exclude_health_checks": item.get("u_exclude_health_checks", False),
                "u_exclude_log_collections": item.get("u_exclude_log_collections", False),
                "u_exclude_reason": item.get("u_exclude_reason", ""),
            }
        )

    return hosts, None


def register_hosts_cmdb_only(data: List[Dict], user: str) -> dict:
    error = validate_input(data)
    if error:
        return {
            "statusCode": 400,
            "body": {"status": "error", "message": error},
        }

    if len(data) > 100:
        return {
            "statusCode": 413,
            "body": {"status": "error", "message": "Max 100 hosts allowed"},
        }

    hosts, error = extract_hosts(data, user)
    if error:
        return {
            "statusCode": 400,
            "body": {"status": "error", "message": error},
        }

    try:
        response = CMDBClient().upload_ips_to_cmdb_inventory(hosts)
    except Exception as e:
        return {
            "statusCode": 500,
            "body": {
                "status": "error",
                "message": f"CMDB upload failed: {str(e)}",
            },
        }

    if response and isinstance(response, dict):
        status = response.get("status")
        if status and status.lower() not in ("success", "ok", "created"):
            return {
                "statusCode": 500,
                "body": {
                    "status": "error",
                    "message": f"CMDB did not confirm host creation: {response}",
                },
            }

    return {
        "statusCode": 200,
        "body": {
            "status": "success",
            "message": f"{len(hosts)} host(s) uploaded to CMDB successfully",
        },
    }
