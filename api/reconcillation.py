# api/v1/reconciliation.py
import csv
from sqlalchemy.orm import Session
from typing import Dict, List
from common.db import Host

def list_all_hosts_for_reconciliation(db_session: Session) -> Dict:
    """
    Fetch all hosts and return them in API response format for reconciliation.
    """
    hosts = db_session.query(Host).all()
    host_list = [
        {
            "ip_address": host.ip_address,
            "hostname": host.hostname,
            "domain_name": host.domain_name,
            "datacenter": host.datacenter,
            "platform": host.platform,
            "environment": host.environment,
            "serial_number": host.serial_number,
            "user": host.user,
            "registration_time": host.registration_time.isoformat(),
            "block": host.block,
            "host_type": host.host_type,
            "workload_domain": host.workload_domain,
            "vcd_org": host.vcd_org,
        }
        for host in hosts
    ]
    return {
        "statusCode": 200,
        "body": {
            "status": "success",
            "data": host_list,
        },
    }


def perform_inventory_reconciliation(
    db_session: Session, 
    csv_file_path: str
) -> Dict:
    """
    Perform inventory reconciliation between VMCA hosts and VM inventory report.
    
    Args:
        db_session: Database session
        csv_file_path: Path to the CSV file containing VM inventory (with IP and vCenter columns)
    
    Returns:
        Dictionary containing reconciliation results
    """
    # Get all hosts from VMCA
    vmca_response = list_all_hosts_for_reconciliation(db_session)
    vmca_hosts = vmca_response["body"]["data"]
    
    # Read VM inventory from CSV
    vm_inventory = []
    try:
        with open(csv_file_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            # Strip whitespace from headers
            reader.fieldnames = [name.strip() for name in reader.fieldnames]
            for row in reader:
                vm_inventory.append({
                    "IP": row.get("IP", "").strip(),
                    "vCenter": row.get("vCenter", "").strip()
                })
    except FileNotFoundError:
        return {
            "statusCode": 404,
            "body": {
                "status": "error",
                "message": f"CSV file not found: {csv_file_path}"
            }
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": {
                "status": "error",
                "message": f"Error reading CSV file: {str(e)}"
            }
        }
    
    # Create lookup dictionaries for O(1) comparison
    # This allows fast IP-based matching instead of nested loops
    vmca_by_ip = {host["ip_address"]: host for host in vmca_hosts}
    vm_by_ip = {vm["IP"]: vm for vm in vm_inventory if vm["IP"]}
    
    # Reconciliation results - 4 categories
    matched_hosts = []                    # IPs found in both, domains match
    missing_in_vmca = []                  # In CSV but not in VMCA (gap)
    missing_in_vm_inventory = []          # In VMCA but not in CSV (gap)
    broader_servers_excluded = []         # In CSV but intentionally not in VMCA
    
    # === COMPARISON LOGIC ===
    # Step 1: For each VMCA host, check if it exists in VM inventory
    # Primary key for matching: IP Address
    
    # Check each VMCA host against VM inventory
    for ip, vmca_host in vmca_by_ip.items():
        if ip in vm_by_ip:
            vm = vm_by_ip[ip]
            workload_domain = vmca_host.get("workload_domain", "")
            vcenter = vm["vCenter"]
            
            # LOGIC: Check if workload_domain is substring of vCenter (as per point 3)
            # Example: workload_domain="w381" should match vCenter="vcenter-w381-prod.domain.com"
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
            # LOGIC: VMCA host not found in CSV - this is a missing host
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
            
            # LOGIC (Point 4): Check if this is a broader server to exclude
            # Broader servers are out of scope - they have vCenter patterns like:
            # "dalm001-vc-m001.dalstdst.dir" or similar infrastructure servers
            # These should be excluded from "missing" list as they're intentionally not in VMCA
            is_broader_server = (
                "dalm" in vcenter.lower() or 
                "vc-m" in vcenter.lower() or
                "-m0" in vcenter.lower()  # Infrastructure management servers
            )
            
            if is_broader_server:
                broader_servers_excluded.append({
                    "ip_address": ip,
                    "vCenter": vcenter,
                    "reason": "Broader server out of scope (infrastructure/management server)"
                })
            else:
                # LOGIC: VM exists in inventory but not registered in VMCA
                # This could be a gap - hosts that should be registered
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


def reconciliation_endpoint(db_session: Session, csv_file_path: str) -> Dict:
    """
    API endpoint for inventory reconciliation.
    
    Usage:
        result = reconciliation_endpoint(db_session, "/path/to/vm_inventory.csv")
    """
    return perform_inventory_reconciliation(db_session, csv_file_path)
