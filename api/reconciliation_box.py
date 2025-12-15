import os
import csv
import io
import datetime
import re
from sqlalchemy.orm import Session
from typing import Dict, List, Optional
from common.db import Host
from box_sdk_gen import BoxClient, BoxCCGAuth, CCGConfig

BOX_CLIENT_ID = os.getenv("BOX_CLIENT_ID")
BOX_CLIENT_SECRET = os.getenv("BOX_CLIENT_SECRET")
ENTERPRISE_ID = os.getenv("ENTERPRISE_ID")
BOX_FOLDER_DALST = os.getenv("BOX_FOLDER_DALST")
BOX_FOLDER_TOKST = os.getenv("BOX_FOLDER_TOKST")


class BoxAuthenticationError(Exception):
    """Raised when Box authentication fails."""
    pass


class InventoryFileNotFoundError(Exception):
    """Raised when a required file is not found."""
    pass


def box_auth(client_id: str, client_secret: str, enterprise_id: str) -> BoxClient:
    if not all([client_id, client_secret, enterprise_id]):
        raise BoxAuthenticationError(
            "Missing required Box credentials. Check BOX_CLIENT_ID, BOX_CLIENT_SECRET, and ENTERPRISE_ID environment variables."
        )
    try:
        ccg_config = CCGConfig(
            client_id=client_id,
            client_secret=client_secret,
            enterprise_id=enterprise_id,
        )
        auth = BoxCCGAuth(config=ccg_config)
        return BoxClient(auth)
    except Exception as e:
        raise BoxAuthenticationError(f"Box authentication failed: {str(e)}") from e


def list_files_in_folder(folder_id: str, client: BoxClient) -> List[str]:
    items = client.folders.get_folder_items(folder_id, limit=1000)
    return [item.name for item in items.entries if item.type == "file"]


def get_latest_inventory_file(file_names: List[str]) -> Optional[str]:
    inventory_files = [
        f for f in file_names if re.match(r"\d{2}-\d{2}-\d{2}_vCD_Inventory.*\.csv", f)
    ]
    if not inventory_files:
        return None
    try:
        inventory_files.sort(
            key=lambda x: datetime.datetime.strptime(x[:8], "%m-%d-%y"),
            reverse=True,
        )
        return inventory_files[0]
    except ValueError:
        return None


def download_file_from_box(file_name: str, folder_id: str, client: BoxClient) -> str:
    try:
        # FIX: ensure pagination limit matches list_files_in_folder
        items = client.folders.get_folder_items(folder_id, limit=1000)

        for item in items.entries:
            if item.type == "file" and item.name == file_name:
                file = client.downloads.download_file(item.id)
                return file.read().decode("utf-8")

        raise InventoryFileNotFoundError(
            f'File "{file_name}" not found in folder {folder_id}'
        )

    except InventoryFileNotFoundError:
        raise
    except Exception as e:
        raise RuntimeError(f"Error downloading file {file_name}") from e


def get_vm_inventory_from_box(offering: Optional[str] = None) -> List[Dict]:
    file_name_today = (
        f'{datetime.datetime.now().strftime("%m-%d-%y")}_vCD_Inventory.csv'
    )

    folders_to_check = [BOX_FOLDER_DALST, BOX_FOLDER_TOKST]

    if not folders_to_check:
        raise ValueError(
            "No Box folder IDs configured. Check BOX_FOLDER_DALST and BOX_FOLDER_TOKST environment variables."
        )

    vm_inventory = []
    client = box_auth(BOX_CLIENT_ID, BOX_CLIENT_SECRET, ENTERPRISE_ID)
    files_found = []

    for folder_id in folders_to_check:
        try:
            file_names = list_files_in_folder(folder_id, client)

            if file_name_today in file_names:
                target_file = file_name_today
            else:
                target_file = get_latest_inventory_file(file_names)

            if not target_file:
                raise InventoryFileNotFoundError(
                    f"No inventory file found in Box folder {folder_id}"
                )

            file_content = download_file_from_box(target_file, folder_id, client)
            files_found.append((folder_id, target_file, file_content))

        except Exception as e:
            raise RuntimeError("Inventory retrieval failed") from e

    for folder_id, target_file, file_content in files_found:
        csv_file = io.StringIO(file_content)
        first_line = csv_file.readline()
        if not first_line.startswith("#TYPE"):
            csv_file.seek(0)

        reader = csv.DictReader(csv_file)

        if not reader.fieldnames:
            raise RuntimeError(
                f"CSV file '{target_file}' from folder {folder_id} has no headers"
            )

        reader.fieldnames = [name.strip() if name else "" for name in reader.fieldnames]

        for row in reader:
            ips = row.get("IP", "").strip()
            vcd = row.get("vCD", "").strip()
            org = row.get("Org", "").strip()
            name = row.get("Name", "").strip()

            if not ips or org.lower() == "public-catalog":
                continue

            for ip in ips.split():
                if ip.strip():
                    vm_inventory.append(
                        {"IP": ip.strip(), "vCD": vcd, "Org": org, "Name": name}
                    )

    return vm_inventory


def list_all_hosts_for_reconciliation(
    db_session: Session, offering: Optional[str] = None
) -> List[Dict]:
    query = db_session.query(
        Host.ip_address, Host.hostname, Host.workload_domain, Host.user, Host.vcd_org
    )

    if offering:
        query = query.filter(Host.host_type == offering)
    else:
        query = query.filter(Host.host_type == "VCFaaS")

    hosts = query.all()

    return [
        {
            "ip_address": host.ip_address,
            "hostname": host.hostname,
            "workload_domain": host.workload_domain,
            "user": host.user,
            "vcd_org": host.vcd_org,
        }
        for host in hosts
    ]


def perform_inventory_reconciliation(
    db_session: Session, offering: Optional[str] = None
) -> Dict:
    try:
        vmca_hosts = list_all_hosts_for_reconciliation(db_session, offering)
    except Exception as e:
        return {
            "statusCode": 500,
            "body": {"status": "error", "message": str(e)},
        }

    try:
        vm_inventory = get_vm_inventory_from_box(offering)
    except InventoryFileNotFoundError as e:
        return {"statusCode": 404, "body": {"status": "error", "message": str(e)}}
    except BoxAuthenticationError as e:
        return {"statusCode": 401, "body": {"status": "error", "message": str(e)}}
    except Exception as e:
        return {"statusCode": 500, "body": {"status": "error", "message": str(e)}}

    vmca_by_ip = {host["ip_address"]: host for host in vmca_hosts}

    vm_by_ip = {}
    duplicates = []

    for vm in vm_inventory:
        ip = vm.get("IP")
        if not ip:
            continue
        if ip in vm_by_ip:
            duplicates.append(vm)
        else:
            vm_by_ip[ip] = vm

    matched_hosts = []
    missing_in_vmca = []
    not_deployed = []

    for ip, vmca_host in vmca_by_ip.items():
        if ip in vm_by_ip:
            matched_hosts.append(vmca_host)
        else:
            not_deployed.append(vmca_host)

    for ip, vm in vm_by_ip.items():
        if ip not in vmca_by_ip:
            missing_in_vmca.append(vm)

    return {
        "statusCode": 200,
        "body": {
            "status": "success",
            "reconciliation_summary": {
                "total_vmca_hosts": len(vmca_hosts),
                "total_hosts_in_report": len(vm_inventory),
                "matched_hosts": len(matched_hosts),
                "missing_in_vmca": len(missing_in_vmca),
                "not_deployed": len(not_deployed),
                "duplicates": len(duplicates),
            },
        },
    }


def reconciliation_endpoint(
    db_session: Session, offering: Optional[str] = None
) -> Dict:
    return perform_inventory_reconciliation(db_session, offering)
