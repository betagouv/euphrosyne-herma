import httpx
import pytest

from data_upload.euphrosyne import project
from data_upload.euphrosyne.project import ProjectLoadingError


def setup_function():
    project.list_projects.cache_clear()


def test_list_projects_returns_projects_and_sends_bearer_token(httpx_mock):
    expected_projects = [
        {
            "name": "Project A",
            "slug": "project-a",
            "runs": [
                {
                    "label": "Run 1",
                    "particle_type": "proton",
                    "energy_in_keV": 120,
                    "objects": [{"id": 1, "label": "Object 1"}],
                    "methods_url": "https://example.com/methods",
                }
            ],
        }
    ]
    httpx_mock.add_response(
        method="GET",
        url="https://euphrosyne.example/api/lab/projects/",
        json=expected_projects,
    )

    projects = project.list_projects("https://euphrosyne.example", "access-token")

    assert projects == expected_projects
    request = httpx_mock.get_request()
    assert request.headers["Accept"] == "application/json"
    assert request.headers["Authorization"] == "Bearer access-token"


def test_list_projects_caches_by_host_and_access_token(httpx_mock):
    httpx_mock.add_response(
        method="GET",
        url="https://euphrosyne.example/api/lab/projects/",
        json=[],
    )

    assert project.list_projects("https://euphrosyne.example", "access-token") == []
    assert project.list_projects("https://euphrosyne.example", "access-token") == []

    assert len(httpx_mock.get_requests()) == 1


def test_list_projects_raises_for_non_200_responses(httpx_mock):
    httpx_mock.add_response(
        method="GET",
        url="https://euphrosyne.example/api/lab/projects/",
        status_code=500,
        json={"detail": "server error"},
    )

    with pytest.raises(httpx.HTTPStatusError):
        project.list_projects("https://euphrosyne.example", "access-token")


def test_list_projects_wraps_connection_errors(httpx_mock):
    httpx_mock.add_exception(
        httpx.ConnectError("connection failed"),
        method="GET",
        url="https://euphrosyne.example/api/lab/projects/",
    )

    with pytest.raises(ProjectLoadingError, match="Failed to connect"):
        project.list_projects("https://euphrosyne.example", "access-token")


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"detail": "server error"}, "must be a list"),
        ([{"runs": []}], "missing a name"),
        ([{"name": "Project A"}], "missing a runs list"),
        ([{"name": "Project A", "runs": [{}]}], "missing a label"),
    ],
)
def test_list_projects_raises_for_malformed_project_payloads(
    httpx_mock, payload, message
):
    httpx_mock.add_response(
        method="GET",
        url="https://euphrosyne.example/api/lab/projects/",
        json=payload,
    )

    with pytest.raises(ProjectLoadingError, match=message):
        project.list_projects("https://euphrosyne.example", "access-token")


def test_list_projects_raises_for_invalid_json(httpx_mock):
    httpx_mock.add_response(
        method="GET",
        url="https://euphrosyne.example/api/lab/projects/",
        text="not json",
    )

    with pytest.raises(ProjectLoadingError, match="valid JSON"):
        project.list_projects("https://euphrosyne.example", "access-token")


def test_first_project_with_runs_returns_first_uploadable_project():
    projects = [
        {"name": "Project A", "slug": "a", "runs": []},
        {"name": "Project B", "slug": "b", "runs": [{"label": "Run 1"}]},
    ]

    assert project.first_project_with_runs(projects) == projects[1]


def test_first_project_with_runs_returns_none_when_no_runs_exist():
    assert (
        project.first_project_with_runs(
            [{"name": "Project A", "slug": "a", "runs": []}]
        )
        is None
    )
