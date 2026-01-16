from typing import List, Dict
from common.cmdb_client import CMDBClient
from common.constants import IBM_CLOUD_DATACENTER_LIST, IBM_CLOUD_ZONES_MAP
import ipaddress

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


def validate_input(data):
    for item in data:
        for field in REQUIRED_FIELDS:
            if not item.get(field):
                return f"Missing or empty field: {field}"

        try:
            ipaddress.ip_address(item["ip_address"])
        except ValueError:
            return f"Invalid IP address: {item['ip_address']}"

        if item["host_type"] not in ALLOWED_HOST_TYPES:
            return f"Invalid host_type: {item['host_type']}"

        if item["host_type"] == "VCFaaS":
            if not item.get("workload_domain") or not item.get("vcd_org"):
                return "workload_domain and vcd_org are required for VCFaaS"

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

        hosts.append(
            {
                "ip": item["ip_address"],
                "fqdn": fqdn,
                "hostname": hostname,
                "domain": domain,
                "platform": item["platform"],
                "environment": item["environment"],
                "datacenter": datacenter,
                "serial_number": item["serial_number"],
                "host_type": item["host_type"],
                "workload_domain": item.get("workload_domain"),
                "vcd_org": item.get("vcd_org"),
                "user_email": user,
            }
        )

    return hosts, None


def register_hosts_cmdb_only(data: List[Dict], user: str) -> dict:
    error = validate_input(data)
    if error:
        return {"statusCode": 400, "body": {"status": "error", "message": error}}

    if len(data) > 100:
        return {
            "statusCode": 413,
            "body": {"status": "error", "message": "Max 100 hosts allowed"},
        }

    hosts, error = extract_hosts(data, user)
    if error:
        return {"statusCode": 400, "body": {"status": "error", "message": error}}

    try:
        CMDBClient().upload_ips_to_cmdb_inventory(hosts)
    except Exception as e:
        return {
            "statusCode": 500,
            "body": {"status": "error", "message": f"CMDB upload failed: {e}"},
        }

    return {
        "statusCode": 200,
        "body": {
            "status": "success",
            "message": f"{len(hosts)} host(s) uploaded to CMDB successfully",
        },
    }
