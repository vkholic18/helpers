import requests
from typing import Dict, Any, List
import json
import os
from typing import Optional
import time

IC4VMWS_UC_CODE = "ic4vmws"
DECOMMISION_REASON = "Graveyarding the VM"
HOST_TYPE_VCF_FOR_VPC = "VCFforVPC"


class CMDBClient:
    """
    Client to upload Hosts in CMDB inventory
    """

    def __init__(self):
        self.CMDB_GETCI_PROD_API_URL = os.getenv("CMDB_GETCI_PROD_API_URL")
        self.CMDB_INSERT_MULTIPLE_PROD_API_URL = os.getenv(
            "CMDB_INSERT_MULTIPLE_PROD_API_URL"
        )
        self.CMDB_ACCESS_TOKEN = os.getenv("CMDB_ACCESS_TOKEN")

        if (
            not self.CMDB_GETCI_PROD_API_URL
            or not self.CMDB_INSERT_MULTIPLE_PROD_API_URL
            or not self.CMDB_ACCESS_TOKEN
        ):
            raise RuntimeError(
                "Missing CMDB URL's or Access Token environment variables!!!"
            )

    def fetch_cmdb_server_list(
        self,
        c_code: Optional[str] = None,
        hostname: Optional[str] = None,
        serial_number: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """This will fetch the servers in the CMDB database
        
        Uses offset-based pagination matching ServiceNow API standards.
        """

        headers = {
            "Authorization": f"Bearer {self.CMDB_ACCESS_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # Use provided c_code or fallback to default
        effective_c_code = c_code or IC4VMWS_UC_CODE
        
        # Build the query string exactly as in working curl
        query_parts = [f"u_c_code={effective_c_code}", "u_dcim_status=Live"]
        
        if hostname:
            query_parts.append(f"name={hostname}")
        if serial_number:
            query_parts.append(f"serial_number={serial_number}")
        
        query_string = "^".join(query_parts)

        all_records = []
        offset = 0
        limit = 1000
        max_retries = 5
        backoff_factor = 2

        while True:
            # Exact parameter structure from working curl
            params = {
                "sysparm_table": "cmdb_ci_server",
                "sysparm_start": offset,
                "sysparm_limit": limit,
                "sysparm_query": query_string
            }
            
            print(f"[INFO] Fetching records with offset={offset}, query={query_string}")
            
            retries = 0
            while retries < max_retries:
                try:
                    response = requests.get(
                        self.CMDB_GETCI_PROD_API_URL,
                        headers=headers,
                        params=params,
                        timeout=60,
                    )

                    # Handle rate limiting
                    if response.status_code == 429:
                        retry_after = int(
                            response.headers.get("Retry-After", backoff_factor**retries)
                        )
                        print(f"[Warning] Rate limited (429). Retrying in {retry_after} seconds...")
                        time.sleep(retry_after)
                        retries += 1
                        continue

                    # Log and raise on 416 errors with details
                    if response.status_code == 416:
                        print(f"[ERROR] 416 Range Not Satisfiable")
                        print(f"[ERROR] URL: {response.url}")
                        print(f"[ERROR] Params: {params}")
                        print(f"[ERROR] Response: {response.text[:500]}")
                        response.raise_for_status()
                    
                    # Raise exception for other HTTP errors
                    response.raise_for_status()
                    
                    # Parse JSON response
                    data = response.json()

                    # Extract records from response
                    records = data.get("result", [])
                    
                    # If no records returned, we've fetched everything
                    if not records:
                        print(f"[INFO] No more records. Total fetched: {len(all_records)}")
                        return all_records

                    # Add records to our collection
                    all_records.extend(records)
                    print(f"[INFO] Fetched {len(records)} records at offset {offset} (Total: {len(all_records)})")

                    # If we got fewer records than the limit, we're done
                    if len(records) < limit:
                        print(f"[INFO] Fetching complete. Total records: {len(all_records)}")
                        return all_records

                    # Move to next page
                    offset += limit
                    break

                except requests.RequestException as e:
                    wait_time = backoff_factor**retries
                    print(
                        f"[Error] Request failed: {e}"
                        f"\n  URL: {self.CMDB_GETCI_PROD_API_URL}"
                        f"\n  Params: {params}"
                        f"\n  Retrying in {wait_time} seconds..."
                    )
                    time.sleep(wait_time)
                    retries += 1
                    
                except ValueError as e:
                    print(f"[ERROR] Invalid JSON response: {e}")
                    raise ValueError(
                        f"Invalid JSON response from {self.CMDB_GETCI_PROD_API_URL}"
                    )
            else:
                # Exhausted all retries
                print(f"[ERROR] Failed after {max_retries} retries. Returning {len(all_records)} records.")
                return all_records

    def upload_ips_to_cmdb_inventory(
        self, ips_list: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        payload = self.build_cmdb_payload(ips_list)
        print(
            f"[INFO] Uploading payload to CMDB: {json.dumps(payload, indent=2)} with URL : {self.CMDB_INSERT_MULTIPLE_PROD_API_URL}"
        )

        headers = {
            "Authorization": f"Bearer {self.CMDB_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }

        response = requests.post(
            self.CMDB_INSERT_MULTIPLE_PROD_API_URL,
            headers=headers,
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def build_cmdb_payload(missing_ips_list: List[Dict[str, str]]) -> dict:
        records = []

        for record in missing_ips_list:
            network_adapter = [
                {
                    "vlan": "0",
                    "ip": record["ip"],
                    "type": "BEN",
                    "mac": "FF:FF:FF:FF:FF:FF",
                }
            ]

            payload_record = {
                "u_sys_class_name": "cmdb_ci_server",
                "u_sos_form_type": "server",
                "u_c_code": record["c_code"],
                "u_name": record.get("hostname") or record.get("fqdn"),
                "u_dns_domain": record["domain"],
                "u_data_center": record["datacenter"],
                "u_system_admin": record.get("system_admin"),
                "u_environment": record.get("env") or record.get("environment"),
                "u_dcim_status": "Live",
                "u_internet_facing": "Other",
                "u_model_manufacturer": "Virtual",
                "u_model_name": "Virtual",
                "u_platform": record.get("platform", "Virtual"),
                "u_owned_by": record["owned_by"],
                "u_additional_owners": record.get("additional_owners", ""),
                "u_business_unit": record["business_unit"],
                "u_application": record["app_name"],
                "u_component": record.get("u_component", ""),
                "u_role": record["role"],
                "u_management_ip_address": record["ip"],
                "u_network_adapters": json.dumps(network_adapter),
                "u_serial_number": record["serial_number"],
                "u_emergency_contacts": record.get("emergency_contacts", ""),
                "u_exclude_patching": record["u_exclude_patching"],
                "u_exclude_anti_virus": record["u_exclude_anti_virus"],
                "u_exclude_health_checks": record["u_exclude_health_checks"],
                "u_exclude_log_collections": record["u_exclude_log_collections"],
                "u_exclude_reason": record["u_exclude_reason"],
            }

            records.append(payload_record)

        return {"records": records}

    @staticmethod
    def build_cmdb_graveyard_payload(graveyard_server_list):
        records = []

        for record in graveyard_server_list:
            records.append(
                {
                    "u_sys_class_name": "cmdb_ci_server",
                    "u_c_code": record["c_code"],
                    "u_dcim_status": "Graveyard",
                    "u_decom_reason": DECOMMISION_REASON,
                    "u_name": record["hostname"],
                    "u_serial_number": record["serial_number"],
                    "u_sos_form_type": "server",
                }
            )

        return {"records": records}

    def remove_hosts_from_cmdb(self, hosts_list):
        payload = self.build_cmdb_graveyard_payload(hosts_list)

        headers = {
            "Authorization": f"Bearer {self.CMDB_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }

        response = requests.post(
            self.CMDB_INSERT_MULTIPLE_PROD_API_URL,
            headers=headers,
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        return response.json()
