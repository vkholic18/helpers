import json
from common.cmdb_client import CMDBClient


def list_hosts_cmdb_only(c_code, offset=0, limit=500):
    """
    Serverless-safe paginated endpoint.
    """

    try:
        client = CMDBClient()

        hosts = client.fetch_cmdb_server_list_paginated(
            c_code=c_code,
            offset=int(offset),
            limit=int(limit),
        )

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "status": "success",
                "count": len(hosts),
                "offset": int(offset),
                "limit": int(limit),
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
