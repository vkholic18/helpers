from common.auth import authenticate
from api.v1.listing import list_hosts
from api.v1.register_cidr_block import register_cidr_block
from api.v1.register_hosts import register_hosts
from api.v1.register_hosts_cmdb_only import register_hosts_cmdb_only
from api.v1.deregister_hosts import deregister_hosts
from api.v1.deregister_hosts_cmdb_only import deregister_hosts_cmdb_only  # ✅ NEW
from api.v1.deregister_cidr_block import deregister_cidr_block
from api.v1.cidr_authorized_users import patch_authorized_users
from api.v1.listing_cidr_block import list_cidr_blocks
from api.v1.vpc import get_vpc_instance_crn
from common.db import get_db_session
from api.v1.tgw_connection import create_and_approve_connection, delete_tgw_connection
from api.v1.reconciliation import reconciliation_endpoint
import json
import base64
import binascii
from urllib.parse import parse_qs


def parse_ce_body(args):
    raw_body = args.get("__ce_body")

    if not raw_body:
        return {
            "statusCode": 400,
            "body": {
                "status": "error",
                "message": "Request body is missing",
            },
        }, None

    try:
        decoded = base64.b64decode(raw_body)
        decoded_str = decoded.decode("utf-8").strip()
        if not decoded_str:
            raise ValueError("Decoded body is empty")

        request_body = json.loads(decoded_str)
        return None, request_body
    except (json.JSONDecodeError, binascii.Error, ValueError) as e:
        return {
            "body": f"Malformed JSON {getattr(e, 'msg', str(e))} in request body",
            "statusCode": 400,
        }, None


@authenticate
def main(args):
    db_session = get_db_session()
    print("Successfully created db session")
    try:
        path = args["__ce_path"]
        method = args["__ce_method"]
        user = args.get("email")

        query_string = args.get("__ce_query", "")
        query_params = parse_qs(query_string)

        if path == "/hosts/register":
            if method.lower() != "post":
                return {"body": "Method not allowed", "statusCode": 405}

            error_response, request_body = parse_ce_body(args)
            if error_response:
                return error_response

            return register_hosts(request_body, db_session, user)

        elif path == "/hosts/register/cmdb":
            if method.lower() != "post":
                return {"body": "Method not allowed", "statusCode": 405}

            error_response, request_body = parse_ce_body(args)
            if error_response:
                return error_response

            return register_hosts_cmdb_only(request_body, user)

        elif path == "/hosts/deregister":
            if method.lower() != "post":
                return {"body": "Method not allowed", "statusCode": 405}

            error_response, request_body = parse_ce_body(args)
            if error_response:
                return error_response

            return deregister_hosts(request_body, db_session, user)

        # ✅ NEW CMDB-ONLY DEREGISTER ENDPOINT
        elif path == "/hosts/deregister/cmdb":
            if method.lower() != "post":
                return {"body": "Method not allowed", "statusCode": 405}

            error_response, request_body = parse_ce_body(args)
            if error_response:
                return error_response

            return deregister_hosts_cmdb_only(request_body, user)

        elif path == "/hosts/list":
            all_users_str = query_params.get("all_users", ["false"])[0].lower()
            all_users = all_users_str == "true"
            return list_hosts(method, db_session, user, all_users)

        elif path == "/cidr/list":
            if method.lower() != "get":
                return {"body": "Method not allowed", "statusCode": 405}

            all_users_str = query_params.get("all_users", ["false"])[0].lower()
            all_users = all_users_str == "true"

            is_vcf_for_vpc_str = query_params.get("is_vcf_for_vpc", ["false"])[0].lower()
            is_vcf_for_vpc = is_vcf_for_vpc_str == "true"

            return list_cidr_blocks(db_session, user, all_users, is_vcf_for_vpc)

        elif path == "/cidr/register":
            if method.lower() != "post":
                return {"body": "Method not allowed", "statusCode": 405}

            error_response, request_body = parse_ce_body(args)
            if error_response:
                return error_response

            return register_cidr_block(request_body, db_session, user)

        elif path == "/cidr/deregister":
            if method.lower() != "post":
                return {"body": "Method not allowed", "statusCode": 405}

            error_response, request_body = parse_ce_body(args)
            if error_response:
                return error_response

            return deregister_cidr_block(request_body, db_session, user)

        elif path == "/cidr/authorized-users":
            if method.lower() != "patch":
                return {"body": "Method not allowed", "statusCode": 405}

            error_response, request_body = parse_ce_body(args)
            if error_response:
                return error_response

            return patch_authorized_users(request_body, db_session, user)

        elif path.startswith("/vpc"):
            if method.lower() != "get":
                return {"body": "Method not allowed", "statusCode": 405}

            vpc_id = path.split("/").pop()
            region = query_params.get("region", [False])[0]

            if not region:
                return {
                    "statusCode": 400,
                    "body": {
                        "status": "error",
                        "message": 'Missing or invalid "region" query parameter.',
                    },
                }

            return get_vpc_instance_crn(region, vpc_id)

        elif path == "/tgw_connection":
            method = method.lower()
            if method not in ["post", "delete"]:
                return {"body": "Method not allowed", "statusCode": 405}

            error_response, request_data = parse_ce_body(args)
            if error_response:
                return error_response

            vpc_crn = request_data.get("crn")
            if not vpc_crn:
                return {
                    "statusCode": 400,
                    "body": {"status": "error", "message": "Missing CRN of VPC"},
                }

            if method == "post":
                vcf_for_vpc_name = request_data.get("vcf_for_vpc_name")
                if not vcf_for_vpc_name:
                    return {
                        "statusCode": 400,
                        "body": {
                            "status": "error",
                            "message": "Missing vcf_for_vpc_name in the request",
                        },
                    }

                iam_token = request_data.get("iam_access_token")
                return create_and_approve_connection(
                    vpc_crn,
                    vcf_for_vpc_name,
                    db_session,
                    approve_iam_token=iam_token,
                )
            else:
                return delete_tgw_connection(vpc_crn)

        elif path == "/reconciliation":
            if method.lower() != "get":
                return {"body": "Method not allowed", "statusCode": 405}

            offering = query_params.get("offering", [None])[0]
            if offering is None or offering.lower() == "vcfaas":
                response = reconciliation_endpoint(db_session)
                response["body"] = json.dumps(response["body"])
                response.setdefault("headers", {"Content-Type": "application/json"})
                return response
            else:
                return {"body": "Offering not implemented", "statusCode": 400}

        else:
            return {"body": "Operation not allowed", "path": path, "statusCode": 400}

    except Exception as e:
        print(
            f'Unhandled exception occurred during handling request "{method} {path}". The exception was: {e}'
        )
        return {
            "body": "An internal error occurred while handling your request. Please contact the VMCA support team.",
            "statusCode": 500,
        }
    finally:
        db_session.close()
