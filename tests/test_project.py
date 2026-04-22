from data_upload.euphrosyne import project


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


def test_list_projects_currently_returns_error_json_for_non_200_responses(httpx_mock):
    httpx_mock.add_response(
        method="GET",
        url="https://euphrosyne.example/api/lab/projects/",
        status_code=500,
        json={"detail": "server error"},
    )

    assert project.list_projects("https://euphrosyne.example", "access-token") == {
        "detail": "server error"
    }
