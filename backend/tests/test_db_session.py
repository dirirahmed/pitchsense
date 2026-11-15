import pytest

from pitchsense.db.session import build_engine, database_is_available, get_engine


def test_unreachable_database_reports_unavailable() -> None:
    # Port 1 on localhost refuses connections immediately: a real failure, not a mock.
    engine = build_engine("postgresql+psycopg://user:pass@127.0.0.1:1/missing")

    assert database_is_available(engine) is False


@pytest.mark.integration
def test_configured_database_is_available() -> None:
    assert database_is_available(get_engine()) is True
