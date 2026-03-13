import requests
import base64
import json
import time

# Hardcoded repo lists for Tornado Non-Prod Gen1
TORNADO_NONPROD_REPOS = [
    "onecloud-tracker", "vcloud", "defect-analysis-tool", "Office-of-the-CTO", "vuln_scan_output", "JIL_MCV_Architecture", "personal_ms", "vcd-jil-test-automation", "foo-repo", "bar-repo", "vcd-test", "skytap-tracker", "vuln_scan_output_nonprod", "MVCS-Documentation", "NextGenVPC", "LOGAN-Documentation", "mvcs-prototype", "mvcs-tracker", "mvcs-mgmt-comm", "mvcs-mgmt-scheduler", "mvcs-mgmt-worker", "mvcs-mgmt-api", "mvcs-ansible", "mvcs-cli", "Isolation", "artemis-teams", "hpo-hipaa-assessment-2020", "vcd-access", "mvcs-change-management", "vcd-infra-comm", "vcd-infra-api", "vcd-infra-worker", "vcd-infra-scheduler", "codescan", "ursula_env", "non-personal-ids", "git-issue-analysis", "vpc-sp", "newrelic-monitor-synthetic", "vpc-veeam", "atlas-github-app-test-repo", "vcd-billing-resubmission-script", "v2t", "vcd-billing-reporting-script", "vcd-billing-cos-reader", "pvs-bur-sp", "vcd-reports-prototype", "console-e2e", "UIAutomationResult", "add-on-services-team", "vcd-language-translation", "PIM_to_Secrete_Manager_ESXI_Automation", "vcd-iaas-vro", "ipops-vcd-dev-request", "auditree_config", "vcd-SF-rev-20221114", "ic4v-evidence-locker", "ic4v-auditree-config", "vmware-sol-locker", "auditree-VCS-evidence-locker", "auditree-VCS", "gen1-evidence-locker-test1", "gen1-auditree-config", "ic4v-patent", "vcf-on-vpc-documentation", "vcd-pscli-veeam", "VCD-Price-change-July2023", "auditree-vuln-scan-output", "svelte-pocs", "advisory", "bss_cloudant_account_compare", "veeam-customer-schedule", "sf-shared-deprecation", "security-scans-config", "security-scans-compliance-issues", "security-scans-compliance-inventory", "security-scans-compliance-evidence", "postgressqlreportresults", "ic4v-data-analytics", "ic4v-data-analytics-common", "ic4v-vrops", "ic4v-platform-team-synlab", "license-expiry-reminder", "logger-agent-config", "onepipeline-compliance-incident-issues", "onepipeline-compliance-evidence-locker", "onepipeline-compliance-inventory", "kmip4hpcs_monitor"
]

GITHUB_TOKEN = "YOUR_TOKEN"
GITHUB_ORG = "YOUR_ORG"
GITHUB_BASE = "https://api.github.com"

SLEEP_INTERVAL = 0.3

class GitHubAPIClient:
    def __init__(self, base_url, token):
        self.base_url = base_url
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"token {self.token}",
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
        resp.raise_for_status()
        return resp.json()


def metadata_exists(api, org, repo, branch="master"):
    url = f"/repos/{org}/{repo}/contents/.metadata?ref={branch}"
    result = api.get(url, allow_404=True)
    time.sleep(SLEEP_INTERVAL)
    return bool(result)


def create_metadata(api, org, repo, branch="master", dry_run=False):
    if metadata_exists(api, org, repo, branch):
        print(f"SKIP: .metadata already exists for {repo}")
        return
    # Non-Prod Gen1 format
    metadata_content = {
        "service": "vmware-solutions",
        "production_code": "No",
        "production_branches": [""],
        "security_sensitive": "no",
        "ip_sensitive": "no",
        "allow_cloud_readers": "yes"
    }
    url = f"/repos/{org}/{repo}/contents/.metadata"
    data = {
        "message": "Add .metadata file for compliance",
        "content": base64.b64encode(json.dumps(metadata_content, indent=2).encode("utf-8")).decode("utf-8"),
        "branch": branch
    }
    if not dry_run:
        resp = api.put(url, data)
        if resp and resp.get("content"):
            print(f"SUCCESS: Created .metadata for {repo}")
        else:
            print(f"ERROR: Failed to create .metadata for {repo}")
    else:
        print(f"DRY RUN: Would create .metadata for {repo}")


def main():
    api = GitHubAPIClient(GITHUB_BASE, GITHUB_TOKEN)
    for repo in TORNADO_NONPROD_REPOS:
        create_metadata(api, GITHUB_ORG, repo)

if __name__ == "__main__":
    main()
