import json
from common.cmdb_client import CMDBClient

def list_hosts_cmdb_only(c_code, dns_domain=None):
    """
    Fetches all CMDB hosts for a given c_code and optional dns_domain.
    """
    try:
        client = CMDBClient()
        hosts = client.fetch_cmdb_server_list_paginated(
            c_code=c_code,
            dns_domain=dns_domain,
        )
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "status": "success",
                "count": len(hosts),
                "data": hosts,
            }),
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "status": "error",
                "message": str(e),
            }),
        }
