from typing import List, Tuple
from box_sdk_gen import BoxClient, BoxCCGAuth, CCGConfig


# =========================
# HARD-CODED CONFIG VALUES
# =========================
BOX_CLIENT_ID = "YOUR_CLIENT_ID"
BOX_CLIENT_SECRET = "YOUR_CLIENT_SECRET"
ENTERPRISE_ID = "YOUR_ENTERPRISE_ID"

# Optional: set this later after listing folders
BOX_FOLDER_DALST = ""   # keep empty initially


# =========================
# CUSTOM EXCEPTIONS
# =========================
class BoxAuthenticationError(Exception):
    pass


class InventoryFileNotFoundError(Exception):
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
# LIST FOLDERS
# =========================
def list_folders(folder_id: str, client: BoxClient) -> List[Tuple[str, str]]:
    """
    Returns list of (folder_id, folder_name)
    """
    items = client.folders.get_folder_items(folder_id, limit=1000)
    return [
        (item.id, item.name)
        for item in items.entries
        if item.type == "folder"
    ]


# =========================
# MAIN EXECUTION
# =========================
def main():
    client = box_auth(
        BOX_CLIENT_ID,
        BOX_CLIENT_SECRET,
        ENTERPRISE_ID,
    )

    # 1️⃣ List folders in ROOT
    print("Available folders in ROOT:")
    root_folders = list_folders("0", client)

    for folder_id, folder_name in root_folders:
        print(f"📁 {folder_name}  (ID: {folder_id})")

    # 2️⃣ If folder ID is provided, list files
    if BOX_FOLDER_DALST:
        print("\nFiles in selected folder:")
        files = list_files_in_folder(BOX_FOLDER_DALST, client)

        if not files:
            raise InventoryFileNotFoundError("No files found in the Box folder")

        for file_name in files:
            print(f"- {file_name}")
    else:
        print("\n⚠️ BOX_FOLDER_DALST is empty. Set folder ID to list files.")


if __name__ == "__main__":
    main()
