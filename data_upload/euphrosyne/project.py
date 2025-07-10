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


@functools.lru_cache
def list_projects(host: str, access_token: str) -> list[Project]:
    return httpx.get(
        f"{host}/api/lab/projects/",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
        },
    ).json()
