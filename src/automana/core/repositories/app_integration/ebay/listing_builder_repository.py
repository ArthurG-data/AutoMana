from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from automana.core.models.ebay.listing_inputs import CardData
from automana.core.repositories.abstract_repositories.AbstractDBRepository import (
    AbstractRepository,
)

logger = logging.getLogger(__name__)

_FETCH_CARD_SQL = """
SELECT
    v.card_version_id,
    v.card_name,
    v.set_name,
    v.set_code,
    v.collector_number,
    v.mana_cost,
    v.oracle_text,
    v.type_line,
    v.rarity_name,
    v.color_identity,
    v.power,
    v.toughness,
    v.loyalty,
    COALESCE(
        v.illustrations -> 0 -> 'image_uris' ->> 'large',
        v.illustrations -> 0 -> 'image_uris' ->> 'normal'
    ) AS image_url,
    v.card_faces -> 0 ->> 'flavor_text' AS flavor_text,
    ei.value AS scryfall_id
FROM card_catalog.v_card_versions_complete v
LEFT JOIN card_catalog.card_external_identifier ei
    ON ei.card_version_id = v.card_version_id
    AND ei.card_identifier_ref_id = (
        SELECT card_identifier_ref_id
        FROM card_catalog.card_identifier_ref
        WHERE identifier_name = 'scryfall_id'
    )
WHERE v.card_version_id = $1
"""


class EbayListingBuilderRepository(AbstractRepository):

    @property
    def name(self) -> str:
        return "EbayListingBuilderRepository"

    async def fetch_card_data(self, card_version_id: UUID) -> Optional[CardData]:
        """Return CardData for the given card version, or None if not found."""
        rows = await self.execute_query(_FETCH_CARD_SQL, (card_version_id,))
        if not rows:
            logger.info(
                "ebay_listing_builder_card_not_found",
                extra={"card_version_id": str(card_version_id)},
            )
            return None
        row = rows[0]
        return CardData(
            card_version_id=row["card_version_id"],
            card_name=row["card_name"],
            set_name=row["set_name"],
            set_code=row["set_code"],
            collector_number=row["collector_number"] or "",
            mana_cost=row["mana_cost"],
            oracle_text=row["oracle_text"],
            type_line=row["type_line"],
            rarity_name=row["rarity_name"],
            color_identity=list(row["color_identity"] or []),
            power=row["power"],
            toughness=row["toughness"],
            loyalty=row["loyalty"],
            image_url=row["image_url"],
            flavor_text=row["flavor_text"],
            scryfall_id=row["scryfall_id"],
        )
