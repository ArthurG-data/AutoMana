"""Unit tests: PaginatedResponse carries facets field."""
import pytest
from automana.api.schemas.StandardisedQueryResponse import PaginatedResponse, PaginationInfo

pytestmark = pytest.mark.unit


def test_paginated_response_facets_defaults_none():
    resp = PaginatedResponse[str](
        data=[],
        pagination=PaginationInfo(limit=20, offset=0, total_count=0, has_next=False, has_previous=False),
    )
    assert resp.facets is None


def test_paginated_response_facets_field():
    resp = PaginatedResponse[str](
        data=[],
        pagination=PaginationInfo(limit=20, offset=0, total_count=0, has_next=False, has_previous=False),
        facets={"promo_types": ["prerelease", "buyabox"]},
    )
    assert resp.facets == {"promo_types": ["prerelease", "buyabox"]}
