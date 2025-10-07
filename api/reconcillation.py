import os
import csv
import io
import datetime
import re
from sqlalchemy.orm import Session
from typing import Dict, List, Optional
from common.db import Host
from box_sdk_gen import BoxClient, BoxCCGAuth, CCGConfig


# Box Configuration
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
            enterprise_id=enterprise_id
        )
        auth = BoxCCGAuth(config=ccg_config)
        client = BoxClient(auth)
        return client
    except Exception as e:
        raise BoxAuthenticationError(f'Box authentication failed: {str(e)}') from e


def list_files_in_folder(folder_id: str, client: BoxClient) -> List[str]:
    items = client.folders.get_folder_items(folder_id, limit=1000)
    file_names = [item.name for item in items.entries if item.type == "file"]
    return file_names


def get_latest_inventory_file(file_names: List[str]) -> Optional[str]:
    # Updated pattern from _VM_Inventory to _vCD_Inventory
    inventory_files = [
        f for f in file_names if re.match(r"\d{2}-\d{2}-\d{2}_vCD_Inventory.*\.csv", f)
    ]
    if not inventory_files:
        return None
    try:
        inventory_files.sort(
            key=lambda x: datetime.datetime.strptime(x[:8], "%m-%d-%y"), 
            reverse=True
        )
        return inventory_files[0]
    except ValueError:
        return None


def download_file_from_box(file_name: str, folder_id: str, client: BoxClient) -> str:
    try:
        folder = client.folders.get_folder_items(folder_id=folder_id)
        if folder is None:
            raise InventoryFileNotFoundError(f"Folder with ID {folder_id} does not exist")
        items = folder.entries
        for item in items:
            if item.name == file_name:
                file = client.downloads.download_file(item.id)
                content = file.read().decode('utf-8')
                return content
        raise InventoryFileNotFoundError(f'File "{file_name}" not found in folder {folder_id}')
    except InventoryFileNotFoundError:
        raise
    except Exception as e:
        raise Exception(f'Error downloading file {file_name}: {str(e)}') from e


def get_vm_inventory_from_box(offering: Optional[str] = None) -> List[Dict]:
    # Updated filename pattern from VM_Inventory to vCD_Inventory
    file_name_today = f'{datetime.datetime.now().strftime("%m-%d-%y")}_vCD_Inventory.csv'
    
    # Check both folders right away
    folders_to_check = [BOX_FOLDER_DALST, BOX_FOLDER_TOKST]
    

    if not folders_to_check:
        raise ValueError("No Box folder IDs configured. Check BOX_FOLDER_DALST and BOX_FOLDER_TOKST environment variables.")

    vm_inventory = []
    client = box_auth(BOX_CLIENT_ID, BOX_CLIENT_SECRET, ENTERPRISE_ID)
    files_found = []

    # Check all folders and collect files from each
    for folder_id in folders_to_check:
        try:
            file_names = list_files_in_folder(folder_id, client)
            target_file = None
            
            if file_name_today in file_names:
                target_file = file_name_today
            else:
                target_file = get_latest_inventory_file(file_names)
            
            if not target_file:
                # No inventory file found in this folder, continue to next
                continue
            
            file_content = download_file_from_box(target_file, folder_id, client)
            files_found.append((folder_id, target_file, file_content))
            
        except InventoryFileNotFoundError:
            continue
        except Exception:
            continue

    if not files_found:
        raise InventoryFileNotFoundError('No vCD Inventory file found in any Box folder')

    # Process all found files
    for folder_id, target_file, file_content in files_found:
        csv_file = io.StringIO(file_content)
        first_line = csv_file.readline()
        if not first_line.startswith('#TYPE'):
            csv_file.seek(0)

        reader = csv.DictReader(csv_file)
        
        # Handle case where reader.fieldnames might be None
        if not reader.fieldnames:
            continue
        
        reader.fieldnames = [name.strip() if name else '' for name in reader.fieldnames]

        for row in reader:
            ips = row.get("IP", "").strip()
            vcenter = row.get("vCenter", "").strip()
            org = row.get("Org", "").strip()  # Added Org column
            
            if not ips:
                continue
            
            # Filter out entries with Org name as "public-catalog"
            if org.lower() == "public-catalog":
                continue
                
            for ip in ips.split():
                ip_cleaned = ip.strip()
                if ip_cleaned:
                    vm_inventory.append({
                        "IP": ip_cleaned,
                        "vCenter": vcenter,
                        "Org": org  # Include Org in inventory
                    })
    
    return vm_inventory


def list_all_hosts_for_reconciliation(db_session: Session, offering: Optional[str] = None) -> List[Dict]:
    # Added user field and offering filter
    query = db_session.query(
        Host.ip_address,
        Host.hostname,
        Host.workload_domain,
        Host.user  # Added user field
    )
    
    # Filter by offering - only VCFaaS for now, will filter out VCS later
    if offering:
        query = query.filter(Host.host_type  == offering)
    else:
        # Default to VCFaaS when offering is None
        query = query.filter(Host.host_type  == "VCFaaS")
    
    hosts = query.all()
    
    return [
        {
            "ip_address": host.ip_address,
            "hostname": host.hostname,
            "workload_domain": host.workload_domain,
            "user": host.user,  # Include user in response
        }
        for host in hosts
    ]


def perform_inventory_reconciliation(db_session: Session, offering: Optional[str] = None) -> Dict:
    try:
        vmca_hosts = list_all_hosts_for_reconciliation(db_session, offering)
    except Exception as e:
        return {
            "statusCode": 500,
            "body": {"status": "error", "message": f"Error retrieving VMCA hosts: {str(e)}"}
        }

    try:
        vm_inventory = get_vm_inventory_from_box(offering)
    except InventoryFileNotFoundError as e:
        return {"statusCode": 404, "body": {"status": "error", "message": str(e)}}
    except BoxAuthenticationError as e:
        return {"statusCode": 401, "body": {"status": "error", "message": f"Box authentication failed: {str(e)}"}}
    except Exception as e:
        return {"statusCode": 500, "body": {"status": "error", "message": f"Error reading VM inventory from Box: {str(e)}"}}

    # Duplicate detection
    duplicates = []

    vmca_by_ip = {}
    for host in vmca_hosts:
        ip = host.get("ip_address")
        if not ip:
            continue
        if ip in vmca_by_ip:
            duplicates.append({
                "ip_address": ip,
                "hostname": host["hostname"],
                "workload_domain": host["workload_domain"],
                "user": host["user"],
                "reason": "Duplicate IP detected in VMCA"
            })
        else:
            vmca_by_ip[ip] = host

    vm_by_ip = {}
    for vm in vm_inventory:
        ip = vm.get("IP")
        if not ip:
            continue
        if ip in vm_by_ip:
            duplicates.append({
                "ip_address": ip,
                "vCenter": vm.get("vCenter"),
                "Org": vm.get("Org"),
                "reason": "Duplicate IP detected in VM inventory"
            })
        else:
            vm_by_ip[ip] = vm

    matched_hosts = []
    missing_in_vmca = []
    not_deployed = []

    # Compare VMCA hosts with VM inventory
    for ip, vmca_host in vmca_by_ip.items():
        if ip in vm_by_ip:
            vm = vm_by_ip[ip]
            workload_domain = vmca_host.get("workload_domain", "")
            vcenter = vm.get("vCenter", "")
            org = vm.get("Org", "")
            
            if workload_domain and vcenter and workload_domain.lower() in vcenter.lower():
                matched_hosts.append({
                    "ip_address": ip,
                    "hostname": vmca_host.get("hostname"),
                    "workload_domain": workload_domain,
                    "user": vmca_host.get("user"),
                    "vCenter": vcenter,
                    "Org": org,
                    "match_status": "matched",
                    "match_reason": f"workload_domain '{workload_domain}' found in vCenter '{vcenter}'"
                })
            else:
                matched_hosts.append({
                    "ip_address": ip,
                    "hostname": vmca_host.get("hostname"),
                    "workload_domain": workload_domain,
                    "user": vmca_host.get("user"),
                    "vCenter": vcenter,
                    "Org": org,
                    "match_status": "ip_matched_but_domain_mismatch",
                    "match_reason": f"IP matched but workload_domain '{workload_domain}' NOT found in vCenter '{vcenter}'"
                })
        else:
            not_deployed.append({
                "ip_address": ip,
                "hostname": vmca_host.get("hostname"),
                "workload_domain": vmca_host.get("workload_domain"),
                "user": vmca_host.get("user"),
                "reason": "Host registered in VMCA but not found in VM inventory report"
            })

    # Compare VM inventory with VMCA
    for ip, vm in vm_by_ip.items():
        if ip not in vmca_by_ip:
            missing_in_vmca.append({
                "ip_address": ip,
                "vCenter": vm.get("vCenter"),
                "Org": vm.get("Org"),
                "reason": "Found in VM inventory but not registered in VMCA"
            })

    # Updated response structure per reviewer's suggestion
    return {
        "statusCode": 200,
        "body": {
            "status": "success",
            "reconciliation_summary": {
                "total_vmca_hosts": len(vmca_hosts),
                "total_hosts_in_report": len(vm_inventory),  # Renamed from total_vm_inventory
                "matched_hosts": len(matched_hosts),
                "missing_in_vmca": len(missing_in_vmca),
                "not_deployed": len(not_deployed),
                "duplicates": len(duplicates)
            },
            "offerings": {
                "VCFaaS": {
                    "matched_hosts": matched_hosts,
                    "missing_in_vmca": missing_in_vmca,
                    "not_deployed": not_deployed,
                    "duplicates": duplicates
                }
            }
        }
    }


def reconciliation_endpoint(db_session: Session, offering: Optional[str] = None) -> Dict:
    return perform_inventory_reconciliation(db_session, offering)
