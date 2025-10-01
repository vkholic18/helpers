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
    """
    Authenticate with Box and return a client.
    
    Args:
        client_id: Box application client ID
        client_secret: Box application client secret
        enterprise_id: Box enterprise ID
        
    Returns:
        BoxClient: Authenticated Box client
        
    Raises:
        BoxAuthenticationError: If authentication fails
    """
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
    """
    List all file names in a given Box folder.
    
    Args:
        folder_id: Box folder ID
        client: Authenticated Box client
        
    Returns:
        List of file names in the folder
    """
    items = client.folders.get_folder_items(folder_id, limit=1000)
    file_names = [item.name for item in items.entries if item.type == "file"]
    return file_names


def get_latest_inventory_file(file_names: List[str]) -> Optional[str]:
    """
    Find the latest VM_Inventory.csv file by date in filename.
    Accepts files like MM-DD-YY_VM_Inventory.csv or MM-DD-YY_VM_Inventory-OLD.csv
    
    Args:
        file_names: List of file names to search
        
    Returns:
        Name of the latest inventory file, or None if not found
    """
    inventory_files = [
        f for f in file_names if re.match(r"\d{2}-\d{2}-\d{2}_VM_Inventory.*\.csv", f)
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


def download_file_from_box(
        file_name: str, 
        folder_id: str, 
        client: BoxClient
) -> str:
    """
    Download a file from Box and return its content as a string.
    
    Args:
        file_name: Name of the file to download
        folder_id: Box folder ID containing the file
        client: Authenticated Box client
        
    Returns:
        File content as string
        
    Raises:
        InventoryFileNotFoundError: If file is not found in folder
        Exception: If download fails
    """
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
    """
    Download VM inventory from Box based on offering.
    Tries today's file first, then falls back to latest available.
    
    Args:
        offering: The offering type (e.g., 'VCFaas'). If None, tries all folders.
    
    Returns:
        List of VM inventory records
        
    Raises:
        InventoryFileNotFoundError: If no inventory file is found
        BoxAuthenticationError: If authentication fails
    """
    file_name_today = f'{datetime.datetime.now().strftime("%m-%d-%y")}_VM_Inventory.csv'
    
    # Determine which folders to check
    folders_to_check = [BOX_FOLDER_DALST]
    if BOX_FOLDER_TOKST:
        folders_to_check.append(BOX_FOLDER_TOKST)
    
    # Filter out None values
    folders_to_check = [f for f in folders_to_check if f]
    
    if not folders_to_check:
        raise ValueError("No Box folder IDs configured. Check BOX_FOLDER_DALST and BOX_FOLDER_TOKST environment variables.")
    
    vm_inventory = []
    file_content = None
    target_file = None
    
    # Authenticate once for all operations
    client = box_auth(BOX_CLIENT_ID, BOX_CLIENT_SECRET, ENTERPRISE_ID)
    
    # Try to find the file in Box folders
    for folder_id in folders_to_check:
        try:
            file_names = list_files_in_folder(folder_id, client)
            
            # Prefer today's file, else fallback to latest
            if file_name_today in file_names:
                target_file = file_name_today
            else:
                target_file = get_latest_inventory_file(file_names)
            
            if not target_file:
                continue

            file_content = download_file_from_box(target_file, folder_id, client)
            break
            
        except InventoryFileNotFoundError:
            continue
        except Exception:
            continue
    
    if not file_content:
        raise InventoryFileNotFoundError('No VM Inventory file found in any Box folder')
    
    # Parse CSV content
    csv_file = io.StringIO(file_content)
    
    # Skip PowerShell header line if present (starts with #TYPE)
    first_line = csv_file.readline()
    if not first_line.startswith('#TYPE'):
        csv_file.seek(0)
    
    reader = csv.DictReader(csv_file)
    
    # Strip whitespace from headers
    if reader.fieldnames:
        reader.fieldnames = [name.strip() if name else '' for name in reader.fieldnames]
    
    for row in reader:
        ips = row.get("IP", "").strip()
        vcenter = row.get("vCenter", "").strip()
        
        if not ips:
            continue
        
        # Split multiple IPs on space and create separate entries
        for ip in ips.split():
            ip_cleaned = ip.strip()
            if ip_cleaned:
                vm_inventory.append({
                    "IP": ip_cleaned,
                    "vCenter": vcenter
                })
    
    return vm_inventory


def list_all_hosts_for_reconciliation(db_session: Session) -> List[Dict]:
    """
    Fetch hosts with only the fields needed for reconciliation.
    Only queries necessary fields for better performance.
    
    Args:
        db_session: SQLAlchemy database session
        
    Returns:
        List of host dictionaries with ip_address, hostname, and workload_domain
    """
    hosts = db_session.query(
        Host.ip_address,
        Host.hostname,
        Host.workload_domain
    ).all()
    
    host_list = [
        {
            "ip_address": host.ip_address,
            "hostname": host.hostname,
            "workload_domain": host.workload_domain,
        }
        for host in hosts
    ]
    return host_list


def perform_inventory_reconciliation(
    db_session: Session, 
    offering: Optional[str] = None
) -> Dict:
    """
    Perform inventory reconciliation between VMCA hosts and VM inventory report from Box.
    
    Args:
        db_session: Database session
        offering: Optional offering type (e.g., 'VCFaas')
    
    Returns:
        Dictionary containing reconciliation results with statusCode and body
    """
    # Get all hosts from VMCA
    try:
        vmca_hosts = list_all_hosts_for_reconciliation(db_session)
    except Exception as e:
        return {
            "statusCode": 500,
            "body": {
                "status": "error",
                "message": f"Error retrieving VMCA hosts: {str(e)}"
            }
        }
    
    # Get VM inventory from Box
    try:
        vm_inventory = get_vm_inventory_from_box(offering)
    except InventoryFileNotFoundError as e:
        return {
            "statusCode": 404,
            "body": {
                "status": "error",
                "message": str(e)
            }
        }
    except BoxAuthenticationError as e:
        return {
            "statusCode": 401,
            "body": {
                "status": "error",
                "message": f"Box authentication failed: {str(e)}"
            }
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": {
                "status": "error",
                "message": f"Error reading VM inventory from Box: {str(e)}"
            }
        }
    
    # Create lookup dictionaries for O(1) comparison
    vmca_by_ip = {host["ip_address"]: host for host in vmca_hosts if host.get("ip_address")}
    vm_by_ip = {vm["IP"]: vm for vm in vm_inventory if vm.get("IP")}
    
    # Reconciliation results - 4 categories
    matched_hosts = []
    missing_in_vmca = []
    missing_in_vm_inventory = []
    broader_servers_excluded = []
    
    # Check each VMCA host against VM inventory
    for ip, vmca_host in vmca_by_ip.items():
        if ip in vm_by_ip:
            vm = vm_by_ip[ip]
            workload_domain = vmca_host.get("workload_domain", "")
            vcenter = vm.get("vCenter", "")
            
            # Check if workload_domain is substring of vCenter
            if workload_domain and vcenter and workload_domain.lower() in vcenter.lower():
                matched_hosts.append({
                    "ip_address": ip,
                    "hostname": vmca_host.get("hostname"),
                    "workload_domain": workload_domain,
                    "vCenter": vcenter,
                    "match_status": "matched",
                    "match_reason": f"workload_domain '{workload_domain}' found in vCenter '{vcenter}'"
                })
            else:
                matched_hosts.append({
                    "ip_address": ip,
                    "hostname": vmca_host.get("hostname"),
                    "workload_domain": workload_domain,
                    "vCenter": vcenter,
                    "match_status": "ip_matched_but_domain_mismatch",
                    "match_reason": f"IP matched but workload_domain '{workload_domain}' NOT found in vCenter '{vcenter}'"
                })
        else:
            missing_in_vm_inventory.append({
                "ip_address": ip,
                "hostname": vmca_host.get("hostname"),
                "workload_domain": vmca_host.get("workload_domain"),
                "reason": "Host registered in VMCA but not found in VM inventory report"
            })
    
    # Check for VMs in inventory but not in VMCA
    for ip, vm in vm_by_ip.items():
        if ip not in vmca_by_ip:
            vcenter = vm.get("vCenter", "")
            
            # Check if this is a broader server to exclude
            vcenter_lower = vcenter.lower()
            is_broader_server = (
                "dalm" in vcenter_lower or 
                "vc-m" in vcenter_lower or
                "-m0" in vcenter_lower
            )
            
            if is_broader_server:
                broader_servers_excluded.append({
                    "ip_address": ip,
                    "vCenter": vcenter,
                    "reason": "Broader server out of scope (infrastructure/management server)"
                })
            else:
                missing_in_vmca.append({
                    "ip_address": ip,
                    "vCenter": vcenter,
                    "reason": "Found in VM inventory but not registered in VMCA"
                })
    
    # Prepare response
    return {
        "statusCode": 200,
        "body": {
            "status": "success",
            "reconciliation_summary": {
                "total_vmca_hosts": len(vmca_hosts),
                "total_vm_inventory": len(vm_inventory),
                "matched_hosts": len(matched_hosts),
                "missing_in_vmca": len(missing_in_vmca),
                "missing_in_vm_inventory": len(missing_in_vm_inventory),
                "broader_servers_excluded": len(broader_servers_excluded)
            },
            "details": {
                "matched_hosts": matched_hosts,
                "missing_in_vmca": missing_in_vmca,
                "missing_in_vm_inventory": missing_in_vm_inventory,
                "broader_servers_excluded": broader_servers_excluded
            }
        }
    }


def reconciliation_endpoint(db_session: Session, offering: Optional[str] = None) -> Dict:
    """
    API endpoint for inventory reconciliation.
    
    Args:
        db_session: Database session
        offering: Optional offering type (e.g., 'VCFaas')
    
    Returns:
        Dictionary with statusCode and body containing reconciliation results
        
    Usage:
        result = reconciliation_endpoint(db_session, offering="VCFaas")
    """
    return perform_inventory_reconciliation(db_session, offering)
