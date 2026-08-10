import pytest


@pytest.fixture
def vcr_config() -> dict[str, object]:
    return {
        "filter_query_parameters": ["api_key"],
        "filter_headers": ["User-Agent"],
    }
