import json
import logging
import os

from automana.core.repositories.abstract_repositories.AbstractAPIRepository import BaseApiClient

logger = logging.getLogger(__name__)


class ShopifyAPIRepository(BaseApiClient):

    def __init__(self, **kwargs):
        super().__init__(timeout=30)

    @property
    def name(self) -> str:
        return "ShopifyAPIRepository"

    def _get_base_url(self) -> str:
        return ""

    async def fetch_products_pages(self, api_url: str, source_id: int, data_root: str) -> tuple[str, int]:
        """Paginate /products.json and write each page as page_N_products.json.

        Returns (out_dir, page_count).
        """
        out_dir = os.path.join(data_root, f"{source_id}_fetch")
        os.makedirs(out_dir, exist_ok=True)
        page = 0
        next_url = f"{api_url.rstrip('/')}/products.json?limit=250"

        async with self:
            while next_url:
                response = await self.send("GET", next_url)
                response.raise_for_status()
                data = response.json()
                products = data.get("products") or data.get("items") or []
                if not products:
                    break
                page_path = os.path.join(out_dir, f"page_{page}_products.json")
                with open(page_path, "w", encoding="utf-8") as f:
                    json.dump({"items": products}, f)
                page += 1
                link_header = response.headers.get("link", "")
                next_url = None
                for part in link_header.split(","):
                    if 'rel="next"' in part:
                        next_url = part.split(";")[0].strip().strip("<>")
                        break

        logger.info("shopify_fetch_complete", extra={"source_id": source_id, "pages": page})
        return out_dir, page
