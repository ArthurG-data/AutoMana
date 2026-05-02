# eBay Integration Guide

## Overview

The eBay integration enables AutoMana to authenticate users via eBay's OAuth 2.0 protocol and access eBay's REST APIs for browsing, buying, and selling Magic: The Gathering cards. The integration handles token management, API client abstraction, and multi-environment support (sandbox and production).

**Key capabilities:**
- OAuth 2.0 authorization code flow with refresh token support
- Browse API for item search and pricing discovery
- Buy API for transaction history and order management
- Selling API for inventory and listing management
- Trading API (legacy XML) for advanced operations
- Automatic token refresh with Redis caching
- Rate limiting and error handling with exponential backoff

---

## Architecture Overview

### OAuth 2.0 Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         eBay OAuth 2.0 Flow                               │
└─────────────────────────────────────────────────────────────────────────┘

User                    FastAPI Router          eBay Authorization        eBay API
 │                           │                        Server                 │
 │─ "login with eBay"───────>│                                               │
 │                           │─────────────────────────────────────────────> │
 │                           │  Redirect to Authorization URL               │
 │                           │  (app_id, redirect_uri, state, scopes)      │
 │                           │                                               │
 │<──── Redirect to Login ────│<───────────────────────────────────────────  │
 │                           │                                               │
 │─ [User Authenticates] ─>  │                                               │
 │                           │<────── Redirect with Code + State ───────────│
 │                           │                                               │
 │<─ Redirect to Callback ────│                                               │
 │                           │─ Exchange Code ──────────────────────────> │
 │                           │  (code, app_id, client_secret, redirect_uri)│
 │                           │                                               │
 │                           │<──── Access Token + Refresh Token ──────────│
 │                           │                                               │
 │<─ Session Created ────────│  [Token stored in user session]             │
 │    (user authenticated)   │  [Refresh token cached in Redis]            │

```

### Layered Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│ API Router Layer (ebay_auth.py, ebay_browse.py, etc.)               │
│  - Handles HTTP requests/responses                                    │
│  - Calls ServiceManager for business logic                            │
│  - Enforces authentication via CurrentUserDep                         │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Service Layer (integrations/ebay/*.py)                               │
│  - OAuth flow orchestration (start_oauth, process_callback)           │
│  - Token management (acquire, refresh)                                │
│  - Business logic for app registration and user linking               │
│  - Error mapping and retry logic                                      │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Repository Layer                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │ API Repositories (eBay REST endpoints)                           │ │
│  │  - ApiAuthRepository: /oauth2/token                              │ │
│  │  - EbayBrowseAPIRepository: /buy/browse/v1                       │ │
│  │  - EbaySellingAPIRepository: /sell/inventory/v1                  │ │
│  │  - TradingAPIRepository: XML-RPC legacy API                      │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                        │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │ DB Repositories                                                  │ │
│  │  - AppRepository: app registration, settings, scopes             │ │
│  │  - UserAppRepository: user-app linkages, tokens                  │ │
│  │  - ListingRepository: persisted eBay listings                    │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                        │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │ Cache Layer (Redis)                                              │ │
│  │  - Short-lived access tokens (TTL = expires_in)                  │ │
│  │  - Refresh tokens (persistent, user-scoped)                      │ │
│  │  - State nonce for OAuth security                                │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│ External APIs                                                          │
│  - api.ebay.com (production)                                           │
│  - api.sandbox.ebay.com (sandbox)                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. OAuth 2.0 Authentication

**File:** `src/automana/core/repositories/app_integration/ebay/ApiAuth_repository.py`

The OAuth repository manages the token exchange flow:

```python
class ApiAuthRepository(BaseApiClient):
    """Handles OAuth 2.0 token operations with eBay."""
    
    async def exchange_code_for_tokens(
        self,
        code: str,
        app_id: str,
        secret: str,
        redirect_uri: str,
        scopes: List[str]
    ) -> Dict[str, Any]:
        """
        Exchange authorization code for access + refresh tokens.
        
        Returns:
            {
                "access_token": str,
                "expires_in": int (seconds),
                "refresh_token": str,
                "token_type": "Bearer",
                "refresh_token_expires_in": int
            }
        """
        
    async def refresh_access_token(
        self,
        refresh_token: str,
        app_id: str,
        secret: str,
        scopes: List[str]
    ) -> Dict[str, Any]:
        """Refresh an expired access token using the refresh token."""
```

**Token Response Model:**

```python
class TokenResponse(BaseModel):
    access_token: str                          # Bearer token for API calls
    expires_in: int                            # Seconds until expiration
    expires_on: Optional[datetime] = None      # Computed expiration timestamp
    refresh_token: Optional[str] = None        # Persisted for re-auth
    token_type: str = "Bearer"                 # OAuth 2.0 standard
    refresh_token_expires_in: Optional[int] = None  # Refresh token TTL
    refresh_expires_on: Optional[datetime] = None   # Computed expiration
    
    @model_validator(mode='after')
    def compute_expires_on(self):
        """Auto-compute expiration times from TTL."""
```

### 2. API Client Abstraction

**File:** `src/automana/core/repositories/app_integration/ebay/EbayApiRepository.py`

Base client providing HTTP methods with authentication:

```python
class EbayApiClient(BaseApiClient):
    """Abstract base for all eBay API clients."""
    
    def __init__(self, environment: str = "sandbox", timeout: int = 30):
        self.environment = environment
        self.timeout = timeout
        self.base_url = self._get_base_url(environment)
    
    async def _make_get_request(
        self,
        endpoint: str,
        params: Dict = None,
        headers: Dict = None,
        access_token: str = None
    ) -> Dict[str, Any]:
        """Make authenticated GET request to eBay API."""
        
    async def _make_post_request(
        self,
        endpoint: str,
        body: Dict = None,
        headers: Dict = None,
        access_token: str = None
    ) -> Dict[str, Any]:
        """Make authenticated POST request to eBay API."""
```

**Subclasses:**

| Class | Endpoint | Purpose |
|-------|----------|---------|
| `ApiAuthRepository` | `/oauth2/token` | Token exchange and refresh |
| `EbayBrowseAPIRepository` | `/buy/browse/v1` | Item search, details, pricing |
| `EbaySellingAPIRepository` | `/sell/inventory/v1` | Inventory, listings, offers |
| `TradingAPIRepository` | XML-RPC endpoint | Legacy bulk operations |

### 3. Token Management

**File:** `src/automana/core/utils/ebay_utils.py`

Token lifecycle management:

```python
class TokenManager:
    """Manages eBay tokens with automatic refresh and caching."""
    
    async def get_or_refresh_token(
        self,
        user_id: str,
        app_code: str,
        force_refresh: bool = False
    ) -> str:
        """
        Retrieve cached access token or refresh if expired.
        
        1. Check Redis for valid cached token
        2. If expired/missing, retrieve refresh token from DB
        3. Call ApiAuthRepository.refresh_access_token()
        4. Cache result in Redis (TTL = expires_in)
        5. Return access token
        """
```

**Redis key patterns:**

```
ebay_token:user:{user_id}:{app_code}         # User's access token
ebay_refresh:{user_id}:{app_code}            # User's refresh token
ebay_oauth_state:{state_nonce}               # OAuth state (5 min TTL)
```

### 4. API Endpoints

#### Browse API (Item Search)

**File:** `src/automana/api/routers/integrations/ebay/ebay_browse.py`

```python
@ebay_browse_router.get("/search", tags=["ebay", "browse"])
async def search_items(
    user: CurrentUserDep,
    service_manager: ServiceManagerDep,
    q: str = Query(..., description="Search query"),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    category: Optional[str] = None,
    filter: Optional[str] = None,  # JSON filter expression
) -> ApiResponse:
    """
    Search eBay for items matching card query.
    
    Example:
        GET /integrations/ebay/search?q=Lightning+Bolt&limit=50
        
    Returns:
        {
            "data": [
                {
                    "itemId": "str",
                    "title": "str",
                    "price": {"currency": "USD", "value": "123.45"},
                    "condition": "NEW",
                    "seller": {"username": "str"},
                    "sellerItemStatus": "ACTIVE"
                },
                ...
            ],
            "pagination": {
                "total_count": 1000,
                "limit": 50,
                "offset": 0,
                "has_next": true
            }
        }
    """
    result = await service_manager.execute_service(
        "integrations.ebay.search_items",
        user_id=user.id,
        query=q,
        limit=limit,
        offset=offset,
        category=category,
        filters=filter
    )
    return ApiResponse(data=result)
```

#### OAuth Callback Handler

**File:** `src/automana/api/routers/integrations/ebay/ebay_auth.py`

```python
@ebay_auth_router.get("/callback")
async def handle_ebay_callback(
    request: Request,
    response: Response,
    service_manager: ServiceManagerDep,
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None),
) -> ApiResponse:
    """
    Handle OAuth 2.0 callback from eBay.
    
    Flow:
    1. Validate state nonce against Redis
    2. Exchange code for tokens
    3. Store refresh token in user's session
    4. Create user-app linkage in DB
    5. Redirect to dashboard or error page
    """
    if error:
        raise HTTPException(400, detail=error)
    
    # Retrieve stored state from Redis to prevent CSRF
    env = await service_manager.execute_service(
        "integrations.ebay.get_environment_callback",
        state=state
    )
    
    # Exchange code for tokens
    token_data = await service_manager.execute_service(
        "integrations.ebay.process_callback",
        code=code,
        state=state,
        app_code=env.app_code
    )
    
    # Link user to eBay account
    await service_manager.execute_service(
        "integrations.ebay.link_user_to_app",
        user_id=request.user.id,
        app_code=env.app_code,
        tokens=token_data
    )
    
    return ApiResponse(
        message="eBay account linked successfully",
        data={"authorized": True}
    )
```

---

## Data Synchronization

### Listing Sync Pipeline

The system periodically syncs active eBay listings to AutoMana's local schema for analytics:

```
┌──────────────────────────────────────────────────────────────────┐
│ eBay Selling API (user's listings)                                │
└──────────────────────────────────────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────────────────┐
│ ListingSyncService (service layer)                                │
│  - Fetch paginated listings from Selling API                      │
│  - Parse SKU to card_version_id                                   │
│  - Extract pricing and condition metadata                         │
│  - Map to local product/source_product                            │
└──────────────────────────────────────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────────────────┐
│ staging.ebay_listings (PostgreSQL)                                │
│  - External listing_id (eBay)                                     │
│  - Product mapping (card_version_id + condition)                  │
│  - Price (cents), quantity, last_modified                         │
└──────────────────────────────────────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────────────────┐
│ pricing.price_source (inventory table)                             │
│  - Aggregate across user's eBay listings                          │
│  - Daily aggregation into print_price_daily                       │
└──────────────────────────────────────────────────────────────────┘
```

---

## Error Handling

### Mapped Error Categories

```python
class EbayApiError(Exception):
    """eBay API error mapping."""
    pass

class EbayAuthError(EbayApiError):
    """Authentication/authorization failures."""
    # - invalid_grant (refresh token expired)
    # - invalid_scope (app not authorized for scope)
    # - access_denied (user denied permissions)
    pass

class EbayRateLimitError(EbayApiError):
    """Rate limit exceeded (429)."""
    # Includes Retry-After header for backoff
    pass

class EbayValidationError(EbayApiError):
    """Invalid request parameters (400)."""
    pass
```

### Retry Logic

Service layer implements exponential backoff for transient errors:

```python
@ServiceRegistry.register("integrations.ebay.search_items")
async def search_items(
    ebay_repository: EbayBrowseAPIRepository,
    user_id: str,
    query: str,
    **kwargs
):
    """Search with automatic retry on transient failures."""
    max_retries = 3
    backoff_base = 2  # seconds
    
    for attempt in range(max_retries):
        try:
            token = await get_valid_token(user_id)
            return await ebay_repository.search_items(
                q=query,
                access_token=token,
                **kwargs
            )
        except EbayRateLimitError as e:
            wait_time = int(e.response.headers.get("Retry-After", 60))
            if attempt < max_retries - 1:
                logger.warning("eBay rate limited", extra={
                    "wait_seconds": wait_time,
                    "attempt": attempt + 1
                })
                await asyncio.sleep(wait_time)
            else:
                raise
        except EbayAuthError as e:
            # Refresh token and retry once
            if attempt == 0:
                await refresh_user_token(user_id)
                continue
            else:
                raise
```

---

## Rate Limiting

**eBay API Rate Limits:**
- Browse API: 5,000 requests per hour (per user)
- Selling API: 10,000 requests per hour (per seller)
- Trading API: 50 calls per minute (legacy)

**Implementation:**

```python
class EbayRateLimiter:
    """Token bucket rate limiter per user."""
    
    async def check_rate_limit(self, user_id: str) -> bool:
        """
        Check if user has calls remaining.
        Uses Redis sorted set to track request timestamps.
        """
        window_key = f"ebay:rate:{user_id}:browse"
        return await redis_client.incr_with_expiry(
            window_key,
            ttl=3600  # 1 hour window
        ) < 5000
```

---

## Production Considerations

### 1. Token Security

- **Refresh tokens** MUST be encrypted at rest in the database
- **Access tokens** cached in Redis (volatile, no persistence)
- All tokens have signed JWTs (validate signature in service layer)
- Use environment-specific app credentials (sandbox ≠ production)

### 2. Multi-Tenancy

Each user can authorize multiple eBay accounts via different `app_code` values:

```python
# User has seller account on two eBay sites
tokens_us = await get_valid_token(user_id, app_code="automana_usa_001")
tokens_uk = await get_valid_token(user_id, app_code="automana_uk_001")
```

### 3. Webhook Support (Future)

eBay webhooks notify on inventory changes (optional integration):

```python
@ebay_auth_router.post("/webhooks/inventory-changed")
async def handle_inventory_webhook(
    request: Request,
    service_manager: ServiceManagerDep
):
    """Receive and process eBay inventory change notifications."""
    payload = await request.json()
    
    # Verify X-EBAY-SIGNATURE header
    await service_manager.execute_service(
        "integrations.ebay.process_inventory_event",
        event_type=payload["eventType"],
        listings=payload["inventoryItems"]
    )
```

### 4. User Revocation

When a user revokes eBay access:

```python
async def revoke_ebay_access(user_id: str, app_code: str):
    """
    1. Delete refresh token from DB
    2. Flush Redis cache entries
    3. Mark user-app linkage as inactive
    4. Log revocation event
    """
```

---

## Code Examples

### Example 1: Complete OAuth Flow

```python
# Step 1: Start OAuth (GET /integrations/ebay/auth/app/login?app_code=xyz)
@ServiceRegistry.register("integrations.ebay.start_oauth_flow")
async def start_oauth_flow(
    app_repository: AppRepository,
    user_id: str,
    app_code: str,
    environment: str
) -> Dict[str, str]:
    """Generate authorization URL."""
    app = await app_repository.get_by_code(app_code)
    
    state = secrets.token_urlsafe(32)
    await redis_client.setex(
        f"ebay_oauth_state:{state}",
        300,  # 5 minute window
        json.dumps({"user_id": user_id, "app_code": app_code})
    )
    
    auth_url = (
        f"https://auth.ebay.com/oauth2/authorize"
        f"?response_type=code"
        f"&client_id={app.app_id}"
        f"&redirect_uri={app.redirect_uri}"
        f"&scope={'+'.join(app.scopes)}"
        f"&state={state}"
    )
    return {"authorization_url": auth_url}

# Step 2: Handle Callback (GET /integrations/ebay/auth/callback?code=...&state=...)
@ServiceRegistry.register("integrations.ebay.process_callback")
async def process_callback(
    api_auth_repo: ApiAuthRepository,
    app_repository: AppRepository,
    user_app_repo: UserAppRepository,
    code: str,
    state: str,
    app_code: str
) -> Dict[str, Any]:
    """Exchange code for tokens and store."""
    # Verify state
    state_data = await redis_client.get(f"ebay_oauth_state:{state}")
    if not state_data:
        raise ValueError("Invalid or expired state")
    
    app = await app_repository.get_by_code(app_code)
    
    # Exchange code for tokens
    token_response = await api_auth_repo.exchange_code_for_tokens(
        code=code,
        app_id=app.app_id,
        secret=app.secret,  # decrypted from vault
        redirect_uri=app.redirect_uri,
        scopes=app.scopes
    )
    
    # Store refresh token (encrypted)
    await user_app_repo.store_tokens(
        user_id=state_data["user_id"],
        app_code=app_code,
        access_token=token_response["access_token"],
        refresh_token=token_response["refresh_token"],
        expires_in=token_response["expires_in"]
    )
    
    # Cache access token in Redis
    await redis_client.setex(
        f"ebay_token:user:{state_data['user_id']}:{app_code}",
        token_response["expires_in"],
        json.dumps({
            "access_token": token_response["access_token"],
            "expires_at": (
                datetime.utcnow() + 
                timedelta(seconds=token_response["expires_in"])
            ).isoformat()
        })
    )
    
    return token_response

# Step 3: Search Items (GET /integrations/ebay/browse/search?q=...)
@ServiceRegistry.register("integrations.ebay.search_items")
async def search_items(
    ebay_browse_repo: EbayBrowseAPIRepository,
    user_app_repo: UserAppRepository,
    user_id: str,
    query: str,
    limit: int = 50,
    offset: int = 0
) -> Dict[str, Any]:
    """Search eBay with user's linked credentials."""
    # Get valid token (refresh if needed)
    token_record = await user_app_repo.get_tokens(user_id)
    access_token = token_record["access_token"]
    
    if token_record.get("expires_at") < datetime.utcnow():
        # Refresh
        token_response = await refresh_access_token(
            user_id=user_id,
            refresh_token=token_record["refresh_token"]
        )
        access_token = token_response["access_token"]
    
    # Search
    result = await ebay_browse_repo.search_items(
        params={
            "q": query,
            "limit": limit,
            "offset": offset,
            "filter": "conditionIds:{3000}"  # New condition
        },
        access_token=access_token
    )
    
    return {
        "items": result.get("itemSummaries", []),
        "total": result.get("total", 0),
        "pagination": {
            "limit": limit,
            "offset": offset,
            "has_next": offset + limit < result.get("total", 0)
        }
    }
```

### Example 2: Token Refresh

```python
async def refresh_access_token(
    api_auth_repo: ApiAuthRepository,
    app_repository: AppRepository,
    user_app_repo: UserAppRepository,
    user_id: str,
    app_code: str
) -> Dict[str, Any]:
    """Refresh expired access token."""
    # Retrieve refresh token from DB
    token_record = await user_app_repo.get_tokens(user_id, app_code)
    if not token_record or not token_record.get("refresh_token"):
        raise EbayAuthError("User not authorized for this app")
    
    app = await app_repository.get_by_code(app_code)
    
    # Call eBay token endpoint
    new_tokens = await api_auth_repo.refresh_access_token(
        refresh_token=token_record["refresh_token"],
        app_id=app.app_id,
        secret=app.secret,
        scopes=app.scopes
    )
    
    # Update DB
    await user_app_repo.update_tokens(
        user_id=user_id,
        app_code=app_code,
        access_token=new_tokens["access_token"],
        refresh_token=new_tokens.get("refresh_token", token_record["refresh_token"]),
        expires_in=new_tokens["expires_in"]
    )
    
    # Update Redis cache
    await redis_client.setex(
        f"ebay_token:user:{user_id}:{app_code}",
        new_tokens["expires_in"],
        json.dumps({
            "access_token": new_tokens["access_token"],
            "expires_at": (
                datetime.utcnow() + 
                timedelta(seconds=new_tokens["expires_in"])
            ).isoformat()
        })
    )
    
    return new_tokens
```

---

## Monitoring & Troubleshooting

### Metrics

Track in `core/metrics/ebay_metrics.py`:

```python
class EbayMetrics:
    oauth_flow_start = Counter("ebay_oauth_flows_started")
    oauth_flow_success = Counter("ebay_oauth_flows_completed")
    oauth_flow_error = Counter("ebay_oauth_flows_failed")
    search_requests = Counter("ebay_search_requests")
    search_errors = Counter("ebay_search_errors")
    token_refresh_success = Counter("ebay_token_refreshes_ok")
    token_refresh_fail = Counter("ebay_token_refreshes_failed")
    rate_limit_hit = Counter("ebay_rate_limit_exceeded")
```

### Logging

All operations logged with structured context:

```python
logger.info("ebay_token_refreshed", extra={
    "user_id": user_id,
    "app_code": app_code,
    "expires_in": expires_in,
    "timestamp": datetime.utcnow().isoformat()
})

logger.error("ebay_auth_failed", extra={
    "user_id": user_id,
    "error_code": error.error_code,
    "error_description": error.error_description
})
```

### Common Issues

| Issue | Cause | Resolution |
|-------|-------|-----------|
| `invalid_grant` | Refresh token expired (>18 months) | Re-authorize user |
| `invalid_scope` | App not authorized for requested scope | Update app permissions in eBay dashboard |
| `429 Too Many Requests` | Rate limit exceeded | Implement exponential backoff |
| `access_denied` | User denied permissions during OAuth | Prompt user to re-authorize |
| Token cache miss | Redis eviction or server restart | Token refresh on miss (service layer) |

---

## Related Documentation

- **API Guide:** `docs/API.md` — API router structure and design
- **Architecture:** `docs/ARCHITECTURE.md` — Layered architecture patterns
- **OAuth Best Practices:** [RFC 6749 - OAuth 2.0](https://tools.ietf.org/html/rfc6749)
- **eBay API Docs:** [eBay Developers](https://developer.ebay.com/)
- **Seller Center:** [eBay Selling Resources](https://www.ebay.com/help/selling)
