# eBay Listing Image Upload — Design Spec

## Goal

Allow users to attach multiple images to an eBay listing when creating or editing. Images can be selected from disk (file upload) or pasted as a URL. When a card is selected in the create flow, the card's image from the database is automatically pre-populated as the first image.

## Architecture

### Backend — upload endpoint

**`POST /integrations/ebay/listing/upload-picture?app_code={code}`**

- Accepts `multipart/form-data` with a single image file
- Validates Content-Type is an image (rejects with 400 otherwise)
- Retrieves the app's eBay credentials from the database
- Calls eBay's `UploadSiteHostedPictures` Trading API using the app credentials
- Returns `{ "url": "https://i.ebayimg.com/..." }` on success
- No image is stored in AutoMana — the file goes directly to eBay's hosting
- Auth: same pattern as other selling endpoints (user must own the app)

**Payload changes to existing endpoints:**

`ListingItemPayload` in `api.ts` gains `pictureUrls?: string[]`. When non-empty, `createListing` and `updateListing` include `PictureDetails: { PictureURL: pictureUrls }` in the eBay Trading API XML payload.

### Frontend — `ImagePicker` component

**File:** `src/frontend/src/features/ebay/components/ImagePicker.tsx`

**Props:**
```typescript
interface ImagePickerProps {
  images: string[]
  onChange: (images: string[]) => void
  appCode: string
  maxImages?: number  // default 12
}
```

**Behaviour:**
- Renders a thumbnail grid of current images; each thumbnail has a remove (×) button
- At the end of the grid (when `images.length < maxImages`): a drop zone accepting drag-and-drop and click-to-browse (`accept="image/*"`)
- A separate **"+ URL"** button opens an inline text input for pasting an external URL
- Uploading a file: shows a spinner in that slot → on success, replaced by thumbnail → on failure, shows inline error with retry button
- URL paste: validated client-side (must start with `http://` or `https://`) → rejected immediately with inline message if invalid → appended to list if valid
- Drop zone and "+ URL" button are hidden when `images.length >= maxImages` (no silent truncation)

### ListingFormPanel changes

New props added to `ListingFormPanel`:
```typescript
imageUrls: string[]
onImageChange: (urls: string[]) => void
appCode: string
```

`ImagePicker` is rendered between the Description field and the App selector. The `onSave` signature is unchanged — images are managed independently via `onImageChange`.

### Create flow (`listings_.new.tsx`)

- `imageUrls` state initialised as `[]`
- When a card is selected via `CardPicker`, `card.image_normal` (filtered for null) is injected as `imageUrls[0]` — user can remove it or add more
- `imageUrls` and `onImageChange` passed to `ListingFormPanel`
- `imageUrls` passed to `createListing` call as `pictureUrls`

### Edit flow (`listings.tsx`)

- `imageUrls` state initialised as `[selectedListing.imageUrl].filter(Boolean)` when a listing row is selected
- `imageUrls` and `onImageChange` passed to `ListingFormPanel`
- `imageUrls` passed to `updateListing` call as `pictureUrls`

## Error Handling

| Scenario | Behaviour |
|---|---|
| Upload fails (network / eBay rejection) | Slot shows inline error + retry button; other images unaffected |
| Invalid URL pasted | Rejected immediately client-side; inline validation message |
| File is not an image | Backend returns 400; frontend shows error in slot |
| `images.length >= maxImages` | Drop zone and "+ URL" hidden; no silent truncation |
| Form submitted with no images | Allowed — `PictureDetails` omitted from payload |

## File Map

| File | Change |
|---|---|
| `src/automana/api/routers/integrations/ebay/ebay_selling.py` | Add `POST /listing/upload-picture` endpoint |
| `src/automana/core/services/app_integration/ebay/` | Add `upload_site_hosted_picture(app, file_bytes, content_type)` service function |
| `src/frontend/src/features/ebay/components/ImagePicker.tsx` | **Create** — image management UI |
| `src/frontend/src/features/ebay/components/ImagePicker.module.css` | **Create** — styles |
| `src/frontend/src/features/ebay/components/__tests__/ImagePicker.test.tsx` | **Create** — unit tests |
| `src/frontend/src/features/ebay/api.ts` | Add `uploadListingPicture`, extend `ListingItemPayload` with `pictureUrls?` |
| `src/frontend/src/features/ebay/__tests__/api.test.ts` | Extend — test `uploadListingPicture` |
| `src/frontend/src/features/ebay/components/ListingFormPanel.tsx` | Add `imageUrls`, `onImageChange`, `appCode` props + render `ImagePicker` |
| `src/frontend/src/features/ebay/components/__tests__/ListingFormPanel.test.tsx` | Update tests for new props |
| `src/frontend/src/routes/listings_.new.tsx` | Wire `imageUrls` state, auto-populate from card selection, pass to form + API |
| `src/frontend/src/routes/__tests__/listings.new.test.tsx` | Update tests for image pre-population |
| `src/frontend/src/routes/listings.tsx` | Wire `imageUrls` state, pre-populate from listing, pass to form + API |
| `src/frontend/src/routes/__tests__/listings.test.tsx` | Update tests for image pre-population in edit flow |

## Testing Strategy

**`ImagePicker` unit tests:**
- Renders thumbnails for provided image URLs
- Remove button deletes image from list
- URL validation rejects non-HTTP strings with inline error
- Valid URL paste appends to list
- File selection triggers upload → spinner shown → resolved to thumbnail
- Failed upload shows error slot with retry button
- Drop zone hidden when at `maxImages` limit

**`uploadListingPicture` API unit test:**
- Calls `POST /integrations/ebay/listing/upload-picture?app_code=X` with FormData
- Returns `{ url }` from response

**`ListingFormPanel` tests:**
- Updated to pass `imageUrls`, `onImageChange`, `appCode` props

**`listings_.new.tsx` integration tests:**
- Selecting a card injects `card.image_normal` into `imageUrls`
- `createListing` receives `pictureUrls` when images are present

**`listings.tsx` integration tests:**
- Selecting a listing pre-populates `imageUrls` from `selectedListing.imageUrl`
- `updateListing` receives `pictureUrls` when images are present

**Backend unit test:**
- `upload_picture` endpoint calls `UploadSiteHostedPictures` and returns the eBay URL
- Rejects non-image Content-Type with 400
