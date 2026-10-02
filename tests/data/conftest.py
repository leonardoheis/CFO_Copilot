import json

import pytest

from app.data.companies import CompanyRegistry
from app.data.sources.sec_edgar.concepts import DILUTED_SHARES_FALLBACK, TAG_CHAINS
from app.settings import Settings

_RECORDED_TAGS = frozenset(
    tag for spec in (*TAG_CHAINS.values(), DILUTED_SHARES_FALLBACK) for tag in spec.tags
)


def _without_unread_tags(
    response: dict[str, dict[str, object]],
) -> dict[str, dict[str, object]]:
    """Trim a ~5 MB companyfacts body to the tags the chains read before recording.

    Returns:
        The response, with any companyfacts body reduced to the chain tags.
    """
    body = response["body"]["string"]
    text = body.decode("utf-8") if isinstance(body, bytes) else str(body)
    if '"facts"' not in text[:200]:
        return response
    payload = json.loads(text)
    us_gaap = payload.get("facts", {}).get("us-gaap", {})
    payload["facts"] = {
        "us-gaap": {
            tag: facts for tag, facts in us_gaap.items() if tag in _RECORDED_TAGS
        },
    }
    response["body"]["string"] = json.dumps(payload).encode("utf-8")
    return response


@pytest.fixture
def vcr_config() -> dict[str, object]:
    return {
        "filter_query_parameters": ["api_key"],
        "filter_headers": ["User-Agent"],
        "decode_compressed_response": True,
        "before_record_response": _without_unread_tags,
    }


@pytest.fixture
def company_registry() -> CompanyRegistry:
    return CompanyRegistry.from_path(Settings.COMPANY_REGISTRY_PATH)
