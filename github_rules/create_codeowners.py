import requests
import base64
import json
import time
import os
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Try YAML support (optional, same as branch_compliance.py)
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

# -----------------------------
# Owners per org
# -----------------------------

TORNADO_OWNERS = [
"@durgadas","@Vishakha-Sawant3","@Tushar-Velingkar2",
"@Jeetendra-Nayak2","@Sankalp-Bhat1","@Yvens-Pinto"
]

VMW_OWNERS = [
"@durgadas","@Shakil-Usgaonker2","@Tushar-Velingkar2",
"@Jeetendra-Nayak2","@Yvens Pinto","@Shruti-Vasudeo2",
"@Siddhi-Borkar2","@Prachi-Kamat4","@Bhushan-Borkar2"
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

        # Skip archived repos
        if archived:
            print(f"    SKIP archived: {name}")
            continue

        # Skip repos with default branch 'main'
        if default_branch == "main":
            print(f"    SKIP default branch 'main': {name}")
            continue

        # Check .metadata on master for production_code
        metadata = fetch_metadata(org, name, "master")
        if not metadata:
            continue

        production_code = str(metadata.get("production_code", "no")).lower()
        if production_code == "yes":
            production_repos.append({"name": name, "default_branch": default_branch})
            print(f"    PRODUCTION: {name}")

    print(f"\n  Found {len(production_repos)} production repos needing CODEOWNERS check\n")
    return production_repos

# -----------------------------
# Detect CODEOWNERS
# -----------------------------

def find_codeowners(org, repo, branch):

    paths = [
        ".github/CODEOWNERS",
        "CODEOWNERS",
        "docs/CODEOWNERS"
    ]

    for path in paths:

        url = f"{GITHUB_BASE}/repos/{org}/{repo}/contents/{path}?ref={branch}"

        resp = session.get(url, verify=False, timeout=20)

        if resp.status_code == 200:
            return path

        if resp.status_code not in (200,404):
            resp.raise_for_status()

        time.sleep(SLEEP_INTERVAL)

    return None

# -----------------------------
# Print helper
# -----------------------------

def print_location(org, repo, branch, path, status):

    full = f"{org}/{repo}/{path}"
    url = f"{GITHUB_WEB}/{org}/{repo}/blob/{branch}/{path}"

    print(f"{status}: {full}")
    print(f"URL: {url}")

# -----------------------------
# Main
# -----------------------------

def main():

    if not GITHUB_TOKEN or not GITHUB_ORG:
        raise Exception("Missing GITHUB_TOKEN or GITHUB_ORG")

    print(f"\nRunning CODEOWNERS check for org: {GITHUB_ORG}\n")

    if GITHUB_ORG == "tornado":
        owners = TORNADO_OWNERS
    elif GITHUB_ORG == "vmwsolutions":
        owners = VMW_OWNERS
    else:
        raise Exception("Unsupported org. Use tornado or vmwsolutions.")

    # Dynamically discover all production repos
    repos = discover_production_repos(GITHUB_ORG)

    created = 0
    existed = 0
    errors = 0

    for repo_info in repos:
        repo = repo_info["name"]
        branch = repo_info["default_branch"]

        path = find_codeowners(GITHUB_ORG, repo, branch)

        if path:
            print_location(GITHUB_ORG, repo, branch, path, "EXISTS")
            existed += 1
            continue

        # Create CODEOWNERS
        content = "* " + " ".join(owners) + "\n"
        url = f"{GITHUB_BASE}/repos/{GITHUB_ORG}/{repo}/contents/.github/CODEOWNERS"
        data = {
            "message": "Add CODEOWNERS for compliance",
            "content": base64.b64encode(content.encode()).decode(),
            "branch": branch
        }
        resp = session.put(url, json=data, verify=False, timeout=20)

        if resp.status_code in (200, 201):
            print_location(GITHUB_ORG, repo, branch, ".github/CODEOWNERS", "CREATED")
            created += 1
        elif resp.status_code == 409:
            path = find_codeowners(GITHUB_ORG, repo, branch)
            if path:
                print_location(GITHUB_ORG, repo, branch, path, "EXISTS (409)")
                existed += 1
            else:
                print(f"CONFLICT: {repo} - 409 but CODEOWNERS not found on '{branch}'")
                errors += 1
        else:
            print(f"ERROR creating CODEOWNERS for {repo}: {resp.status_code}")
            errors += 1

    print(f"\n--- Summary ---")
    print(f"  Production repos found: {len(repos)}")
    print(f"  CODEOWNERS already existed: {existed}")
    print(f"  CODEOWNERS created: {created}")
    print(f"  Errors: {errors}")


if __name__ == "__main__":
    main()
