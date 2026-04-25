"""
Unit tests for card_catalog.card.register_external_identifier.

Scope:
  - All five behavioral paths through the service function (insert, no-op,
    unknown identifier_name, unknown card_version_id, repo-level DB error).
  - ServiceRegistry invariants (registration, db_repositories, transaction flag).

Not in scope:
  - Repository SQL correctness — that belongs in the integration suite.
  - Log-message content — incidental to behavior, would rot on every wording change.
"""
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

# Importing the module causes @ServiceRegistry.register to execute, which is
# required for the invariant assertions below.
import automana.core.services.card_catalog.card_service as card_service
from automana.core.repositories.card_catalog.card_repository import CardReferenceRepository
from automana.core.exceptions.service_layer_exceptions.card_catalogue.card_exception import (
    CardInsertError,
    CardNotFoundError,
    UnknownIdentifierNameError,
)
from automana.core.service_registry import ServiceRegistry

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_CARD_VERSION_ID = UUID("12345678-1234-5678-1234-567812345678")
_IDENTIFIER_NAME = "scryfall_id"
_VALUE = "abc-123"

Outcome = CardReferenceRepository.ExternalIdentifierRegistration


def _make_repo(*, ref_found: bool, card_version_exists: bool, inserted: bool) -> AsyncMock:
    """Return a mocked CardReferenceRepository pre-configured with the given outcome."""
    repo = AsyncMock(spec=CardReferenceRepository)
    repo.register_external_identifier.return_value = Outcome(
        ref_found=ref_found,
        card_version_exists=card_version_exists,
        inserted=inserted,
    )
    return repo


# ---------------------------------------------------------------------------
# Behavioral tests
# ---------------------------------------------------------------------------

class TestRegisterExternalIdentifierHappyPaths:
    async def test_new_insert_returns_true_and_calls_repo_with_exact_args(self):
        """When the repo signals a fresh row was written, service returns True."""
        repo = _make_repo(ref_found=True, card_version_exists=True, inserted=True)

        result = await card_service.register_external_identifier(
            card_repository=repo,
            card_version_id=_CARD_VERSION_ID,
            identifier_name=_IDENTIFIER_NAME,
            value=_VALUE,
        )

        assert result is True
        repo.register_external_identifier.assert_awaited_once_with(
            card_version_id=_CARD_VERSION_ID,
            identifier_name=_IDENTIFIER_NAME,
            value=_VALUE,
        )

    async def test_idempotent_noop_returns_false_without_raising(self):
        """When the (card_version_id, ref_id) pair already exists, service
        returns False — the ON CONFLICT DO NOTHING no-op case."""
        repo = _make_repo(ref_found=True, card_version_exists=True, inserted=False)

        result = await card_service.register_external_identifier(
            card_repository=repo,
            card_version_id=_CARD_VERSION_ID,
            identifier_name=_IDENTIFIER_NAME,
            value=_VALUE,
        )

        assert result is False


class TestRegisterExternalIdentifierFailurePaths:
    async def test_unknown_identifier_name_raises_with_name_in_message(self):
        """ref_found=False → UnknownIdentifierNameError; message must mention
        the bad identifier_name so the caller can act on it."""
        repo = _make_repo(ref_found=False, card_version_exists=True, inserted=False)

        with pytest.raises(UnknownIdentifierNameError, match=_IDENTIFIER_NAME):
            await card_service.register_external_identifier(
                card_repository=repo,
                card_version_id=_CARD_VERSION_ID,
                identifier_name=_IDENTIFIER_NAME,
                value=_VALUE,
            )

    async def test_unknown_card_version_raises_with_id_in_message(self):
        """card_version_exists=False → CardNotFoundError; message must mention
        the card_version_id so the caller can identify which ID was invalid."""
        repo = _make_repo(ref_found=True, card_version_exists=False, inserted=False)

        with pytest.raises(CardNotFoundError, match=str(_CARD_VERSION_ID)):
            await card_service.register_external_identifier(
                card_repository=repo,
                card_version_id=_CARD_VERSION_ID,
                identifier_name=_IDENTIFIER_NAME,
                value=_VALUE,
            )

    async def test_ref_found_checked_before_card_version_when_both_missing(self):
        """Both ref_found=False and card_version_exists=False: service must raise
        UnknownIdentifierNameError (not CardNotFoundError) — the docstring
        documents this ordering so callers get the more informative error."""
        repo = _make_repo(ref_found=False, card_version_exists=False, inserted=False)

        with pytest.raises(UnknownIdentifierNameError):
            await card_service.register_external_identifier(
                card_repository=repo,
                card_version_id=_CARD_VERSION_ID,
                identifier_name=_IDENTIFIER_NAME,
                value=_VALUE,
            )

    async def test_db_error_wrapped_in_card_insert_error_with_context(self):
        """A repo-side exception must be translated to CardInsertError with the
        original message plus enough context (card_version_id, identifier_name)
        for an operator to diagnose."""
        repo = AsyncMock(spec=CardReferenceRepository)
        repo.register_external_identifier.side_effect = Exception("boom")

        with pytest.raises(CardInsertError) as exc_info:
            await card_service.register_external_identifier(
                card_repository=repo,
                card_version_id=_CARD_VERSION_ID,
                identifier_name=_IDENTIFIER_NAME,
                value=_VALUE,
            )

        error_msg = str(exc_info.value)
        assert "boom" in error_msg
        assert str(_CARD_VERSION_ID) in error_msg
        assert _IDENTIFIER_NAME in error_msg


# ---------------------------------------------------------------------------
# ServiceRegistry invariants
# ---------------------------------------------------------------------------

class TestServiceRegistryInvariants:
    def test_service_registration(self):
        cfg = ServiceRegistry.get("card_catalog.card.register_external_identifier")
        assert cfg is not None
        assert cfg.db_repositories == ["card"]
