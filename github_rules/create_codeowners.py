import requests
import base64
import time
import os
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# -------------------------------
# Repo Lists
# -------------------------------

TORNADO_REPOS = [
    "common-utils","build-ci","bootstrap","console","service-framework","service-implementations",
    "devops","mgmt-comm","mgmt-event","kmipadapter","kmipmgmt","service-broker","k8s-deploy",
    "mgmt-cos","vcd-mgmt-api","vcd-mgmt-job","mgmt-metering","vcd-bin-vdbc","vcd-tracking-service",
    "atlas-dashboard","vcd-mgmt-db","vcd-billing-service","vcd-billing-job","vcd-mgmt-e2e",
    "skytap-console","vcd-mgmt-veeam","mgmt-mq","images","schematics","mgmt-sysdig",
    "vcd-mgmt-scheduler","ic4v-golang-sdk","ic4v-java-sdk","vcd-metrics-collector","ic4v-node-sdk",
    "metrics-ingestor","managed-portal-and-billing-team","vcd-iaas-vra","vcd-vrealize-webhook",
    "UX-Design","console_scan","vpc-msql","istio-egress-control","svt-automation-ui",
    "VRA-G1-FRA-PRD","VRA-G1-DAL-PRD","VRA-G1-PAR-PRD","ipops-vcd-cases","evidence_locker",
    "secretsmanager-utils","IC4V-lifecycle-image","per-core-licensing","monitoring",
    "vcd-metering-reconciliation-patch","vcd-iaas-vro-g2","vcd-iaas-vro-g1",
    "credreconcileresults","agent-configs","common-scripts","core-helper-scripts",
    "ci-pipeline-defs"
]

TORNADO_OWNERS = [
    "@durgadas","@Vishakha-Sawant3","@Tushar-Velingkar2",
    "@Jeetendra-Nayak2","@Sankalp-Bhat1","@Yvens Pinto"
]

VMW_REPOS = [
    "ic4v-flask-lib","ic4v-sddc","ic4v-sqlalchemy-lib","roks-configs",
    "ic4v-iaas","ic4v-vmware-cloud-director","ic4v-iaas-vhost","ic4v-data",
    "atlas-dashboard","ic4v-vdc-lifecycle","vpc-vmware-terraform","ic4v-update-vcd"
]

VMW_OWNERS = [
    "@durgadas","@Shakil-Usgaonker2","@Tushar-Velingkar2",
    "@Jeetendra-Nayak2","@Yvens Pinto","@Shruti-Vasudeo2",
    "@Siddhi-Borkar2","@Prachi-Kamat4","@Bhushan-Borkar2"
]

# -------------------------------
# ENV Configuration
# -------------------------------

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_ORG = os.getenv("GITHUB_ORG")

GITHUB_BASE = "https://github.ibm.com/api/v3"
GITHUB_WEB = "https://github.ibm.com"

SLEEP_INTERVAL = 0.3


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

        resp = self.session.get(url, verify=False)

        if allow_404 and resp.status_code == 404:
            return None

        resp.raise_for_status()

        return resp.json()


    def put(self, endpoint, data):

        url = self.base_url + endpoint

        resp = self.session.put(url, json=data, verify=False)

        if resp.status_code == 409:
            return None

        resp.raise_for_status()

        return resp.json()


# -------------------------------
# Check CODEOWNERS existence
# -------------------------------

def codeowners_exists(api, org, repo, branch="master"):

    locations = [
        f"/repos/{org}/{repo}/contents/.github/CODEOWNERS?ref={branch}",
        f"/repos/{org}/{repo}/contents/CODEOWNERS?ref={branch}",
        f"/repos/{org}/{repo}/contents/docs/CODEOWNERS?ref={branch}",
    ]

    for endpoint in locations:

        result = api.get(endpoint, allow_404=True)

        time.sleep(SLEEP_INTERVAL)

        if result is not None:

            file_path = result.get("path", "unknown")

            full_repo_path = f"{org}/{repo}/{file_path}"

            github_url = f"{GITHUB_WEB}/{org}/{repo}/blob/{branch}/{file_path}"

            print(f"SKIP: CODEOWNERS exists at {full_repo_path}")
            print(f"      URL: {github_url}")

            return True

    return False


# -------------------------------
# Create CODEOWNERS
# -------------------------------

def create_codeowners(api, org, repo, owners, branch="master"):

    try:

        if codeowners_exists(api, org, repo, branch):
            return

        codeowners_content = "* " + " ".join(owners) + "\n"

        encoded = base64.b64encode(codeowners_content.encode()).decode()

        endpoint = f"/repos/{org}/{repo}/contents/.github/CODEOWNERS"

        data = {
            "message": "Add CODEOWNERS file for compliance",
            "content": encoded,
            "branch": branch
        }

        resp = api.put(endpoint, data)

        if resp and resp.get("content"):

            print(f"SUCCESS: Created CODEOWNERS for {repo}")

            print(
                f"URL: {GITHUB_WEB}/{org}/{repo}/blob/{branch}/.github/CODEOWNERS"
            )

        else:

            print(f"SKIP: CODEOWNERS already exists for {repo}")


    except requests.exceptions.HTTPError as e:

        if e.response.status_code == 404:

            print(f"ERROR: Repo not found -> {repo}")

        else:

            print(f"ERROR: {repo} -> {e}")


# -------------------------------
# Main
# -------------------------------

def main():

    if not GITHUB_TOKEN or not GITHUB_ORG:

        raise Exception("Missing ENV variables: GITHUB_TOKEN or GITHUB_ORG")


    api = GitHubAPIClient(GITHUB_BASE, GITHUB_TOKEN)

    print(f"\nRunning CODEOWNERS automation for org: {GITHUB_ORG}\n")


    if GITHUB_ORG == "tornado":

        for repo in TORNADO_REPOS:

            create_codeowners(api, GITHUB_ORG, repo, TORNADO_OWNERS)


    elif GITHUB_ORG == "vmwsolutions":

        for repo in VMW_REPOS:

            create_codeowners(api, GITHUB_ORG, repo, VMW_OWNERS)


    else:

        raise Exception("Unsupported org. Use tornado or vmwsolutions.")



if __name__ == "__main__":

    main()
