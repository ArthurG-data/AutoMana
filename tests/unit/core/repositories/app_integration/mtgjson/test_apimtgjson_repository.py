"""Unit tests for ApimtgjsonRepository.

W1: name() is a plain method, not a @property. This breaks any caller that
    accesses repo.name (e.g. service registry lookups that treat name as a
    property consistent with other repositories).
"""
import pytest

from automana.core.repositories.app_integration.mtgjson.Apimtgjson_repository import (
    ApimtgjsonRepository,
)


def test_name_is_a_property():
    """W1: ApimtgjsonRepository.name must be a @property, not a plain method."""
    assert isinstance(
        ApimtgjsonRepository.__dict__.get("name"), property
    ), "name should be a @property so repo.name returns the string directly"


def test_name_returns_correct_string():
    repo = ApimtgjsonRepository(environment="test")
    assert repo.name == "ApimtgjsonRepository"
