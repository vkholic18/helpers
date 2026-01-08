from typing import List
from box_sdk_gen import BoxClient, BoxCCGAuth, CCGConfig


# =========================
# HARD-CODED CONFIG VALUES
# =========================
BOX_CLIENT_ID = "YOUR_CLIENT_ID"
BOX_CLIENT_SECRET = "YOUR_CLIENT_SECRET"
ENTERPRISE_ID = "YOUR_ENTERPRISE_ID"
BOX_FOLDER_DALST = "YOUR_FOLDER_ID"


# =========================
# CUSTOM EXCEPTIONS
# =========================
class BoxAuthenticationError(Exception):
    """Raised when Box authentication fails."""
    pass


class InventoryFileNotFoundError(Exception):
    """Raised when a required file is not found."""
    pass


# =========================
# BOX AUTHENTICATION
# =========================
def box_auth(client_id: str, client_secret: str, enterprise_id: str) -> BoxClient:
    if not all([client_id, client_secret, enterprise_id]):
        raise BoxAuthenticationError("Missing required Box credentials")

    try:
        ccg_config = CCGConfig(
            client_id=client_id,
            client_secret=client_secret,
            enterprise_id=enterprise_id,
        )
        auth = BoxCCGAuth(config=ccg_config)
        return BoxClient(auth)
    except Exception as e:
        raise BoxAuthenticationError(f"Box authentication failed: {e}") from e


# =========================
# LIST FILES IN FOLDER
# =========================
def list_files_in_folder(folder_id: str, client: BoxClient) -> List[str]:
    items = client.folders.get_folder_items(folder_id, limit=1000)
    return [item.name for item in items.entries if item.type == "file"]


# =========================
# MAIN EXECUTION
# =========================
def main():
    client = box_auth(
        client_id=BOX_CLIENT_ID,
        client_secret=BOX_CLIENT_SECRET,
        enterprise_id=ENTERPRISE_ID,
    )

    files = list_files_in_folder(BOX_FOLDER_DALST, client)

    if not files:
        raise InventoryFileNotFoundError("No files found in the Box folder")

    print("Files in Box folder:")
    for file_name in files:
        print(f"- {file_name}")


if __name__ == "__main__":
    main()
