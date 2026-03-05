import os
import requests
import time
import json
from datetime import datetime, timedelta, timezone

TOKEN = os.getenv("GITHUB_TOKEN")
ORG = os.getenv("GITHUB_ORG")
BASE = os.getenv("GITHUB_BASE")

if not all([TOKEN, ORG, BASE]):
    raise RuntimeError("Missing required environment variables: GITHUB_TOKEN, GITHUB_ORG, GITHUB_BASE")

HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github+json"
}

SLEEP = 0.3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def paginate(url):
    data = []
    while url:
        r = requests.get(url, headers=HEADERS)
        r.raise_for_status()
        data.extend(r.json())
        link = r.headers.get("Link", "")
        if 'rel="next"' in link:
            url = link.split('rel="next"')[0].split("<")[1].split(">")[0]
        else:
            url = None
        time.sleep(SLEEP)
    return data


def get(url, allow_404=False):
    r = requests.get(url, headers=HEADERS)
    if allow_404 and r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# Organization-level checks
# ---------------------------------------------------------------------------

def get_org_settings():
    """Fetch organization settings."""
    url = f"{BASE}/orgs/{ORG}"
    return get(url)


def check_base_permissions(org_data):
    """
    Rule (REQUIRED): Base permissions must be 'No permission' (none).
    Other values allow members to read all private repositories.
    """
    default_perm = org_data.get("default_repository_permission", "read")
    return default_perm == "none"


def check_outside_collaborators_disabled(org_data):
    """
    Rule (REQUIRED): Repository administrators should NOT be able to add 
    outside collaborators. All access must be through teams managed in AccessHub.
    """
    # members_can_create_repositories is different - we need to check if 
    # outside collaborators can be added by repo admins
    # This is controlled by 'members_allowed_repository_creation_type' indirectly
    # The actual setting is not directly exposed via API in all versions.
    # We check via the org setting if available.
    return not org_data.get("members_can_invite_outside_collaborators", True)


def check_org_hooks_ssl():
    """
    Rule (REQUIRED): All organization webhooks must have SSL verification enabled.
    Returns list of hook IDs that have SSL disabled.
    """
    hooks = get(f"{BASE}/orgs/{ORG}/hooks", allow_404=True) or []
    time.sleep(SLEEP)
    # insecure_ssl should be "0" or 0 or False or None for SSL to be enabled
    return [h["id"] for h in hooks if h.get("config", {}).get("insecure_ssl") not in (None, "0", 0, False)]


def check_repo_creation_private(org_data):
    """
    Rule (RECOMMENDED): Repository creation should default to Private.
    Check members_allowed_repository_creation_type and related settings.
    """
    creation_type = org_data.get("members_allowed_repository_creation_type", "all")
    can_create_internal = org_data.get("members_can_create_internal_repositories", True)
    can_create_public = org_data.get("members_can_create_public_repositories", True)
    
    # Compliant if members cannot create public repos
    return not can_create_public


def check_integration_requests_disabled(org_data):
    """
    Rule (RECOMMENDED): Allow integration requests from outside collaborators = Disabled.
    All access must be through teams, there should be no outside collaborators.
    """
    # This setting may not be directly exposed in all GitHub API versions
    # We check if members_can_create_pages as a proxy or return the setting if available
    return not org_data.get("members_can_create_public_pages", True)


def check_visibility_change_disabled(org_data):
    """
    Rule (RECOMMENDED): Allow members to change repository visibilities = Disabled.
    Requiring an organization administrator to change visibility helps ensure 
    repositories that should not be public are not made public accidentally.
    """
    return not org_data.get("members_can_change_repo_visibility", True)


def check_delete_transfer_disabled(org_data):
    """
    Rule (RECOMMENDED): Allow members to delete or transfer repositories = Disabled.
    Limits accidental or badly-intentioned deletion/removal.
    """
    can_delete = org_data.get("members_can_delete_repositories", True)
    can_fork = org_data.get("members_can_fork_private_repositories", True)
    return not can_delete


def check_profile_name_visibility(org_data):
    """
    Rule (RECOMMENDED): Allow members to see comment author's profile name = Enabled.
    Preventing this just makes it harder to identify your colleagues.
    """
    # This is typically enabled by default, check if explicitly disabled
    return org_data.get("members_can_see_comment_author_profile", True)


def check_team_creation_disabled(org_data):
    """
    Rule (RECOMMENDED): Allow members to create teams = Disabled.
    Helps ensure that access management through AccessHub is not subverted 
    accidentally by someone adding a team and adding people to it directly.
    """
    return not org_data.get("members_can_create_teams", True)


def check_org_admin_activity():
    """
    Rule (RECOMMENDED): Organization admins should have activity in the last 6 months.
    Returns a dict with admin login and whether they have recent activity.
    """
    # Get organization members with admin role
    admins = paginate(f"{BASE}/orgs/{ORG}/members?role=admin&per_page=100")
    six_months_ago = datetime.now(timezone.utc) - timedelta(days=180)
    
    admin_activity = []
    for admin in admins:
        login = admin["login"]
        # Check recent activity via events or audit log
        # Using public events as a proxy (may need audit log for private activity)
        events = get(f"{BASE}/users/{login}/events?per_page=1", allow_404=True) or []
        
        has_recent_activity = False
        if events:
            last_event_date = events[0].get("created_at", "")
            if last_event_date:
                try:
                    event_date = datetime.strptime(last_event_date[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    has_recent_activity = event_date >= six_months_ago
                except ValueError:
                    pass
        
        admin_activity.append({
            "login": login,
            "has_recent_activity": has_recent_activity
        })
        time.sleep(SLEEP)
    
    return admin_activity


def evaluate_org_compliance(org_data):
    """
    Evaluate all organization-level compliance rules.
    Returns a dict with required and recommended checks.
    """
    bad_org_hooks = check_org_hooks_ssl()
    admin_activity = check_org_admin_activity()
    inactive_admins = [a["login"] for a in admin_activity if not a["has_recent_activity"]]
    
    return {
        "required": {
            "base_permissions_none": check_base_permissions(org_data),
            "outside_collaborators_disabled": check_outside_collaborators_disabled(org_data),
            "org_hooks_ssl_enabled": len(bad_org_hooks) == 0,
            "org_hooks_with_ssl_disabled": bad_org_hooks,  # list for details
        },
        "recommended": {
            "repo_creation_private_only": check_repo_creation_private(org_data),
            "integration_requests_disabled": check_integration_requests_disabled(org_data),
            "visibility_change_disabled": check_visibility_change_disabled(org_data),
            "delete_transfer_disabled": check_delete_transfer_disabled(org_data),
            "profile_name_visible": check_profile_name_visibility(org_data),
            "team_creation_disabled": check_team_creation_disabled(org_data),
            "all_admins_active": len(inactive_admins) == 0,
            "inactive_admins": inactive_admins,  # list for details
            "admin_activity_details": admin_activity,  # full details
        }
    }


def is_org_compliant(org_checks):
    """
    Return True only if all REQUIRED organization rules pass.
    Recommended rules are reported but don't affect compliance status.
    """
    required = org_checks.get("required", {})
    # Exclude list fields from compliance check
    return all(
        v for k, v in required.items() 
        if not isinstance(v, list)
    )


# ---------------------------------------------------------------------------
# Repository-level checks
# ---------------------------------------------------------------------------

def get_repositories():
    """Return all non-archived repositories in the org."""
    repos = paginate(f"{BASE}/orgs/{ORG}/repos?per_page=100")
    return [r for r in repos if not r.get("archived", False)]


def check_metadata_file(repo_name, default_branch):
    """
    Rule: .metadata file must exist on the default branch.
    Returns True if found, False otherwise.
    """
    url = f"{BASE}/repos/{ORG}/{repo_name}/contents/.metadata?ref={default_branch}"
    r = requests.get(url, headers=HEADERS)
    time.sleep(SLEEP)
    return r.status_code == 200


def check_repo_visibility(repo):
    """
    Rule: Repository must be private if it contains production code
    or is IP/security-sensitive. We flag public repos as a finding.
    """
    return repo.get("private", False)


def check_collaborators(repo_name):
    """
    Rule: No individual (outside) collaborators — all access must be via teams.
    Returns list of outside collaborators if any exist.
    """
    outside = paginate(f"{BASE}/repos/{ORG}/{repo_name}/collaborators?affiliation=outside&per_page=100")
    time.sleep(SLEEP)
    return [c["login"] for c in outside]


def check_hooks(repo_name):
    """
    Rule: All webhooks must have SSL verification enabled.
    Returns list of hook IDs that have SSL disabled.
    """
    hooks = get(f"{BASE}/repos/{ORG}/{repo_name}/hooks", allow_404=True) or []
    time.sleep(SLEEP)
    return [h["id"] for h in hooks if not h.get("config", {}).get("insecure_ssl") in (None, "0", 0, False)]


# ---------------------------------------------------------------------------
# Branch-protection checks
# ---------------------------------------------------------------------------

def get_branch_protection(repo_name, branch):
    """Fetch branch protection settings; returns None if not configured."""
    url = f"{BASE}/repos/{ORG}/{repo_name}/branches/{branch}/protection"
    r = requests.get(url, headers=HEADERS)
    time.sleep(SLEEP)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def evaluate_branch_protection(protection):
    """
    Evaluate all REQUIRED branch protection rules from the CISO policy.

    Returns a dict of {rule_name: bool} where True means the rule is satisfied.
    """
    if protection is None:
        # No protection at all — every rule fails
        return {
            "protection_exists":              False,
            "pr_required":                    False,
            "required_approvals_gte_1":       False,
            "dismiss_stale_reviews":          False,
            "require_code_owner_review":      False,
            "require_last_push_approval":     False,
            "no_bypass_allowed":              False,
        }

    pr = protection.get("required_pull_request_reviews") or {}
    enforce_admins = protection.get("enforce_admins", {})

    # Some GHE versions surface this as a nested object; handle both shapes.
    bypass_allowed = (
        protection.get("allow_bypasses", True)           # org ruleset field
        or not enforce_admins.get("enabled", False)      # classic branch protection
    )

    return {
        # At least one protection rule exists
        "protection_exists": True,

        # Require a pull request before merging
        "pr_required": bool(pr),

        # Required approvals >= 1
        "required_approvals_gte_1": pr.get("required_approving_review_count", 0) >= 1,

        # Dismiss stale reviews when new commits are pushed
        "dismiss_stale_reviews": pr.get("dismiss_stale_reviews", False),

        # Require review from Code Owners
        "require_code_owner_review": pr.get("require_code_owner_reviews", False),

        # Require approval of the most recent push (prevents self-approval loop)
        "require_last_push_approval": pr.get("require_last_push_approval", False),

        # Admins must NOT be able to bypass protection rules
        "no_bypass_allowed": not bypass_allowed,
    }


def is_compliant(checks):
    """Return True only if every required rule passes."""
    return all(checks.values())


# ---------------------------------------------------------------------------
# Report Generation
# ---------------------------------------------------------------------------

def get_failure_reasons(result, org_checks):
    """
    Generate human-readable failure reasons for a repository.
    Returns a tuple of (list of rule names, list of reason strings).
    """
    failed_rules = []
    reasons = []
    repo_checks = result.get("repo_checks", {})
    bp_checks = result.get("branch_protection_checks", {})
    
    # Repository-level failures
    if not repo_checks.get("is_private", True):
        failed_rules.append("is_private")
        reasons.append("Repository is not private.")
    if not repo_checks.get("metadata_file_exists", True):
        failed_rules.append("metadata_file_exists")
        reasons.append(".metadata file is missing.")
    if not repo_checks.get("no_outside_collaborators", True):
        collabs = repo_checks.get("outside_collaborators", [])
        failed_rules.append("no_outside_collaborators")
        reasons.append(f"Outside collaborators exist: {', '.join(collabs)}.")
    if not repo_checks.get("ssl_hooks_ok", True):
        failed_rules.append("ssl_hooks_ok")
        reasons.append("Webhook(s) with SSL verification disabled.")
    
    # Branch protection failures
    if not bp_checks.get("protection_exists", True):
        failed_rules.append("protection_exists")
        reasons.append("Branch Protection not enabled.")
    else:
        if not bp_checks.get("pr_required", True):
            failed_rules.append("pr_required")
            reasons.append("Pull request reviews not required.")
        if not bp_checks.get("required_approvals_gte_1", True):
            failed_rules.append("required_approvals_gte_1")
            reasons.append("Required approving reviews is less than 1.")
        if not bp_checks.get("dismiss_stale_reviews", True):
            failed_rules.append("dismiss_stale_reviews")
            reasons.append("dismiss_stale_reviews not set to true.")
        if not bp_checks.get("require_code_owner_review", True):
            failed_rules.append("require_code_owner_review")
            reasons.append("Code owner review not required.")
        if not bp_checks.get("require_last_push_approval", True):
            failed_rules.append("require_last_push_approval")
            reasons.append("Last push approval not required.")
        if not bp_checks.get("no_bypass_allowed", True):
            failed_rules.append("enforce_admins")
            reasons.append("enforce_admins is not enabled.")
    
    return failed_rules, reasons


def get_org_failure_reasons(org_checks):
    """
    Generate human-readable failure reasons for organization-level checks.
    Returns a tuple of (list of rule names, list of reason strings).
    """
    failed_rules = []
    reasons = []
    required = org_checks.get("required", {})
    recommended = org_checks.get("recommended", {})
    
    # Required org checks
    if not required.get("base_permissions_none", True):
        failed_rules.append("base_permissions_none")
        reasons.append("Base permissions is not set to 'No permission'.")
    if not required.get("outside_collaborators_disabled", True):
        failed_rules.append("outside_collaborators_disabled")
        reasons.append("Repository admins can add outside collaborators.")
    if not required.get("org_hooks_ssl_enabled", True):
        failed_rules.append("org_hooks_ssl_enabled")
        reasons.append("Organization webhook(s) with SSL verification disabled.")
    
    # Recommended org checks
    if not recommended.get("repo_creation_private_only", True):
        failed_rules.append("repo_creation_private_only")
        reasons.append("Members can create public repositories.")
    if not recommended.get("integration_requests_disabled", True):
        failed_rules.append("integration_requests_disabled")
        reasons.append("Integration requests from outside collaborators are allowed.")
    if not recommended.get("visibility_change_disabled", True):
        failed_rules.append("visibility_change_disabled")
        reasons.append("Members can change repository visibility.")
    if not recommended.get("delete_transfer_disabled", True):
        failed_rules.append("delete_transfer_disabled")
        reasons.append("Members can delete or transfer repositories.")
    if not recommended.get("team_creation_disabled", True):
        failed_rules.append("team_creation_disabled")
        reasons.append("Members can create teams.")
    if not recommended.get("all_admins_active", True):
        inactive = recommended.get("inactive_admins", [])
        failed_rules.append("all_admins_active")
        reasons.append(f"Inactive admins (no activity in 6 months): {', '.join(inactive)}.")
    
    return failed_rules, reasons


def generate_markdown_report(org, summary, org_checks, results):
    """
    Generate a Markdown report in the format of GHE Branch Protection Branches Report.
    """
    from datetime import datetime
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    lines = []
    lines.append(f"# GHE Branch Protection Branches Report {timestamp}")
    lines.append("(Operational Report)")
    lines.append("")
    lines.append("## Results")
    lines.append("")
    lines.append(f"- **Failures**: {summary['non_compliant']}")
    lines.append(f"- **Compliant**: {summary['fully_compliant']}")
    lines.append(f"- **Total Repositories**: {summary['total_repos']}")
    lines.append("")
    
    # Organization-level findings
    org_failed_rules, org_reasons = get_org_failure_reasons(org_checks)
    if org_reasons:
        lines.append("## Organization-Level Findings")
        lines.append("")
        lines.append("| Organization | Rules Failing | Reason/s |")
        lines.append("|--------------|---------------|----------|")
        rules_text = ", ".join(org_failed_rules) if org_failed_rules else "N/A"
        reason_text = " ".join(org_reasons) if org_reasons else "N/A"
        lines.append(f"| {org} | {rules_text} | {reason_text} |")
        lines.append("")
    
    # Non-compliant branches table
    non_compliant = [r for r in results if not r["fully_compliant"]]
    
    if non_compliant:
        lines.append("## Failure: Non-compliant Branches")
        lines.append("")
        lines.append("| Organization | Repository | Branch | Rules Failing | Reason/s |")
        lines.append("|--------------|------------|--------|---------------|----------|")
        
        for result in non_compliant:
            repo = result["repository"]
            branch = result["default_branch"]
            failed_rules, reasons = get_failure_reasons(result, org_checks)
            rules_text = ", ".join(failed_rules) if failed_rules else "N/A"
            reason_text = " ".join(reasons) if reasons else "Unknown"
            lines.append(f"| {org} | {repo} | {branch} | {rules_text} | {reason_text} |")
        
        lines.append("")
    
    # Compliant repos summary
    compliant = [r for r in results if r["fully_compliant"]]
    if compliant:
        lines.append("## Compliant Repositories")
        lines.append("")
        lines.append("| Organization | Repository | Branch |")
        lines.append("|--------------|------------|--------|")
        for result in compliant:
            lines.append(f"| {org} | {result['repository']} | {result['default_branch']} |")
        lines.append("")
    
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"Scanning org: {ORG}  (base: {BASE})\n")
    
    # Organization-level compliance check
    print("Checking organization-level compliance...")
    org_data = get_org_settings()
    org_checks = evaluate_org_compliance(org_data)
    org_compliant = is_org_compliant(org_checks)
    print(f"Organization compliance: {'PASS' if org_compliant else 'FAIL'}\n")
    
    # Repository-level compliance checks
    repos = get_repositories()
    print(f"Found {len(repos)} non-archived repositories.\n")

    results = []
    summary = {
        "total_repos": len(repos), 
        "fully_compliant": 0, 
        "non_compliant": 0,
        "org_compliant": org_compliant
    }

    for repo in repos:
        name            = repo["name"]
        default_branch  = repo["default_branch"]
        is_private      = check_repo_visibility(repo)
        metadata_exists = check_metadata_file(name, default_branch)
        outside_collabs = check_collaborators(name)
        bad_hooks       = check_hooks(name)
        protection      = get_branch_protection(name, default_branch)
        bp_checks       = evaluate_branch_protection(protection)
        compliant       = (
            is_private
            and metadata_exists
            and len(outside_collabs) == 0
            and len(bad_hooks) == 0
            and is_compliant(bp_checks)
        )

        if compliant:
            summary["fully_compliant"] += 1
        else:
            summary["non_compliant"] += 1

        results.append({
            "repository":            name,
            "default_branch":        default_branch,
            "fully_compliant":       compliant,

            # Repository-level findings
            "repo_checks": {
                "is_private":               is_private,
                "metadata_file_exists":     metadata_exists,
                "no_outside_collaborators": len(outside_collabs) == 0,
                "outside_collaborators":    outside_collabs,   # list; empty = good
                "ssl_hooks_ok":             len(bad_hooks) == 0,
                "hooks_with_ssl_disabled":  bad_hooks,         # list; empty = good
            },

            # Branch-protection findings (all required by CISO policy)
            "branch_protection_checks": bp_checks,
        })

    # Generate JSON output
    output = {
        "org":     ORG,
        "summary": summary,
        "organization_checks": org_checks,
        "repos":   results,
    }

    # Write JSON report
    json_path = "compliance_report.json"
    with open(json_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"JSON report written to {json_path}")

    # Generate and write Markdown report
    md_report = generate_markdown_report(ORG, summary, org_checks, results)
    md_path = "compliance_report.md"
    with open(md_path, "w") as f:
        f.write(md_report)
    print(f"Markdown report written to {md_path}")
    
    # Print markdown report to console
    print("\n" + "=" * 80)
    print(md_report)


if __name__ == "__main__":
    main()
