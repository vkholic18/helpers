import os
import requests
import time
import json

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
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"Scanning org: {ORG}  (base: {BASE})\n")
    repos = get_repositories()
    print(f"Found {len(repos)} non-archived repositories.\n")

    results = []
    summary = {"total": len(repos), "fully_compliant": 0, "non_compliant": 0}

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

    output = {
        "org":     ORG,
        "summary": summary,
        "repos":   results,
    }

    print(json.dumps(output, indent=2))

    # Also write to file for CI/audit ingestion
    out_path = "compliance_report.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nReport written to {out_path}")


if __name__ == "__main__":
    main()
