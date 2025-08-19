import json
from collections.abc import Callable
from typing import Annotated
import requests
import typer
from rich import print
from ic4v_vm_cli.common.util.constants import (
    HOSTS_DEREGISTER_PATH,
    GITHUB_TOKEN,
    RESERVATION_SERVICE_BASE_URL,
)

def release_ips_command() -> Callable[..., None]:
    return create_release_ips_command_with()

def create_release_ips_command_with(
    reservation_service: ReservationService,
) -> Callable[..., None]:
    """Return a function to release ips for the user."""
    
    def command(
        file: Annotated[
            typer.FileText,
            typer.Option("--file", "-f", help="JSON file containing host information to release"),
        ],
    ) -> None:
        """
        Release hosts provided in a JSON input file.

        Examples:\n
        Release hosts provided in the JSON input file:\n
            vmca ips release -f hosts_file.json \n
            
            Example JSON format for single host:
            {
                "ip": "172.19.1.18",
                "hostname": "hostname5.domain5",
                "serial_number": "072728a0-223jwd-dwdthw"
            }
            
            Example JSON format for multiple hosts:
            [
                {
                    "ip": "172.19.1.18",
                    "hostname": "hostname5.domain5",
                    "serial_number": "072728a0-223jwd-dwdthw"
                },
                {
                    "ip": "172.19.1.19",
                    "hostname": "hostname6.domain5",
                    "serial_number": "072728a0-223jwd-dwdthx"
                }
            ]
        """
        
        hosts_list = []
        try:
            file_content = file.read()
            hosts_data = json.loads(file_content)
            
            # Handle both single host object and array of hosts
            if isinstance(hosts_data, dict):
                hosts_data = [hosts_data]
            elif not isinstance(hosts_data, list):
                print("Invalid JSON format: Expected object or array of objects")
                raise typer.Exit(1)
            
            for host in hosts_data:
                if not isinstance(host, dict):
                    print("Invalid JSON format: Each entry must be an object")
                    raise typer.Exit(1)
                
                # Validate required fields
                required_fields = ["ip", "hostname", "serial_number"]
                missing_fields = [field for field in required_fields if field not in host]
                
                if missing_fields:
                    print(f"Missing required fields in host entry: {missing_fields}")
                    raise typer.Exit(1)
                
                # Validate IP address format
                if not is_valid_ip(host["ip"]):
                    print(f"Invalid IP address format: {host['ip']}")
                    raise typer.Exit(1)
                
                hosts_list.append({
                    "ip": host["ip"],
                    "hostname": host["hostname"],
                    "serial_number": host["serial_number"]
                })
                
        except json.JSONDecodeError as e:
            print(f"Invalid JSON format in file: {e}")
            raise typer.Exit(1)
        except Exception as e:
            print(f"Error reading file: {e}")
            raise typer.Exit(1)

        if not hosts_list:
            print("No valid host entries to be released")
            raise typer.Exit(1)

        if len(hosts_list) > 100:
            print(
                "Release Limit Exceeded: You attempted to release more than 100 hosts. Please reduce the number and try again."
            )
            raise typer.Exit(1)

        # Release hosts using the new API
        release_hosts_via_api(hosts_list)

    return command

def release_hosts_via_api(hosts_list: list[dict]) -> None:
    """Release hosts using the VMCA deregister API."""
    
    print(f"Releasing {len(hosts_list)} host(s)...")
    
    url = f"{RESERVATION_SERVICE_BASE_URL}/{HOSTS_DEREGISTER_PATH}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Content-Type": "application/json",
    }
    
    try:
        response = requests.post(
            url, headers=headers, json=hosts_list, timeout=30
        )
        response_body = response.json()
    except requests.RequestException as exc:
        print(
            "[ERROR]: Host deregistration API request could not be sent, "
            "please try again."
        )
        raise typer.Exit(1) from exc
    except json.JSONDecodeError as exc:
        print(
            "[ERROR]: Host deregistration API request returned "
            "invalid response."
        )
        raise typer.Exit(1) from exc

    status_code = response.status_code
    
    if status_code == 200:
        # Parse the success response
        status = response_body.get("body", {}).get("status")
        message = response_body.get("body", {}).get("message", "No response message provided")
        
        if status == "success":
            print(f"[SUCCESS] {message}")
        else:
            print(f"[ERROR]: {message}")
            raise typer.Exit(1)
    else:
        # Handle error responses
        error_message = response_body.get("message", "Unknown error occurred")
        print(f"[ERROR {status_code}]: {error_message}")
        raise typer.Exit(1)

def is_valid_ip(ip: str) -> bool:
    """Validate IP address format."""
    import ipaddress
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False
