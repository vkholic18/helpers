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

    # 🔹 ONLY CHANGE: added optional c_code
    def fetch_cmdb_server_list(
        self,
        c_code: Optional[str] = None,
        hostname: Optional[str] = None,
        serial_number: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """This will fetch the servers in the CMDB database"""

        headers = {
            "Authorization": f"Bearer {self.CMDB_GETCI_PROD_API_URL}",
            "Content-Type": "application/json",
        }

        # 🔹 ONLY CHANGE: use provided c_code or fallback
        effective_c_code = c_code or IC4VMWS_UC_CODE
        base_query = f"u_c_code={effective_c_code}^u_dcim_status=Pre-live"

        if hostname:
            base_query += f"^name={hostname}"
        if serial_number:
            base_query += f"^serial_number={serial_number}"

        all_records = []
        limit = 1000
        page = 1
        last_sys_id = ""

        while True:
            query = f"{base_query}^ORDERBYsys_id"

            if last_sys_id:
                query += f"^sys_id>{last_sys_id}"

            params = {"sysparm_query": query, "sysparm_limit": str(limit)}

            max_retries = 5
            backoff_factor = 2

            retries = 0
            while retries < max_retries:
                try:
                    response = requests.get(
                        self.CMDB_GETCI_PROD_API_URL,
                        headers=headers,
                        params=params,
                        timeout=60,
                    )
                    if response.status_code == 429:
                        print(response.headers)
                        retry_after = int(
                            response.headers.get("Retry-After", backoff_factor**retries)
                        )
                        print(
                            f"[Warning] Rate limited (429). Retrying in {retry_after} seconds..."
                        )
                        time.sleep(retry_after)
                        retries += 1
                        continue

                    response.raise_for_status()
                    data = response.json()

                    records = data.get("result")
                    if not records:
                        return all_records

                    all_records.extend(records)
                    last_sys_id = records[-1]["sys_id"]

                    if len(records) < limit:
                        return all_records

                    page += 1
                    break
                except requests.RequestException as e:
                    wait_time = backoff_factor**retries
                    print(
                        f"Error {e} fetching CMDB records for api_url: {self.CMDB_GETCI_PROD_API_URL} and params: {params}, Retrying in {wait_time} seconds.."
                    )
                    time.sleep(wait_time)
                    retries += 1
                except ValueError:
                    raise ValueError(
                        f"Invalid JSON response from api_url: {self.CMDB_GETCI_PROD_API_URL}"
                    )
            else:
                print(f"[Error] Failed after {max_retries}. Giving up.")
                return all_records

    # EVERYTHING BELOW IS UNCHANGED

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
