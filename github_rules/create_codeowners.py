import requests
import base64
import time
import os
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# -----------------------------
# Repo Lists
# -----------------------------

TORNADO_REPOS = [
"common-utils","build-ci","bootstrap","console","service-framework",
"service-implementations","devops","mgmt-comm","mgmt-event","kmipadapter",
"kmipmgmt","service-broker","k8s-deploy","mgmt-cos","vcd-mgmt-api",
"vcd-mgmt-job","mgmt-metering","vcd-bin-vdbc","vcd-tracking-service",
"atlas-dashboard","vcd-mgmt-db","vcd-billing-service","vcd-billing-job",
"vcd-mgmt-e2e","skytap-console","vcd-mgmt-veeam","mgmt-mq","images",
"schematics","mgmt-sysdig","vcd-mgmt-scheduler","ic4v-golang-sdk",
"ic4v-java-sdk","vcd-metrics-collector","ic4v-node-sdk","metrics-ingestor",
"managed-portal-and-billing-team","vcd-iaas-vra","vcd-vrealize-webhook",
"UX-Design","console_scan","vpc-msql","istio-egress-control",
"svt-automation-ui","VRA-G1-FRA-PRD","VRA-G1-DAL-PRD","VRA-G1-PAR-PRD",
"ipops-vcd-cases","evidence_locker","secretsmanager-utils",
"IC4V-lifecycle-image","per-core-licensing","monitoring",
"vcd-metering-reconciliation-patch","vcd-iaas-vro-g2","vcd-iaas-vro-g1",
"credreconcileresults","agent-configs","common-scripts",
"core-helper-scripts","ci-pipeline-defs"
]

TORNADO_OWNERS = [
"@durgadas","@Vishakha-Sawant3","@Tushar-Velingkar2",
"@Jeetendra-Nayak2","@Sankalp-Bhat1","@Yvens Pinto"
]

VMW_REPOS = [
"ic4v-flask-lib","ic4v-sddc","ic4v-sqlalchemy-lib","roks-configs",
"ic4v-iaas","ic4v-vmware-cloud-director","ic4v-iaas-vhost",
"ic4v-data","atlas-dashboard","ic4v-vdc-lifecycle",
"vpc-vmware-terraform","ic4v-update-vcd"
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
# Default branch
# -----------------------------

def get_default_branch(org, repo):

    url = f"{GITHUB_BASE}/repos/{org}/{repo}"

    resp = session.get(url, verify=False, timeout=20)

    if resp.status_code == 404:
        return None

    resp.raise_for_status()

    return resp.json()["default_branch"]

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
# Create CODEOWNERS
# -----------------------------

def create_codeowners(org, repo, owners):

    branch = get_default_branch(org, repo)

    if branch is None:
        print(f"ERROR: {repo} not found")
        return

    path = find_codeowners(org, repo, branch)

    # exists
    if path:
        print_location(org, repo, branch, path, "EXISTS")
        return

    # create
    content = "* " + " ".join(owners) + "\n"

    url = f"{GITHUB_BASE}/repos/{org}/{repo}/contents/.github/CODEOWNERS"

    data = {
        "message": "Add CODEOWNERS for compliance",
        "content": base64.b64encode(content.encode()).decode(),
        "branch": branch
    }

    resp = session.put(url, json=data, verify=False, timeout=20)

    if resp.status_code in (200,201):

        print_location(org, repo, branch, ".github/CODEOWNERS", "CREATED")

    elif resp.status_code == 409:

        path = find_codeowners(org, repo, branch)

        if path:
            print_location(org, repo, branch, path, "EXISTS")

    else:

        print(f"ERROR creating CODEOWNERS for {repo}")
        print(resp.text)

# -----------------------------
# Main
# -----------------------------

def main():

    if not GITHUB_TOKEN or not GITHUB_ORG:
        raise Exception("Missing GITHUB_TOKEN or GITHUB_ORG")

    print(f"\nRunning CODEOWNERS check for org: {GITHUB_ORG}\n")

    if GITHUB_ORG == "tornado":
        repos = TORNADO_REPOS
        owners = TORNADO_OWNERS

    elif GITHUB_ORG == "vmwsolutions":
        repos = VMW_REPOS
        owners = VMW_OWNERS

    else:
        raise Exception("Unsupported org")

    for repo in repos:
        create_codeowners(GITHUB_ORG, repo, owners)


if __name__ == "__main__":
    main()
