# Shopify Integration Guide

## Overview

The Shopify integration allows AutoMana to sync card inventory and pricing data bidirectionally with Shopify storefronts. The system handles OAuth authentication, product catalog sync, price updates, and order/inventory webhooks for real-time synchronization.

**Key capabilities:**
- OAuth 2.0 authorization with custom app scopes
- Product and inventory sync (bulk and incremental)
- Price discovery and competitive analysis
- Market-based pricing (USD, GBP, EUR, etc.)
- Webhook-based inventory updates
- Collection management and theme customization
- Stock level aggregation across fulfillment locations

---

## Architecture Overview

### Shopify Integration Flow

```
┌──────────────────────────────────────────────────────────────────────┐
│ Shopify Admin API (GraphQL)                                            │
│  - Products (SKU, title, collections)                                  │
│  - Variants (price, weight, barcode)                                   │
│  - Inventory Levels (location, qty available)                          │
│  - Orders (for demand signals)                                         │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│ AutoMana Shopify Service Layer                                         │
│  - OAuth flow (install → authorize → token cache)                      │
│  - Product sync (parse SKU → card_version_id)                          │
│  - Inventory aggregation (multi-location stock)                        │
│  - Price sync (local prices → Shopify variant updates)                 │
│  - Webhook processing (product/inventory changes)                      │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│ PostgreSQL Staging Schemas                                             │
│  - staging.shopify_products (raw product sync)                         │
│  - staging.shopify_inventory (inventory levels per location)           │
│  - staging.shopify_prices (variant prices)                             │
│  - pricing.source_product (linked to local products)                   │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│ AutoMana Analytics Layer                                               │
│  - Inventory visibility across storefronts                             │
│  - Price elasticity analysis (Shopify vs. TCGPlayer vs. eBay)          │
│  - Demand signals (order history)                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### Layered Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│ API Router Layer (data_loading.py)                                    │
│  - Shopify product sync endpoints                                      │
│  - Webhook receivers (inventory/product changes)                       │
│  - Price update endpoints                                              │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Service Layer (services/app_integration/shopify/)                     │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │ collection_service.py                                            │ │
│  │  - List collections                                              │ │
│  │  - Create/update collections                                     │ │
│  │  - Link products to collections                                  │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │ product_service.py                                               │ │
│  │  - Parse product SKU to card_version_id                          │ │
│  │  - Sync product metadata                                         │ │
│  │  - Handle variant creation                                       │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │ market_service.py                                                │ │
│  │  - Manage markets (countries, currencies)                        │ │
│  │  - Market-specific pricing                                       │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │ data_staging_service.py                                          │ │
│  │  - Inventory aggregation logic                                   │ │
│  │  - Warehouse-to-Shopify mapping                                  │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Repository Layer                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │ API: ShopifyGraphQLRepository                                    │ │
│  │  - Execute GraphQL queries against Shopify Admin API              │ │
│  │  - Parse responses into Python dicts                             │ │
│  │  - Handle pagination (cursors)                                   │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │ DB: ProductRepository, CollectionRepository, etc.                │ │
│  │  - Staging table CRUD                                            │ │
│  │  - Bulk COPY operations                                          │ │
│  │  - Price table updates                                           │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│ External APIs                                                          │
│  - https://admin-api.shopify.com/graphql.json (GraphQL endpoint)      │
│  - https://{store}.myshopify.com/webhooks (webhook delivery)         │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. OAuth Authentication

**File:** `src/automana/api/routers/integrations/shopify/auth.py`

Shopify uses OAuth 2.0 with public vs. custom app modes:

```python
# Public App OAuth Flow (user installs on their store)
@ServiceRegistry.register("integrations.shopify.start_oauth_flow")
async def start_oauth_flow(
    app_repository: ShopifyAppRepository,
    user_id: str,
    store_url: str  # e.g., "mystore.myshopify.com"
) -> Dict[str, str]:
    """
    Generate OAuth URL for user to authorize app on their store.
    
    User flow:
    1. User enters store URL (mystore.myshopify.com)
    2. Redirect to: 
       https://mystore.myshopify.com/admin/oauth/authorize
       ?client_id=...
       &scope=read_products,write_products,read_inventory
       &redirect_uri=...
    3. User authorizes
    4. Redirected to callback with code
    """
    
    state = secrets.token_urlsafe(32)
    await redis_client.setex(
        f"shopify_oauth:{state}",
        600,  # 10 min window
        json.dumps({
            "user_id": user_id,
            "store_url": store_url,
            "created_at": datetime.utcnow().isoformat()
        })
    )
    
    app_config = app_repository.get_config()  # Public app settings
    
    oauth_url = (
        f"https://{store_url}/admin/oauth/authorize"
        f"?client_id={app_config.client_id}"
        f"&scope={','.join(app_config.scopes)}"
        f"&redirect_uri={app_config.redirect_uri}"
        f"&state={state}"
    )
    
    return {"oauth_url": oauth_url}

@ServiceRegistry.register("integrations.shopify.process_callback")
async def process_callback(
    app_repository: ShopifyAppRepository,
    user_app_repo: UserShopifyAppRepository,
    code: str,
    state: str,
    shop: str  # myshopify.com URL from Shopify
) -> Dict[str, Any]:
    """
    Exchange code for access token and store.
    
    Args:
        code: Authorization code from Shopify
        state: CSRF token (validate against Redis)
        shop: Store's myshopify.com domain
    """
    # Verify state
    state_data = await redis_client.get(f"shopify_oauth:{state}")
    if not state_data:
        raise ValueError("Invalid or expired state")
    
    state_json = json.loads(state_data)
    app_config = app_repository.get_config()
    
    # Exchange code for access token (server-to-server)
    token_response = await app_repository.exchange_code(
        code=code,
        shop=shop,
        client_id=app_config.client_id,
        client_secret=app_config.client_secret
    )
    
    # Store access token in user's app linkage
    await user_app_repo.store_tokens(
        user_id=state_json["user_id"],
        shop_url=shop,
        access_token=token_response["access_token"],
        scopes=token_response.get("scopes", app_config.scopes)
    )
    
    # Cache token in Redis (no expiration for custom tokens)
    await redis_client.set(
        f"shopify_token:{shop}",
        token_response["access_token"]
    )
    
    return {
        "shop": shop,
        "access_token": token_response["access_token"]
    }
```

### 2. GraphQL Repository

**File:** `src/automana/core/repositories/app_integration/shopify/ShopifyGraphQLRepository.py`

Shopify's Admin API uses GraphQL exclusively:

```python
class ShopifyGraphQLRepository(BaseApiClient):
    """Execute GraphQL queries against Shopify Admin API."""
    
    def __init__(self, shop_url: str, access_token: str, timeout: int = 30):
        self.shop_url = shop_url
        self.access_token = access_token
        self.endpoint = f"https://{shop_url}/admin/api/2024-01/graphql.json"
        self.timeout = timeout
    
    async def execute_query(
        self,
        query: str,
        variables: Dict = None
    ) -> Dict[str, Any]:
        """
        Execute GraphQL query.
        
        Args:
            query: GraphQL query string
            variables: Query variables dict
            
        Returns:
            Response data (errors field present if failures)
        """
        headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": self.access_token
        }
        
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        
        response = await self._make_post_request(
            self.endpoint,
            json=payload,
            headers=headers
        )
        
        # Check for GraphQL errors
        if response.get("errors"):
            raise ShopifyGraphQLError(response["errors"])
        
        return response.get("data", {})
    
    async def paginate_query(
        self,
        query: str,
        path: str,  # e.g., "products.edges"
        page_size: int = 100,
        max_pages: int = None
    ):
        """
        Paginate through results using cursor-based pagination.
        
        Yields:
            Individual nodes from the paginated result set
        """
        first = min(page_size, 250)  # Shopify max is 250
        after = None
        page = 0
        
        while True:
            variables = {"first": first}
            if after:
                variables["after"] = after
            
            # Fetch page
            result = await self.execute_query(query, variables)
            
            # Navigate to connection edge
            connection = self._navigate_path(result, path)
            if not connection:
                break
            
            page_edges = connection.get("edges", [])
            
            # Yield each node
            for edge in page_edges:
                yield edge.get("node")
            
            # Check for next page
            page_info = connection.get("pageInfo", {})
            if not page_info.get("hasNextPage"):
                break
            
            after = page_info.get("endCursor")
            page += 1
            
            if max_pages and page >= max_pages:
                break
```

### 3. Product & Inventory Sync

**File:** `src/automana/core/services/app_integration/shopify/product_service.py`

```python
@ServiceRegistry.register(
    "integrations.shopify.sync_products",
    api_repositories=["shopify"],
    db_repositories=["shopify_product"],
    storage_services=["shopify"]
)
async def sync_products(
    shopify_repo: ShopifyGraphQLRepository,
    product_repo: ProductRepository,
    user_id: str,
    shop_url: str,
    force_full_sync: bool = False
) -> Dict[str, Any]:
    """
    Sync Shopify products to staging table.
    
    Process:
    1. Query Shopify for products (with variants)
    2. Parse SKU field to extract card_version_id
    3. Batch insert into staging.shopify_products
    4. Track last_sync timestamp for incremental updates
    
    Returns:
        {
            "products_synced": int,
            "products_failed": int,
            "last_sync": datetime,
            "new_unmapped": List[{gid, title, sku}]  # SKUs we couldn't map
        }
    """
    
    # GraphQL query to fetch products with all variants
    PRODUCTS_QUERY = """
    query GetProducts($first: Int!, $after: String, $query: String) {
      products(first: $first, after: $after, query: $query) {
        edges {
          node {
            id
            title
            vendor
            productType
            handle
            variants(first: 100) {
              edges {
                node {
                  id
                  title
                  sku
                  barcode
                  price
                  compareAtPrice
                  inventoryQuantity
                  weight
                }
              }
            }
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
    """
    
    if force_full_sync:
        query_filter = ""
    else:
        # Incremental: only products updated since last sync
        last_sync = await product_repo.get_last_sync_time(shop_url)
        query_filter = f' updated_at:>"{last_sync.isoformat()}"'
    
    synced = []
    failed = []
    unmapped_skus = []
    
    # Paginate through products
    async for product in shopify_repo.paginate_query(
        PRODUCTS_QUERY,
        path="products.edges",
        page_size=100,
        variables={"query": query_filter}
    ):
        try:
            # Parse variants and map SKUs
            for variant in product.get("variants", {}).get("edges", []):
                variant_node = variant.get("node", {})
                sku = variant_node.get("sku", "")
                
                if not sku:
                    unmapped_skus.append({
                        "gid": variant_node.get("id"),
                        "title": product.get("title"),
                        "sku": sku
                    })
                    continue
                
                # Map SKU to card_version_id
                card_version_id = await map_sku_to_card(sku)
                
                if not card_version_id:
                    unmapped_skus.append({
                        "gid": variant_node.get("id"),
                        "title": product.get("title"),
                        "sku": sku
                    })
                    continue
                
                # Insert staging record
                staging_record = {
                    "shopify_product_id": product.get("id"),
                    "shopify_variant_id": variant_node.get("id"),
                    "card_version_id": card_version_id,
                    "title": product.get("title"),
                    "variant_title": variant_node.get("title"),
                    "sku": sku,
                    "price_cents": int(float(variant_node.get("price", 0)) * 100),
                    "inventory_qty": variant_node.get("inventoryQuantity", 0),
                    "synced_at": datetime.utcnow()
                }
                
                synced.append(staging_record)
        
        except Exception as e:
            logger.error("Product sync error", extra={
                "shop": shop_url,
                "product_id": product.get("id"),
                "error": str(e)
            })
            failed.append(product.get("id"))
    
    # Bulk insert to staging table
    if synced:
        await product_repo.bulk_insert_products(synced)
    
    await product_repo.update_last_sync_time(shop_url)
    
    return {
        "products_synced": len(synced),
        "products_failed": len(failed),
        "unmapped_count": len(unmapped_skus),
        "unmapped_skus": unmapped_skus[:10]  # Return sample
    }
```

### 4. Inventory Aggregation

**File:** `src/automana/core/services/app_integration/shopify/data_staging_service.py`

```python
@ServiceRegistry.register(
    "integrations.shopify.aggregate_inventory",
    api_repositories=["shopify"],
    db_repositories=["shopify_inventory"]
)
async def aggregate_inventory(
    shopify_repo: ShopifyGraphQLRepository,
    inventory_repo: InventoryRepository,
    shop_url: str
) -> Dict[str, Any]:
    """
    Aggregate inventory levels across Shopify locations.
    
    Query inventory levels per variant across all fulfillment locations:
    - Default (warehouse)
    - Retail store locations
    - Dropshipper locations
    
    Returns total available qty per variant.
    """
    
    INVENTORY_QUERY = """
    query GetInventory($first: Int!, $after: String) {
      inventoryLevels(first: $first, after: $after) {
        edges {
          node {
            id
            quantities(names: ["available"]) {
              name
              quantity
            }
            location {
              id
              name
              isActive
            }
            item {
              variant {
                id
                sku
              }
            }
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
    """
    
    inventory_by_sku = {}
    
    # Paginate through inventory levels
    async for level in shopify_repo.paginate_query(
        INVENTORY_QUERY,
        path="inventoryLevels.edges"
    ):
        sku = level.get("item", {}).get("variant", {}).get("sku")
        if not sku:
            continue
        
        location = level.get("location", {})
        quantities = level.get("quantities", [])
        available = 0
        
        for qty_entry in quantities:
            if qty_entry.get("name") == "available":
                available = qty_entry.get("quantity", 0)
        
        if sku not in inventory_by_sku:
            inventory_by_sku[sku] = {
                "locations": [],
                "total_available": 0
            }
        
        inventory_by_sku[sku]["locations"].append({
            "location_id": location.get("id"),
            "location_name": location.get("name"),
            "available": available
        })
        inventory_by_sku[sku]["total_available"] += available
    
    # Insert to staging
    staging_records = []
    for sku, inv_data in inventory_by_sku.items():
        staging_records.append({
            "shop_url": shop_url,
            "sku": sku,
            "total_available": inv_data["total_available"],
            "location_detail": json.dumps(inv_data["locations"]),
            "synced_at": datetime.utcnow()
        })
    
    if staging_records:
        await inventory_repo.bulk_insert_inventory(staging_records)
    
    return {
        "inventory_records_synced": len(staging_records)
    }
```

### 5. Market Management

**File:** `src/automana/core/models/shopify/Market.py`

Shopify Markets allow market-specific pricing (e.g., US vs. UK):

```python
class Market(BaseModel):
    """Shopify market definition (country + currency)."""
    name: str                      # e.g., "United States"
    country_code: str              # ISO 3166-1 alpha-2 (US, GB, etc.)
    city: Optional[str] = None     # For multi-city markets
    currency: str                  # ISO 4217 (USD, GBP, EUR)
    api_url: str                   # Market API endpoint
    
class MarketInDb(Market):
    market_id: int
    created_at: datetime
    updated_at: datetime

@ServiceRegistry.register(
    "integrations.shopify.update_market_prices",
    api_repositories=["shopify"],
    db_repositories=["shopify_price"]
)
async def update_market_prices(
    shopify_repo: ShopifyGraphQLRepository,
    price_repo: PriceRepository,
    shop_url: str,
    market_id: str,  # Shopify gid
    price_updates: List[Dict]  # [{variant_id, price_cents}, ...]
) -> Dict[str, Any]:
    """
    Update variant prices for specific market.
    
    Note: Shopify Markets use PriceList feature for per-market pricing.
    This creates/updates price rules in the market's price list.
    """
    
    MUTATION = """
    mutation UpdateVariantPrice(
        $variantId: ID!,
        $price: String!,
        $marketId: ID!
    ) {
      productVariantUpdate(
        input: {
          id: $variantId,
          marketRegionalPricing: [{
            marketId: $marketId,
            price: $price
          }]
        }
      ) {
        productVariant {
          id
          title
          price
        }
        userErrors {
          field
          message
        }
      }
    }
    """
    
    updated = []
    failed = []
    
    for update in price_updates:
        try:
            result = await shopify_repo.execute_query(
                MUTATION,
                variables={
                    "variantId": update["variant_id"],
                    "price": str(update["price_cents"] / 100),  # Convert to currency
                    "marketId": market_id
                }
            )
            
            if result.get("productVariantUpdate", {}).get("userErrors"):
                failed.append(update["variant_id"])
            else:
                updated.append(update["variant_id"])
        
        except Exception as e:
            logger.error("Market price update failed", extra={
                "shop": shop_url,
                "variant_id": update["variant_id"],
                "error": str(e)
            })
            failed.append(update["variant_id"])
    
    return {
        "updated": len(updated),
        "failed": len(failed)
    }
```

---

## Webhook Integration

### Webhook Receivers

**File:** `src/automana/api/routers/integrations/shopify/webhooks.py`

Shopify sends webhooks for real-time updates:

```python
@shopify_webhooks_router.post("/products/update")
async def handle_product_update(
    request: Request,
    service_manager: ServiceManagerDep
):
    """
    Webhook: product.update
    Triggered when product or variant is modified.
    """
    # Verify X-Shopify-Hmac-SHA256 header
    payload = await request.body()
    if not verify_shopify_webhook(payload, request.headers):
        raise HTTPException(401, detail="Invalid webhook signature")
    
    data = await request.json()
    
    # Queue re-sync for this product
    await service_manager.execute_service(
        "integrations.shopify.sync_single_product",
        shop_url=data["shop"]["myshopify_domain"],
        product_id=data["id"]
    )
    
    return {"status": "ok"}

@shopify_webhooks_router.post("/inventory-levels/update")
async def handle_inventory_update(
    request: Request,
    service_manager: ServiceManagerDep
):
    """
    Webhook: inventory_levels/update
    Triggered when stock level changes.
    """
    payload = await request.body()
    if not verify_shopify_webhook(payload, request.headers):
        raise HTTPException(401, detail="Invalid webhook signature")
    
    data = await request.json()
    
    # Update inventory in staging
    await service_manager.execute_service(
        "integrations.shopify.update_single_inventory",
        variant_id=data["variant_id"],
        location_id=data["location_id"],
        available_qty=data["available"]
    )
    
    return {"status": "ok"}
```

### Webhook Registration

Shopify webhooks must be registered during app install:

```python
async def register_webhooks(
    shopify_repo: ShopifyGraphQLRepository,
    shop_url: str
) -> Dict[str, Any]:
    """Register required webhooks when user installs app."""
    
    REGISTER_MUTATION = """
    mutation CreateWebhook($topic: WebhookSubscriptionTopic!, $endpoint: URL!) {
      webhookSubscriptionCreate(
        topic: $topic,
        webhookSubscription: {
          callbackUrl: $endpoint
        }
      ) {
        webhookSubscription {
          id
          topic
          endpoint {
            __typename
          }
        }
        userErrors {
          field
          message
        }
      }
    }
    """
    
    webhook_topics = [
        "PRODUCTS_UPDATE",
        "INVENTORY_LEVELS_UPDATE",
        "ORDERS_CREATE",
        "ORDERS_UPDATED"
    ]
    
    registered = []
    
    for topic in webhook_topics:
        try:
            result = await shopify_repo.execute_query(
                REGISTER_MUTATION,
                variables={
                    "topic": topic,
                    "endpoint": f"{WEBHOOK_BASE_URL}/integrations/shopify/webhooks/{topic.lower()}"
                }
            )
            registered.append(topic)
        except Exception as e:
            logger.error("Webhook registration failed", extra={
                "shop": shop_url,
                "topic": topic,
                "error": str(e)
            })
    
    return {
        "registered_webhooks": registered,
        "failed_count": len(webhook_topics) - len(registered)
    }
```

---

## Production Considerations

### 1. Rate Limiting

Shopify enforces API call budgets:

```python
class ShopifyRateLimiter:
    """
    Shopify uses a leaky bucket rate limiter with 2 second refill.
    Each API call costs points; max 40 points per request.
    """
    
    async def check_budget(self, shopify_repo: ShopifyGraphQLRepository) -> Dict:
        """
        Query API rate limit status.
        
        Query:
        query {
          appInstallation {
            apiCallLimitPerApiCallBudgetResetCounter {
              budget
              currentlyAvailable
              restoreRate
            }
          }
        }
        """
        
        BUDGET_QUERY = """
        query {
          appInstallation {
            apiCallLimitPerApiCallBudgetResetCounter {
              budget
              currentlyAvailable
              restoreRate
            }
          }
        }
        """
        
        result = await shopify_repo.execute_query(BUDGET_QUERY)
        budget_info = result["appInstallation"]["apiCallLimitPerApiCallBudgetResetCounter"]
        
        # Warn if < 20% available
        available_pct = budget_info["currentlyAvailable"] / budget_info["budget"]
        if available_pct < 0.2:
            logger.warning("Shopify API budget low", extra={
                "available": budget_info["currentlyAvailable"],
                "budget": budget_info["budget"]
            })
        
        return budget_info
```

### 2. Multi-Store Tenancy

Each user can link multiple Shopify stores:

```python
# User has 3 Shopify stores
stores = await user_app_repo.get_linked_stores(user_id)
# [
#   {"shop_url": "store1.myshopify.com", "token": "..."},
#   {"shop_url": "store2.myshopify.com", "token": "..."},
#   {"shop_url": "store3.myshopify.com", "token": "..."}
# ]

# Sync each store independently
for store in stores:
    await sync_products(store["shop_url"], store["token"])
```

### 3. Webhook Security

Always verify webhook signatures:

```python
import hmac
import hashlib
import base64

def verify_shopify_webhook(payload: bytes, headers: dict) -> bool:
    """
    Verify X-Shopify-Hmac-SHA256 header.
    
    Shopify signs: HMAC-SHA256(payload, client_secret)
    """
    hmac_header = headers.get("X-Shopify-Hmac-SHA256")
    if not hmac_header:
        return False
    
    client_secret = settings.SHOPIFY_CLIENT_SECRET.encode()
    expected_hmac = base64.b64encode(
        hmac.new(client_secret, payload, hashlib.sha256).digest()
    ).decode()
    
    return hmac.compare_digest(expected_hmac, hmac_header)
```

### 4. Bulk Operations

For large syncs, use Shopify's Bulk Operations API (async):

```python
async def bulk_sync_products(
    shopify_repo: ShopifyGraphQLRepository,
    shop_url: str
) -> Dict[str, Any]:
    """
    Use Bulk Operations API for full product sync.
    
    Advantage: No API budget consumed; results downloaded via SFTP.
    Drawback: ~5 min processing time.
    """
    
    CREATE_BULK_MUTATION = """
    mutation {
      bulkOperationRunQuery(
        query: \"\"\"
          {
            products(first: 100) {
              edges {
                node {
                  id
                  title
                  variants {
                    id
                    sku
                    price
                  }
                }
              }
            }
          }
        \"\"\"
      ) {
        bulkOperation {
          id
          status
        }
      }
    }
    """
    
    result = await shopify_repo.execute_query(CREATE_BULK_MUTATION)
    operation_id = result["bulkOperationRunQuery"]["bulkOperation"]["id"]
    
    # Poll for completion
    return await poll_bulk_operation(shopify_repo, operation_id)
```

---

## Monitoring & Analytics

### Metrics

```python
class ShopifyMetrics:
    product_syncs_total = Counter("shopify_product_syncs_total")
    product_sync_duration_seconds = Histogram("shopify_product_sync_duration_seconds")
    inventory_syncs_total = Counter("shopify_inventory_syncs_total")
    price_updates_total = Counter("shopify_price_updates_total")
    price_update_errors = Counter("shopify_price_update_errors")
    webhook_events_received = Counter("shopify_webhook_events_received")
    webhook_processing_duration_seconds = Histogram("shopify_webhook_processing_duration_seconds")
    api_budget_remaining = Gauge("shopify_api_budget_remaining")
```

### Logging

```python
logger.info("shopify_product_sync_started", extra={
    "shop_url": shop_url,
    "force_full": force_full_sync
})

logger.info("shopify_product_sync_completed", extra={
    "shop_url": shop_url,
    "synced": len(synced),
    "failed": len(failed),
    "unmapped": len(unmapped_skus),
    "duration_seconds": (datetime.utcnow() - start_time).total_seconds()
})
```

---

## Related Documentation

- **API Guide:** `docs/API.md`
- **Architecture:** `docs/ARCHITECTURE.md`
- **Shopify Admin API:** [Shopify Docs](https://shopify.dev/api/admin-graphql)
- **OAuth 2.0:** [RFC 6749](https://tools.ietf.org/html/rfc6749)
- **GraphQL:** [graphql.org](https://graphql.org/)
