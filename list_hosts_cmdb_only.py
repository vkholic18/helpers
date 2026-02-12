from common.cmdb_client import CMDBClient


def list_hosts_cmdb_only(c_code):

    try:
        client = CMDBClient()
        hosts = client.fetch_cmdb_server_list(c_code=c_code)

        return {
            "statusCode": 200,
            "body": {
                "status": "success",
                "count": len(hosts),
                "data": hosts,
            },
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "body": {
                "status": "error",
                "message": str(e),
            },
        }
