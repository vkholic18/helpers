# api/v1/reconciliation.py

from sqlalchemy.orm import Session
from typing import Dict
from models import Host  # Update the import path as needed


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
