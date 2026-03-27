import os
import pytest
from unittest.mock import MagicMock, patch

from action import (
    _jql_quote,
    get_required_env,
    get_jira_field_ids,
    get_common_jira_fields,
    format_ticket_keys,
    write_github_output,
    get_committed_ticket_keys,
    main,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

JIRA_FIELDS_RESPONSE = [
    {"name": "Tags", "id": "customfield_10076"},
    {"name": "Summary", "id": "summary"},
    {"name": "Issue Type", "id": "issuetype"},
]

REQUIRED_ENV = {
    "JIRA_URL": "https://jira.example.com",
    "JIRA_USER": "user",
    "JIRA_TOKEN": "token",
    "JIRA_PROJECT": "NXP",
    "JIRA_PRIORITY": "Highest",
    "JIRA_IGNORE_TAG": "grype",
    "JIRA_TAGS_FIELD": "Tags",
    "JIRA_MOVING_VERSION": "NXP-2023.x",
}


def _make_ticket(key: str, summary: str = "Some issue") -> dict:
    return {
        "key": key,
        "fields": {
            "issuetype": {"name": "Bug"},
            "summary": summary,
            "customfield_10076": [],
        },
    }


def _jira_response(issues: list[dict]) -> dict:
    return {"issues": issues, "total": len(issues)}


@pytest.fixture
def mock_jira():
    jira = MagicMock()
    jira.get_all_fields.return_value = JIRA_FIELDS_RESPONSE
    return jira


@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.working_dir = "/fake/repo"
    return repo


@pytest.fixture
def base_env(tmp_path):
    """Minimum env vars for main() to run, with GITHUB_OUTPUT pointing to a temp file."""
    output_file = tmp_path / "github_output.txt"
    return {
        **REQUIRED_ENV,
        "GITHUB_OUTPUT": str(output_file),
        "GITHUB_WORKSPACE": "/fake/repo",
        "CHECK_UNCOMMITTED": "false",
    }


def _read_outputs(env: dict) -> dict:
    """Parse the GITHUB_OUTPUT file into a dict."""
    path = env["GITHUB_OUTPUT"]
    if not os.path.exists(path):
        return {}
    result = {}
    with open(path) as f:
        for line in f:
            k, _, v = line.strip().partition("=")
            result[k] = v
    return result


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------


class TestGetRequiredEnv:
    def test_returns_value(self, monkeypatch):
        monkeypatch.setenv("MY_VAR", "hello")
        assert get_required_env("MY_VAR") == "hello"

    def test_exits_on_missing(self):
        with pytest.raises(SystemExit):
            get_required_env("DEFINITELY_NOT_SET_12345")

    def test_exits_on_empty(self, monkeypatch):
        monkeypatch.setenv("MY_VAR", "   ")
        with pytest.raises(SystemExit):
            get_required_env("MY_VAR")


class TestJqlQuote:
    def test_simple_string(self):
        assert _jql_quote("Highest") == '"Highest"'

    def test_string_with_dots_and_hyphens(self):
        assert _jql_quote("NXCON-2023.x") == '"NXCON-2023.x"'

    def test_string_with_embedded_quotes(self):
        assert _jql_quote('value"with"quotes') == '"value\\"with\\"quotes"'


class TestGetJiraFieldIds:
    def test_builds_name_to_id_map(self, mock_jira):
        result = get_jira_field_ids(mock_jira)
        assert result == {
            "Tags": "customfield_10076",
            "Summary": "summary",
            "Issue Type": "issuetype",
        }


class TestGetCommonJiraFields:
    def test_returns_fields_with_tag_id(self, mock_jira):
        fields, tags_id = get_common_jira_fields(mock_jira, "Tags")
        assert fields == ["key", "issuetype", "summary", "customfield_10076"]
        assert tags_id == "customfield_10076"

    def test_returns_fields_without_tag_id_when_missing(self, mock_jira):
        fields, tags_id = get_common_jira_fields(mock_jira, "NonExistentField")
        assert fields == ["key", "issuetype", "summary"]
        assert tags_id is None


class TestFormatTicketKeys:
    def test_formats_keys(self):
        tickets = [_make_ticket("NXP-1"), _make_ticket("NXP-2")]
        assert format_ticket_keys(tickets) == "NXP-1,NXP-2"

    def test_empty_list(self):
        assert format_ticket_keys([]) == ""


class TestWriteGithubOutput:
    def test_writes_to_file(self, tmp_path):
        out = tmp_path / "output.txt"
        with patch.dict(os.environ, {"GITHUB_OUTPUT": str(out)}):
            write_github_output("key1", "val1")
            write_github_output("key2", "val2")
        content = out.read_text()
        assert "key1=val1\n" in content
        assert "key2=val2\n" in content

    def test_noop_without_env(self):
        with patch.dict(os.environ, {}, clear=True):
            # Should not raise
            write_github_output("key", "val")


class TestGetCommittedTicketKeys:
    def test_extracts_keys_from_log(self, mock_repo):
        mock_repo.git.log.return_value = (
            "abc1234 NXP-100 Fix something\n"
            "def5678 NXP-200 Another fix\n"
            "ghi9012 No ticket here\n"
        )
        keys = get_committed_ticket_keys(mock_repo, "1.0.0", "2.0.0")
        assert keys == {"NXP-100", "NXP-200"}
        mock_repo.git.log.assert_called_once_with("--oneline", "v1.0.0..v2.0.0")

    def test_custom_tag_prefix(self, mock_repo):
        mock_repo.git.log.return_value = "abc NXP-1 fix"
        get_committed_ticket_keys(mock_repo, "1.0", "2.0", tag_prefix="release-")
        mock_repo.git.log.assert_called_once_with("--oneline", "release-1.0..release-2.0")

    def test_empty_log(self, mock_repo):
        mock_repo.git.log.return_value = ""
        keys = get_committed_ticket_keys(mock_repo, "1.0", "2.0")
        assert keys == set()

    def test_raises_on_git_error(self, mock_repo):
        from git.exc import GitCommandError

        mock_repo.git.log.side_effect = GitCommandError("git log", 128)
        mock_repo.git.tag.return_value = "v1.0.0\nv2.0.0"
        with pytest.raises(GitCommandError):
            get_committed_ticket_keys(mock_repo, "1.0.0", "2.0.0")


# ---------------------------------------------------------------------------
# Integration-style tests for main()
# ---------------------------------------------------------------------------

class TestMainNoUnresolvedNoUncommitted:
    """Scenario: no unresolved tickets, uncommitted check disabled → success."""

    def test_exits_cleanly(self, base_env):
        with (
            patch.dict(os.environ, base_env, clear=True),
            patch("action.Jira") as MockJira,
            patch("action.Repo") as MockRepo,
        ):
            jira = MockJira.return_value
            jira.get_all_fields.return_value = JIRA_FIELDS_RESPONSE
            jira.enhanced_jql.return_value = _jira_response([])

            repo = MockRepo.return_value
            repo.working_dir = "/fake/repo"

            main()  # should not raise

        outputs = _read_outputs(base_env)
        assert outputs["has_blocker_issues"] == "false"
        assert outputs["unresolved_tickets"] == ""
        assert outputs["uncommitted_tickets"] == ""


class TestMainUnresolvedTicketsFound:
    """Scenario: unresolved blocker tickets exist → sys.exit(1)."""

    def test_fails_with_exit_1(self, base_env):
        with (
            patch.dict(os.environ, base_env, clear=True),
            patch("action.Jira") as MockJira,
            patch("action.Repo") as MockRepo,
        ):
            jira = MockJira.return_value
            jira.get_all_fields.return_value = JIRA_FIELDS_RESPONSE
            jira.enhanced_jql.return_value = _jira_response([
                _make_ticket("NXP-101", "Blocker bug"),
                _make_ticket("NXP-102", "Another blocker"),
            ])

            repo = MockRepo.return_value
            repo.working_dir = "/fake/repo"

            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

        outputs = _read_outputs(base_env)
        assert outputs["has_blocker_issues"] == "true"
        assert outputs["unresolved_tickets"] == "NXP-101,NXP-102"


class TestMainUncommittedTicketsFound:
    """Scenario: no unresolved tickets, but some blocker tickets are not in the git log → sys.exit(1)."""

    def test_fails_when_tickets_not_in_commits(self, base_env):
        base_env["CHECK_UNCOMMITTED"] = "true"
        base_env["BUILD_VERSION"] = "2023.2.0"
        base_env["PREVIOUS_RELEASE_VERSION"] = "2023.1.0"

        with (
            patch.dict(os.environ, base_env, clear=True),
            patch("action.Jira") as MockJira,
            patch("action.Repo") as MockRepo,
        ):
            jira = MockJira.return_value
            jira.get_all_fields.return_value = JIRA_FIELDS_RESPONSE

            # First call: unresolved query → no issues
            # Second call: all blockers query → 2 tickets, only 1 is committed
            jira.enhanced_jql.side_effect = [
                _jira_response([]),
                _jira_response([
                    _make_ticket("NXP-200", "Committed fix"),
                    _make_ticket("NXP-201", "Uncommitted fix"),
                ]),
            ]

            repo = MockRepo.return_value
            repo.working_dir = "/fake/repo"
            repo.git.log.return_value = "abc1234 NXP-200 Committed fix"

            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

        outputs = _read_outputs(base_env)
        assert outputs["has_blocker_issues"] == "true"
        assert outputs["uncommitted_tickets"] == "NXP-201"
        assert outputs["unresolved_tickets"] == ""


class TestMainAllTicketsCommitted:
    """Scenario: no unresolved tickets, all blocker tickets are committed → success."""

    def test_passes_when_all_committed(self, base_env):
        base_env["CHECK_UNCOMMITTED"] = "true"
        base_env["BUILD_VERSION"] = "2023.2.0"
        base_env["PREVIOUS_RELEASE_VERSION"] = "2023.1.0"

        with (
            patch.dict(os.environ, base_env, clear=True),
            patch("action.Jira") as MockJira,
            patch("action.Repo") as MockRepo,
        ):
            jira = MockJira.return_value
            jira.get_all_fields.return_value = JIRA_FIELDS_RESPONSE

            jira.enhanced_jql.side_effect = [
                _jira_response([]),
                _jira_response([
                    _make_ticket("NXP-300"),
                    _make_ticket("NXP-301"),
                ]),
            ]

            repo = MockRepo.return_value
            repo.working_dir = "/fake/repo"
            repo.git.log.return_value = (
                "aaa NXP-300 fix one\n"
                "bbb NXP-301 fix two"
            )

            main()  # should not raise

        outputs = _read_outputs(base_env)
        assert outputs["has_blocker_issues"] == "false"
        assert outputs["uncommitted_tickets"] == ""


class TestMainBothUnresolvedAndUncommitted:
    """Scenario: both unresolved AND uncommitted tickets → sys.exit(1) with both outputs."""

    def test_reports_both(self, base_env):
        base_env["CHECK_UNCOMMITTED"] = "true"
        base_env["BUILD_VERSION"] = "2023.2.0"
        base_env["PREVIOUS_RELEASE_VERSION"] = "2023.1.0"

        with (
            patch.dict(os.environ, base_env, clear=True),
            patch("action.Jira") as MockJira,
            patch("action.Repo") as MockRepo,
        ):
            jira = MockJira.return_value
            jira.get_all_fields.return_value = JIRA_FIELDS_RESPONSE

            jira.enhanced_jql.side_effect = [
                _jira_response([_make_ticket("NXP-400", "Open blocker")]),
                _jira_response([_make_ticket("NXP-401", "Uncommitted blocker")]),
            ]

            repo = MockRepo.return_value
            repo.working_dir = "/fake/repo"
            repo.git.log.return_value = ""  # no commits match

            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

        outputs = _read_outputs(base_env)
        assert outputs["has_blocker_issues"] == "true"
        assert outputs["unresolved_tickets"] == "NXP-400"
        assert outputs["uncommitted_tickets"] == "NXP-401"


class TestMainOptionalReleaseVersion:
    """Scenario: JIRA_RELEASE_VERSION not set → fix_versions uses only moving version."""

    def test_works_without_release_version(self, base_env):
        # Ensure JIRA_RELEASE_VERSION is not set
        base_env.pop("JIRA_RELEASE_VERSION", None)

        with (
            patch.dict(os.environ, base_env, clear=True),
            patch("action.Jira") as MockJira,
            patch("action.Repo") as MockRepo,
        ):
            jira = MockJira.return_value
            jira.get_all_fields.return_value = JIRA_FIELDS_RESPONSE
            jira.enhanced_jql.return_value = _jira_response([])

            repo = MockRepo.return_value
            repo.working_dir = "/fake/repo"

            main()

            # Verify JQL contains only the moving version
            jql_call = jira.enhanced_jql.call_args[0][0]
            assert "NXP-2023.x" in jql_call
            assert 'fixVersion in ("NXP-2023.x")' in jql_call


class TestMainWithReleaseVersion:
    """Scenario: JIRA_RELEASE_VERSION set → fix_versions includes both."""

    def test_includes_both_versions_in_jql(self, base_env):
        base_env["JIRA_RELEASE_VERSION"] = "NXP-2023.2"

        with (
            patch.dict(os.environ, base_env, clear=True),
            patch("action.Jira") as MockJira,
            patch("action.Repo") as MockRepo,
        ):
            jira = MockJira.return_value
            jira.get_all_fields.return_value = JIRA_FIELDS_RESPONSE
            jira.enhanced_jql.return_value = _jira_response([])

            repo = MockRepo.return_value
            repo.working_dir = "/fake/repo"

            main()

            jql_call = jira.enhanced_jql.call_args[0][0]
            assert 'fixVersion in ("NXP-2023.x", "NXP-2023.2")' in jql_call


class TestMainUncommittedJqlContent:
    """Verify the second JQL query (resolved blockers for uncommitted check) restricts to Done."""

    def test_second_jql_filters_done_tickets_only(self, base_env):
        base_env["CHECK_UNCOMMITTED"] = "true"
        base_env["BUILD_VERSION"] = "2023.2.0"
        base_env["PREVIOUS_RELEASE_VERSION"] = "2023.1.0"

        with (
            patch.dict(os.environ, base_env, clear=True),
            patch("action.Jira") as MockJira,
            patch("action.Repo") as MockRepo,
        ):
            jira = MockJira.return_value
            jira.get_all_fields.return_value = JIRA_FIELDS_RESPONSE
            jira.enhanced_jql.side_effect = [
                _jira_response([]),
                _jira_response([]),
            ]

            repo = MockRepo.return_value
            repo.working_dir = "/fake/repo"
            repo.git.log.return_value = ""

            main()

            # Second call is the resolved-blockers query
            second_jql = jira.enhanced_jql.call_args_list[1][0][0]
            assert "statusCategory = Done" in second_jql
            assert 'priority = "Highest"' in second_jql
            assert 'fixVersion in ("NXP-2023.x")' in second_jql
            assert 'Tags is EMPTY OR Tags != "grype"' in second_jql


class TestMainMissingVersionsForUncommitted:
    """Scenario: check_uncommitted=true but BUILD_VERSION or PREVIOUS_RELEASE_VERSION missing → sys.exit(1)."""

    def test_exits_on_missing_build_version(self, base_env):
        base_env["CHECK_UNCOMMITTED"] = "true"
        base_env["BUILD_VERSION"] = ""
        base_env["PREVIOUS_RELEASE_VERSION"] = "1.0.0"

        with (
            patch.dict(os.environ, base_env, clear=True),
            patch("action.Jira") as MockJira,
            patch("action.Repo") as MockRepo,
        ):
            jira = MockJira.return_value
            jira.get_all_fields.return_value = JIRA_FIELDS_RESPONSE
            jira.enhanced_jql.return_value = _jira_response([])

            repo = MockRepo.return_value
            repo.working_dir = "/fake/repo"

            with pytest.raises(SystemExit):
                main()

    def test_exits_on_missing_previous_version(self, base_env):
        base_env["CHECK_UNCOMMITTED"] = "true"
        base_env["BUILD_VERSION"] = "2.0.0"
        base_env["PREVIOUS_RELEASE_VERSION"] = ""

        with (
            patch.dict(os.environ, base_env, clear=True),
            patch("action.Jira") as MockJira,
            patch("action.Repo") as MockRepo,
        ):
            jira = MockJira.return_value
            jira.get_all_fields.return_value = JIRA_FIELDS_RESPONSE
            jira.enhanced_jql.return_value = _jira_response([])

            repo = MockRepo.return_value
            repo.working_dir = "/fake/repo"

            with pytest.raises(SystemExit):
                main()


class TestMainMissingRequiredEnv:
    """Scenario: required env var missing → sys.exit(1) immediately."""

    def test_exits_on_missing_jira_url(self, base_env):
        del base_env["JIRA_URL"]
        with (
            patch.dict(os.environ, base_env, clear=True),
            pytest.raises(SystemExit),
        ):
            main()

    def test_exits_on_missing_jira_project(self, base_env):
        del base_env["JIRA_PROJECT"]
        with (
            patch.dict(os.environ, base_env, clear=True),
            pytest.raises(SystemExit),
        ):
            main()


JIRA_FIELDS_NO_TAGS = [
    {"name": "Summary", "id": "summary"},
    {"name": "Issue Type", "id": "issuetype"},
]


class TestMainTagsFieldMissing:
    """Scenario: Tags field does not exist in Jira → tag filtering skipped, action still works."""

    def test_succeeds_without_tags_field(self, base_env):
        with (
            patch.dict(os.environ, base_env, clear=True),
            patch("action.Jira") as MockJira,
            patch("action.Repo") as MockRepo,
        ):
            jira = MockJira.return_value
            jira.get_all_fields.return_value = JIRA_FIELDS_NO_TAGS
            jira.enhanced_jql.return_value = _jira_response([])

            repo = MockRepo.return_value
            repo.working_dir = "/fake/repo"

            main()

        outputs = _read_outputs(base_env)
        assert outputs["has_blocker_issues"] == "false"

    def test_uncommitted_jql_skips_tags_filter(self, base_env):
        base_env["CHECK_UNCOMMITTED"] = "true"
        base_env["BUILD_VERSION"] = "2023.2.0"
        base_env["PREVIOUS_RELEASE_VERSION"] = "2023.1.0"

        with (
            patch.dict(os.environ, base_env, clear=True),
            patch("action.Jira") as MockJira,
            patch("action.Repo") as MockRepo,
        ):
            jira = MockJira.return_value
            jira.get_all_fields.return_value = JIRA_FIELDS_NO_TAGS
            jira.enhanced_jql.side_effect = [
                _jira_response([]),
                _jira_response([]),
            ]

            repo = MockRepo.return_value
            repo.working_dir = "/fake/repo"
            repo.git.log.return_value = ""

            main()

            second_jql = jira.enhanced_jql.call_args_list[1][0][0]
            assert "statusCategory = Done" in second_jql
            assert "Tags" not in second_jql
