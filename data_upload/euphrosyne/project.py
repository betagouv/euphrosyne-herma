import functools
import typing

import httpx


class ObjectSummary(typing.TypedDict):
    id: int
    label: str


class Run(typing.TypedDict):
    label: str
    particle_type: str
    energy_in_keV: int
    objects: list[ObjectSummary]
    methods_url: str


class Project(typing.TypedDict):
    name: str
    runs: list[Run]
    slug: str


class ProjectLoadingError(Exception):
    """Raised when projects cannot be loaded or parsed."""


def validate_projects(data: typing.Any) -> list[Project]:
    if not isinstance(data, list):
        raise ProjectLoadingError("Projects response must be a list.")

    for project_index, project in enumerate(data):
        if not isinstance(project, dict):
            raise ProjectLoadingError(
                f"Project at index {project_index} must be an object."
            )
        if not isinstance(project.get("name"), str) or not project["name"]:
            raise ProjectLoadingError(
                f"Project at index {project_index} is missing a name."
            )
        if not isinstance(project.get("runs"), list):
            raise ProjectLoadingError(
                f"Project {project['name']} is missing a runs list."
            )

        for run_index, run in enumerate(project["runs"]):
            if not isinstance(run, dict):
                raise ProjectLoadingError(
                    f"Run at index {run_index} in project {project['name']} must be an object."
                )
            if not isinstance(run.get("label"), str) or not run["label"]:
                raise ProjectLoadingError(
                    f"Run at index {run_index} in project {project['name']} is missing a label."
                )

    return typing.cast(list[Project], data)


def first_project_with_runs(projects: list[Project]) -> Project | None:
    return next((project for project in projects if project["runs"]), None)


@functools.lru_cache
def list_projects(host: str, access_token: str) -> list[Project]:
    try:
        response = httpx.get(
            f"{host}/api/lab/projects/",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
            },
        )
    except httpx.ConnectError as e:
        raise ProjectLoadingError("Failed to connect to Euphrosyne server.") from e

    response.raise_for_status()
    try:
        data = response.json()
    except ValueError as e:
        raise ProjectLoadingError("Projects response must be valid JSON.") from e
    return validate_projects(data)
