# 🔍 Check Blocker Jira Issues

A composite GitHub Action that gates releases by checking Jira for blocker issues. It queries Jira for high-priority tickets matching specified `fixVersion`(s) and optionally cross-references resolved tickets against the Git changelog to detect missing commits.

## How it works

### 1. Read configuration

The action reads required inputs (Jira credentials, project key, moving version, priority) and optional ones (release version, uncommitted check settings) from environment variables.

### 2. Connect to Jira

Authenticates with Jira Cloud using the provided URL, username, and API token.

### 3. Resolve the Tags field

Fetches all Jira field definitions to map the `Tags` field name to its internal custom field ID (e.g. `customfield_10076`). This ID is needed for JQL queries and result parsing.

### 4. Check for unresolved blocker tickets

Runs a JQL query to find tickets that are:

- In the configured project
- At the configured priority level (default: `Highest`)
- Assigned to the specified `fixVersion`(s) — the moving version and optionally a release version
- **Not Done** (`statusCategory != Done`)

If any are found, they are flagged and the action will fail.

### 5. (Optional) Check for uncommitted blocker tickets

When `check-uncommitted` is `true`, the action performs an additional check:

1. **Extract committed ticket keys** — runs `git log --oneline v<previous>..v<current>` and extracts all Jira ticket keys (e.g. `NXP-12345`) from commit messages using a regex.
2. **Query resolved blockers** — runs a second JQL query for tickets that are:
   - In the same project, priority, and `fixVersion`(s)
   - **Done** (`statusCategory = Done`)
   - Not tagged with the ignore tag (default: `grype`)
3. **Diff** — any resolved ticket whose key does **not** appear in the git log is reported as "uncommitted" (resolved in Jira but the fix is missing from the release branch).

### 6. Write outputs and exit

The action writes three GitHub outputs:

| Output                | Description                                                   |
|-----------------------|---------------------------------------------------------------|
| `has-blocker-issues`  | `"true"` if any unresolved or uncommitted blockers were found |
| `unresolved-tickets`  | Comma-separated keys of unresolved tickets                    |
| `uncommitted-tickets` | Comma-separated keys of uncommitted tickets                   |

If blockers were found, the action exits with code **1** (fails the workflow step).

### 7. Generate GitHub summary

A final step (runs even on failure) renders a Markdown summary in the GitHub Actions UI listing all found tickets with links to Jira.
