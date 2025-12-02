from typing import List, Dict, Union, Optional, Tuple
from typing import Any
from common.db import Host, CIDR_BLOCK
import datetime
from sqlalchemy.orm import Session
from common.cmdb_client import CMDBClient
from common.constants import IBM_CLOUD_DATACENTER_LIST
from common.constants import IBM_CLOUD_ZONES_MAP

import ipaddress
# from common.security_center_client import SecurityCenterClient

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

        # Validate if ip_address has correct format as X.X.X.X
        ip_address = item.get("ip_address")
        try:
            ipaddress.ip_address(ip_address)
        except ValueError:
            return f"Invalid IP address format: {ip_address}, (e.g. 172.16.12.222)"

        # validate if host_type is within the allowed values.
        host_type = item.get("host_type")
        if host_type not in ALLOWED_HOST_TYPES:
            return f"Invalid value for field 'host_type'={host_type}, allowed values={ALLOWED_HOST_TYPES}"

        # validate if host_type=VCFaaS then 'workload_domain' and 'vcd_org' cannot be empty or null
        if host_type and host_type == "VCFaaS":
            workload_domain = item.get("workload_domain")
            vcd_org = item.get("vcd_org")
            if not workload_domain or not vcd_org:
                return f"Invalid or empty field : 'workload_domain' and/or 'vcd_org' cannot be empty or null for host with ip={item.get('ip_address')} when 'host_type=VCFaaS'"

    return None


def extract_reserved_ips_details(
    json_data: List[Dict[str, Any]], user: str
) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
    """Extracts data of hosts to be registered, and validates datacenter field."""

    ip_hostnames_list = []
    error = {}

    for item in json_data:
        ip = item["ip_address"]
        fqdn = item["fqdn"]

        hostname = ""
        domain = ""

        host_domain = fqdn.split(".", 1)
        hostname = host_domain[0]
        domain = host_domain[1] if len(host_domain) > 1 else ""

        datacenter = item["datacenter"]

        if datacenter.upper() not in IBM_CLOUD_DATACENTER_LIST:
            zone = datacenter.lower()
            if zone not in IBM_CLOUD_ZONES_MAP:
                print(
                    f"[ERROR] A data center could not be mapped with the given zone name: {zone}"
                )
                error = {
                    "statusCode": 400,
                    "body": {
                        "status": "error",
                        "message": f'Entry for host "{hostname}" has an invalid datacenter: {datacenter}',
                    },
                }
                break
            datacenter = IBM_CLOUD_ZONES_MAP[zone]["datacenter"]

        ip_hostnames_list.append(
            {
                "ip": ip,
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


def upload_hosts_to_db(
    db_session: Session, ip_hostnames_list: List[Dict[str, str]]
) -> Dict[str, Any] | None:
    # Adding the hosts in the postgres sql database
    for item in ip_hostnames_list:
        new_host = Host(
            ip_address=item["ip"],
            hostname=item["hostname"],
            domain_name=item["domain"],
            datacenter=item["datacenter"],
            platform=item["platform"],
            environment=item["environment"],
            serial_number=item["serial_number"],
            user=item["user_email"],
            registration_time=datetime.datetime.now(datetime.timezone.utc),
            block=item["block"],
            host_type=item["host_type"],
            workload_domain=item["workload_domain"],
            vcd_org=item["vcd_org"],
        )
        db_session.add(new_host)

    try:
        db_session.commit()
        print(
            f"[INFO] The incoming hosts {ip_hostnames_list} persisted to the database successfully."
        )
    except Exception as e:
        db_session.rollback()
        print(f"[ERROR] Database error: {str(e)}")
        return {
            "statusCode": 500,
            "body": {
                "status": "error",
                "message": f"Database error occurred: {str(e)}",
            },
        }


def validate_and_attach_cidr_block(
    ip_hostnames_list: List[Dict[str, str]], db_session: Session
) -> Union[Dict[str, str], None]:
    """
    Update the ip_hostnames_list in-place by attaching the 'block' key to each dict.
    If any IP does not belong to reserved CIDR block , return an error response.
    """

    cidr_blocks = db_session.query(CIDR_BLOCK).all()
    for entry in ip_hostnames_list:
        ip = entry["ip"]
        ip_obj = ipaddress.ip_address(ip)
        user = entry["user_email"]

        matched_block = None
        for cidr in cidr_blocks:
            block_net = ipaddress.ip_network(cidr.block)
            if ip_obj in block_net:
                matched_block = cidr
                break

        # Check if any CIDR block reserved for this IP, if not reject with error message
        if not matched_block:
            return {
                "statusCode": 400,
                "body": {
                    "status": "error",
                    "message": f"No CIDR block reserved for the host with IP : {ip}. Host cannot be registered",
                },
            }

        # Check if user of the host matches the owner of the CIDR block, if not reject with error message.
        authorized_users_list = matched_block.authorized_users or []
        if matched_block.owner != user and user not in authorized_users_list:
            return {
                "statusCode": 403,
                "body": {
                    "status": "error",
                    "message": f"IP Address {ip} belongs to CIDR block {matched_block.block}, which is reserved by other user: {matched_block.owner} and you are not in the authorized users list. Host cannot be registered",
                },
            }

        # Adding matched block to original entry
        entry["block"] = matched_block.block

    return None


def validate_duplicate_serial_numbers(
    data: List[Dict], db_session: Session
) -> Optional[dict]:
    # Collect incoming serial numbers
    input_serial_numbers = [item["serial_number"] for item in data]

    # Query DB for existing serial_numbers and unpack in a set
    duplicate_serials = {
        host.serial_number
        for host in db_session.query(Host.serial_number)
        .filter(Host.serial_number.in_(input_serial_numbers))
        .all()
        if host.serial_number is not None
    }

    # If any serial number exists then throw error
    if duplicate_serials:
        return {
            "statusCode": 409,
            "body": {
                "status": "error",
                "message": f"Serial number(s) already exists in the DB from the input: {', '.join(duplicate_serials)}",
            },
        }

    return None


def register_hosts(data: List[Dict], db_session: Session, user: str) -> dict:
    # Validate input structure coming as input to register_hosts from vmca
    print("[INFO] Validate input json structure for the register hosts api.")
    error_msg = validate_input(data)
    if error_msg:
        return {"statusCode": 400, "body": {"status": "error", "message": error_msg}}

    # Validate if the length of input list of hosts is not > 100
    if len(data) > 100:
        return {
            "statusCode": 413,  # Payload Too Large
            "body": {
                "status": "error",
                "message": "Import Limit Exceeded: Too Many Hosts! You can only import up to 100 at once.",
            },
        }

    # Validate if any serial number is existing in the DB and if yes then returns error
    error_msg = validate_duplicate_serial_numbers(data, db_session)
    if error_msg:
        return error_msg

    # Hostname and Domain split from FQDN
    ip_hostnames_list, error = extract_reserved_ips_details(data, user)
    if error:
        return error

    # Check for uniqueness of host based on ip and hostname
    ips = [item["ip"] for item in ip_hostnames_list]
    hostnames = [item["hostname"] for item in ip_hostnames_list]

    # query for existing ips
    existing_hosts = db_session.query(Host).filter((Host.ip_address.in_(ips))).all()
    existing_ips = "".join(f"{host.ip_address}, " for host in existing_hosts)
    if existing_ips:
        return {
            "statusCode": 409,
            "body": {
                "status": "error",
                "message": f"IP addresses already registered : {existing_ips[:-2]}",
            },
        }

    # query for existing hostnames
    existing_hosts = db_session.query(Host).filter((Host.hostname.in_(hostnames))).all()
    existing_hostnames = "".join(f"{host.hostname}, " for host in existing_hosts)
    if existing_hostnames:
        return {
            "statusCode": 409,
            "body": {
                "status": "error",
                "message": f"Hostnames already registered : {existing_hostnames[:-2]}",
            },
        }

    error_response = validate_and_attach_cidr_block(ip_hostnames_list, db_session)
    if error_response:
        return error_response

    print(
        f"[INFO] All the hosts :{data} requested to be registered has correct structure and are unique and can be registered."
    )
    print("[INFO] Registering the incoming hosts..")

    response = upload_hosts_to_db(db_session, ip_hostnames_list)
    if response:
        return response

    # Upload the hosts to CMDB inventory
    print(
        f"[INFO] Uploading the incoming hosts {ip_hostnames_list} to CMDB inventory.."
    )
    try:
        cmdb_client = CMDBClient()
        cmdb_client.upload_ips_to_cmdb_inventory(ip_hostnames_list)
    except Exception as cmdb_error:
        print(
            f"[ERROR] Uploading the incoming hosts to CMDB inventory with error : {str(cmdb_error)}"
        )
        return {
            "statusCode": 500,
            "body": {
                "status": "error",
                "message": f"Hosts saved successfully in the database, but CMDB upload failed. {str(cmdb_error)}",
            },
        }

    # Reached here means that all registeration steps were successful
    print(f"[INFOR] Successfully registered the incoming hosts : {data}.")
    return {
        "statusCode": 200,
        "body": {
            "status": "success",
            "message": f"{len(ip_hostnames_list)} host(s) registered successfully.",
        },
    }
