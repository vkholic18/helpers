from api.v1.tgw_connection import create_tgw_connection


elif path == "/tgw_connection":
    if method.lower() != "post":
        return {"body": "Method not allowed", "statusCode": 405}

    error_response, request_data = parse_ce_body(args)
    if error_response:
        return error_response

    vpc_crn = request_data.get("vpc_crn")
    transit_gateway_id = args.get("transit_gateway_id")
    if not vpc_crn or not transit_gateway_id:
        return {"body": "Missing vpc_crn or transit_gateway_id", "statusCode": 400}

    return create_tgw_connection(vpc_crn,transit_gateway_id)


