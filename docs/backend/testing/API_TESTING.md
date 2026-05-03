# Manual API Testing

This document describes how to manually test the AutoMana API using curl, test authentication flows, and clean up test data.

For automated testing, see [`docs/backend/testing/TESTING_STRATEGY.md`](TESTING_STRATEGY.md).

---

## Quick Start Workflow

A typical manual testing session follows this flow:

1. **Create a throwaway test user** (not the persistent `testuser` account)
2. **Authenticate and capture the access token**
3. **Make authenticated requests** using the token
4. **Test error scenarios** (invalid inputs, permissions)
5. **Clean up**: Delete the test user and unset password variables

---

## 1. Create a Throwaway Test User

Always create a fresh user for each testing session — never reuse the persistent `testuser` or `curltest` accounts.

The `hashed_password` field in the registration request is misleading: pass a **plain-text password**, not a bcrypted hash. The server hashes it on receipt.

```bash
TEST_PASS="Testpass123!"
TEST_USER="apitest_$$"

curl -s -X POST http://localhost:8000/api/users/ \
  -H "Content-Type: application/json" \
  -d "{\"username\": \"${TEST_USER}\", \"email\": \"${TEST_USER}@automana.dev\", \"hashed_password\": \"${TEST_PASS}\"}" \
  | python3 -m json.tool
```

**Example response:**
```json
{
  "unique_id": "550e8400-e29b-41d4-a716-446655440000",
  "username": "apitest_12345",
  "email": "apitest_12345@automana.dev",
  "created_at": "2026-05-02T10:30:00Z"
}
```

**Save the `unique_id`** — you'll need it for cleanup later.

```bash
TEST_USER_ID="550e8400-e29b-41d4-a716-446655440000"
```

---

## 2. Authenticate and Capture the Access Token

Exchange the username and password for a JWT access token and refresh token.

```bash
curl -s -X POST http://localhost:8000/api/users/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=${TEST_USER}&password=${TEST_PASS}" \
  | python3 -m json.tool
```

**Example response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "550e8400-e29b-41d4-a716-446655440001",
  "token_type": "bearer",
  "expires_in": 1800
}
```

**Extract the access token into a variable:**
```bash
ACCESS_TOKEN=$(curl -s \
  -X POST http://localhost:8000/api/users/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=${TEST_USER}&password=${TEST_PASS}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo "Token: ${ACCESS_TOKEN:0:20}..."
```

---

## 3. Make Authenticated Requests

All protected endpoints require the `Authorization: Bearer <token>` header.

### Verify Identity

```bash
curl -s -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8000/api/users/me \
  | python3 -m json.tool
```

**Response:**
```json
{
  "unique_id": "550e8400-e29b-41d4-a716-446655440000",
  "username": "apitest_12345",
  "email": "apitest_12345@automana.dev",
  "created_at": "2026-05-02T10:30:00Z"
}
```

---

## 4. Collection + Card Entry Workflow

A complete round-trip: create a collection, add card entries, list them, and delete.

### Create a Collection

```bash
COLLECTION_ID=$(curl -s -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"collection_name": "test_col", "description": "api test"}' \
  http://localhost:8000/api/catalog/mtg/collection/ \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['collection_id'])")

echo "Created collection: $COLLECTION_ID"
```

### Search for a Card

Use the typeahead suggest endpoint to find a card by name:

```bash
curl -s "http://localhost:8000/api/catalog/mtg/card/suggest?query=Sheoldred" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  | python3 -m json.tool
```

**Example response:**
```json
{
  "data": [
    {
      "card_version_id": "abc123...",
      "name": "Sheoldred's Edict",
      "set_code": "dmu",
      "collector_number": "107",
      "image_uri": "..."
    },
    ...
  ]
}
```

Save a `card_version_id` from the results for the next step.

```bash
CARD_VERSION_ID="abc123..."
```

### Add Card Entries (Three Strategies)

AutoMana supports three ways to identify a card:

#### Strategy A: By `card_version_id` (from suggest)

```bash
curl -s -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"card_version_id\": \"$CARD_VERSION_ID\", \"condition\": \"NM\", \"finish\": \"NONFOIL\", \"purchase_price\": \"15.99\"}" \
  http://localhost:8000/api/catalog/mtg/collection/${COLLECTION_ID}/entries \
  | python3 -m json.tool
```

#### Strategy B: By `scryfall_id`

```bash
SCRYFALL_ID="abc123..."
curl -s -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"scryfall_id\": \"$SCRYFALL_ID\", \"condition\": \"LP\", \"finish\": \"FOIL\", \"purchase_price\": \"22.50\"}" \
  http://localhost:8000/api/catalog/mtg/collection/${COLLECTION_ID}/entries \
  | python3 -m json.tool
```

#### Strategy C: By `set_code` + `collector_number`

```bash
curl -s -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"set_code": "dmu", "collector_number": "107", "condition": "MP", "finish": "NONFOIL", "purchase_price": "8.00"}' \
  http://localhost:8000/api/catalog/mtg/collection/${COLLECTION_ID}/entries \
  | python3 -m json.tool
```

**Response:**
```json
{
  "data": {
    "entry_id": "xyz789...",
    "collection_id": "...",
    "card_version_id": "...",
    "condition": "MP",
    "finish": "NONFOIL",
    "purchase_price": 8.00,
    "added_at": "2026-05-02T10:35:00Z"
  }
}
```

Valid condition values: `NM`, `LP`, `SP`, `MP`, `HP`, `DMG`  
Valid finish values: `NONFOIL`, `FOIL`, `ETCHED`

### List Collection Entries

```bash
curl -s "http://localhost:8000/api/catalog/mtg/collection/${COLLECTION_ID}/entries" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  | python3 -m json.tool
```

**Response:**
```json
{
  "data": [
    {
      "entry_id": "xyz789...",
      "card_version_id": "...",
      "condition": "NM",
      "finish": "NONFOIL",
      "purchase_price": 15.99,
      "added_at": "2026-05-02T10:35:00Z"
    },
    ...
  ],
  "pagination": {
    "total": 3,
    "page": 1,
    "per_page": 50
  }
}
```

### Delete a Collection

```bash
curl -s -X DELETE \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8000/api/catalog/mtg/collection/${COLLECTION_ID}

echo "Deleted collection $COLLECTION_ID"
```

---

## 5. Testing Error Scenarios

### 401 Unauthorized

Missing or invalid token:

```bash
curl -s http://localhost:8000/api/catalog/mtg/collection/ \
  | python3 -m json.tool
```

**Response:**
```json
{
  "error": "Not authenticated",
  "detail": "Credentials are missing"
}
```

### 400 Bad Request

Invalid input (missing required field):

```bash
curl -s -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"collection_name": ""}' \
  http://localhost:8000/api/catalog/mtg/collection/ \
  | python3 -m json.tool
```

**Response:**
```json
{
  "error": "Validation error",
  "detail": [
    {
      "field": "collection_name",
      "message": "ensure this value has at least 1 characters"
    }
  ]
}
```

### 403 Forbidden

User lacks permission to access another user's collection:

```bash
# Create a second test user
TEST_USER_2="apitest_other"
TEST_PASS_2="Otherpass123!"
curl -s -X POST http://localhost:8000/api/users/ \
  -H "Content-Type: application/json" \
  -d "{\"username\": \"$TEST_USER_2\", \"email\": \"${TEST_USER_2}@automana.dev\", \"hashed_password\": \"${TEST_PASS_2}\"}" \
  > /dev/null

# Get TOKEN_2 for the second user
TOKEN_2=$(curl -s \
  -X POST http://localhost:8000/api/users/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=${TEST_USER_2}&password=${TEST_PASS_2}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Try to list the first user's collection with TOKEN_2
curl -s "http://localhost:8000/api/catalog/mtg/collection/${COLLECTION_ID}/entries" \
  -H "Authorization: Bearer $TOKEN_2" \
  | python3 -m json.tool
```

**Response:**
```json
{
  "error": "Forbidden",
  "detail": "You do not have permission to access this collection"
}
```

### 404 Not Found

Resource does not exist:

```bash
curl -s "http://localhost:8000/api/catalog/mtg/collection/nonexistent-id" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  | python3 -m json.tool
```

**Response:**
```json
{
  "error": "Not found",
  "detail": "Collection not found"
}
```

---

## 6. Token Refresh

Access tokens expire after 30 minutes. Use the refresh token to get a new access token without logging in again.

```bash
REFRESH_TOKEN="..."  # Saved from step 2

curl -s -X POST http://localhost:8000/api/users/auth/token/refresh \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "refresh_token=${REFRESH_TOKEN}" \
  | python3 -m json.tool
```

**Response:**
```json
{
  "access_token": "new-jwt-token...",
  "token_type": "bearer"
}
```

---

## 7. Cleanup

Always clean up test data and unset variables.

### Option A: Via API

```bash
curl -s -X DELETE \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8000/api/users/${TEST_USER_ID}

unset TEST_PASS TEST_USER TEST_USER_ID ACCESS_TOKEN REFRESH_TOKEN
```

### Option B: Directly in psql

If the API delete fails, clean up directly in the database:

```bash
docker exec automana-postgres-dev psql -U app_admin -d automana -c \
  "DELETE FROM user_management.users WHERE username LIKE 'apitest%' RETURNING username;"
```

Then unset variables:
```bash
unset TEST_PASS TEST_USER TEST_USER_ID ACCESS_TOKEN REFRESH_TOKEN
```

---

## Testing with Postman

Postman is useful for interactive testing and saving request collections.

### Setup

1. **Create a collection** for AutoMana tests
2. **Set up environment variables:**
   - `base_url` = `http://localhost:8000`
   - `access_token` = (populate manually after login)
   - `collection_id` = (populate after creating a collection)

3. **Create requests:**
   - `POST /api/users/` — Register test user
   - `POST /api/users/auth/token` — Login and capture token
   - `POST /api/catalog/mtg/collection/` — Create collection
   - `GET /api/catalog/mtg/card/suggest` — Search cards
   - `POST /api/catalog/mtg/collection/{{collection_id}}/entries` — Add card
   - `DELETE /api/users/{{user_id}}` — Cleanup

### Tips

- Use **Pre-request Script** to extract and save the access token:
  ```javascript
  var jsonData = pm.response.json();
  pm.environment.set("access_token", jsonData.access_token);
  ```

- Use **Environments** to switch between `dev` (localhost:8000), `staging`, and `prod`

- Export the collection and commit it to the repo (gitignored) for team reference

---

## Testing with cURL and jq

For JSON processing without Python, use `jq`:

```bash
# Pretty-print JSON
curl -s http://localhost:8000/api/health | jq

# Extract a specific field
ACCESS_TOKEN=$(curl -s -X POST http://localhost:8000/api/users/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=${TEST_USER}&password=${TEST_PASS}" \
  | jq -r '.access_token')

# Filter array results
curl -s "http://localhost:8000/api/catalog/mtg/card/suggest?query=Sheoldred" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  | jq '.data[] | {name, set_code, collector_number}'
```

---

## Notes

- **Port**: The backend runs on `8000` in dev. In production, nginx proxies on `80/443`.
- **Password field**: The `hashed_password` field in the user registration endpoint is **not** a bcrypted hash — pass a plain-text password and the server hashes it.
- **Never commit test passwords**: Always `unset` sensitive variables when done.
- **Throwaway users only**: Create a fresh user for each session; never reuse persistent test accounts.
- **Check endpoint docs**: Run the API server and visit `http://localhost:8000/docs` for interactive Swagger documentation.

---

## Complete Session Example

```bash
#!/bin/bash
set -e

# Setup
TEST_PASS="Testpass123!"
TEST_USER="apitest_$$"
BASE_URL="http://localhost:8000"

echo "=== Creating test user ==="
RESPONSE=$(curl -s -X POST "${BASE_URL}/api/users/" \
  -H "Content-Type: application/json" \
  -d "{\"username\": \"${TEST_USER}\", \"email\": \"${TEST_USER}@automana.dev\", \"hashed_password\": \"${TEST_PASS}\"}")
TEST_USER_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['unique_id'])")
echo "Created user: $TEST_USER_ID"

echo "=== Logging in ==="
ACCESS_TOKEN=$(curl -s \
  -X POST "${BASE_URL}/api/users/auth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=${TEST_USER}&password=${TEST_PASS}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "Got access token: ${ACCESS_TOKEN:0:20}..."

echo "=== Verifying identity ==="
curl -s -H "Authorization: Bearer $ACCESS_TOKEN" \
  "${BASE_URL}/api/users/me" | python3 -m json.tool

echo "=== Creating collection ==="
COLLECTION_ID=$(curl -s -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"collection_name": "Test Cards", "description": "API test"}' \
  "${BASE_URL}/api/catalog/mtg/collection/" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['collection_id'])")
echo "Created collection: $COLLECTION_ID"

echo "=== Searching for cards ==="
curl -s "${BASE_URL}/api/catalog/mtg/card/suggest?query=Sheoldred" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | python3 -m json.tool | head -20

echo "=== Cleanup ==="
curl -s -X DELETE \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  "${BASE_URL}/api/users/${TEST_USER_ID}"
echo "Deleted user $TEST_USER"

unset TEST_PASS TEST_USER TEST_USER_ID ACCESS_TOKEN
echo "Done. Variables unset."
```

Save as `test_api.sh`, make executable (`chmod +x test_api.sh`), and run:
```bash
./test_api.sh
```

---

## See Also

- [`docs/backend/testing/TESTING_STRATEGY.md`](TESTING_STRATEGY.md) — Automated testing (unit, integration, E2E)
- [`docs/API.md`](../API.md) — Full API specification and endpoint reference
- `http://localhost:8000/docs` — Interactive Swagger documentation (while running)
- [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) — Request flow and authentication details
