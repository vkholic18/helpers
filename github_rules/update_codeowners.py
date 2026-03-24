"""
================================================================================
UPDATE CODEOWNERS FILE CONTENT
================================================================================
Updates the content of existing CODEOWNERS files in all production repositories
with the corrected code reviewer names.

HOW TO RUN:
    export GITHUB_TOKEN=<your-token>
    export GITHUB_ORG=tornado        # or vmwsolutions
    python update_codeowners.py
================================================================================
"""

import requests
import base64
import json
import time
import os
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

# -----------------------------
# Updated owners per org
# -----------------------------

TORNADO_OWNERS = [
    "@Kamath-Durgadas", "@Vishakha-Sawant3", "@Tushar-Velingkar2",
    "@Jeetendra-Nayak2", "@Sankalp-Bhat1", "@Shail-Kumari",
    "@Avinash-Boini", "@Pinto-Yvens"
]

VMW_OWNERS = [
    "@Kamath-Durgadas", "@Shakil-Usgaonker2", "@Tushar-Velingkar2",
    "@Jeetendra-Nayak2", "@Pinto-Yvens", "@Shruti-Vasudeo2",
    "@Siddhi-Borkar2", "@Prachi-Kamat4", "@Bhushan-Borkar2"
]

# -----------------------------
# ENV
# -----------------------------

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_ORG = os.getenv("GITHUB_ORG")

GITHUB_BASE = "https://github.ibm.com/api/v3"
GITHUB_WEB = "https://github.ibm.com"

SLEEP_INTERVAL = 0.2

# -----------------------------
# GitHub Client
# -----------------------------

session = requests.Session()
session.headers.update({
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
})

# -----------------------------
# Pagination helper
# -----------------------------

def paginate(url):
    results = []
    while url:
        resp = session.get(url, verify=False, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            results.extend(data)
        else:
            results.append(data)
        url = None
        link_header = resp.headers.get("Link", "")
        for link in link_header.split(","):
            if 'rel="next"' in link:
                url = link.split(";")[0].strip()[1:-1]
                break
        time.sleep(SLEEP_INTERVAL)
    return results

# -----------------------------
# Fetch .metadata
# -----------------------------

def fetch_metadata(org, repo, branch):
    url = f"{GITHUB_BASE}/repos/{org}/{repo}/contents/.metadata?ref={branch}"
    resp = session.get(url, verify=False, timeout=20)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    try:
        content = base64.b64decode(resp.json().get("content", "")).decode("utf-8")
        if YAML_AVAILABLE:
            try:
                return yaml.safe_load(content)
            except:
                pass
        return json.loads(content)
    except:
        return None

# -----------------------------
# Discover production repos
# -----------------------------

def discover_production_repos(org):
    print(f"  Fetching all repos from '{org}'...")
    all_repos = paginate(f"{GITHUB_BASE}/orgs/{org}/repos?per_page=100")
    print(f"  Found {len(all_repos)} total repos")

    production_repos = []
    for repo_data in all_repos:
        name = repo_data["name"]
        default_branch = repo_data.get("default_branch", "master")
        archived = repo_data.get("archived", False)

        if archived:
            print(f"    SKIPPED (archived): {name}")
            continue

        if default_branch == "main":
            continue

        metadata = fetch_metadata(org, name, "master")
        if not metadata:
            continue

        production_code = str(metadata.get("production_code", "no")).lower()
        if production_code == "yes":
            production_repos.append({"name": name, "default_branch": default_branch})
            print(f"    PRODUCTION: {name}")

    print(f"\n  Found {len(production_repos)} production repos\n")
    return production_repos

# -----------------------------
# Find CODEOWNERS and get SHA
# -----------------------------

def find_codeowners_with_sha(org, repo, branch):
    """Find CODEOWNERS file and return its path and SHA (needed for update)."""
    paths = [
        ".github/CODEOWNERS",
        "CODEOWNERS",
        "docs/CODEOWNERS"
    ]
    for path in paths:
        url = f"{GITHUB_BASE}/repos/{org}/{repo}/contents/{path}?ref={branch}"
        resp = session.get(url, verify=False, timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            return path, data.get("sha")
        time.sleep(SLEEP_INTERVAL)
    return None, None

# -----------------------------
# Main
# -----------------------------

def main():
    if not GITHUB_TOKEN or not GITHUB_ORG:
        raise Exception("Missing GITHUB_TOKEN or GITHUB_ORG")

    print(f"\nUpdating CODEOWNERS for org: {GITHUB_ORG}\n")

    if GITHUB_ORG == "tornado":
        owners = TORNADO_OWNERS
    elif GITHUB_ORG == "vmwsolutions":
        owners = VMW_OWNERS
    else:
        raise Exception("Unsupported org. Use tornado or vmwsolutions.")

    new_content = "* " + " ".join(owners) + "\n"
    encoded_content = base64.b64encode(new_content.encode()).decode()

    repos = discover_production_repos(GITHUB_ORG)

    updated = 0
    not_found = 0
    skipped_protected = 0
    errors = 0

    for repo_info in repos:
        repo = repo_info["name"]
        branch = repo_info["default_branch"]

        path, sha = find_codeowners_with_sha(GITHUB_ORG, repo, branch)

        if not path or not sha:
            print(f"  NOT FOUND: {repo} - no CODEOWNERS file")
            not_found += 1
            continue

        # Update the file using PUT with the SHA
        url = f"{GITHUB_BASE}/repos/{GITHUB_ORG}/{repo}/contents/{path}"
        data = {
            "message": "Update CODEOWNERS with corrected reviewer names",
            "content": encoded_content,
            "sha": sha,
            "branch": branch
        }

        resp = session.put(url, json=data, verify=False, timeout=20)

        if resp.status_code in (200, 201):
            print(f"  UPDATED: {repo}/{path}")
            print(f"    URL: {GITHUB_WEB}/{GITHUB_ORG}/{repo}/blob/{branch}/{path}")
            updated += 1
        elif resp.status_code == 409:
            print(f"  SKIPPED (409 conflict): {repo}/{path} - branch is protected, run this script BEFORE applying branch protection")
            skipped_protected += 1
        else:
            print(f"  ERROR: {repo}/{path} - HTTP {resp.status_code}")
            errors += 1

        time.sleep(SLEEP_INTERVAL)

    print(f"\n--- Summary ---")
    print(f"  Production repos found: {len(repos)}")
    print(f"  CODEOWNERS updated: {updated}")
    print(f"  CODEOWNERS not found: {not_found}")
    print(f"  Skipped (409 - branch protected): {skipped_protected}")
    print(f"  Errors: {errors}")


if __name__ == "__main__":
    main()
