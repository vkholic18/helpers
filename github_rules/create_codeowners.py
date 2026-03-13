import requests
import base64
import time

# Hardcoded repo lists and owner mappings
TORNADO_REPOS = [
    "common-utils", "build-ci", "bootstrap", "console", "service-framework", "service-implementations", "devops", "mgmt-comm", "mgmt-event", "kmipadapter", "kmipmgmt", "service-broker", "k8s-deploy", "mgmt-cos", "vcd-mgmt-api", "vcd-mgmt-job", "mgmt-metering", "vcd-bin-vdbc", "vcd-tracking-service", "atlas-dashboard", "vcd-mgmt-db", "vcd-billing-service", "vcd-billing-job", "vcd-mgmt-e2e", "skytap-console", "vcd-mgmt-veeam", "mgmt-mq", "images", "schematics", "mgmt-sysdig", "vcd-mgmt-scheduler", "ic4v-golang-sdk", "ic4v-java-sdk", "vcd-metrics-collector", "ic4v-node-sdk", "metrics-ingestor", "managed-portal-and-billing-team", "vcd-iaas-vra", "vcd-vrealize-webhook", "UX-Design", "console_scan", "vpc-msql", "istio-egress-control", "svt-automation-ui", "VRA-G1-FRA-PRD", "VRA-G1-DAL-PRD", "VRA-G1-PAR-PRD", "ipops-vcd-cases", "evidence_locker", "secretsmanager-utils", "IC4V-lifecycle-image", "per-core-licensing", "monitoring", "vcd-metering-reconciliation-patch", "vcd-iaas-vro-g2", "vcd-iaas-vro-g1", "credreconcileresults", "agent-configs", "common-scripts", "core-helper-scripts", "ci-pipeline-defs"
]
TORNADO_OWNERS = [
    "@durgadas", "@Vishakha-Sawant3", "@Tushar-Velingkar2", "@Jeetendra-Nayak2", "@Sankalp-Bhat1", "@Shail Kumari", "@Avinash Boini", "@Yvens Pinto"
]
VMW_REPOS = [
    "ic4v-flask-lib", "ic4v-sddc", "ic4v-sqlalchemy-lib", "roks-configs", "ic4v-iaas", "ic4v-vmware-cloud-director", "ic4v-iaas-vhost", "ic4v-data", "atlas-dashboard", "ic4v-vdc-lifecycle", "vpc-vmware-terraform", "ic4v-update-vcd", "vpc-vmware-iaas-pub", "VCD-Terraform", "ic4v-license-check-result", "ic4v-metrics-ingestor", "ic4v-sysdig", "devops_tracker", "vpc-observability-terraform", "auditree_evidence_locker", "auditree_config", "change-management", "ic4v-control-plane-iac", "vpc-demo-modules", "vpc-demo-3tier", "auto-infra-devops", "auditree-vuln-scan-output", "ic4v-utils", "vpc-demo-3tier-autoscale", "ic4v-vpc-vsi-roks-bastion", "vpc-demo-hubspoke", "nonprod_auditree_config", "nonprod_auditree_evidence_locker", "ic4v-backup-restore", "ic4v-update-veeam", "ic4v-performance", "ic4v-smm", "ic4v-console", "iaas-mgmt", "onepipeline-compliance-inventory", "ic4v-vcda", "ic4v-reconciliation", "ic4v-licensing", "ic4v-update-vcda", "vcf-vpc-automation", "vcf-vpc-automation-sddc", "ic4v-licensing-service", "ic4v-veeam-kpi-collector", "rmc_xls_part_price_compare", "ic4v-update-usage-meter", "g11n-tracker", "ic4v-cos-sync", "ic4v-licensing-service-billing", "ic4v-vm-operations", "ic4v-licensing-service-iac", "submission_evidence_utils", "ic4v-secrets-operator", "ic4v-secrets-sync", "MT-price-change-202401", "ic4v-ad-learning", "vmaas-terraform", "ic4v-secrets-inventory", "ic4v-sm-migrate", "devtest-compliance", "devtest-compliance-sos", "onepipeline-compliance-evidence-locker", "ic4v-cot", "monitoring", "ic4v-vmc-cli", "ic4v-vmc-cli-ops", "ic4v-logging-demo", "ic4v-srx-template", "ic4v-srx-configs", "ic4v-usage-meter", "ic4v-syslog-demo", "ic4v-um-proxy", "ic4v-vmca-cli", "ic4v-security", "WIP-SLA", "ic4v-governance", "ic4v-srx-configs-change-log", "ic4v-vmc-cli-fake-remote", "ansible-change-log", "ic4v-vmca-edr-installer", "ansible-password-rotation", "doc-separation-test", "ic4v-vmca-playbooks", "openapi-client-generator", "ic4v-governance-automation", "ic4v-vmca-ip-loader", "ic4v-secrets-placeholder-creator", "vm_system_uuid_reset", "ic4v-sos-cli", "ic4v-secrets-operator-v2", "copy_dev_cos_to_stag", "ansible-monitoring", "ansible-health-checks", "ic4v-license-inventory", "PlatformDevOps", "ic4v-usage-meter-proxy", "ic4v-update-vrni", "security-compliance-output", "titan", "ic4v-pipeline-iac", "workernodeupdatelogs", "ic4v-iaas-vpc", "ic4v-license-ui", "icl_alerts", "ic4v-vcfvpc-automation", "ic4v-external-apis-lib", "vcd-iaas-vra", "vcd-iaas-vro-g2", "ic4v-vmca-scripts", "compliance-pipeline-defs", "iaas-vro-g2", "cli-vmaas-plugin", "security-scans-compliance-evidence", "security-scans-compliance-inventory", "ic4v-cos-sync-tekton"
]
VMW_OWNERS = [
    "@durgadas", "@Shakil-Usgaonker2", "@Tushar-Velingkar2", "@Jeetendra-Nayak2", "@Yvens Pinto", "@Shruti-Vasudeo2", "@Siddhi-Borkar2", "@Prachi-Kamat4", "@Bhushan-Borkar2"
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


def codeowners_exists(api, org, repo, branch="master"):
    locations = [
        f"/repos/{org}/{repo}/contents/CODEOWNERS?ref={branch}",
        f"/repos/{org}/{repo}/contents/docs/CODEOWNERS?ref={branch}",
        f"/repos/{org}/{repo}/contents/.github/CODEOWNERS?ref={branch}",
    ]
    for url in locations:
        result = api.get(url, allow_404=True)
        time.sleep(SLEEP_INTERVAL)
        if result:
            return True
    return False


def create_codeowners(api, org, repo, owners, branch="master", dry_run=False):
    if codeowners_exists(api, org, repo, branch):
        print(f"SKIP: CODEOWNERS already exists for {repo}")
        return
    codeowners_content = "* " + " ".join(owners) + "\n"
    url = f"/repos/{org}/{repo}/contents/CODEOWNERS"
    data = {
        "message": "Add CODEOWNERS file for compliance",
        "content": base64.b64encode(codeowners_content.encode("utf-8")).decode("utf-8"),
        "branch": branch
    }
    if not dry_run:
        resp = api.put(url, data)
        if resp and resp.get("content"):
            print(f"SUCCESS: Created CODEOWNERS for {repo}")
        else:
            print(f"ERROR: Failed to create CODEOWNERS for {repo}")
    else:
        print(f"DRY RUN: Would create CODEOWNERS for {repo}")


def main():
    api = GitHubAPIClient(GITHUB_BASE, GITHUB_TOKEN)
    for repo in TORNADO_REPOS:
        create_codeowners(api, GITHUB_ORG, repo, TORNADO_OWNERS)
    for repo in VMW_REPOS:
        create_codeowners(api, GITHUB_ORG, repo, VMW_OWNERS)

if __name__ == "__main__":
    main()
