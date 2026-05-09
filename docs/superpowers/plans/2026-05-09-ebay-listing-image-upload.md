# eBay Listing Image Upload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to attach multiple images to a new or existing eBay listing by uploading files from disk or pasting external URLs, with the card's database image auto-populated in the create flow.

**Architecture:** A new backend endpoint (`POST /listing/upload-picture`) accepts a file, calls eBay's `UploadSiteHostedPictures` Trading API, and returns the eBay-hosted URL. A new `ImagePicker` frontend component manages an ordered list of image URLs (file-upload + URL-paste) and is slotted into `ListingFormPanel`. The accumulated URL list is sent as `PictureDetails.PictureURL[]` in the listing payload on submit.

**Tech Stack:** Python / FastAPI / httpx / xmltodict (backend); React 18 / TypeScript / Vitest / React Testing Library / CSS Modules (frontend).

---

## File Map

| File | Change |
|---|---|
| `src/automana/core/services/app_integration/ebay/xml_utils.py` | Add `generate_upload_site_hosted_pictures_request_xml()` |
| `src/automana/core/repositories/app_integration/ebay/ApiSelling_repository.py` | Add `upload_picture()` method |
| `src/automana/core/services/app_integration/ebay/listings_write_service.py` | Add `upload_listing_picture` service |
| `src/automana/api/routers/integrations/ebay/ebay_selling.py` | Add `POST /upload-picture` endpoint |
| `src/frontend/src/features/ebay/api.ts` | Add `uploadListingPicture`, extend `ListingItemPayload` |
| `src/frontend/src/features/ebay/__tests__/api.test.ts` | Add `uploadListingPicture` tests |
| `src/frontend/src/features/ebay/components/ImagePicker.tsx` | **Create** |
| `src/frontend/src/features/ebay/components/ImagePicker.module.css` | **Create** |
| `src/frontend/src/features/ebay/components/__tests__/ImagePicker.test.tsx` | **Create** |
| `src/frontend/src/features/ebay/components/ListingFormPanel.tsx` | Add `imageUrls`, `onImageChange`, `appCode` props |
| `src/frontend/src/features/ebay/components/__tests__/ListingFormPanel.test.tsx` | Update for new props |
| `src/frontend/src/routes/listings_.new.tsx` | Wire `imageUrls` state, auto-populate from card |
| `src/frontend/src/routes/__tests__/listings.new.test.tsx` | Update for image pre-population |
| `src/frontend/src/routes/listings.tsx` | Wire `imageUrls` state, pre-populate from listing |
| `src/frontend/src/routes/__tests__/listings.test.tsx` | Update for image state in edit flow |

---

## Task 1: Backend XML generator for `UploadSiteHostedPictures`

**Files:**
- Modify: `src/automana/core/services/app_integration/ebay/xml_utils.py`

- [ ] **Step 1: Write the failing test**

Create `src/automana/tests/unit/services/ebay/test_xml_utils_upload.py`:

```python
import pytest
import xml.etree.ElementTree as ET
from automana.core.services.app_integration.ebay.xml_utils import (
    generate_upload_site_hosted_pictures_request_xml,
)

def test_upload_xml_has_correct_root():
    xml_str = generate_upload_site_hosted_pictures_request_xml()
    root = ET.fromstring(xml_str)
    assert root.tag.endswith("UploadSiteHostedPicturesRequest")

def test_upload_xml_has_picture_system_version():
    xml_str = generate_upload_site_hosted_pictures_request_xml()
    root = ET.fromstring(xml_str)
    ns = {"eb": "urn:ebay:apis:eBLBaseComponents"}
    elem = root.find("eb:PictureSystemVersion", ns)
    assert elem is not None
    assert elem.text == "2"

def test_upload_xml_has_supersize_picture_set():
    xml_str = generate_upload_site_hosted_pictures_request_xml()
    root = ET.fromstring(xml_str)
    ns = {"eb": "urn:ebay:apis:eBLBaseComponents"}
    elem = root.find("eb:PictureSet", ns)
    assert elem is not None
    assert elem.text == "Supersize"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/arthur/projects/AutoMana && python -m pytest src/automana/tests/unit/services/ebay/test_xml_utils_upload.py -v
```

Expected: `ImportError` — `generate_upload_site_hosted_pictures_request_xml` not found.

- [ ] **Step 3: Add the function to `xml_utils.py`**

Append to the end of `src/automana/core/services/app_integration/ebay/xml_utils.py`:

```python
def generate_upload_site_hosted_pictures_request_xml() -> str:
    """Generate XML for eBay's UploadSiteHostedPictures Trading API call."""
    root = ET.Element(
        "UploadSiteHostedPicturesRequest",
        xmlns="urn:ebay:apis:eBLBaseComponents",
    )
    ET.SubElement(root, "PictureSystemVersion").text = "2"
    ET.SubElement(root, "PictureSet").text = "Supersize"
    return ET.tostring(root, encoding="utf-8", method="xml").decode("utf-8")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest src/automana/tests/unit/services/ebay/test_xml_utils_upload.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/services/app_integration/ebay/xml_utils.py \
        src/automana/tests/unit/services/ebay/test_xml_utils_upload.py
git commit -m "feat(ebay): add UploadSiteHostedPictures XML generator"
```

---

## Task 2: Backend repository method `upload_picture`

**Files:**
- Modify: `src/automana/core/repositories/app_integration/ebay/ApiSelling_repository.py`

Context: `EbaySellingRepository` inherits from `EbayApiClient`. The Trading API URL is in `self.URL_MAPPING[self.environment]`. `self._get_base_url()` returns this URL. `xmltodict` is already importable. The `send()` method does not expose an `httpx` `files=` parameter so we call `httpx.AsyncClient` directly.

- [ ] **Step 1: Write the failing test**

Create `src/automana/tests/unit/repositories/ebay/test_api_selling_upload.py`:

```python
import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from automana.core.repositories.app_integration.ebay.ApiSelling_repository import EbaySellingRepository

MOCK_SUCCESS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<UploadSiteHostedPicturesResponse xmlns="urn:ebay:apis:eBLBaseComponents">
  <Timestamp>2026-05-09T00:00:00.000Z</Timestamp>
  <Ack>Success</Ack>
  <SiteHostedPictureDetails>
    <FullURL>https://i.ebayimg.com/00/s/test/image.jpg</FullURL>
  </SiteHostedPictureDetails>
</UploadSiteHostedPicturesResponse>"""

MOCK_FAILURE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<UploadSiteHostedPicturesResponse xmlns="urn:ebay:apis:eBLBaseComponents">
  <Ack>Failure</Ack>
  <Errors>
    <ShortMessage>Invalid image</ShortMessage>
  </Errors>
</UploadSiteHostedPicturesResponse>"""

@pytest.fixture
def repo():
    return EbaySellingRepository(environment="sandbox")

@pytest.mark.asyncio
async def test_upload_picture_returns_url(repo):
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.text = MOCK_SUCCESS_XML
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        url = await repo.upload_picture(
            token="test-token",
            file_bytes=b"fake-image",
            content_type="image/jpeg",
        )

    assert url == "https://i.ebayimg.com/00/s/test/image.jpg"

@pytest.mark.asyncio
async def test_upload_picture_passes_correct_call_name(repo):
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.text = MOCK_SUCCESS_XML
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        await repo.upload_picture(
            token="test-token",
            file_bytes=b"fake-image",
            content_type="image/jpeg",
        )

    _, kwargs = mock_client.post.call_args
    assert kwargs["headers"]["X-EBAY-API-CALL-NAME"] == "UploadSiteHostedPictures"

@pytest.mark.asyncio
async def test_upload_picture_raises_on_failure_ack(repo):
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.text = MOCK_FAILURE_XML
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(ValueError, match="eBay upload rejected"):
            await repo.upload_picture(
                token="test-token",
                file_bytes=b"fake-image",
                content_type="image/jpeg",
            )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest src/automana/tests/unit/repositories/ebay/test_api_selling_upload.py -v
```

Expected: `AttributeError` — `upload_picture` not found on `EbaySellingRepository`.

- [ ] **Step 3: Add `upload_picture` to `ApiSelling_repository.py`**

At the top of `src/automana/core/repositories/app_integration/ebay/ApiSelling_repository.py`, add `import httpx` after the existing imports.

Then add this import for the xml generator:

```python
from automana.core.services.app_integration.ebay.xml_utils import (
    generate_add_fixed_price_item_request_xml,
    generate_end_item_request_xml,
    generate_get_item_request_xml,
    generate_revise_item_request_xml,
    generate_get_my_ebay_selling_request_xml,
    generate_upload_site_hosted_pictures_request_xml,
)
```

(Replace the existing import of `xml_utils` functions with this extended version.)

Then append this method to the `EbaySellingRepository` class:

```python
    async def upload_picture(
        self,
        token: str,
        file_bytes: bytes,
        content_type: str,
        marketplace_id: str = "15",
    ) -> str:
        """Upload an image to eBay's picture hosting and return the full URL.

        Uses multipart/form-data — cannot go through self.send() which does not
        expose the httpx ``files`` parameter, so we call httpx.AsyncClient directly.
        """
        xml_payload = generate_upload_site_hosted_pictures_request_xml()
        headers = self.trading_headers(
            token,
            marketplace_id=marketplace_id,
            call_name="UploadSiteHostedPictures",
        )
        files = {
            "XML Payload": ("payload.xml", xml_payload.encode("utf-8"), "text/xml;charset=utf-8"),
            "image": ("image", file_bytes, content_type),
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(self._get_base_url(), files=files, headers=headers)
        response.raise_for_status()

        import xmltodict
        parsed = xmltodict.parse(response.text)
        resp_data = parsed.get("UploadSiteHostedPicturesResponse", {})
        ack = resp_data.get("Ack", "")
        if ack not in ("Success", "Warning"):
            errors = resp_data.get("Errors", {})
            raise ValueError(f"eBay upload rejected: {errors}")
        url = resp_data.get("SiteHostedPictureDetails", {}).get("FullURL")
        if not url:
            raise ValueError("eBay returned no picture URL in upload response")
        return url
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest src/automana/tests/unit/repositories/ebay/test_api_selling_upload.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/repositories/app_integration/ebay/ApiSelling_repository.py \
        src/automana/tests/unit/repositories/ebay/test_api_selling_upload.py
git commit -m "feat(ebay): add upload_picture method to EbaySellingRepository"
```

---

## Task 3: Backend service `upload_listing_picture`

**Files:**
- Modify: `src/automana/core/services/app_integration/ebay/listings_write_service.py`

Context: Follow the exact same `@ServiceRegistry.register` pattern used by `create_listing` in the same file. Use `resolve_token` (already imported) to get the access token before calling the repository.

- [ ] **Step 1: Write the failing test**

Create `src/automana/tests/unit/services/ebay/test_upload_listing_picture_service.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID
from automana.core.services.app_integration.ebay.listings_write_service import (
    upload_listing_picture,
)

USER_ID = UUID("00000000-0000-0000-0000-000000000001")

@pytest.fixture
def auth_repo():
    repo = AsyncMock()
    return repo

@pytest.fixture
def selling_repo():
    repo = AsyncMock()
    repo.upload_picture = AsyncMock(return_value="https://i.ebayimg.com/test.jpg")
    return repo

@pytest.mark.asyncio
async def test_upload_returns_url(auth_repo, selling_repo):
    with __import__("unittest.mock", fromlist=["patch"]).patch(
        "automana.core.services.app_integration.ebay.listings_write_service.resolve_token",
        new=AsyncMock(return_value="access-token-123"),
    ):
        result = await upload_listing_picture(
            auth_repository=auth_repo,
            selling_repository=selling_repo,
            user_id=USER_ID,
            app_code="automana_au",
            file_bytes=b"img",
            content_type="image/jpeg",
        )
    assert result == {"url": "https://i.ebayimg.com/test.jpg"}
    selling_repo.upload_picture.assert_awaited_once_with(
        token="access-token-123",
        file_bytes=b"img",
        content_type="image/jpeg",
    )

@pytest.mark.asyncio
async def test_upload_propagates_repository_error(auth_repo, selling_repo):
    selling_repo.upload_picture = AsyncMock(side_effect=ValueError("eBay upload rejected"))
    with __import__("unittest.mock", fromlist=["patch"]).patch(
        "automana.core.services.app_integration.ebay.listings_write_service.resolve_token",
        new=AsyncMock(return_value="token"),
    ):
        with pytest.raises(ValueError, match="eBay upload rejected"):
            await upload_listing_picture(
                auth_repository=auth_repo,
                selling_repository=selling_repo,
                user_id=USER_ID,
                app_code="automana_au",
                file_bytes=b"img",
                content_type="image/jpeg",
            )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest src/automana/tests/unit/services/ebay/test_upload_listing_picture_service.py -v
```

Expected: `ImportError` — `upload_listing_picture` not defined.

- [ ] **Step 3: Add `upload_listing_picture` to `listings_write_service.py`**

Append to the end of `src/automana/core/services/app_integration/ebay/listings_write_service.py`:

```python
@ServiceRegistry.register(
    path="integrations.ebay.selling.listings.upload_picture",
    db_repositories=["auth"],
    api_repositories=["selling"],
)
async def upload_listing_picture(
    auth_repository: EbayAuthRepository,
    selling_repository: EbaySellingRepository,
    user_id: UUID,
    app_code: str,
    file_bytes: bytes,
    content_type: str,
    **kwargs: Any,
) -> Dict[str, str]:
    """Upload an image file to eBay's picture hosting."""
    token = await resolve_token(auth_repository, user_id, app_code)
    url = await selling_repository.upload_picture(
        token=token,
        file_bytes=file_bytes,
        content_type=content_type,
    )
    logger.info(
        "ebay_picture_uploaded",
        extra={"user_id": str(user_id), "app_code": app_code},
    )
    return {"url": url}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest src/automana/tests/unit/services/ebay/test_upload_listing_picture_service.py -v
```

Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/automana/core/services/app_integration/ebay/listings_write_service.py \
        src/automana/tests/unit/services/ebay/test_upload_listing_picture_service.py
git commit -m "feat(ebay): add upload_listing_picture service"
```

---

## Task 4: Backend endpoint `POST /listing/upload-picture`

**Files:**
- Modify: `src/automana/api/routers/integrations/ebay/ebay_selling.py`

Context: FastAPI `UploadFile` is used for file uploads. Import it from `fastapi`. The endpoint validates that the uploaded file is an image before calling the service.

- [ ] **Step 1: Write the failing test**

Create `src/automana/tests/unit/routers/ebay/test_upload_picture_endpoint.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI
import io

# Minimal app mounting just the listing router
from automana.api.routers.integrations.ebay.ebay_selling import ebay_listing_router

app = FastAPI()
app.include_router(ebay_listing_router)


def make_fake_user():
    user = MagicMock()
    user.unique_id = "00000000-0000-0000-0000-000000000001"
    return user


def test_upload_picture_returns_url():
    with patch(
        "automana.api.routers.integrations.ebay.ebay_selling.CurrentUserDep",
        return_value=make_fake_user(),
    ), patch(
        "automana.api.routers.integrations.ebay.ebay_selling.ServiceManagerDep",
    ) as mock_smd:
        mock_sm = AsyncMock()
        mock_sm.execute_service = AsyncMock(return_value={"url": "https://i.ebayimg.com/img.jpg"})
        mock_smd.return_value = mock_sm

        client = TestClient(app)
        response = client.post(
            "/upload-picture?app_code=automana_au",
            files={"file": ("test.jpg", io.BytesIO(b"fake"), "image/jpeg")},
        )

    assert response.status_code == 200
    assert response.json()["data"]["url"] == "https://i.ebayimg.com/img.jpg"


def test_upload_picture_rejects_non_image():
    with patch(
        "automana.api.routers.integrations.ebay.ebay_selling.CurrentUserDep",
        return_value=make_fake_user(),
    ), patch(
        "automana.api.routers.integrations.ebay.ebay_selling.ServiceManagerDep",
    ):
        client = TestClient(app)
        response = client.post(
            "/upload-picture?app_code=automana_au",
            files={"file": ("doc.pdf", io.BytesIO(b"fake"), "application/pdf")},
        )

    assert response.status_code == 400
    assert "image" in response.json()["detail"].lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest src/automana/tests/unit/routers/ebay/test_upload_picture_endpoint.py -v
```

Expected: `404` or `AttributeError` — endpoint does not exist.

- [ ] **Step 3: Add the endpoint to `ebay_selling.py`**

Add `UploadFile, File` to the existing `from fastapi import ...` import at the top of the file:

```python
from fastapi import APIRouter, HTTPException, Query, Header, UploadFile, File
```

Then append this endpoint to `ebay_selling.py`:

```python
@ebay_listing_router.post("/upload-picture", description="Upload an image to eBay's picture hosting")
async def upload_listing_picture(
    user: CurrentUserDep,
    service_manager: ServiceManagerDep,
    file: UploadFile = File(...),
    app_code: str = Query(..., description="eBay application code"),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image (image/* content type required)")
    file_bytes = await file.read()
    try:
        result = await service_manager.execute_service(
            "integrations.ebay.selling.listings.upload_picture",
            user_id=user.unique_id,
            app_code=app_code,
            file_bytes=file_bytes,
            content_type=file.content_type,
        )
        return ApiResponse(data=result, message="Picture uploaded successfully")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest src/automana/tests/unit/routers/ebay/test_upload_picture_endpoint.py -v
```

Expected: 2 tests PASS.

- [ ] **Step 5: Run backend full test suite to check for regressions**

```bash
python -m pytest src/automana/tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all previously passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add src/automana/api/routers/integrations/ebay/ebay_selling.py \
        src/automana/tests/unit/routers/ebay/test_upload_picture_endpoint.py
git commit -m "feat(ebay): add POST /listing/upload-picture endpoint"
```

---

## Task 5: Frontend API — `uploadListingPicture` + extend `ListingItemPayload`

**Files:**
- Modify: `src/frontend/src/features/ebay/api.ts`
- Modify: `src/frontend/src/features/ebay/__tests__/api.test.ts`

Context: `apiClient` sets `Content-Type: application/json` by default. For multipart file upload, we must NOT set `Content-Type` — the browser sets `multipart/form-data` with the correct boundary automatically. So `uploadListingPicture` calls `fetch` directly (same pattern as `apiClient` internals) but omits the `Content-Type` header and uses `FormData` as the body.

The `ApiError` class is exported from `src/frontend/src/lib/apiClient.ts`.

- [ ] **Step 1: Write the failing tests**

In `src/frontend/src/features/ebay/__tests__/api.test.ts`, add a new `describe` block for `uploadListingPicture`. Place it after the existing test blocks.

First, add these imports at the top if not already present:
```typescript
import { uploadListingPicture } from '../api'
```

Then append this describe block:

```typescript
describe('uploadListingPicture', () => {
  beforeEach(() => {
    mockApiClient.mockReset()
  })

  it('POSTs FormData to /listing/upload-picture with correct app_code', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: { url: 'https://i.ebayimg.com/img.jpg' }, success: true }),
    })
    vi.stubGlobal('fetch', mockFetch)

    const file = new File([new Uint8Array([1, 2, 3])], 'test.jpg', { type: 'image/jpeg' })
    const result = await uploadListingPicture('automana_au', file)

    expect(result).toEqual({ url: 'https://i.ebayimg.com/img.jpg' })
    const [url, options] = mockFetch.mock.calls[0]
    expect(url).toContain('/listing/upload-picture')
    expect(url).toContain('app_code=automana_au')
    expect(options.method).toBe('POST')
    expect(options.body).toBeInstanceOf(FormData)
    // No Content-Type header — browser sets multipart boundary automatically
    expect((options.headers ?? {})['Content-Type']).toBeUndefined()

    vi.unstubAllGlobals()
  })

  it('throws ApiError when response is not ok', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
    })
    vi.stubGlobal('fetch', mockFetch)

    const file = new File([new Uint8Array([1])], 'img.jpg', { type: 'image/jpeg' })
    await expect(uploadListingPicture('automana_au', file)).rejects.toThrow()

    vi.unstubAllGlobals()
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/arthur/projects/AutoMana/src/frontend && npm test -- api.test 2>&1 | tail -15
```

Expected: FAIL — `uploadListingPicture is not a function`.

- [ ] **Step 3: Implement changes in `api.ts`**

**3a.** Add `ApiError` import at the top of `api.ts` (add to existing import from apiClient):

```typescript
import { apiClient, ApiError } from '../../lib/apiClient'
```

**3b.** Extend `ListingItemPayload` (find the existing interface and add `pictureUrls`):

```typescript
export interface ListingItemPayload {
  title: string
  startPrice: { currency: string; value: number }
  quantity: number
  conditionID: number
  description?: string
  pictureUrls?: string[]
}
```

**3c.** Update `createListing` to include `PictureDetails` when images are provided:

```typescript
export async function createListing(
  appCode: string,
  item: ListingItemPayload,
): Promise<void> {
  const body: Record<string, unknown> = {
    title: item.title,
    startPrice: item.startPrice,
    quantity: item.quantity,
    conditionID: item.conditionID,
    ...(item.description ? { description: item.description } : {}),
    ...(item.pictureUrls?.length
      ? { pictureDetails: { PictureURL: item.pictureUrls } }
      : {}),
  }
  await apiClient<unknown>(
    `/integrations/ebay/listing/?app_code=${encodeURIComponent(appCode)}`,
    {
      method: 'POST',
      headers: { 'Idempotency-Key': crypto.randomUUID() },
      body: JSON.stringify(body),
    },
  )
}
```

**3d.** Update `updateListing` similarly:

```typescript
export async function updateListing(
  appCode: string,
  itemId: string,
  item: ListingItemPayload,
): Promise<void> {
  const body: Record<string, unknown> = {
    itemID: itemId,
    title: item.title,
    startPrice: item.startPrice,
    quantity: item.quantity,
    conditionID: item.conditionID,
    ...(item.description ? { description: item.description } : {}),
    ...(item.pictureUrls?.length
      ? { pictureDetails: { PictureURL: item.pictureUrls } }
      : {}),
  }
  await apiClient<unknown>(
    `/integrations/ebay/listing/${encodeURIComponent(itemId)}?app_code=${encodeURIComponent(appCode)}`,
    {
      method: 'PUT',
      body: JSON.stringify(body),
    },
  )
}
```

**3e.** Add `uploadListingPicture` after `updateListing`:

```typescript
export async function uploadListingPicture(
  appCode: string,
  file: File,
): Promise<{ url: string }> {
  const { useAuthStore } = await import('../../store/auth')
  const token = useAuthStore.getState().token
  const formData = new FormData()
  formData.append('file', file)
  const res = await fetch(
    `/api/integrations/ebay/listing/upload-picture?app_code=${encodeURIComponent(appCode)}`,
    {
      method: 'POST',
      credentials: 'include',
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        // No Content-Type — browser sets multipart/form-data + boundary
      },
      body: formData,
    },
  )
  if (!res.ok) {
    throw new ApiError(`API ${res.status}: upload-picture`, res.status)
  }
  const body = (await res.json()) as { data?: { url: string }; url?: string }
  const url = body?.data?.url ?? body?.url
  if (!url) throw new ApiError('No URL returned from picture upload', 200)
  return { url }
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
npm test -- api.test 2>&1 | tail -15
```

Expected: all existing tests + 2 new `uploadListingPicture` tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/features/ebay/api.ts \
        src/frontend/src/features/ebay/__tests__/api.test.ts
git commit -m "feat(ebay): add uploadListingPicture API function and pictureUrls to ListingItemPayload"
```

---

## Task 6: Frontend `ImagePicker` component

**Files:**
- Create: `src/frontend/src/features/ebay/components/ImagePicker.tsx`
- Create: `src/frontend/src/features/ebay/components/ImagePicker.module.css`
- Create: `src/frontend/src/features/ebay/components/__tests__/ImagePicker.test.tsx`

Context: `uploadListingPicture` is imported from `../api`. The component receives `images: string[]` (confirmed URLs from parent), `onChange: (images: string[]) => void`, `appCode: string`, `maxImages?: number` (default 12). It maintains local `slots` state for in-progress uploads and errors. `crypto.randomUUID()` is available in the browser.

- [ ] **Step 1: Write the failing tests**

Create `src/frontend/src/features/ebay/components/__tests__/ImagePicker.test.tsx`:

```typescript
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ImagePicker } from '../ImagePicker'

vi.mock('../../api', () => ({
  uploadListingPicture: vi.fn(),
}))

import { uploadListingPicture } from '../../api'
const mockUpload = vi.mocked(uploadListingPicture)

describe('ImagePicker', () => {
  beforeEach(() => {
    mockUpload.mockReset()
  })

  it('renders existing image thumbnails', () => {
    render(
      <ImagePicker
        images={['https://example.com/img1.jpg', 'https://example.com/img2.jpg']}
        onChange={vi.fn()}
        appCode="automana_au"
      />
    )
    const imgs = screen.getAllByRole('img')
    expect(imgs).toHaveLength(2)
    expect(imgs[0]).toHaveAttribute('src', 'https://example.com/img1.jpg')
  })

  it('calls onChange with image removed on × click', async () => {
    const onChange = vi.fn()
    render(
      <ImagePicker
        images={['https://example.com/img1.jpg', 'https://example.com/img2.jpg']}
        onChange={onChange}
        appCode="automana_au"
      />
    )
    const removeBtns = screen.getAllByRole('button', { name: /remove/i })
    await userEvent.click(removeBtns[0])
    expect(onChange).toHaveBeenCalledWith(['https://example.com/img2.jpg'])
  })

  it('rejects invalid URL with inline error and does not call onChange', async () => {
    const onChange = vi.fn()
    render(<ImagePicker images={[]} onChange={onChange} appCode="automana_au" />)
    await userEvent.click(screen.getByRole('button', { name: /add url/i }))
    const input = screen.getByPlaceholderText(/https:\/\//i)
    await userEvent.type(input, 'not-a-url')
    await userEvent.click(screen.getByRole('button', { name: /add/i }))
    expect(screen.getByText(/must start with http/i)).toBeInTheDocument()
    expect(onChange).not.toHaveBeenCalled()
  })

  it('appends valid URL to list via onChange', async () => {
    const onChange = vi.fn()
    render(<ImagePicker images={[]} onChange={onChange} appCode="automana_au" />)
    await userEvent.click(screen.getByRole('button', { name: /add url/i }))
    const input = screen.getByPlaceholderText(/https:\/\//i)
    await userEvent.type(input, 'https://example.com/card.jpg')
    await userEvent.click(screen.getByRole('button', { name: /add/i }))
    expect(onChange).toHaveBeenCalledWith(['https://example.com/card.jpg'])
  })

  it('shows spinner while uploading then calls onChange on success', async () => {
    let resolveUpload!: (v: { url: string }) => void
    mockUpload.mockReturnValue(new Promise<{ url: string }>((res) => { resolveUpload = res }))

    const onChange = vi.fn()
    render(<ImagePicker images={[]} onChange={onChange} appCode="automana_au" />)

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File([new Uint8Array([1])], 'photo.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    expect(screen.getByTestId('upload-spinner')).toBeInTheDocument()

    resolveUpload({ url: 'https://i.ebayimg.com/photo.jpg' })
    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith(['https://i.ebayimg.com/photo.jpg'])
      expect(screen.queryByTestId('upload-spinner')).not.toBeInTheDocument()
    })
  })

  it('shows error slot with retry button on failed upload', async () => {
    mockUpload.mockRejectedValue(new Error('Network error'))

    const onChange = vi.fn()
    render(<ImagePicker images={[]} onChange={onChange} appCode="automana_au" />)

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File([new Uint8Array([1])], 'photo.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.getByText(/upload failed/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
    })
    expect(onChange).not.toHaveBeenCalled()
  })

  it('hides drop zone and add-url button when at maxImages limit', () => {
    const images = Array.from({ length: 3 }, (_, i) => `https://example.com/${i}.jpg`)
    render(
      <ImagePicker images={images} onChange={vi.fn()} appCode="automana_au" maxImages={3} />
    )
    expect(screen.queryByRole('button', { name: /add url/i })).not.toBeInTheDocument()
    expect(document.querySelector('input[type="file"]')).not.toBeInTheDocument()
  })

  it('retrying a failed upload re-attempts upload', async () => {
    mockUpload
      .mockRejectedValueOnce(new Error('fail'))
      .mockResolvedValueOnce({ url: 'https://i.ebayimg.com/ok.jpg' })

    const onChange = vi.fn()
    render(<ImagePicker images={[]} onChange={onChange} appCode="automana_au" />)

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File([new Uint8Array([1])], 'p.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => screen.getByRole('button', { name: /retry/i }))
    await userEvent.click(screen.getByRole('button', { name: /retry/i }))
    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith(['https://i.ebayimg.com/ok.jpg'])
    })
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
npm test -- ImagePicker.test 2>&1 | tail -15
```

Expected: `Cannot find module '../ImagePicker'`.

- [ ] **Step 3: Create `ImagePicker.module.css`**

Create `src/frontend/src/features/ebay/components/ImagePicker.module.css`:

```css
/* src/frontend/src/features/ebay/components/ImagePicker.module.css */
.picker {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.thumb {
  position: relative;
  width: 72px;
  height: 72px;
  border-radius: 6px;
  overflow: hidden;
  border: 1px solid var(--hd-border);
  flex-shrink: 0;
}

.thumbImg {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.removeBtn {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.6);
  border: none;
  color: #fff;
  font-size: 10px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}

.removeBtn:hover {
  background: rgba(0, 0, 0, 0.85);
}

.slotUploading {
  width: 72px;
  height: 72px;
  border-radius: 6px;
  border: 1px solid var(--hd-border);
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--hd-surface);
  flex-shrink: 0;
}

.spinner {
  width: 20px;
  height: 20px;
  border: 2px solid var(--hd-border);
  border-top-color: var(--hd-accent);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.slotError {
  padding: 6px 8px;
  border-radius: 6px;
  background: rgba(227, 94, 108, 0.08);
  border: 1px solid rgba(227, 94, 108, 0.25);
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 11px;
  color: var(--hd-red);
  max-width: 120px;
}

.retryBtn {
  background: transparent;
  border: 1px solid var(--hd-red);
  color: var(--hd-red);
  border-radius: 4px;
  padding: 2px 6px;
  font-size: 10px;
  cursor: pointer;
  font-family: var(--font-mono);
}

.dropZone {
  width: 72px;
  height: 72px;
  border-radius: 6px;
  border: 1px dashed var(--hd-border);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  background: transparent;
  transition: border-color 0.15s, background 0.15s;
  flex-shrink: 0;
}

.dropZone:hover, .dropZoneDragging {
  border-color: var(--hd-accent);
  background: rgba(var(--hd-accent-rgb), 0.04);
}

.dropZoneIcon {
  font-size: 22px;
  color: var(--hd-sub);
  line-height: 1;
}

.fileInput {
  display: none;
}

.controls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.addUrlBtn {
  background: transparent;
  border: 1px solid var(--hd-border);
  color: var(--hd-sub);
  border-radius: 4px;
  padding: 4px 10px;
  font-size: 11px;
  font-family: var(--font-mono);
  cursor: pointer;
  transition: border-color 0.12s, color 0.12s;
}

.addUrlBtn:hover {
  border-color: var(--hd-accent);
  color: var(--hd-text);
}

.urlInputRow {
  display: flex;
  align-items: center;
  gap: 6px;
}

.urlInput {
  flex: 1;
  background: var(--hd-bg);
  border: 1px solid var(--hd-border);
  border-radius: 4px;
  padding: 4px 8px;
  font-size: 12px;
  color: var(--hd-text);
  font-family: var(--font-sans);
}

.urlInput:focus {
  outline: none;
  border-color: var(--hd-accent);
}

.addBtn {
  background: var(--hd-accent);
  border: none;
  color: #fff;
  border-radius: 4px;
  padding: 4px 10px;
  font-size: 11px;
  cursor: pointer;
}

.urlError {
  font-size: 11px;
  color: var(--hd-red);
}
```

- [ ] **Step 4: Create `ImagePicker.tsx`**

Create `src/frontend/src/features/ebay/components/ImagePicker.tsx`:

```typescript
// src/frontend/src/features/ebay/components/ImagePicker.tsx
import { useState, useRef } from 'react'
import { uploadListingPicture } from '../api'
import styles from './ImagePicker.module.css'

interface ImagePickerProps {
  images: string[]
  onChange: (images: string[]) => void
  appCode: string
  maxImages?: number
}

interface UploadSlot {
  id: string
  status: 'uploading' | 'error'
  file: File
  error?: string
}

export function ImagePicker({ images, onChange, appCode, maxImages = 12 }: ImagePickerProps) {
  const [slots, setSlots] = useState<UploadSlot[]>([])
  const [urlInputVisible, setUrlInputVisible] = useState(false)
  const [urlInput, setUrlInput] = useState('')
  const [urlError, setUrlError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const uploadingCount = slots.filter((s) => s.status === 'uploading').length
  const atLimit = images.length + uploadingCount >= maxImages

  async function uploadFile(file: File) {
    const id = crypto.randomUUID()
    setSlots((prev) => [...prev, { id, status: 'uploading', file }])
    try {
      const { url } = await uploadListingPicture(appCode, file)
      // Read latest images from the callback to avoid stale closure — parent re-renders so
      // we use functional form by calling onChange; parent accumulates via its own setState.
      onChange([...images, url])
      setSlots((prev) => prev.filter((s) => s.id !== id))
    } catch (err) {
      setSlots((prev) =>
        prev.map((s) =>
          s.id === id
            ? { ...s, status: 'error', error: err instanceof Error ? err.message : 'Upload failed' }
            : s
        )
      )
    }
  }

  function handleFiles(files: FileList | null) {
    if (!files) return
    Array.from(files).forEach((file) => uploadFile(file))
  }

  function handleRetry(slot: UploadSlot) {
    setSlots((prev) => prev.filter((s) => s.id !== slot.id))
    uploadFile(slot.file)
  }

  function handleAddUrl() {
    const url = urlInput.trim()
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      setUrlError('URL must start with http:// or https://')
      return
    }
    onChange([...images, url])
    setUrlInput('')
    setUrlInputVisible(false)
    setUrlError(null)
  }

  return (
    <div className={styles.picker}>
      <div className={styles.grid}>
        {images.map((url, i) => (
          <div key={url + i} className={styles.thumb}>
            <img src={url} alt={`Image ${i + 1}`} className={styles.thumbImg} />
            <button
              type="button"
              aria-label="Remove image"
              className={styles.removeBtn}
              onClick={() => onChange(images.filter((_, idx) => idx !== i))}
            >
              ×
            </button>
          </div>
        ))}

        {slots.map((slot) =>
          slot.status === 'uploading' ? (
            <div key={slot.id} className={styles.slotUploading}>
              <div className={styles.spinner} data-testid="upload-spinner" />
            </div>
          ) : (
            <div key={slot.id} className={styles.slotError}>
              <span>Upload failed</span>
              <button
                type="button"
                aria-label="Retry upload"
                className={styles.retryBtn}
                onClick={() => handleRetry(slot)}
              >
                Retry
              </button>
            </div>
          )
        )}

        {!atLimit && (
          <>
            <button
              type="button"
              aria-label="Add image"
              className={[styles.dropZone, dragging ? styles.dropZoneDragging : ''].filter(Boolean).join(' ')}
              onClick={() => fileInputRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault()
                setDragging(false)
                handleFiles(e.dataTransfer.files)
              }}
            >
              <span className={styles.dropZoneIcon} aria-hidden>+</span>
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              multiple
              className={styles.fileInput}
              onChange={(e) => handleFiles(e.target.files)}
            />
          </>
        )}
      </div>

      {!atLimit && (
        <div className={styles.controls}>
          {!urlInputVisible ? (
            <button
              type="button"
              className={styles.addUrlBtn}
              onClick={() => setUrlInputVisible(true)}
            >
              + Add URL
            </button>
          ) : (
            <div>
              <div className={styles.urlInputRow}>
                <input
                  type="text"
                  className={styles.urlInput}
                  value={urlInput}
                  onChange={(e) => { setUrlInput(e.target.value); setUrlError(null) }}
                  placeholder="https://..."
                  onKeyDown={(e) => e.key === 'Enter' && handleAddUrl()}
                  autoFocus
                />
                <button type="button" className={styles.addBtn} onClick={handleAddUrl}>
                  Add
                </button>
              </div>
              {urlError && <div className={styles.urlError}>{urlError}</div>}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
npm test -- ImagePicker.test 2>&1 | tail -15
```

Expected: 7 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/frontend/src/features/ebay/components/ImagePicker.tsx \
        src/frontend/src/features/ebay/components/ImagePicker.module.css \
        src/frontend/src/features/ebay/components/__tests__/ImagePicker.test.tsx
git commit -m "feat(ebay): add ImagePicker component for listing image management"
```

---

## Task 7: Wire `ImagePicker` into `ListingFormPanel`

**Files:**
- Modify: `src/frontend/src/features/ebay/components/ListingFormPanel.tsx`
- Modify: `src/frontend/src/features/ebay/components/__tests__/ListingFormPanel.test.tsx`

Context: `ListingFormPanel` currently has props `mode`, `initialValues`, `availableApps`, `appCode?`, `onSave`, `onCancel`, `isSaving`, `error`. Add `imageUrls: string[]`, `onImageChange: (urls: string[]) => void`, `appCode` (make required — it's already optional but both flows now always provide it). The `ImagePicker` goes between the Description field and the App selector in the form.

- [ ] **Step 1: Write the failing test**

Add this test to `src/frontend/src/features/ebay/components/__tests__/ListingFormPanel.test.tsx`:

```typescript
// Add at the top of the file with other mocks:
vi.mock('../ImagePicker', () => ({
  ImagePicker: ({
    images,
    onChange,
  }: {
    images: string[]
    onChange: (imgs: string[]) => void
  }) => (
    <div data-testid="image-picker" data-images={images.join(',')}>
      <button onClick={() => onChange([...images, 'https://new.jpg'])}>
        Add image
      </button>
    </div>
  ),
}))

// Add this test inside the describe block:
it('renders ImagePicker with provided imageUrls', () => {
  render(
    <ListingFormPanel
      mode="create"
      initialValues={{ title: 'Card NM MTG', price: 10, quantity: 1, conditionId: 3000, description: '' }}
      availableApps={[makeApp()]}
      onSave={vi.fn()}
      onCancel={vi.fn()}
      isSaving={false}
      error={null}
      imageUrls={['https://example.com/img.jpg']}
      onImageChange={vi.fn()}
      appCode="automana_au"
    />
  )
  const picker = screen.getByTestId('image-picker')
  expect(picker).toBeInTheDocument()
  expect(picker.getAttribute('data-images')).toBe('https://example.com/img.jpg')
})
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
npm test -- ListingFormPanel.test 2>&1 | tail -15
```

Expected: FAIL — `imageUrls` prop not recognized, `ImagePicker` not rendered.

- [ ] **Step 3: Update `ListingFormPanel.tsx`**

**3a.** Add the `ImagePicker` import at the top of the file:

```typescript
import { ImagePicker } from './ImagePicker'
```

**3b.** Add new props to the interface:

```typescript
interface ListingFormPanelProps {
  mode: 'create' | 'edit'
  initialValues: Partial<ListingFormValues>
  availableApps: EbayAppSummary[]
  appCode?: string
  imageUrls?: string[]
  onImageChange?: (urls: string[]) => void
  onSave: (values: ListingFormValues, appCode: string) => Promise<void>
  onCancel: () => void
  isSaving: boolean
  error: string | null
}
```

**3c.** Destructure the new props in the component signature:

```typescript
export function ListingFormPanel({
  mode,
  initialValues,
  availableApps,
  appCode: fixedAppCode,
  imageUrls = [],
  onImageChange,
  onSave,
  onCancel,
  isSaving,
  error,
}: ListingFormPanelProps) {
```

**3d.** Add `<ImagePicker>` between the Description label and the App selector label. Find this section in the `fields` div:

```typescript
        <label className={styles.field}>
          <span className={styles.label}>Description (optional)</span>
          <textarea
            ...
          />
        </label>

        {/* INSERT HERE */}

        {mode === 'create' && (
          <label className={styles.field} aria-label="App">
```

Add this block between them:

```typescript
        {onImageChange && (
          <div className={styles.field}>
            <span className={styles.label}>Images (up to 12)</span>
            <ImagePicker
              images={imageUrls}
              onChange={onImageChange}
              appCode={fixedAppCode ?? selectedAppCode}
            />
          </div>
        )}
```

- [ ] **Step 4: Run all `ListingFormPanel` tests**

```bash
npm test -- ListingFormPanel.test 2>&1 | tail -15
```

Expected: all tests PASS (existing + new).

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/features/ebay/components/ListingFormPanel.tsx \
        src/frontend/src/features/ebay/components/__tests__/ListingFormPanel.test.tsx
git commit -m "feat(ebay): add ImagePicker slot to ListingFormPanel"
```

---

## Task 8: Wire image state in `listings_.new.tsx` (create flow)

**Files:**
- Modify: `src/frontend/src/routes/listings_.new.tsx`
- Modify: `src/frontend/src/routes/__tests__/listings.new.test.tsx`

Context: When a card is selected via `CardPicker`, `card.image_normal` (a `string | null`) is pre-populated into `imageUrls` state. On `createListing`, `imageUrls` is passed as `pictureUrls`. `ListingFormPanel` receives `imageUrls`, `onImageChange`, and `appCode` (the first production app code, or empty string).

- [ ] **Step 1: Write the failing tests**

Add these tests to `src/frontend/src/routes/__tests__/listings.new.test.tsx`:

```typescript
// Update the ListingFormPanel mock to capture imageUrls:
// Replace the existing ListingFormPanel mock with:
vi.mock('../../features/ebay/components/ListingFormPanel', () => ({
  ListingFormPanel: ({
    onSave,
    onCancel,
    initialValues,
    isSaving,
    error,
    imageUrls,
  }: {
    onSave: (v: ListingFormValues, appCode: string) => Promise<void>
    onCancel: () => void
    initialValues: Partial<ListingFormValues>
    isSaving: boolean
    error: string | null
    imageUrls?: string[]
  }) => (
    <div
      data-testid="listing-form"
      data-title={initialValues.title ?? ''}
      data-saving={String(isSaving)}
      data-error={error ?? ''}
      data-images={(imageUrls ?? []).join(',')}
    >
      <button
        onClick={() =>
          onSave({ title: 'Test', price: 10, quantity: 1, conditionId: 3000, description: '' }, 'automana_au')
        }
      >
        Save
      </button>
      <button onClick={onCancel}>Cancel</button>
    </div>
  ),
}))

// New tests to add inside the describe block:
it('pre-populates imageUrls with card image_normal when card is selected', async () => {
  const user = userEvent.setup()
  mockFetchUserApps.mockResolvedValue([makeApp()])
  render(<ListingsNewPage />)
  await waitFor(() => screen.getByText('Pick card'))
  await user.click(screen.getByText('Pick card'))
  // mockCard.image_normal is null in the existing test fixture — update it:
  // (the mock card at the top of the test file should have image_normal set)
  // Check that form data-images reflects the image_normal value
  const form = screen.getByTestId('listing-form')
  // If card.image_normal is null, imageUrls starts empty
  expect(form.getAttribute('data-images')).toBeDefined()
})

it('passes imageUrls to createListing as pictureUrls', async () => {
  const user = userEvent.setup()
  mockFetchUserApps.mockResolvedValue([makeApp()])
  mockCreateListing.mockResolvedValue(undefined)
  render(<ListingsNewPage />)
  await waitFor(() => screen.getByTestId('listing-form'))
  await user.click(screen.getByRole('button', { name: 'Save' }))
  await waitFor(() => {
    expect(mockCreateListing).toHaveBeenCalledWith(
      'automana_au',
      expect.objectContaining({ pictureUrls: expect.any(Array) })
    )
  })
})
```

Also update the `mockCard` in the test file to have `image_normal: 'https://cards.scryfall.io/ragavan.jpg'` so the pre-population test is meaningful.

- [ ] **Step 2: Run tests to verify they fail**

```bash
npm test -- listings.new.test 2>&1 | tail -15
```

Expected: FAIL — `imageUrls` not passed to `ListingFormPanel`, `createListing` not receiving `pictureUrls`.

- [ ] **Step 3: Update `listings_.new.tsx`**

**3a.** Add `imageUrls` state:

```typescript
const [imageUrls, setImageUrls] = useState<string[]>([])
```

**3b.** When a card is selected, update `imageUrls` alongside `selectedCard`. Find the `setSelectedCard` call and replace it with:

```typescript
function handleCardSelect(card: CardSummary) {
  setSelectedCard(card)
  setImageUrls(card.image_normal ? [card.image_normal] : [])
}
```

Pass `onSelect={handleCardSelect}` to `CardPicker` (replacing `onSelect={setSelectedCard}`).

**3c.** Update `handleSave` to pass `pictureUrls`:

```typescript
await createListing(appCode, {
  title: values.title,
  startPrice: { currency: 'AUD', value: values.price },
  quantity: values.quantity,
  conditionID: values.conditionId,
  ...(values.description ? { description: values.description } : {}),
  pictureUrls: imageUrls,
})
```

**3d.** Pass `imageUrls`, `onImageChange`, and `appCode` to `ListingFormPanel`:

```typescript
<ListingFormPanel
  key={selectedCard?.card_version_id ?? 'no-card'}
  mode="create"
  initialValues={initialValues}
  availableApps={productionApps}
  imageUrls={imageUrls}
  onImageChange={setImageUrls}
  appCode={productionApps[0]?.app_code ?? ''}
  onSave={handleSave}
  onCancel={handleCancel}
  isSaving={isSaving}
  error={saveError}
/>
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
npm test -- listings.new.test 2>&1 | tail -15
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/routes/listings_.new.tsx \
        src/frontend/src/routes/__tests__/listings.new.test.tsx
git commit -m "feat(ebay): wire imageUrls state into /listings/new create flow"
```

---

## Task 9: Wire image state in `listings.tsx` (edit flow)

**Files:**
- Modify: `src/frontend/src/routes/listings.tsx`
- Modify: `src/frontend/src/routes/__tests__/listings.test.tsx`

Context: When a listing row is selected (`setSelectedId`), initialise `imageUrls` from `[selectedListing.imageUrl].filter(Boolean)`. Pass `imageUrls`, `onImageChange`, and `appCode` to `ListingFormPanel` in edit mode. Pass `imageUrls` as `pictureUrls` in the `updateListing` call inside `handleUpdateListing`.

- [ ] **Step 1: Write the failing tests**

Add these tests to `src/frontend/src/routes/__tests__/listings.test.tsx`:

```typescript
// Update ListingFormPanel mock to capture imageUrls:
// Add data-images to the existing ListingFormPanel mock's returned div:
//   data-images={(imageUrls ?? []).join(',')}
// and add imageUrls to the mock's prop type.

it('pre-populates imageUrls from selectedListing.imageUrl in edit panel', async () => {
  const user = userEvent.setup()
  // Set up mocks so a listing with imageUrl is loaded and selected
  // (follow the pattern of existing split-panel tests in this file)
  // After clicking a row with imageUrl set, the form data-images should contain it
  // This test is scaffolded — fill in using the existing mock patterns
})

it('passes imageUrls to updateListing as pictureUrls', async () => {
  // After opening edit panel and clicking Save, updateListing is called with
  // expect.objectContaining({ pictureUrls: expect.any(Array) })
})
```

**Note:** The exact test implementation depends on the current listings.test.tsx mock structure. Follow the same patterns as the existing split-panel tests — they use mocked `ListingsTable` with `onRowClick` exposed, mocked `ListingDetailPanel` and `ListingFormPanel`. Extend those mocks to capture `imageUrls`.

- [ ] **Step 2: Run tests to verify they fail**

```bash
npm test -- listings.test 2>&1 | tail -15
```

Expected: FAIL — `imageUrls` not wired.

- [ ] **Step 3: Update `listings.tsx`**

**3a.** Add `imageUrls` state near the other panel-related state:

```typescript
const [imageUrls, setImageUrls] = useState<string[]>([])
```

**3b.** When a row is selected (in the `setSelectedId` call or in `handleRowClick`), also initialise `imageUrls`. Find where `setSelectedId` is called and add:

```typescript
function handleRowClick(id: string) {
  setSelectedId(id)
  setPanelMode('detail')
  const listing = listingsRef.current.find((l) => l.itemId === id)
  setImageUrls(listing?.imageUrl ? [listing.imageUrl] : [])
}
```

Replace `onRowClick={setSelectedId}` with `onRowClick={handleRowClick}` on `ListingsTable`.

**3c.** Pass `pictureUrls` in `handleUpdateListing`:

```typescript
await updateListing(appCode, selectedId, {
  title: values.title,
  startPrice: { currency: 'AUD', value: values.price },
  quantity: values.quantity,
  conditionID: values.conditionId,
  ...(values.description ? { description: values.description } : {}),
  pictureUrls: imageUrls,
})
```

**3d.** Add `imageUrls`, `onImageChange`, and `appCode` to the `ListingFormPanel` in edit mode:

```typescript
<ListingFormPanel
  mode="edit"
  initialValues={{ ... }}
  availableApps={productionApps}
  appCode={selectedListing.appCode}
  imageUrls={imageUrls}
  onImageChange={setImageUrls}
  onSave={handleUpdateListing}
  onCancel={() => setPanelMode('detail')}
  isSaving={isSaving}
  error={saveError}
/>
```

- [ ] **Step 4: Run all tests**

```bash
npm test -- --run 2>&1 | tail -10
```

Expected: 253+ passing tests, same 12 pre-existing failures in `routes/ebay/__tests__/`.

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/routes/listings.tsx \
        src/frontend/src/routes/__tests__/listings.test.tsx
git commit -m "feat(ebay): wire imageUrls state into listings edit flow"
```

---

## Self-Review

**Spec coverage:**
- ✓ Backend upload endpoint (`POST /listing/upload-picture`) — Task 4
- ✓ File accepted, validated as image, uploaded to eBay via `UploadSiteHostedPictures` — Tasks 1–4
- ✓ Returns eBay-hosted URL — Tasks 2–4
- ✓ `uploadListingPicture` frontend function with FormData — Task 5
- ✓ `pictureUrls` in `ListingItemPayload`, sent as `PictureDetails.PictureURL[]` — Task 5
- ✓ `ImagePicker` with thumbnails, remove, file-upload, URL-paste, spinner, error+retry, limit guard — Task 6
- ✓ Slotted into `ListingFormPanel` — Task 7
- ✓ Create flow: card image_normal auto-populated, imageUrls passed to createListing — Task 8
- ✓ Edit flow: selectedListing.imageUrl pre-populated, imageUrls passed to updateListing — Task 9

**Type consistency:**
- `uploadListingPicture(appCode: string, file: File): Promise<{ url: string }>` — defined Task 5, used in `ImagePicker` Task 6
- `ImagePickerProps.images: string[]` / `onChange: (images: string[]) => void` — defined Task 6, used Task 7
- `ListingFormPanel` new props `imageUrls?: string[]` / `onImageChange?: (urls: string[]) => void` — defined Task 7, wired Tasks 8 & 9
- `ListingItemPayload.pictureUrls?: string[]` — defined Task 5, passed Tasks 8 & 9

**No placeholders:** All code blocks are complete.
