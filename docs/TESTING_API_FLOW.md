# API Testing Flow

Standard procedure for manual API testing using curl. Always use a throwaway test user — never the persistent `testuser` or `curltest` accounts.

---

## 1. Create a test user

The `hashed_password` field must be bcrypt-hashed by the caller before sending.

```bash
# Generate a bcrypt hash for a known test password
TEST_PASS="test-$(date +%s)"
HASHED=$(python3 -c "import bcrypt; print(bcrypt.hashpw(b'${TEST_PASS}', bcrypt.gensalt()).decode())")
echo "Password: $TEST_PASS"
echo "Hash:     $HASHED"

# Register the user
curl -s -X POST http://localhost:8000/api/users/ \
  -H "Content-Type: application/json" \
  -d "{\"username\": \"apitest_$$\", \"email\": \"apitest_$$@test.local\", \"hashed_password\": \"$HASHED\"}" \
  | python3 -m json.tool
```

Save the returned `user_id` for the cleanup step.

---

## 2. Log in and capture tokens

```bash
# Login — returns access_token (Bearer) + sets session_id cookie
curl -s -c /tmp/apitest_cookies.txt \
  -X POST http://localhost:8000/api/users/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=apitest_$$&password=${TEST_PASS}" \
  | python3 -m json.tool

# Extract the access token
ACCESS_TOKEN=$(curl -s -c /tmp/apitest_cookies.txt \
  -X POST http://localhost:8000/api/users/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=apitest_$$&password=${TEST_PASS}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
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

# Remove local cookie jar
rm -f /tmp/apitest_cookies.txt

# Clear shell variables holding the password
unset TEST_PASS HASHED ACCESS_TOKEN
```

---

## Collection test example (full round-trip)

```bash
# Create collection
COLLECTION_ID=$(curl -s -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"collection_name": "test_col", "description": "api test"}' \
  http://localhost:8000/api/catalog/mtg/collection/ \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['collection_id'])")
echo "Collection: $COLLECTION_ID"

# Get a card version ID to insert
CARD_ID=$(docker exec automana-postgres-dev psql -U app_admin -d automana -t -c \
  "SELECT card_version_id FROM card_catalog.card_version LIMIT 1;" | tr -d ' \n')

# Add a card entry  (endpoint not yet implemented — placeholder)
curl -s -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"unique_card_id\": \"$CARD_ID\", \"is_foil\": false, \"purchase_price\": \"1.50\", \"condition\": \"NM\", \"currency_code\": \"USD\"}" \
  http://localhost:8000/api/catalog/mtg/collection/${COLLECTION_ID}/entries \
  | python3 -m json.tool

# Delete the collection
curl -s -X DELETE \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8000/api/catalog/mtg/collection/${COLLECTION_ID}
echo "Deleted collection $COLLECTION_ID"
```

---

## Notes

- `bcrypt` must be available: `pip show bcrypt` or `docker exec automana-backend-dev pip show bcrypt`
- The backend runs on port `8000` in dev; nginx proxies `80/443` in all other envs
- Cookie jar (`/tmp/apitest_cookies.txt`) holds the `session_id` — delete it at end of session
- Never commit test passwords; always `unset` them when done
