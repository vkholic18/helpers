"""
================================================================================
CREATE CODEOWNERS — Specific Repos
================================================================================

Creates CODEOWNERS files for specific repos that are missing them.

Repos:
  - tornado/secretsmanager-utils
  - tornado/vcd-metering-reconciliation-patch

HOW TO RUN:
    1. Set environment variables:
       - GITHUB_TOKEN: Your GitHub personal access token

    2. Dry-run (no changes):
         python create_codeowners_specific.py --dry-run

    3. Apply:
         python create_codeowners_specific.py

    4. Single repo:
         python create_codeowners_specific.py --repo secretsmanager-utils
================================================================================
"""

import os
import sys
import base64
import argparse
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =============================================================================
# CONFIGURATION
# =============================================================================

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_BASE  = "https://github.ibm.com/api/v3"
GITHUB_WEB   = "https://github.ibm.com"
GITHUB_ORG   = "tornado"

# CODEOWNERS content — wildcard rule covering all files
OWNERS = [
    "@Kamath-Durgadas",
    "@Vishakha-Sawant3",
    "@Tushar-Velingkar2",
    "@Jeetendra-Nayak2",
    "@Sankalp-Bhat1",
    "@Shail-Kumari",
    "@Avinash-Boini",
    "@Pinto-Yvens",
]
CODEOWNERS_CONTENT = "* " + " ".join(OWNERS) + "\n"

# Repos to process
TARGET_REPOS = [
    "secretsmanager-utils",
    "vcd-metering-reconciliation-patch",
]


# =============================================================================
# GITHUB SESSION
# =============================================================================

session = requests.Session()
session.headers.update({
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
})


# =============================================================================
# HELPERS
# =============================================================================

def get_repo_info(repo_name):
    """Fetch repo metadata. Returns dict or None if not found."""
    url = f"{GITHUB_BASE}/repos/{GITHUB_ORG}/{repo_name}"
    resp = session.get(url, verify=False, timeout=20)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def find_codeowners(repo_name, branch):
    """Return the path of existing CODEOWNERS file, or None."""
    for path in [".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"]:
        url = f"{GITHUB_BASE}/repos/{GITHUB_ORG}/{repo_name}/contents/{path}?ref={branch}"
        resp = session.get(url, verify=False, timeout=20)
        if resp.status_code == 200:
            return path
        if resp.status_code not in (200, 404):
            resp.raise_for_status()
    return None


def get_codeowners_sha(repo_name, branch, path):
    """Return the sha of an existing CODEOWNERS file at path, or None."""
    url = f"{GITHUB_BASE}/repos/{GITHUB_ORG}/{repo_name}/contents/{path}?ref={branch}"
    resp = session.get(url, verify=False, timeout=20)
    if resp.status_code == 200:
        return resp.json().get("sha")
    return None


def create_codeowners(repo_name, branch, dry_run):
    """
    Create .github/CODEOWNERS (falls back to root CODEOWNERS).
    On 409 (file exists but sha check missed it), fetches sha and retries as update.

    Returns:
        dict: {"success": bool, "path": str, "reason": str}
    """
    encoded = base64.b64encode(CODEOWNERS_CONTENT.encode()).decode()

    if dry_run:
        return {"success": True, "path": ".github/CODEOWNERS", "reason": "(dry-run) would create .github/CODEOWNERS"}

    for path, msg in [
        (".github/CODEOWNERS", "Add CODEOWNERS for compliance"),
        ("CODEOWNERS",         "Add CODEOWNERS for compliance (root)"),
    ]:
        url = f"{GITHUB_BASE}/repos/{GITHUB_ORG}/{repo_name}/contents/{path}"
        payload = {"message": msg, "content": encoded, "branch": branch}

        resp = session.put(url, json=payload, verify=False, timeout=20)

        if resp.status_code in (200, 201):
            return {"success": True, "path": path, "reason": f"created {path}"}

        if resp.status_code == 409:
            # File exists but wasn't found by earlier GET — fetch sha and overwrite
            print(f"    409 on {path} — fetching sha and retrying as update...")
            sha = get_codeowners_sha(repo_name, branch, path)
            if sha:
                payload["sha"] = sha
                payload["message"] = msg.replace("Add", "Update")
                resp2 = session.put(url, json=payload, verify=False, timeout=20)
                if resp2.status_code in (200, 201):
                    return {"success": True, "path": path, "reason": f"updated {path} (already existed)"}
                try:
                    err = resp2.json().get("message", resp2.text)
                except Exception:
                    err = resp2.text
                return {"success": False, "path": None, "reason": f"update failed HTTP {resp2.status_code}: {err}"}
            # sha not found either — try next path
            continue

        # Any other error — report it
        try:
            err = resp.json().get("message", resp.text)
        except Exception:
            err = resp.text
        return {"success": False, "path": None, "reason": f"HTTP {resp.status_code}: {err}"}

    return {"success": False, "path": None, "reason": "both .github/CODEOWNERS and root CODEOWNERS failed"}


# =============================================================================
# MAIN
# =============================================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="Create CODEOWNERS for specific tornado repos.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python create_codeowners_specific.py --dry-run
  python create_codeowners_specific.py
  python create_codeowners_specific.py --repo secretsmanager-utils
        """,
    )
    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="Preview without making changes")
    parser.add_argument("--repo", metavar="REPO_NAME",
                        help="Process a single repo only")
    return parser.parse_args()


def main():
    args = parse_args()

    print("\n" + "=" * 60)
    print("CREATE CODEOWNERS — Specific Repos")
    print("=" * 60)

    if not GITHUB_TOKEN:
        print("ERROR: GITHUB_TOKEN environment variable is not set.")
        sys.exit(1)

    print(f"  Organization : {GITHUB_ORG}")
    print(f"  Dry-run      : {args.dry_run}")

    if args.dry_run:
        print("\n  *** DRY-RUN MODE — no changes will be made ***")

    print(f"\n  CODEOWNERS content:")
    print(f"    {CODEOWNERS_CONTENT.strip()}")

    work_list = [args.repo] if args.repo else TARGET_REPOS

    if args.repo and args.repo not in TARGET_REPOS:
        print(f"\n  WARNING: '{args.repo}' is not in the TARGET_REPOS list — proceeding anyway.")

    print(f"\n  Repos to process : {len(work_list)}")
    print("\n" + "-" * 40)

    created = 0
    existed = 0
    errors  = 0

    for repo_name in work_list:
        print(f"\n  [{repo_name}]")

        # Fetch repo info
        repo_data = get_repo_info(repo_name)
        if not repo_data:
            print(f"    ERROR: repo not found (404)")
            errors += 1
            continue

        branch = repo_data.get("default_branch", "master")
        archived = repo_data.get("archived", False)
        print(f"    default branch : {branch}")
        print(f"    archived       : {archived}")

        if archived:
            print(f"    WARNING: repo is archived — CODEOWNERS cannot be created on archived repos")
            errors += 1
            continue

        # Check if CODEOWNERS already exists
        existing_path = find_codeowners(repo_name, branch)
        if existing_path:
            print(f"    CODEOWNERS already exists: {existing_path}")
            print(f"    URL: {GITHUB_WEB}/{GITHUB_ORG}/{repo_name}/blob/{branch}/{existing_path}")
            existed += 1
            continue

        # Create it
        result = create_codeowners(repo_name, branch, dry_run=args.dry_run)
        if result["success"]:
            print(f"    OK: {result['reason']}")
            print(f"    URL: {GITHUB_WEB}/{GITHUB_ORG}/{repo_name}/blob/{branch}/{result['path']}")
            created += 1
        else:
            print(f"    ERROR: {result['reason']}")
            errors += 1

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Repos processed          : {len(work_list)}")
    print(f"  CODEOWNERS already existed: {existed}")
    print(f"  CODEOWNERS created       : {created}")
    print(f"  Errors                   : {errors}")

    if args.dry_run:
        print("\n  *** DRY-RUN — no actual changes were made ***")
    print("=" * 60)


if __name__ == "__main__":
    main()
