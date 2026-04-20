"""
================================================================================
FIX METADATA SCRIPT — VMWSolutions Org
================================================================================

Adds a .metadata file to VMWSolutions repositories that are missing it.
All repos in this list are ARCHIVED, so the workflow is:
  unarchive → add .metadata → re-archive

HOW TO RUN:
    1. Set environment variables:
       - GITHUB_TOKEN: Your GitHub personal access token
       - GITHUB_BASE:  GitHub API base URL (e.g., https://github.ibm.com/api/v3)

    2. Dry-run (no changes made):
         python fix_metadata_vmwsolutions.py --dry-run

    3. Apply changes:
         python fix_metadata_vmwsolutions.py

    4. Single repo (test first):
         python fix_metadata_vmwsolutions.py --repo ic4v-micro-service-example --dry-run
         python fix_metadata_vmwsolutions.py --repo ic4v-micro-service-example

OUTPUT:
    - fix_metadata_vmwsolutions_log_<timestamp>.json   (per-repo result log)

NOTES:
    - If .metadata already exists (HTTP 422/409), repo is skipped.
    - Archived repos are re-archived even if .metadata creation fails,
      so the repo is never left unarchived accidentally.
================================================================================
"""

import os
import sys
import json
import time
import base64
import argparse
import requests
import urllib3
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =============================================================================
# CONFIGURATION
# =============================================================================

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_BASE  = os.environ.get("GITHUB_BASE", "https://api.github.com")
GITHUB_ORG   = "VMWSolutions"

SLEEP_INTERVAL = 0.3   # seconds between API calls

# .metadata content for VMWSolutions Non-Prod repos
METADATA_CONTENT = {
    "service": "vmware",
    "production_code": "no",
    "security_sensitive": "no",
    "ip_sensitive": "no",
    "allow_cloud_readers": "yes"
}

# -----------------------------------------------------------------------------
# Repos that are ARCHIVED — unarchive → add .metadata → re-archive
# -----------------------------------------------------------------------------
ARCHIVED_REPOS = [
    "ic4v-micro-service-example",
    "ic4v-micro-service-test",
    "tekton-ms-example",
    "ic4v-library-example",
    "NG-terraform-templates",
    "IC4V-Dependencies",
    "NG-oneCloud",
    "ic4v-mzr-pipeline-defs",
    "ic4v-ghost",
    "solution-tutorials",
    "ic4v-console-e2e",
    "tekton-toolchain-template",
    "ic4v-auto-infra-epics",
    "vsan-sdk-python",
    "vmware-go-sdk",
    "ic4v-architecture-description",
    "vmware-managed-stress",
    "vmwaas-sf-rev-20221114",
    "SF-MultiTenant-2023",
    "onepipeline-compliance-evidence-locker-2023Apirl-2023Sep",
    "SF-SingleTenant-PriceChange-2023",
    "SF-license-feature",
    "ic4v-billing-reconciliation",
    "security-scans-config-bak",
    "vcd-log-provider-poc",
]

# -----------------------------------------------------------------------------
# Repos that are ACTIVE (not archived):
#   - validation_error: .metadata exists but invalid → overwrite it
#   - missing:          .metadata does not exist    → create it
# -----------------------------------------------------------------------------
ACTIVE_REPOS = [
    # validation_error — .metadata exists but wrong content
    "ic4v-workload-domain",
    "common-automation",
    "ic4v-vcf-vpc",
    "ic4v-addon-lifecycle",
    "ic4v-addon-billing",
    "billing-operations",
    "security-scans-config",
    "helm-properties",
    "vra-salt",
    # missing — .metadata does not exist
    "Vmware-terraform",
    "ic4v-vmca-registration-service",
    "tf-sdn-automation",
    "security-compliance",
]


# =============================================================================
# GITHUB API CLIENT
# =============================================================================

class GitHubAPIClient:
    def __init__(self, base_url, token):
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }

    def get(self, endpoint, allow_404=False):
        url = f"{self.base_url}{endpoint}"
        response = requests.get(url, headers=self.headers, verify=False)
        if response.status_code == 404 and allow_404:
            return None
        response.raise_for_status()
        return response.json()

    def patch(self, endpoint, data):
        url = f"{self.base_url}{endpoint}"
        response = requests.patch(url, headers=self.headers, json=data, verify=False)
        response.raise_for_status()
        return response.json() if response.text else {}

    def put(self, endpoint, data):
        url = f"{self.base_url}{endpoint}"
        response = requests.put(url, headers=self.headers, json=data, verify=False)
        return response  # caller checks status code


# =============================================================================
# CORE HELPERS
# =============================================================================

def get_default_branch(api, repo_name):
    """Return the default branch of a repo, or None if not found."""
    repo_data = api.get(f"/repos/{GITHUB_ORG}/{repo_name}", allow_404=True)
    time.sleep(SLEEP_INTERVAL)
    if not repo_data:
        return None
    return repo_data.get("default_branch", "master")


def get_metadata_sha(api, repo_name, branch):
    """Return the sha of the existing .metadata file, or None if it doesn't exist."""
    result = api.get(
        f"/repos/{GITHUB_ORG}/{repo_name}/contents/.metadata?ref={branch}",
        allow_404=True,
    )
    time.sleep(SLEEP_INTERVAL)
    if result is None:
        return None
    return result.get("sha")


def add_metadata(api, repo_name, branch, dry_run, sha=None):
    """
    PUT .metadata onto the repo. If sha is provided, overwrites the existing file.

    Returns a dict:
      {"success": True/False, "skipped": True/False, "reason": str}
    """
    action = "update" if sha else "create"
    if dry_run:
        return {"success": True, "skipped": False, "reason": f"(dry-run) would {action} .metadata"}

    encoded = base64.b64encode(
        json.dumps(METADATA_CONTENT, indent=2).encode("utf-8")
    ).decode("utf-8")

    payload = {
        "message": "Add .metadata file for compliance" if not sha else "Update .metadata file for compliance",
        "content": encoded,
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha

    response = api.put(
        f"/repos/{GITHUB_ORG}/{repo_name}/contents/.metadata", payload
    )
    time.sleep(SLEEP_INTERVAL)

    if response.status_code in (200, 201):
        verb = "updated" if sha else "created"
        return {"success": True, "skipped": False, "reason": f".metadata {verb} successfully"}

    if response.status_code in (409, 422):
        return {"success": True, "skipped": True, "reason": ".metadata already exists — skipped (use sha to overwrite)"}

    try:
        msg = response.json().get("message", response.text)
    except Exception:
        msg = response.text
    return {"success": False, "skipped": False, "reason": f"HTTP {response.status_code}: {msg}"}


def set_archived(api, repo_name, archived, dry_run):
    """Archive or unarchive a repo. Returns True on success."""
    action = "archive" if archived else "unarchive"
    if dry_run:
        print(f"      (dry-run) would {action} {repo_name}")
        return True
    try:
        api.patch(f"/repos/{GITHUB_ORG}/{repo_name}", {"archived": archived})
        time.sleep(SLEEP_INTERVAL)
        return True
    except requests.exceptions.HTTPError as e:
        print(f"      ERROR {action} {repo_name}: {e}")
        return False


# =============================================================================
# PER-REPO WORKFLOWS
# =============================================================================

def process_active_repo(api, repo_name, dry_run):
    """
    Workflow for a non-archived repo:
      - If .metadata exists (validation_error): fetch sha → overwrite
      - If .metadata missing:                   create fresh
    """
    result = {
        "repo": repo_name,
        "was_archived": False,
        "unarchived": False,
        "metadata_added": False,
        "metadata_skipped": False,
        "re_archived": False,
        "error": None,
    }

    print(f"\n  [{repo_name}] (active)")

    branch = get_default_branch(api, repo_name)
    if branch is None:
        msg = "repo not found (404)"
        print(f"    SKIP: {msg}")
        result["error"] = msg
        return result

    print(f"    default branch: {branch}")

    # Check if .metadata already exists and get its sha for overwrite
    sha = get_metadata_sha(api, repo_name, branch)
    if sha:
        print(f"    .metadata exists (sha: {sha[:7]}...) — will overwrite")
    else:
        print(f"    .metadata missing — will create")

    meta_result = add_metadata(api, repo_name, branch, dry_run, sha=sha)
    result["metadata_added"]   = meta_result["success"] and not meta_result["skipped"]
    result["metadata_skipped"] = meta_result["skipped"]
    if not meta_result["success"]:
        result["error"] = meta_result["reason"]
        print(f"    FAILED — {meta_result['reason']}")
    else:
        print(f"    {meta_result['reason']}")

    return result


def process_archived_repo(api, repo_name, dry_run):
    """
    Workflow:
      1. Unarchive
      2. Add .metadata
      3. Re-archive (always, even on .metadata failure)
    """
    result = {
        "repo": repo_name,
        "was_archived": True,
        "unarchived": False,
        "metadata_added": False,
        "metadata_skipped": False,
        "re_archived": False,
        "error": None,
    }

    print(f"\n  [{repo_name}]")

    # Confirm repo exists and get default branch
    branch = get_default_branch(api, repo_name)
    if branch is None:
        msg = "repo not found (404)"
        print(f"    SKIP: {msg}")
        result["error"] = msg
        return result

    print(f"    default branch: {branch}")

    # Step 1: Unarchive
    print(f"    Step 1: unarchiving...")
    ok = set_archived(api, repo_name, archived=False, dry_run=dry_run)
    result["unarchived"] = ok
    if not ok:
        result["error"] = "failed to unarchive"
        return result
    print(f"    Step 1: {'(dry-run) unarchive OK' if dry_run else 'unarchived OK'}")

    # Step 2: Add .metadata
    print(f"    Step 2: adding .metadata...")
    meta_result = add_metadata(api, repo_name, branch, dry_run)
    result["metadata_added"]   = meta_result["success"] and not meta_result["skipped"]
    result["metadata_skipped"] = meta_result["skipped"]
    if not meta_result["success"]:
        result["error"] = meta_result["reason"]
        print(f"    Step 2: FAILED — {meta_result['reason']}")
    else:
        print(f"    Step 2: {meta_result['reason']}")

    # Step 3: Re-archive (always)
    print(f"    Step 3: re-archiving...")
    re_ok = set_archived(api, repo_name, archived=True, dry_run=dry_run)
    result["re_archived"] = re_ok
    if not re_ok:
        result["error"] = (result["error"] or "") + " | failed to re-archive"
        print(f"    Step 3: FAILED to re-archive")
    else:
        print(f"    Step 3: {'(dry-run) re-archive OK' if dry_run else 're-archived OK'}")

    return result


# =============================================================================
# MAIN
# =============================================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="Add .metadata to VMWSolutions repos that are missing it.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python fix_metadata_vmwsolutions.py --dry-run                          Preview all changes
  python fix_metadata_vmwsolutions.py                                    Apply all changes
  python fix_metadata_vmwsolutions.py --repo ic4v-micro-service-example  Single repo only
        """,
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview actions without making any API changes",
    )
    parser.add_argument(
        "--repo",
        metavar="REPO_NAME",
        help="Process a single repository (for testing)",
    )
    parser.add_argument(
        "--active-only",
        action="store_true",
        help="Process only active (non-archived) repos",
    )
    parser.add_argument(
        "--archived-only",
        action="store_true",
        help="Process only archived repos",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    print("\n" + "=" * 60)
    print("FIX METADATA SCRIPT — VMWSolutions Org")
    print("=" * 60)

    if not GITHUB_TOKEN:
        print("ERROR: GITHUB_TOKEN environment variable is not set.")
        sys.exit(1)

    print(f"  Organization : {GITHUB_ORG}")
    print(f"  API Base URL : {GITHUB_BASE}")
    print(f"  Dry-run      : {args.dry_run}")
    if args.repo:
        print(f"  Target repo  : {args.repo}")

    if args.dry_run:
        print("\n  *** DRY-RUN MODE — no changes will be made ***")

    api = GitHubAPIClient(GITHUB_BASE, GITHUB_TOKEN)

    # Build work list
    if args.repo:
        if args.repo in ARCHIVED_REPOS:
            archived_work = [args.repo]
            active_work   = []
        elif args.repo in ACTIVE_REPOS:
            archived_work = []
            active_work   = [args.repo]
        else:
            print(f"\n  ERROR: '{args.repo}' is not in ARCHIVED_REPOS or ACTIVE_REPOS list.")
            sys.exit(1)
    else:
        archived_work = [] if args.active_only  else ARCHIVED_REPOS
        active_work   = [] if args.archived_only else ACTIVE_REPOS

    print(f"\n  Repos to process : {len(archived_work) + len(active_work)}")
    print(f"    Archived         : {len(archived_work)}")
    print(f"    Active           : {len(active_work)}")

    all_results = []

    if archived_work:
        print("\n" + "-" * 40)
        print(f"ARCHIVED REPOS ({len(archived_work)})")
        print("-" * 40)
        for repo_name in archived_work:
            result = process_archived_repo(api, repo_name, dry_run=args.dry_run)
            all_results.append(result)

    if active_work:
        print("\n" + "-" * 40)
        print(f"ACTIVE REPOS ({len(active_work)})")
        print("-" * 40)
        for repo_name in active_work:
            result = process_active_repo(api, repo_name, dry_run=args.dry_run)
            all_results.append(result)

    # Summary
    added   = sum(1 for r in all_results if r["metadata_added"])
    skipped = sum(1 for r in all_results if r["metadata_skipped"])
    failed  = sum(1 for r in all_results if r["error"] and not r["metadata_skipped"])

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Total repos processed : {len(all_results)}")
    print(f"  .metadata added       : {added}")
    print(f"  .metadata skipped     : {skipped}  (already existed)")
    print(f"  Errors                : {failed}")

    if args.dry_run:
        print("\n  *** DRY-RUN — no actual changes were made ***")

    # Save log
    log_file = f"fix_metadata_vmwsolutions_log_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.json"
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": datetime.now().isoformat(),
                "organization": GITHUB_ORG,
                "dry_run": args.dry_run,
                "summary": {
                    "total": len(all_results),
                    "metadata_added": added,
                    "metadata_skipped": skipped,
                    "errors": failed,
                },
                "results": all_results,
            },
            f,
            indent=2,
        )
    print(f"\n  Log saved: {log_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()
