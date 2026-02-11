import os
import requests
import time
import json

TOKEN = os.getenv("GITHUB_TOKEN")
ORG = os.getenv("GITHUB_ORG")
BASE = os.getenv("GITHUB_BASE")

if not all([TOKEN, ORG, BASE]):
    raise RuntimeError("Missing env vars")

HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github+json"
}

SLEEP = 0.3


def paginate(url):
    data = []
    while url:
        r = requests.get(url, headers=HEADERS)
        r.raise_for_status()
        data.extend(r.json())

        link = r.headers.get("Link")
        if link and 'rel="next"' in link:
            url = link.split('rel="next"')[0].split("<")[1].split(">")[0]
        else:
            url = None

        time.sleep(SLEEP)

    return data


def get_repositories():
    return paginate(f"{BASE}/orgs/{ORG}/repos?per_page=100")


def get_contributors(repo):
    return paginate(f"{BASE}/repos/{ORG}/{repo}/contributors?per_page=100")


def get_branch_protection(repo, branch):
    url = f"{BASE}/repos/{ORG}/{repo}/branches/{branch}/protection"
    r = requests.get(url, headers=HEADERS)

    if r.status_code == 404:
        return None

    r.raise_for_status()
    return r.json()


def main():
    repos = get_repositories()
    result = []

    for repo in repos:
        name = repo["name"]
        creator = repo["owner"]["login"]
        default_branch = repo["default_branch"]

        contributors = get_contributors(name)
        authors = [c["login"] for c in contributors]

        protection = get_branch_protection(name, default_branch)

        branch_protected = protection is not None
        pr_required = False

        if protection:
            pr_required = protection.get("required_pull_request_reviews") is not None

        result.append({
            "repository": name,
            "creator": creator,
            "authors": authors,
            "default_branch": default_branch,
            "branch_protected": branch_protected,
            "pr_required": pr_required
        })

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
