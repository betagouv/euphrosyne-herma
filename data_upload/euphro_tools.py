import typing

import httpx


class SASTokenCredentials(typing.TypedDict):
    url: str
    token: str


class InitFoldersError(Exception):
    pass


class EuphrosyneToolsConnectionError(Exception):
    """Custom exception for Euphrosyne tools connection errors."""

    def __init__(self):
        super().__init__(
            "Failed to connect to Euphrosyne tools server. Please check your connection and try again."
        )


class EuphrosyneToolsService:
    def __init__(self, host: str, auth: httpx.Auth):
        self.host = host
        self.auth = auth

    def init_folders(self, project_name: str, run_name: str) -> str:
        """Initialize the project and run data folders."""

        # Project folder
        try:
            response = httpx.post(
                f"{self.host}/data/{project_name}/init",
                headers={
                    "Accept": "application/json",
                },
                auth=self.auth,
            )
        except httpx.ConnectError as e:
            raise EuphrosyneToolsConnectionError() from e

        # TODO : handle folder already created
        if response.status_code == 400:
            message = response.json().get("detail")
            if not message or not "The specified resource already exists" in message:
                raise InitFoldersError(f"Failed to initialize project folders")
        elif response.status_code != 204:
            raise InitFoldersError(
                f"Failed to initialize project folders: {response.text}"
            )

        # Run data folders
        response = httpx.post(
            f"{self.host}/data/{project_name}/runs/{run_name}/init",
            headers={
                "Accept": "application/json",
            },
            auth=self.auth,
        )
        # TODO : handle folder already created
        if response.status_code == 400:
            message = response.json().get("detail")
            if not message or not "The specified resource already exists" in message:
                raise InitFoldersError(
                    f"Failed to initialize run folders: {response.text}"
                )
        elif response.status_code != 204:
            raise InitFoldersError(f"Failed to initialize run folders: {response.text}")

    def get_run_data_upload_shared_access_signature(
        self, project_name: str, run_name: str, data_type: str
    ) -> SASTokenCredentials:
        """Return a token used to upload run data to file storage."""
        try:
            response = httpx.get(
                f"{self.host}/data/{project_name}/runs/{run_name}/upload/shared_access_signature?data_type={data_type}",
                headers={
                    "Accept": "application/json",
                },
                auth=self.auth,
            )
        except httpx.ConnectError as e:
            raise EuphrosyneToolsConnectionError() from e
        response.raise_for_status()
        return SASTokenCredentials(**response.json())
