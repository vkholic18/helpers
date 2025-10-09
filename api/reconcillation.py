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
    file_name_today = f'{datetime.datetime.now().strftime("%m-%d-%y")}_vCD_Inventory.csv'
    
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
                # Log the error and raise exception
                print(f"ERROR: No inventory file found in folder {folder_id}")
                raise Exception(f"No inventory file found in Box folder {folder_id}")
            
            file_content = download_file_from_box(target_file, folder_id, client)
            files_found.append((folder_id, target_file, file_content))
            
        except Exception as e:
            print(f"ERROR: Error retrieving inventory from folder {folder_id}: {str(e)}")
            raise Exception("Error when trying to retrieve inventory reports. Please retry it later") from e

    # Process all found files
    for folder_id, target_file, file_content in files_found:
        csv_file = io.StringIO(file_content)
        first_line = csv_file.readline()
        if not first_line.startswith('#TYPE'):
            csv_file.seek(0)

        reader = csv.DictReader(csv_file)
        
        # Raise error if fieldnames is None
        if not reader.fieldnames:
            print(f"ERROR: CSV file from folder {folder_id} has no fieldnames/headers")
            raise Exception("Error when trying to retrieve inventory reports. Please retry it later")
        
        reader.fieldnames = [name.strip() if name else '' for name in reader.fieldnames]

        for row in reader:
            ips = row.get("IP", "").strip()
            vcd = row.get("vCD", "").strip()  # Changed from vCenter to vCD
            org = row.get("Org", "").strip()
            name = row.get("Name", "").strip()  # Added Name column for reference
            
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
                        "vCD": vcd,  # Changed from vCenter to vCD
                        "Org": org,
                        "Name": name  # Include Name for reference
                    })
    
    return vm_inventory


def list_all_hosts_for_reconciliation(db_session: Session, offering: Optional[str] = None) -> List[Dict]:
    query = db_session.query(
        Host.ip_address,
        Host.hostname,
        Host.workload_domain,
        Host.user,
        Host.vcd_org  # Added vcd_org field
    )
    
    # Filter by offering - only VCFaaS for now
    if offering:
        query = query.filter(Host.host_type == offering)
    else:
        # Default to VCFaaS when offering is None
        query = query.filter(Host.host_type == "VCFaaS")
    
    hosts = query.all()
    
    return [
        {
            "ip_address": host.ip_address,
            "hostname": host.hostname,
            "workload_domain": host.workload_domain,
            "user": host.user,
            "vcd_org": host.vcd_org,  # Include vcd_org in response
        }
        for host in hosts
    ]


def perform_inventory_reconciliation(db_session: Session, offering: Optional[str] = None) -> Dict:
    try:
        vmca_hosts = list_all_hosts_for_reconciliation(db_session, offering)
    except Exception as e:
        print(f"ERROR: Error retrieving VMCA hosts: {str(e)}")
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
        print(f"ERROR: Error reading VM inventory from Box: {str(e)}")
        return {"statusCode": 500, "body": {"status": "error", "message": "Error when trying to retrieve inventory reports. Please retry it later"}}

    # Build VMCA lookup (no need to check duplicates as ip_address is primary key)
    vmca_by_ip = {host.get("ip_address"): host for host in vmca_hosts if host.get("ip_address")}

    # Build VM inventory lookup and detect duplicates
    vm_by_ip = {}
    duplicates = []
    
    for vm in vm_inventory:
        ip = vm.get("IP")
        if not ip:
            continue
        
        if ip in vm_by_ip:
            # Duplicate IP found - check if vCD and Org are different
            existing_vm = vm_by_ip[ip]
            if existing_vm.get("vCD") != vm.get("vCD") or existing_vm.get("Org") != vm.get("Org"):
                duplicates.append({
                    "ip_address": ip,
                    "vCD": vm.get("vCD"),
                    "Org": vm.get("Org"),
                    "Name": vm.get("Name")  # Include Name for reference
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
            vcd = vm.get("vCD", "")
            vm_org = vm.get("Org", "")
            vmca_vcd_org = vmca_host.get("vcd_org", "")
            
            # Check if workload_domain matches vCD and org matches
            if (workload_domain and vcd and workload_domain.lower() in vcd.lower() and 
                vmca_vcd_org and vm_org and vmca_vcd_org.lower() == vm_org.lower()):
                matched_hosts.append({
                    "ip_address": ip,
                    "hostname": vmca_host.get("hostname"),
                    "workload_domain": workload_domain,
                    "user": vmca_host.get("user"),
                    "vcd_org": vmca_vcd_org,
                    "vCD": vcd,
                    "match_status": "matched",
                    "match_reason": f"workload_domain '{workload_domain}' found in vCD '{vcd}' and Org matched"
                })
            else:
                # Mismatch - this is a duplicate
                duplicates.append({
                    "ip_address": ip,
                    "hostname": vmca_host.get("hostname"),
                    "workload_domain": workload_domain,
                    "user": vmca_host.get("user"),
                    "vmca_vcd_org": vmca_vcd_org,
                    "vCD": vcd,
                    "vm_org": vm_org
                })
        else:
            not_deployed.append({
                "ip_address": ip,
                "hostname": vmca_host.get("hostname"),
                "workload_domain": vmca_host.get("workload_domain"),
                "user": vmca_host.get("user"),
                "vcd_org": vmca_host.get("vcd_org")
            })

    # Compare VM inventory with VMCA
    for ip, vm in vm_by_ip.items():
        if ip not in vmca_by_ip:
            missing_in_vmca.append({
                "ip_address": ip,
                "vCD": vm.get("vCD"),
                "Org": vm.get("Org"),
                "Name": vm.get("Name")  # Include Name for reference
            })

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
                "duplicates": len(duplicates)
            },
            "offerings": {
                "VCFaaS": {
                    "matched_hosts": {
                        "description": "Hosts that are registered in VMCA and found in VM inventory with matching workload_domain and Org",
                        "hosts": matched_hosts
                    },
                    "missing_in_vmca": {
                        "description": "Found in VM inventory but not registered in VMCA",
                        "hosts": missing_in_vmca
                    },
                    "not_deployed": {
                        "description": "Host registered in VMCA but not found in VM inventory report",
                        "hosts": not_deployed
                    },
                    "duplicates": {
                        "description": "Hosts with matching IP but mismatched workload_domain, vCD, or Org fields",
                        "hosts": duplicates
                    }
                }
            }
        }
    }


def reconciliation_endpoint(db_session: Session, offering: Optional[str] = None) -> Dict:
    return perform_inventory_reconciliation(db_session, offering)
