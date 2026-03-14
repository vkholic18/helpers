import requests
import base64
import json
import time

# -------------------------------
# Repo Lists
# -------------------------------

TORNADO_REPOS = [
"onecloud-tracker","vcloud","defect-analysis-tool","Office-of-the-CTO","vuln_scan_output",
"JIL_MCV_Architecture","personal_ms","vcd-jil-test-automation","foo-repo","bar-repo",
"vcd-test","skytap-tracker","vuln_scan_output_nonprod","MVCS-Documentation","NextGenVPC",
"LOGAN-Documentation","mvcs-prototype","mvcs-tracker","mvcs-mgmt-comm","mvcs-mgmt-scheduler",
"mvcs-mgmt-worker","mvcs-mgmt-api","mvcs-ansible","mvcs-cli","Isolation","artemis-teams",
"hpo-hipaa-assessment-2020","vcd-access","mvcs-change-management","vcd-infra-comm",
"vcd-infra-api","vcd-infra-worker","vcd-infra-scheduler","codescan","ursula_env",
"non-personal-ids","git-issue-analysis","vpc-sp","newrelic-monitor-synthetic","vpc-veeam",
"atlas-github-app-test-repo","vcd-billing-resubmission-script","v2t","vcd-billing-reporting-script",
"vcd-billing-cos-reader","pvs-bur-sp","vcd-reports-prototype","console-e2e","UIAutomationResult",
"add-on-services-team","vcd-language-translation","PIM_to_Secrete_Manager_ESXI_Automation",
"vcd-iaas-vro","ipops-vcd-dev-request","auditree_config","vcd-SF-rev-20221114","ic4v-evidence-locker",
"ic4v-auditree-config","vmware-sol-locker","auditree-VCS-evidence-locker","auditree-VCS",
"gen1-evidence-locker-test1","gen1-auditree-config","ic4v-patent","vcf-on-vpc-documentation",
"vcd-pscli-veeam","VCD-Price-change-July2023","auditree-vuln-scan-output","svelte-pocs","advisory",
"bss_cloudant_account_compare","veeam-customer-schedule","sf-shared-deprecation",
"security-scans-config","security-scans-compliance-issues","security-scans-compliance-inventory",
"security-scans-compliance-evidence","postgressqlreportresults","ic4v-data-analytics",
"ic4v-data-analytics-common","ic4v-vrops","ic4v-platform-team-synlab","license-expiry-reminder",
"logger-agent-config","onepipeline-compliance-incident-issues","onepipeline-compliance-evidence-locker",
"onepipeline-compliance-inventory","kmip4hpcs_monitor"
]

VMW_REPOS = [
"ic4v-micro-service-example","ic4v-micro-service-test","tekton-ms-example","ic4v-library-example",
"NG-terraform-templates","IC4V-Dependencies","NG-oneCloud","ic4v-mzr-pipeline-defs","ic4v-ghost",
"solution-tutorials","ic4v-console-e2e","tekton-toolchain-template","ic4v-workload-domain",
"ic4v-auto-infra-epics","vsan-sdk-python","vmware-go-sdk","ic4v-architecture-description",
"vmware-managed-stress","vmwaas-sf-rev-20221114","SF-MultiTenant-2023",
"onepipeline-compliance-evidence-locker-2023Apirl-2023Sep","common-automation",
"SF-SingleTenant-PriceChange-2023","SF-license-feature","ic4v-billing-reconciliation",
"security-scans-config-bak","ic4v-licensing-distro","vcd-log-provider-poc","Vmware-terraform",
"ic4v-vmca-registration-service","ic4v-addon-lifecycle","ic4v-addon-billing","billing-operations",
"tf-sdn-automation","security-scans-config","helm-properties","ic4v-vcfvpc-tests","vra-salt",
"ic4v-brickstorm-scan"
]

# -------------------------------
# GitHub Config
# -------------------------------

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_ORG = os.getenv("GITHUB_ORG")

GITHUB_BASE = "https://github.ibm.com/api/v3"

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
        resp = self.session.get(url)

        if allow_404 and resp.status_code == 404:
            return None

        resp.raise_for_status()
        return resp.json()

    def put(self, endpoint, data):

        url = self.base_url + endpoint
        resp = self.session.put(url, json=data)

        resp.raise_for_status()
        return resp.json()

# -------------------------------
# Metadata Templates
# -------------------------------

def build_metadata(service, prod=False):

    if prod:
        return {
            "service": service,
            "production_code": "yes",
            "production_branches": ["master"],
            "security_sensitive": "no",
            "ip_sensitive": "no",
            "allow_cloud_readers": "yes"
        }

    return {
        "service": service,
        "production_code": "No",
        "production_branches": [""],
        "security_sensitive": "no",
        "ip_sensitive": "no",
        "allow_cloud_readers": "yes"
    }

# -------------------------------
# Helpers
# -------------------------------

def get_default_branch(api, org, repo):

    repo_info = api.get(f"/repos/{org}/{repo}")
    return repo_info["default_branch"]


def metadata_exists(api, org, repo, branch):

    result = api.get(
        f"/repos/{org}/{repo}/contents/.metadata?ref={branch}",
        allow_404=True
    )

    return bool(result)

# -------------------------------
# Metadata Creation
# -------------------------------

def process_repo(api, org, repo, service):

    repo_lower = repo.lower()

    if repo_lower.startswith("mvcs-"):
        print(f"SKIP mvcs repo: {repo}")
        return

    if repo_lower.startswith("vcd-"):
        print(f"SKIP vcd repo: {repo}")
        return

    default_branch = get_default_branch(api, org, repo)

    if default_branch == "main":
        print(f"SKIP main branch repo: {repo}")
        return

    if metadata_exists(api, org, repo, default_branch):
        print(f"SKIP metadata exists: {repo}")
        return

    metadata = build_metadata(service, prod=False)

    encoded = base64.b64encode(
        json.dumps(metadata, indent=2).encode()
    ).decode()

    data = {
        "message": "Add .metadata file",
        "content": encoded,
        "branch": default_branch
    }

    api.put(
        f"/repos/{org}/{repo}/contents/.metadata",
        data
    )

    print(f"SUCCESS: .metadata created -> {repo}")

    time.sleep(SLEEP_INTERVAL)

# -------------------------------
# Main
# -------------------------------

def main():

    api = GitHubAPIClient(GITHUB_BASE, GITHUB_TOKEN)

    print("\nProcessing Tornado (Gen1)...\n")

    for repo in TORNADO_REPOS:
        try:
            process_repo(api, GITHUB_ORG, repo, "vmware-solutions")
        except Exception as e:
            print(f"ERROR {repo}: {e}")

    print("\nProcessing VMW (Gen2)...\n")

    for repo in VMW_REPOS:
        try:
            process_repo(api, GITHUB_ORG, repo, "vmware")
        except Exception as e:
            print(f"ERROR {repo}: {e}")


if __name__ == "__main__":
    main()
