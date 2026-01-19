def upload_ips_to_cmdb_inventory(
        self, ips_list: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        payload = self.build_cmdb_payload(ips_list)
        
        # TEMPORARY DEBUG: Return everything needed for Postman testing
        # Wrapped in body so it prints properly in serverless response
        return {
            "statusCode": 200,
            "body": {
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
        }
