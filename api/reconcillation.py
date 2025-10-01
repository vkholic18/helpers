# api/v1/reconciliation.py
import csv
import io
import datetime
import re
from sqlalchemy.orm import Session
from typing import Dict, List
from common.db import Host
from box_sdk_gen import BoxClient, BoxCCGAuth, CCGConfig


# Box Configuration
CLIENT_ID = "qdskgwhpn69qy70rcyq8diu1di723o4c"
CLIENT_SECRET = "xxrvQcaZOra7w4jJGJpGwb1vu08ma8k7"
ENTERPRISE_ID = "455328"
BOX_FOLDERS = {
    'DALST': '304823331811',
    'TOKST': '305028378380'
}


def box_auth(client_id: str, client_secret: str, enterprise_id: str) -> BoxClient:
    """Authenticate with Box and return a client."""
    try:
        print('[INFO] Authenticating BOX user')
        ccg_config = CCGConfig(
            client_id=client_id,
            client_secret=client_secret,
            enterprise_id=enterprise_id
        )
        print('[INFO] Getting client')
        auth = BoxCCGAuth(config=ccg_config)
        client = BoxClient(auth)
        return client
    except Exception as e:
        print(f'[ERROR] There is an error authenticating box: {e}')
        raise Exception(f'There is an error authenticating box: {e}') from e


def list_files_in_folder(folder_id: str, client: BoxClient) -> List[str]:
    """
    List all file names in a given Box folder.
    """
    items = client.folders.get_folder_items(folder_id, limit=1000)
    file_names = [item.name for item in items.entries if item.type == "file"]
    return file_names


def get_latest_inventory_file(file_names: List[str]) -> str:
    """
    Find the latest VM_Inventory.csv file by date in filename.
    Accepts files like MM-DD-YY_VM_Inventory.csv or MM-DD-YY_VM_Inventory-OLD.csv
    """
    inventory_files = [
        f for f in file_names if re.match(r"\d{2}-\d{2}-\d{2}_VM_Inventory.*\.csv", f)
    ]
    if not inventory_files:
        return None
    # Sort by date in filename (MM-DD-YY)
    inventory_files.sort(
        key=lambda x: datetime.datetime.strptime(x[:8], "%m-%d-%y"), 
        reverse=True
    )
    return inventory_files[0]


def download_file_from_box(
        file_name: str, 
        folder_id: str, 
        client_id: str, 
        client_secret: str, 
        enterprise_id: str
) -> str:
    """Download a file from Box and return its content as a string."""
    client = box_auth(client_id, client_secret, enterprise_id)

    try:
        print(f'[INFO] Validating folder: {folder_id}')
        folder = client.folders.get_folder_items(folder_id=folder_id)
        if folder is None:
            print(f"[ERROR] Folder with ID {folder_id} does not exist")
            raise Exception(f"Folder with ID {folder_id} does not exist")

        items = folder.entries
        for item in items:
            if item.name == file_name:
                file = client.downloads.download_file(item.id)
                return file.read().decode('utf-8')

        print(f'[INFO] File "{file_name}" not found')
        raise FileNotFoundError(f'File "{file_name}" not found in folder {folder_id}')
    except Exception as e:
        raise Exception(f'Error downloading file {file_name} with error {e}') from e


def get_vm_inventory_from_box(offering: str = None) -> List[Dict]:
    """
    Download VM inventory from Box based on offering.
    Tries today's file first, then falls back to latest available.
    
    Args:
        offering: The offering type (e.g., 'VCFaas'). If None, tries all folders.
    
    Returns:
        List of VM inventory records
    """
    file_name_today = f'{datetime.datetime.now().strftime("%m-%d-%y")}_VM_Inventory.csv'
    
    # Determine which folders to check
    folders_to_check = BOX_FOLDERS
    
    vm_inventory = []
    file_content = None
    target_file = None
    found_location = None
    
    # Authenticate once for all operations
    print("[INFO] Authenticating BOX user")
    auth = BoxCCGAuth(CCGConfig(CLIENT_ID, CLIENT_SECRET, enterprise_id=ENTERPRISE_ID))
    client = BoxClient(auth)
    
    # Try to find the file in Box folders
    for location, folder_id in folders_to_check.items():
        try:
            print(f'[INFO] Checking files in {location} folder')
            file_names = list_files_in_folder(folder_id, client)
            print(f'[DEBUG] Files in {location}: {file_names}')
            
            # Prefer today's file, else fallback to latest
            if file_name_today in file_names:
                target_file = file_name_today
                print(f'[INFO] Found today\'s file: {target_file}')
            else:
                target_file = get_latest_inventory_file(file_names)
                if target_file:
                    print(f"[WARN] Today's file not found, falling back to latest available: {target_file}")
            
            if not target_file:
                print(f'[INFO] No inventory file found in {location}, trying next folder')
                continue
            
            print(f'[INFO] Downloading {target_file} from {location}')
            file_content = download_file_from_box(
                target_file,
                folder_id,
                CLIENT_ID,
                CLIENT_SECRET,
                ENTERPRISE_ID
            )
            found_location = location
            print(f'[INFO] Successfully downloaded {target_file} from {location}')
            break
            
        except FileNotFoundError:
            print(f'[INFO] File not found in {location}, trying next folder')
            continue
        except Exception as e:
            print(f'[ERROR] Error checking {location} folder: {e}')
            continue
    
    if not file_content:
        raise FileNotFoundError(f'No VM Inventory file found in any Box folder')
    
    # Parse CSV content
    csv_file = io.StringIO(file_content)
    
    # Skip PowerShell header line if present (starts with #TYPE)
    first_line = csv_file.readline()
    if not first_line.startswith('#TYPE'):
        # If it's not a PowerShell header, reset to beginning
        csv_file.seek(0)
    
    reader = csv.DictReader(csv_file)
    print(f"[DEBUG] CSV headers: {reader.fieldnames}")
    
    # Strip whitespace from headers
    reader.fieldnames = [name.strip() for name in reader.fieldnames]
    
    for row in reader:
        ips = row.get("IP", "").strip()
        vcenter = row.get("vCenter", "").strip()
        
        if not ips:
            continue
        
        # Split multiple IPs on space and create separate entries
        for ip in ips.split():
            vm_inventory.append({
                "IP": ip.strip(),
                "vCenter": vcenter
            })
    
    print(f'[INFO] Parsed {len(vm_inventory)} VM records from {target_file}')
    return vm_inventory


def list_all_hosts_for_reconciliation(db_session: Session) -> List[Dict]:
    """
    Fetch hosts with only the fields needed for reconciliation.
    Only queries necessary fields for better performance.
    """
    # Query only the fields we actually need for reconciliation
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
    offering: str = None
) -> Dict:
    """
    Perform inventory reconciliation between VMCA hosts and VM inventory report from Box.
    
    Args:
        db_session: Database session
        offering: Optional offering type (e.g., 'VCFaas')
    
    Returns:
        Dictionary containing reconciliation results
    """
    # Get all hosts from VMCA
    vmca_hosts = list_all_hosts_for_reconciliation(db_session)
    
    # Get VM inventory from Box
    try:
        vm_inventory = get_vm_inventory_from_box(offering)
    except FileNotFoundError as e:
        return {
            "statusCode": 404,
            "body": {
                "status": "error",
                "message": str(e)
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
    vmca_by_ip = {host["ip_address"]: host for host in vmca_hosts}
    vm_by_ip = {vm["IP"]: vm for vm in vm_inventory if vm["IP"]}
    
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
            vcenter = vm["vCenter"]
            
            # Check if workload_domain is substring of vCenter
            if workload_domain and workload_domain.lower() in vcenter.lower():
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
            vcenter = vm["vCenter"]
            
            # Check if this is a broader server to exclude
            is_broader_server = (
                "dalm" in vcenter.lower() or 
                "vc-m" in vcenter.lower() or
                "-m0" in vcenter.lower()
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


def reconciliation_endpoint(db_session: Session, offering: str = None) -> Dict:
    """
    API endpoint for inventory reconciliation.
    
    Args:
        db_session: Database session
        offering: Optional offering type (e.g., 'VCFaas')
    
    Usage:
        result = reconciliation_endpoint(db_session, offering="VCFaas")
    """
    return perform_inventory_reconciliation(db_session, offering)
