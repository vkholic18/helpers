def upload_ips_to_cmdb_inventory(
        self, ips_list: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        payload = self.build_cmdb_payload(ips_list)
        
        # TEMPORARY DEBUG: Return everything needed for Postman testing
        return {
            "debug_mode": True,
            "cmdb_url": self.CMDB_INSERT_MULTIPLE_PROD_API_URL,
            "cmdb_token": self.CMDB_ACCESS_TOKEN,
            "payload": payload,
            "instructions": {
                "step_1": "Copy the 'cmdb_url' into Postman as POST request",
                "step_2": "Add header: Authorization: Bearer {copy cmdb_token here}",
                "step_3": "Add header: Content-Type: application/json",
                "step_4": "Copy the entire 'payload' object into Body (raw JSON)",
                "step_5": "Send and observe the response"
            }
        }
        
        # ORIGINAL CODE (commented out for debugging):
        # print(
        #     f"[INFO] Uploading payload to CMDB: {json.dumps(payload, indent=2)} with URL : {self.CMDB_INSERT_MULTIPLE_PROD_API_URL}"
        # )
        #
        # headers = {
        #     "Authorization": f"Bearer {self.CMDB_ACCESS_TOKEN}",
        #     "Content-Type": "application/json",
        # }
        #
        # try:
        #     response = requests.post(
        #         self.CMDB_INSERT_MULTIPLE_PROD_API_URL,
        #         headers=headers,
        #         json=payload,
        #         timeout=60,
        #     )
        #     response.raise_for_status()
        #
        #     print(
        #         f"[INFO] Uploaded the above missing ips to CMDB successfully!! : response:{response.json()}"
        #     )
        #     return response.json()
        #
        # except requests.exceptions.Timeout:
        #     raise TimeoutError(
        #         "CMDB inventory service is currently unavailable (timeout). Please try again later."
        #     )
        # except requests.exceptions.RequestException:
        #     raise RuntimeError(
        #         "Failed to communicate with CMDB inventory service. Please try again later."
        #     )

    @staticmethod
    def build_cmdb_payload(missing_ips_list: List[Dict[str, str]]) -> Dict[str, str]:
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
                "u_c_code": "ic4vmws",
                "u_dcim_status": "Pre-live",
                "u_internet_facing": "Other",
                "u_owned_by": "Giovanni Viera/Durham/IBM",
                "u_model_manufacturer": "Virtual",
                "u_model_name": "Virtual",
                "u_name": record["hostname"],
                "u_dns_domain": record["domain"],
                "u_data_center": record["datacenter"],
                "u_system_admin": record["user_email"],
                "u_environment": record["environment"],
                "u_platform": record["platform"],
                # Note: stringify the network_adapters list for this specific format
                "u_network_adapters": json.dumps(network_adapter),
                "u_serial_number": record["serial_number"],
            }

            if (
                record.get("host_type")
                and record.get("host_type") == HOST_TYPE_VCF_FOR_VPC
            ):
                payload_record.update(
                    {
                        "u_exclude_patching": "true",
                        "u_exclude_anti_virus": "true",
                        "u_exclude_health_checks": "true",
                        "u_exclude_log_collections": "true",
                        "u_exclude_reason": "Virtual IP",
                    }
                )
            records.append(payload_record)

        return {"records": records}
