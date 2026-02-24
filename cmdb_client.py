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
        """This will fetch the servers in the CMDB database"""

        headers = {
            "Authorization": f"Bearer {self.CMDB_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }

        effective_c_code = c_code or IC4VMWS_UC_CODE
        base_query = f"u_c_code={effective_c_code}^u_dcim_status=Live"

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

            params = {"sysparm_query": query, "sysparm_limit": str(limit), "sysparm_table": "cmdb_ci_server"}

            # 🔍 DEBUG POINT 1: Check params before API call
            # return {
            #     "debug_point": "1_BEFORE_API_CALL",
            #     "c_code": effective_c_code,
            #     "page": page,
            #     "query": query,
            #     "params": params,
            #     "url": self.CMDB_GETCI_PROD_API_URL
            # }

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
                    
                    # 🔍 DEBUG POINT 2: Check response immediately after API call
                    # return {
                    #     "debug_point": "2_AFTER_API_CALL",
                    #     "status_code": response.status_code,
                    #     "final_url": response.url,
                    #     "response_headers": dict(response.headers),
                    #     "response_body_preview": response.text[:500]
                    # }
                    
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

                    # 🔍 DEBUG POINT 3: Check before raise_for_status
                    # return {
                    #     "debug_point": "3_BEFORE_RAISE_FOR_STATUS",
                    #     "status_code": response.status_code,
                    #     "will_raise_error": response.status_code >= 400,
                    #     "response_body": response.text[:500]
                    # }

                    response.raise_for_status()
                    
                    # 🔍 DEBUG POINT 4: Check after raise_for_status (only reaches here if 2xx status)
                    # return {
                    #     "debug_point": "4_AFTER_RAISE_FOR_STATUS",
                    #     "status_code": response.status_code,
                    #     "message": "raise_for_status passed, about to parse JSON"
                    # }
                    
                    data = response.json()

                    # 🔍 DEBUG POINT 5: Check after JSON parsing
                    # return {
                    #     "debug_point": "5_AFTER_JSON_PARSE",
                    #     "data_keys": list(data.keys()),
                    #     "result_count": len(data.get("result", [])),
                    #     "total_count": data.get("count", "N/A")
                    # }

                    records = data.get("result", [])
                    if not records:
                        # 🔍 DEBUG POINT 6: Check when no records returned
                        # return {
                        #     "debug_point": "6_NO_RECORDS",
                        #     "all_records_count": len(all_records),
                        #     "message": "No more records, returning all_records"
                        # }
                        return all_records

                    all_records.extend(records)
                    last_sys_id = records[-1]["sys_id"]

                    # 🔍 DEBUG POINT 7: Check after adding records
                    # return {
                    #     "debug_point": "7_AFTER_ADDING_RECORDS",
                    #     "records_in_this_page": len(records),
                    #     "total_records_so_far": len(all_records),
                    #     "last_sys_id": last_sys_id,
                    #     "will_continue_pagination": len(records) >= limit
                    # }

                    if len(records) < limit:
                        # 🔍 DEBUG POINT 8: Check when pagination completes
                        # return {
                        #     "debug_point": "8_PAGINATION_COMPLETE",
                        #     "final_count": len(all_records),
                        #     "message": "Last page reached, returning all_records"
                        # }
                        return all_records

                    page += 1
                    break
                    
                except requests.RequestException as e:
                    # 🔍 DEBUG POINT 9: Check when exception occurs
                    # return {
                    #     "debug_point": "9_EXCEPTION_CAUGHT",
                    #     "exception_type": type(e).__name__,
                    #     "exception_message": str(e),
                    #     "retry_attempt": retries + 1,
                    #     "max_retries": max_retries
                    # }
                    
                    wait_time = backoff_factor**retries
                    print(
                        f"Error {e} fetching CMDB records for api_url: {self.CMDB_GETCI_PROD_API_URL} and params: {params}, Retrying in {wait_time} seconds.."
                    )
                    time.sleep(wait_time)
                    retries += 1
                    
                except ValueError:
                    # 🔍 DEBUG POINT 10: Check when JSON parsing fails
                    # return {
                    #     "debug_point": "10_JSON_PARSE_ERROR",
                    #     "response_text": response.text[:500],
                    #     "message": "Failed to parse JSON"
                    # }
                    raise ValueError(
                        f"Invalid JSON response from api_url: {self.CMDB_GETCI_PROD_API_URL}"
                    )
            else:
                # 🔍 DEBUG POINT 11: Check when max retries exhausted
                # return {
                #     "debug_point": "11_MAX_RETRIES_EXHAUSTED",
                #     "records_fetched_so_far": len(all_records),
                #     "message": "Giving up after max retries"
                # }
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
