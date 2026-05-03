# Security

AutoMana implements defense-in-depth security across authentication, authorization, secrets management, data protection, and network isolation. This document covers the complete security model.

**Related files:**
- `src/automana/api/utils/auth.py` — Password hashing and JWT utilities
- `src/automana/api/dependancies/auth/` — FastAPI dependency injection for auth checks
- `docs/DATABASE_ROLES.md` — Database RBAC model
- `src/automana/core/settings.py` — Settings and env var loading

---

## Authentication & Authorization

### User Authentication

AutoMana uses **JWT (JSON Web Tokens)** for stateless API authentication and **session cookies** for browser-based access.

#### Password hashing

Passwords are hashed using **bcrypt** (via `passlib`) with automatic salt generation. Never store plaintext passwords.

**Implementation** (`src/automana/api/utils/auth.py`):

```python
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_hash_password(password: str) -> str:
    """Hash a plaintext password."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a hash."""
    return pwd_context.verify(plain_password, hashed_password)
```

**Storage:** Hashed passwords are stored in the `users` table, never the plaintext.

#### JWT tokens

Access tokens are issued on login and must be included in the `Authorization: Bearer <token>` header for API requests.

**Token creation:**

```python
def create_access_token(data: dict, secret_key: str, algorithm: str, 
                       expires_delta: timedelta = None) -> str:
    """Create a signed JWT token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, secret_key, algorithm)
```

**Configuration:**

| Setting | Default | Purpose |
|---------|---------|---------|
| `JWT_SECRET_KEY` | — | Signing key; must be ≥32 random bytes |
| `JWT_ALGORITHM` | `HS256` | HMAC with SHA-256 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Token lifetime |

**Example:** Create a token valid for 30 minutes

```python
from datetime import timedelta
token = create_access_token(
    data={"sub": str(user_id), "scope": "api"},
    secret_key=settings.JWT_SECRET_KEY,
    algorithm=settings.JWT_ALGORITHM,
    expires_delta=timedelta(minutes=30)
)
```

**Validation:**

Tokens are verified in `src/automana/api/dependancies/auth/` using FastAPI dependency injection. Invalid, expired, or missing tokens return `401 Unauthorized`.

```python
def decode_access_token(token: str, secret_key: str, algorithm: str) -> dict:
    """Decode and validate a JWT token."""
    try:
        return jwt.decode(token, key=secret_key, algorithms=[algorithm])
    except jwt.ExpiredSignatureError:
        raise ValueError("Token expired")
    except jwt.InvalidTokenError:
        raise ValueError("Invalid token")
```

### Session-based authentication

Browser users receive a **session cookie** upon login. The session ID is stored in `user_sessions` table with an expiration timestamp.

**Session flow:**

1. User logs in with email and password
2. Backend verifies credentials (bcrypt)
3. Backend generates a `session_id` (UUID v4)
4. Backend stores `{user_id, session_id, expires_at}` in `user_sessions`
5. Backend sends `Set-Cookie: session_id=<uuid>; HttpOnly; Secure; SameSite=Strict`
6. Browser sends `Cookie: session_id=<uuid>` on subsequent requests
7. Backend validates session is still active and user is the same

**Session validation middleware:**

```python
# In src/automana/api/dependancies/auth/
async def get_current_user_from_session(request: Request) -> User:
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    session = await sessions_repository.get_active_session(session_id)
    if not session or session.expires_at < datetime.utcnow():
        raise HTTPException(status_code=401, detail="Session expired")
    
    user = await users_repository.get_by_id(session.user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    return user
```

**Cookie security:**

- `HttpOnly`: Prevents JavaScript access (XSS protection)
- `Secure`: Sent only over HTTPS
- `SameSite=Strict`: Prevents CSRF attacks (blocked on cross-site requests)

### Role-based access control (RBAC)

AutoMana implements RBAC at two levels: **database roles** and **HTTP endpoint permissions**.

**Database roles** (see `docs/DATABASE_ROLES.md`):

| Role | Users | Permissions |
|------|-------|-------------|
| `app_backend` | FastAPI process | SELECT, INSERT, UPDATE, DELETE on application tables |
| `app_celery` | Celery workers | SELECT, INSERT, UPDATE, DELETE on application tables |
| `app_readonly` | Read-only tools | SELECT only (no writes) |
| `automana_admin` | Operators | Full DDL and DML (migration runner) |

**HTTP endpoint roles:**

Each endpoint specifies required scopes (e.g., `api`, `admin`). The `@require_scopes` decorator checks the user's token claims:

```python
from fastapi import Depends

@app.post("/users/{user_id}/delete")
async def delete_user(
    user_id: int,
    current_user: User = Depends(require_scopes(["admin"]))
) -> dict:
    """Delete a user (admin only)."""
    await users_service.delete(user_id)
    return {"status": "deleted"}
```

**Token scope claim:**

When issuing a token, include the user's scopes:

```python
token = create_access_token(
    data={"sub": str(user_id), "scope": "api admin"},  # Space-separated scopes
    secret_key=settings.JWT_SECRET_KEY,
    algorithm=settings.JWT_ALGORITHM,
    expires_delta=timedelta(minutes=30)
)
```

---

## Scope Management (OAuth2 integrations)

AutoMana integrates with eBay and Shopify, which require OAuth2 tokens with specific scopes. Each scope must be requested upfront and stored securely.

### eBay API scopes

**Requested scopes** (see `src/automana/integrations/ebay/oauth.py`):

```python
EBAY_SCOPES = [
    "https://api.ebay.com/oauth/api_scope",
    "https://api.ebay.com/oauth/api_scope/sell.inventory",
    "https://api.ebay.com/oauth/api_scope/sell.analytics.readonly",
]
```

Each scope grants specific permissions:

| Scope | Purpose |
|-------|---------|
| `api_scope` | Read basic user info |
| `sell.inventory` | List, update, and remove items from seller inventory |
| `sell.analytics.readonly` | View seller traffic and sales analytics (read-only) |

**Storage:** eBay tokens are stored encrypted in `integrations.ebay_tokens` table with columns:

```sql
CREATE TABLE integrations.ebay_tokens (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES user_management.users(id),
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    scopes TEXT NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);
```

Tokens are encrypted at rest using the Fernet cipher.

**Encryption:** Use `cryptography` library to encrypt tokens before storing:

```python
from cryptography.fernet import Fernet

cipher = Fernet(settings.TOKEN_ENCRYPTION_KEY)
encrypted_token = cipher.encrypt(token.encode()).decode()
await ebay_tokens_repository.create(
    user_id=user_id,
    access_token=encrypted_token,
    refresh_token=encrypted_refresh_token,
    scopes=",".join(scopes)
)
```

### Shopify API scopes

**Requested scopes** (see `src/automana/integrations/shopify/oauth.py`):

```python
SHOPIFY_SCOPES = [
    "read_products",
    "write_products",
    "read_inventory",
    "write_inventory",
]
```

**Storage:** Similar to eBay, Shopify tokens are encrypted in `integrations.shopify_tokens` table.

### Token refresh and rotation

Both eBay and Shopify access tokens expire. Before each API call, check if the token is expired; if so, refresh it using the refresh token.

**Refresh flow:**

```python
async def get_valid_ebay_token(user_id: UUID) -> str:
    """Get a valid eBay access token, refreshing if expired."""
    token_record = await ebay_tokens_repository.get_by_user_id(user_id)
    
    if token_record.expires_at < datetime.utcnow():
        # Token expired; refresh
        new_access_token, new_refresh_token = await ebay_client.refresh_token(
            refresh_token=cipher.decrypt(token_record.refresh_token.encode()).decode()
        )
        # Update database
        encrypted_new_access = cipher.encrypt(new_access_token.encode()).decode()
        await ebay_tokens_repository.update(
            id=token_record.id,
            access_token=encrypted_new_access,
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )
        return new_access_token
    
    return cipher.decrypt(token_record.access_token.encode()).decode()
```

---

## JWT / Session Token Security

### Token lifetime

- **Access tokens:** 15 minutes (default). Short-lived to limit exposure if a token is leaked.
- **Refresh tokens:** 7 days. Used to obtain new access tokens without re-entering credentials.
- **Sessions:** 1 hour (configurable). Longer lifetime for convenience but invalidated on logout.

### Token validation

Always validate tokens for:

1. **Signature:** Signed with the server's secret key; any tampering is detected.
2. **Expiration:** Token includes `exp` claim; expired tokens are rejected.
3. **Subject (sub):** Identifies the user.
4. **Scopes:** Only endpoints matching the token's scopes are accessible.

### Token storage (client-side)

**Browsers:** Store the session ID in a cookie (HttpOnly, Secure, SameSite=Strict). The browser automatically includes it in requests.

**Mobile/SPA apps:** Store the access token in memory (never localStorage to prevent XSS theft). Use refresh tokens to obtain new access tokens before expiration.

```javascript
// React/SPA example
const [accessToken, setAccessToken] = useState(null);

async function login(email, password) {
    const response = await fetch("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password })
    });
    const { access_token, refresh_token } = await response.json();
    setAccessToken(access_token);
    // Store refresh_token securely (e.g., in a secure HTTP-only cookie)
}

async function fetchWithAuth(url) {
    let response = await fetch(url, {
        headers: { "Authorization": `Bearer ${accessToken}` }
    });
    
    if (response.status === 401) {
        // Token expired; refresh
        const refreshResponse = await fetch("/api/auth/refresh", {
            method: "POST"
        });
        const { access_token } = await refreshResponse.json();
        setAccessToken(access_token);
        
        // Retry with new token
        response = await fetch(url, {
            headers: { "Authorization": `Bearer ${access_token}` }
        });
    }
    
    return response;
}
```

---

## API Security

### CORS (Cross-Origin Resource Sharing)

AutoMana restricts cross-origin requests to whitelisted domains.

**Configuration** (`src/automana/api/main.py`):

```python
from fastapi.middleware.cors import CORSMiddleware

settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)
```

**Environment configuration:**

```bash
# .env.prod
ALLOWED_ORIGINS=["https://app.example.com", "https://admin.example.com"]
```

**Rationale:** Without CORS restrictions, any website could make requests on behalf of your users (session hijacking, CSRF).

### CSRF (Cross-Site Request Forgery) protection

CSRF tokens ensure that POST/PUT/DELETE requests originate from your application, not from a malicious site.

**Implementation:**

1. Server generates a CSRF token per session
2. Server embeds the token in HTML forms
3. Client sends the token in the `X-CSRF-Token` header or form field
4. Server validates the token matches the session's token

**Middleware** (example):

```python
from fastapi import Request, HTTPException

@app.middleware("http")
async def csrf_protection(request: Request, call_next):
    if request.method in {"POST", "PUT", "DELETE"}:
        # For browser requests (not API tokens), require CSRF token
        if "session_id" in request.cookies:
            csrf_token = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
            session = await sessions_repository.get_by_id(request.cookies["session_id"])
            
            if not csrf_token or csrf_token != session.csrf_token:
                raise HTTPException(status_code=403, detail="CSRF token invalid")
    
    return await call_next(request)
```

### XSS (Cross-Site Scripting) prevention

XSS attacks inject malicious scripts into your application. Prevention strategies:

1. **Content Security Policy (CSP):** Restrict script sources via HTTP headers.
2. **Input validation:** Reject invalid inputs (email format, phone number, etc.).
3. **Output escaping:** HTML-escape all user-supplied data before rendering.

**CSP header** (nginx):

```nginx
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.example.com";
```

**Input validation** (FastAPI):

```python
from pydantic import EmailStr, Field

class CreateUserRequest(BaseModel):
    email: EmailStr
    name: str = Field(..., min_length=1, max_length=100)
    age: int = Field(..., ge=0, le=150)
```

**Output escaping:** Use proper HTML sanitization for user-supplied HTML content. Never trust user input when rendering HTML.

### Rate limiting

Prevent brute force attacks and DDoS by limiting requests per IP.

**nginx configuration** (`deploy/docker/nginx/nginx.prod.conf`):

```nginx
limit_req_zone $binary_remote_addr zone=perip:10m rate=10r/s;

server {
    location /api/auth/login {
        limit_req zone=perip burst=5 nodelay;
        proxy_pass http://backend;
    }
    
    location /api/ {
        limit_req zone=perip burst=100 nodelay;
        proxy_pass http://backend;
    }
}
```

### HTTPS and TLS

All production traffic is encrypted with TLS 1.3.

**Certificate management:**

1. **Let's Encrypt:** Automatic renewal via Certbot
2. **Manual certs:** Place in `config/nginx/certs/` (see `docs/DEPLOYMENT.md`)

**Nginx SSL configuration:**

```nginx
server {
    listen 443 ssl http2;
    ssl_certificate /etc/nginx/certs/cert.pem;
    ssl_certificate_key /etc/nginx/certs/key.pem;
    
    # Force TLS 1.3 and 1.2 (no older protocols)
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!eNULL:!EXPORT:!DES:!MD5:!PSK:!RC4;
    ssl_prefer_server_ciphers on;
}
```

---

## Database Security and RBAC

See `docs/DATABASE_ROLES.md` for complete database security model.

### Key principles

1. **Principle of Least Privilege:** Each application process uses the minimum role needed.
   - FastAPI: `app_backend` (SELECT, INSERT, UPDATE, DELETE)
   - Celery: `app_celery` (SELECT, INSERT, UPDATE, DELETE)
   - Read-only tools: `app_readonly` (SELECT only)
   - Migrations: `automana_admin` (full DDL + DML)

2. **No application access to DDL:** The `app_backend` and `app_celery` roles cannot DROP or ALTER tables, preventing accidental schema destruction.

3. **Ownership separation:** All tables are owned by `db_owner` (NOLOGIN). Application roles are granted permissions but never own objects.

### Example: prevent accidental table drop

```sql
-- app_backend cannot drop tables (it doesn't own them)
DROP TABLE card_catalog.cards;  -- Fails: permission denied

-- But automana_admin can (it's a member of db_owner)
DROP TABLE card_catalog.cards;  -- Succeeds (when logged in as automana_admin)
```

### Data encryption at rest

Sensitive fields (passwords, tokens) are hashed or encrypted:

| Field | Table | Method |
|-------|-------|--------|
| Password | `users` | bcrypt (hashing) |
| eBay access token | `ebay_tokens` | Fernet (symmetric encryption) |
| eBay refresh token | `ebay_tokens` | Fernet (symmetric encryption) |
| Shopify access token | `shopify_tokens` | Fernet (symmetric encryption) |

**Encryption key:**

```bash
# .env.prod
TOKEN_ENCRYPTION_KEY=<base64-encoded-32-byte-key>
```

**Key generation:**

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## Secret Management

### Environment variables

All secrets are injected via environment variables or Docker secrets, never committed to git.

**Configuration files:**

- `config/env/.env.dev` (git-ignored, development only)
- `config/env/.env.staging` (git-ignored, staging only)
- `config/env/.env.prod` (git-ignored, production only, stored in secure vault)

**Example** (`config/env/.env.prod`):

```bash
# Database
POSTGRES_HOST=postgres.prod
POSTGRES_PORT=5432
DB_NAME=automana_prod
DB_PASSWORD=/run/secrets/db_password

# Auth
JWT_SECRET_KEY=/run/secrets/jwt_secret_key
TOKEN_ENCRYPTION_KEY=/run/secrets/token_encryption_key

# API keys
EBAY_CLIENT_ID=/run/secrets/ebay_client_id
EBAY_CLIENT_SECRET=/run/secrets/ebay_client_secret
SCRYFALL_API_KEY=/run/secrets/scryfall_api_key

# Logging
LOG_LEVEL=INFO
LOG_JSON=1
SERVICE_NAME=backend
```

### Docker secrets

In production, use Docker secrets for sensitive data:

```yaml
# deploy/docker-compose.prod.yml
services:
  backend:
    environment:
      DB_PASSWORD_FILE: /run/secrets/db_password
      JWT_SECRET_KEY_FILE: /run/secrets/jwt_secret_key
    secrets:
      - db_password
      - jwt_secret_key

secrets:
  db_password:
    external: true
  jwt_secret_key:
    external: true
```

**Creation:**

```bash
echo "my_secure_password" | docker secret create db_password -
echo "my_jwt_secret_key" | docker secret create jwt_secret_key -
```

### Settings loading

`src/automana/core/settings.py` loads secrets from env vars or files:

```python
class Settings(BaseSettings):
    db_password: str = Field(..., alias="DB_PASSWORD")
    jwt_secret_key: str = Field(..., alias="JWT_SECRET_KEY")
    
    class Config:
        env_file = f".env.{os.getenv('ENV', 'dev')}"
        case_sensitive = True
```

**File-based secrets:**

```python
db_password = os.getenv("DB_PASSWORD")
if db_password and db_password.startswith("/run/secrets/"):
    with open(db_password) as f:
        db_password = f.read().strip()
```

---

## Data Encryption in Transit and at Rest

### In transit (HTTPS/TLS)

All production traffic between client and server is encrypted with TLS 1.3.

**Enforcement:**

```nginx
# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name _;
    return 301 https://$host$request_uri;
}
```

### At rest (database)

PostgreSQL does not natively encrypt individual column values. Instead, use application-level encryption for sensitive fields:

```python
from cryptography.fernet import Fernet

cipher = Fernet(settings.TOKEN_ENCRYPTION_KEY)

# Encrypt before storing
encrypted_value = cipher.encrypt(plaintext.encode()).decode()
await repository.create(token=encrypted_value)

# Decrypt after retrieving
decrypted_value = cipher.decrypt(encrypted_value.encode()).decode()
```

**When to encrypt (at rest):**

- OAuth tokens (eBay, Shopify) — use Fernet
- API keys — use Fernet
- Passwords — never store; use bcrypt hash instead

**PostgreSQL full-disk encryption** (infrastructure layer):

In production, enable OS-level disk encryption (e.g., dm-crypt on Linux) so the entire database file is encrypted at rest, even if an attacker gains filesystem access.

---

## Security Checklist

Before deploying to production, verify:

### Authentication

- [ ] Passwords are hashed with bcrypt (never plaintext)
- [ ] JWT tokens are signed with a strong secret (≥32 random bytes)
- [ ] Access tokens expire after 15 minutes
- [ ] Session IDs are UUIDs (cryptographically random)
- [ ] Cookies are HttpOnly, Secure, and SameSite=Strict

### Authorization

- [ ] Database roles follow least-privilege principle
- [ ] Application processes use restricted database users (not root)
- [ ] Endpoints enforce required scopes (e.g., @require_scopes)
- [ ] OAuth2 tokens are refreshed before expiration

### Secrets

- [ ] No hardcoded credentials in code or configs
- [ ] All secrets are injected via environment variables or Docker secrets
- [ ] Sensitive files (.env, private keys) are in .gitignore
- [ ] Secret files are mode 600 (user read/write only)

### API Security

- [ ] CORS is restricted to whitelisted domains
- [ ] CSRF tokens are validated for state-changing requests
- [ ] Input validation is enforced (length, format, range)
- [ ] Output is properly escaped to prevent injection attacks
- [ ] Rate limiting is enabled on sensitive endpoints (login, signup)

### Data Protection

- [ ] HTTPS is enforced (redirect HTTP to HTTPS)
- [ ] TLS 1.3 is mandatory (no legacy protocols)
- [ ] OAuth tokens are encrypted before storing
- [ ] Sensitive database fields are encrypted (passwords, tokens)

### Network

- [ ] Only the reverse proxy (nginx) publishes ports to the internet
- [ ] Backend, database, and cache are on a private network
- [ ] Network policies prevent direct access to database from outside
- [ ] Inter-service communication uses authentication (if over untrusted networks)

### Monitoring

- [ ] Logs capture all authentication failures
- [ ] Alerts trigger on suspicious patterns (repeated login failures, unusual access)
- [ ] Audit trail records all schema changes (migrations)

---

## References

- OWASP Top 10: https://owasp.org/www-project-top-ten/
- JWT best practices: https://tools.ietf.org/html/rfc8725
- PostgreSQL RBAC: https://www.postgresql.org/docs/current/role-attributes.html
- TLS 1.3: https://tools.ietf.org/html/rfc8446
