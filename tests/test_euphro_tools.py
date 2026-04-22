import httpx
import pytest

from data_upload.euphro_tools import (
    EuphrosyneToolsConnectionError,
    EuphrosyneToolsService,
    InitFoldersError,
)


def test_init_folders_initializes_project_and_run(httpx_mock):
    service = EuphrosyneToolsService("https://tools.example", auth=None)
    httpx_mock.add_response(
        method="POST", url="https://tools.example/data/Project A/init", status_code=204
    )
    httpx_mock.add_response(
        method="POST",
        url="https://tools.example/data/Project A/runs/Run 1/init",
        status_code=204,
    )

    assert service.init_folders("Project A", "Run 1") is None

    requests = httpx_mock.get_requests()
    assert [request.headers["Accept"] for request in requests] == [
        "application/json",
        "application/json",
    ]


def test_init_folders_tolerates_already_existing_project_and_run_folders(httpx_mock):
    service = EuphrosyneToolsService("https://tools.example", auth=None)
    detail = "The specified resource already exists"
    httpx_mock.add_response(
        method="POST",
        url="https://tools.example/data/Project A/init",
        status_code=400,
        json={"detail": detail},
    )
    httpx_mock.add_response(
        method="POST",
        url="https://tools.example/data/Project A/runs/Run 1/init",
        status_code=400,
        json={"detail": detail},
    )

    assert service.init_folders("Project A", "Run 1") is None


def test_init_folders_raises_for_project_initialization_failure(httpx_mock):
    service = EuphrosyneToolsService("https://tools.example", auth=None)
    httpx_mock.add_response(
        method="POST",
        url="https://tools.example/data/Project A/init",
        status_code=500,
        text="server error",
    )

    with pytest.raises(InitFoldersError, match="Failed to initialize project folders"):
        service.init_folders("Project A", "Run 1")


def test_init_folders_raises_for_run_initialization_failure(httpx_mock):
    service = EuphrosyneToolsService("https://tools.example", auth=None)
    httpx_mock.add_response(
        method="POST", url="https://tools.example/data/Project A/init", status_code=204
    )
    httpx_mock.add_response(
        method="POST",
        url="https://tools.example/data/Project A/runs/Run 1/init",
        status_code=500,
        text="server error",
    )

    with pytest.raises(InitFoldersError, match="Failed to initialize run folders"):
        service.init_folders("Project A", "Run 1")


def test_init_folders_wraps_project_connection_errors(httpx_mock):
    service = EuphrosyneToolsService("https://tools.example", auth=None)
    httpx_mock.add_exception(
        httpx.ConnectError("connection failed"),
        method="POST",
        url="https://tools.example/data/Project A/init",
    )

    with pytest.raises(EuphrosyneToolsConnectionError):
        service.init_folders("Project A", "Run 1")


def test_get_run_data_upload_shared_access_signature_returns_credentials(httpx_mock):
    service = EuphrosyneToolsService("https://tools.example", auth=None)
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://tools.example/data/Project A/runs/Run 1/upload/"
            "shared_access_signature?data_type=raw_data"
        ),
        json={"url": "https://storage.example/share", "token": "sas-token"},
    )

    credentials = service.get_run_data_upload_shared_access_signature(
        "Project A", "Run 1", "raw_data"
    )

    assert credentials == {"url": "https://storage.example/share", "token": "sas-token"}


def test_get_run_data_upload_shared_access_signature_raises_for_http_errors(httpx_mock):
    service = EuphrosyneToolsService("https://tools.example", auth=None)
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://tools.example/data/Project A/runs/Run 1/upload/"
            "shared_access_signature?data_type=raw_data"
        ),
        status_code=403,
        json={"detail": "forbidden"},
    )

    with pytest.raises(httpx.HTTPStatusError):
        service.get_run_data_upload_shared_access_signature(
            "Project A", "Run 1", "raw_data"
        )


def test_get_run_data_upload_shared_access_signature_wraps_connection_errors(
    httpx_mock,
):
    service = EuphrosyneToolsService("https://tools.example", auth=None)
    httpx_mock.add_exception(
        httpx.ConnectError("connection failed"),
        method="GET",
        url=(
            "https://tools.example/data/Project A/runs/Run 1/upload/"
            "shared_access_signature?data_type=raw_data"
        ),
    )

    with pytest.raises(EuphrosyneToolsConnectionError):
        service.get_run_data_upload_shared_access_signature(
            "Project A", "Run 1", "raw_data"
        )
