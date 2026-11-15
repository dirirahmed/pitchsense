import pytest
from pydantic import ValidationError

from pitchsense.core.config import Settings

DATABASE_URL = "postgresql+psycopg://user:pass@localhost/db"


def test_cors_origins_are_split_and_trimmed() -> None:
    # _env_file=None isolates the test from any .env file on the machine.
    settings = Settings(
        _env_file=None,
        database_url=DATABASE_URL,
        cors_origins=" http://a.test, http://b.test ,,",
    )

    assert settings.cors_origin_list == ["http://a.test", "http://b.test"]


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (
            "postgresql://user:pass@ep-x.neon.tech/db?sslmode=require",
            "postgresql+psycopg://user:pass@ep-x.neon.tech/db?sslmode=require",
        ),
        ("postgres://user:pass@host/db", "postgresql+psycopg://user:pass@host/db"),
        (DATABASE_URL, DATABASE_URL),
    ],
)
def test_database_url_uses_psycopg_driver(given: str, expected: str) -> None:
    settings = Settings(_env_file=None, database_url=given)

    assert settings.database_url == expected


def test_rejects_unknown_environment() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url=DATABASE_URL,
            environment="staging",
        )
