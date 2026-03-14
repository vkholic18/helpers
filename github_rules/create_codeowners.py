import requests
import base64
import time
import os
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# -------------------------------
# ENV Configuration
# -------------------------------

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_ORG = os.getenv("GITHUB_ORG")

GITHUB_BASE = "https://github.ibm.com/api/v3"
SLEEP_INTERVAL = 0.25

# -------------------------------
# GitHub Client
# -------------------------------

class GitHubAPIClient:

    def __init__(self, base_url, token):

        self.base_url = base_url
        self.session = requests.Session()

        self.session.headers.update({
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        })

    def get(self, endpoint, allow_404=False):

        url = self.base_url + endpoint

        resp = self.session.get(url, verify=False, timeout=20)

        if allow_404 and resp.status_code == 404:
            return None

        resp.raise_for_status()
        return resp.json()

    def put(self, endpoint, data):

        url = self.base_url + endpoint

        resp = self.session.put(url, json=data, verify=False, timeout=20)

        if resp.status_code == 409:
            return None

        resp.raise_for_status()
        return resp.json()


# -------------------------------
# Check CODEOWNERS existence
# -------------------------------

def codeowners_exists(api, org, repo, branch="master"):

    locations = {
        ".github/CODEOWNERS": f"/repos/{org}/{repo}/contents/.github/CODEOWNERS?ref={branch}",
        "root/CODEOWNERS": f"/repos/{org}/{repo}/contents/CODEOWNERS?ref={branch}",
        "docs/CODEOWNERS": f"/repos/{org}/{repo}/contents/docs/CODEOWNERS?ref={branch}",
    }

    for location, endpoint in locations.items():

        result = api.get(endpoint, allow_404=True)

        time.sleep(SLEEP_INTERVAL)

        if result is not None:

            print(f"SKIP: {repo} already has CODEOWNERS at {location}")

            return True

    return False


# -------------------------------
# Create CODEOWNERS
# -------------------------------

def create_codeowners(api, org, repo, owners, branch="master"):

    try:

        if codeowners_exists(api, org, repo, branch):
            return

        content = "* " + " ".join(owners) + "\n"

        encoded_content = base64.b64encode(content.encode()).decode()

        endpoint = f"/repos/{org}/{repo}/contents/.github/CODEOWNERS"

        data = {
            "message": "Add CODEOWNERS file for compliance",
            "content": encoded_content,
            "branch": branch
        }

        resp = api.put(endpoint, data)

        if resp and resp.get("content"):

            print(f"SUCCESS: Created CODEOWNERS for {repo} in .github/")

        else:

            print(f"FAILED: Could not create CODEOWNERS for {repo}")

    except requests.exceptions.HTTPError as e:

        if e.response.status_code == 404:

            print(f"ERROR: Repo not found -> {repo}")

        else:

            print(f"ERROR: {repo} -> {e}")


# -------------------------------
# Example repo list
# -------------------------------

REPOS = [
    "common-utils",
    "build-ci",
    "bootstrap",
]

OWNERS = [
    "@durgadas",
    "@Vishakha-Sawant3",
    "@Tushar-Velingkar2",
    "@Jeetendra-Nayak2",
    "@Sankalp-Bhat1",
    "@Yvens Pinto"
]

# -------------------------------
# Main
# -------------------------------

def main():

    if not GITHUB_TOKEN or not GITHUB_ORG:

        raise Exception("Missing ENV variables: GITHUB_TOKEN or GITHUB_ORG")

    api = GitHubAPIClient(GITHUB_BASE, GITHUB_TOKEN)

    print(f"\nRunning CODEOWNERS automation for org: {GITHUB_ORG}\n")

    for repo in REPOS:

        create_codeowners(api, GITHUB_ORG, repo, OWNERS)


if __name__ == "__main__":
    main()
