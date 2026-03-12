import os
import sys
import re
from typing import Any, Dict, Optional

from atlassian import Jira
from requests import HTTPError
from git import Repo


def get_required_env(var_name: str) -> str:
    value = os.getenv(var_name)

    if value is None or value.strip() == "":
        print(f"❌ Missing required environment variable: {var_name}", file=sys.stderr)
        sys.exit(1)

    return value

def get_jira_field_ids(jira: Jira) -> Dict[str, str]:
    return {f["name"]: f["id"] for f in jira.get_all_fields()}


def get_common_jira_fields(jira: Jira, tags_field_name: str) -> list[str]:
    field_ids = get_jira_field_ids(jira)
    return [
        "key",
        "issuetype",
        "summary",
        field_ids[tags_field_name],
    ]

def format_ticket_keys(tickets: list[dict]) -> str:
    """Format ticket keys as a comma-separated string."""
    return ",".join(t["key"] for t in tickets)


def write_github_output(key: str, value: str) -> None:
    out_path = os.getenv("GITHUB_OUTPUT")
    out_path = out_path.strip() if out_path else None

    if not out_path:
        return

    with open(out_path, "a", encoding="utf-8") as f:
        f.write(f"{key}={value}\n")


def get_committed_ticket_keys(repo: Repo, previous_version: str, current_version: str, tag_prefix: str = "v") -> set[str]:
    """Get Jira ticket keys mentioned in commits between two tags."""
    range_spec = f"{tag_prefix}{previous_version}..{tag_prefix}{current_version}"
    commits = repo.git.log("--oneline", range_spec)

    # Extract Jira ticket keys (e.g. NXP-12345) from commit messages
    return set(re.findall(r"[A-Z][A-Z0-9]+-\d+", commits))


def main() -> None:
    JIRA_TAGS_FIELD = "Tags"

    jira_url = get_required_env("JIRA_URL")
    jira_user = get_required_env("JIRA_USER")
    jira_token = get_required_env("JIRA_TOKEN")

    jira_project = get_required_env("JIRA_PROJECT")
    jira_priority = get_required_env("JIRA_PRIORITY")
    jira_ignore_tag = get_required_env("JIRA_IGNORE_TAG") # set to "grype" on gh action level
    jira_moving_version = get_required_env("JIRA_MOVING_VERSION")
    jira_release_version = os.getenv("JIRA_RELEASE_VERSION")

    build_version = os.getenv("BUILD_VERSION", "")
    check_uncommitted = os.getenv("CHECK_UNCOMMITTED", "false")
    previous_release_version = os.getenv("PREVIOUS_RELEASE_VERSION", "")
    repository_path = os.getenv("GITHUB_WORKSPACE", ".")

    jira = Jira(
        url=jira_url,
        username=jira_user,
        password=jira_token,
        cloud=True,
    )

    repo = Repo(repository_path)

    fix_versions = ", ".join(filter(None, [jira_moving_version, jira_release_version]))

    open_blocker_issue_jql = (
        f"project = {jira_project}"
        f" AND priority = {jira_priority}"
        f" AND fixVersion in ({fix_versions})"
        f" AND status NOT IN (Resolved, Closed)"
    )

    fields = get_common_jira_fields(jira, JIRA_TAGS_FIELD)

    unresolved_tickets = jira.jql(open_blocker_issue_jql, fields=",".join(fields))

    uncommitted_tickets = []

    if not unresolved_tickets["issues"]:
        print("✅ No unresolved blocker tickets found.")
    else:
        print(f"⚠️ Found {len(unresolved_tickets['issues'])} unresolved blocker ticket(s):")
        for t in unresolved_tickets["issues"]:
            print(f"  - {t['key']}: {t['fields']['summary']}")

    if check_uncommitted.lower() == "true":
        committed_ticket_keys = get_committed_ticket_keys(repo, previous_release_version, build_version)

        print(f"🔍 Found {len(committed_ticket_keys)} committed ticket keys: {committed_ticket_keys} from {previous_release_version} to {build_version}")

        all_blocker_issue_jql = (
            f"project = {jira_project}"
            f" AND priority = {jira_priority}"
            f" AND fixVersion in ({fix_versions})"
            f" AND {JIRA_TAGS_FIELD} != {jira_ignore_tag}"
        )
        all_blocker_tickets = jira.jql(all_blocker_issue_jql, fields=",".join(fields))

        uncommitted_tickets = [
            t for t in all_blocker_tickets["issues"]
            if t["key"] not in committed_ticket_keys
        ]

        if not uncommitted_tickets:
            print("✅ No uncommitted blocker tickets found.")
        else:
            print(f"⚠️ Found {len(uncommitted_tickets)} uncommitted blocker ticket(s):")
            for t in uncommitted_tickets:
                print(f"  - {t['key']}: {t['fields']['summary']}")

    # Write GitHub outputs
    write_github_output("unresolved_tickets", format_ticket_keys(unresolved_tickets["issues"]))
    write_github_output("uncommitted_tickets", format_ticket_keys(uncommitted_tickets))
    write_github_output("has_blocker_issues", str(bool(unresolved_tickets["issues"] or uncommitted_tickets)).lower())

    if not unresolved_tickets["issues"] and not uncommitted_tickets:
        print("✅ No blocker issues found.")
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()  # pragma: no cover
