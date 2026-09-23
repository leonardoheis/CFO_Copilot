import pytest

from app.data.companies import CompanyRegistry
from app.settings import Settings


@pytest.fixture
def vcr_config() -> dict[str, object]:
    return {
        "filter_query_parameters": ["api_key"],
        "filter_headers": ["User-Agent"],
    }


@pytest.fixture
def company_registry() -> CompanyRegistry:
    return CompanyRegistry.from_path(Settings.COMPANY_REGISTRY_PATH)
