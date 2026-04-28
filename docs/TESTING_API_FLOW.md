# API Testing Flow

Standard procedure for manual API testing using curl. Always use a throwaway test user — never the persistent `testuser` or `curltest` accounts.

---

## 1. Create a test user

Pass a plain-text password in the `hashed_password` field — the server bcrypt-hashes it on receipt.

```bash
TEST_PASS="Testpass123!"
TEST_USER="apitest_$$"

curl -s -X POST http://localhost:8000/api/users/ \
  -H "Content-Type: application/json" \
  -d "{\"username\": \"${TEST_USER}\", \"email\": \"${TEST_USER}@automana.dev\", \"hashed_password\": \"${TEST_PASS}\"}" \
  | python3 -m json.tool
```

Save the returned `unique_id` for the cleanup step.

---

## 2. Log in and capture the access token

```bash
ACCESS_TOKEN=$(curl -s \
  -X POST http://localhost:8000/api/users/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=${TEST_USER}&password=${TEST_PASS}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "Token: ${ACCESS_TOKEN:0:20}..."
```

---

## 3. Make authenticated requests

Use `Authorization: Bearer <token>` on all protected endpoints:

```bash
# Verify identity
curl -s -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8000/api/users/me | python3 -m json.tool
```

---

## 4. Cleanup — delete the user and local state

```bash
# Delete the throwaway user (requires admin role or self-delete)
curl -s -X DELETE \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8000/api/users/<USER_ID>

unset TEST_PASS TEST_USER ACCESS_TOKEN
```

Or delete directly in psql:
```bash
docker exec automana-postgres-dev psql -U app_admin -d automana -c \
  "DELETE FROM user_management.users WHERE username LIKE 'apitest%' RETURNING username;"
```

---

## Collection + entries round-trip

```bash
# Create a collection (returns collection_id, collection_name, user_id)
COLLECTION_ID=$(curl -s -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"collection_name": "test_col", "description": "api test"}' \
  http://localhost:8000/api/catalog/mtg/collection/ \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['collection_id'])")
echo "Collection: $COLLECTION_ID"

# Find a card via typeahead suggest
curl -s "http://localhost:8000/api/catalog/mtg/card/suggest?query=Sheoldred" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | python3 -m json.tool

# Add a card entry — three supported identifier strategies:

# (a) by card_version_id (from suggest)
curl -s -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"card_version_id": "<uuid>", "condition": "NM", "finish": "NONFOIL", "purchase_price": "15.99"}' \
  http://localhost:8000/api/catalog/mtg/collection/${COLLECTION_ID}/entries \
  | python3 -m json.tool

# (b) by scryfall_id
curl -s -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"scryfall_id": "<uuid>", "condition": "LP", "finish": "FOIL", "purchase_price": "22.50"}' \
  http://localhost:8000/api/catalog/mtg/collection/${COLLECTION_ID}/entries \
  | python3 -m json.tool

# (c) by set_code + collector_number
curl -s -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"set_code": "dmu", "collector_number": "107", "condition": "MP", "finish": "NONFOIL", "purchase_price": "8.00"}' \
  http://localhost:8000/api/catalog/mtg/collection/${COLLECTION_ID}/entries \
  | python3 -m json.tool

# List all entries
curl -s "http://localhost:8000/api/catalog/mtg/collection/${COLLECTION_ID}/entries" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | python3 -m json.tool

# Delete the collection
curl -s -X DELETE \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8000/api/catalog/mtg/collection/${COLLECTION_ID}
echo "Deleted collection $COLLECTION_ID"
```

---

## Notes

- `hashed_password` in the registration request is a misnomer — pass the **plain** password, the server hashes it
- Valid `condition` values: `NM`, `LP`, `SP`, `MP`, `HP`, `DMG`
- Valid `finish` values: `NONFOIL`, `FOIL`, `ETCHED`
- The backend runs on port `8000` in dev; nginx proxies `80/443` in all other envs
- Never commit test passwords; always `unset` them when done
