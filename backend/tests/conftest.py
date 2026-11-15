import os
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# DATABASE_URL comes from the environment (CI) or the repository-root .env (local).
os.environ.setdefault("ENVIRONMENT", "test")


@pytest.fixture
def app() -> Iterator[FastAPI]:
    # Imported here so the environment above is set before settings are first read.
    from pitchsense.api.main import create_app

    application = create_app()
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
