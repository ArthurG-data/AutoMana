# eBay MTG Single-Card Listing Template

**Market:** eBay Australia (site ID `15`, currency AUD)
**Listing format:** Fixed-price / Buy It Now, Good Till Cancelled
**Data sources:** Scryfall card data + seller input at listing time + `{{PRICING_STRATEGY.*}}` (future pricing service) + `{{BRAND.*}}` (future brand service)

---

## How to read this document

- **Scryfall field** — the column or relation in AutoMana's `card_catalog.*` schema that supplies the value.
- **`{{BRAND.*}}`** — a brand service slot. Leave as placeholder until the brand service is registered. A future skill will fill these from a seller/store profile record.
- **`{{PRICING_STRATEGY.*}}`** — a pricing strategy slot. The pricing service determines the value; this template only specifies *which* `ItemModel` fields to set.
- **Seller input** — collected interactively from the seller at listing time (condition, quantity, any override notes).

All field names reference `automana.core.models.ebay.listings.ItemModel` (the Python model). The XML generator in `xml_utils.py` serialises it to `AddFixedPriceItemRequest`.

---

## Bug to fix before first use

`listings_write_service.py:51` has an incorrect comment:

```python
# eBay UK site id. Magic numbers are rude; named constants are manners.
DEFAULT_MARKETPLACE_ID: str = "15"
```

Site `15` is **eBay Australia** (EBAY-AU), not eBay UK (which is site `3`, EBAY-GB). The value is correct; the comment is wrong. Fix the comment before the listing service goes to production.

---

## Section 1 — Identity

These fields identify the card in the eBay catalogue. They are populated automatically from Scryfall data.

### 1.1 Title (`ItemModel.Title`)

Max 80 characters. eBay search indexes the title heavily — keyword order matters.

**Formula:**

```
{card_name} {set_code_upper} {collector_number} {foil_tag} {language_tag} {condition_tag} MTG
```

| Token | Source | Example |
|---|---|---|
| `card_name` | `scryfall_cards.name` | `Sheoldred, the Apocalypse` |
| `set_code_upper` | `scryfall_sets.code.upper()` | `DMU` |
| `collector_number` | `scryfall_cards.collector_number` | `107` |
| `foil_tag` | if `scryfall_cards.foil == true` → `"FOIL"`, else omit | `FOIL` |
| `language_tag` | if `scryfall_cards.lang != "en"` → ISO 639-1 code upper, else omit | `JA` |
| `condition_tag` | seller input (NM / LP / MP / HP / DMG) | `NM` |

**Rules:**
- If the result exceeds 80 characters, drop `collector_number` first, then abbreviate `set_code_upper` further.
- Never truncate `card_name` — it is the primary search term.
- Do not include price, store name, or exclamation marks in the title (eBay policy violation risk).

**Example output:**
```
Sheoldred, the Apocalypse DMU 107 FOIL NM MTG               (53 chars)
Sheoldred, the Apocalypse DMU 107 JA NM MTG                 (46 chars)
```

**Brand extension:** `{{BRAND.title_suffix}}` — an optional 1–5 character tag appended after `MTG` if space allows (e.g., store abbreviation). Default: empty.

---

### 1.2 Subtitle (`ItemModel.SubTitle`)

Optional, costs ~AU$2 per listing. Recommended for rare/mythic cards only.

**Formula:**
```
{set_name} · {rarity_display} · {type_line_short} · {{BRAND.store_tagline}}
```

| Token | Source |
|---|---|
| `set_name` | `scryfall_sets.name` |
| `rarity_display` | `scryfall_cards.rarity` capitalised (`Mythic`, `Rare`, etc.) |
| `type_line_short` | first word(s) of `scryfall_cards.type_line` up to `—` (e.g., `Legendary Creature`) |
| `{{BRAND.store_tagline}}` | brand service slot — default: `"Fast AU Shipping"` |

**Rule:** Only generate a subtitle if `rarity IN ('rare', 'mythic')`. Suppress for commons and uncommons to avoid the fee.

---

### 1.3 SKU (`ItemModel.SKU`)

Used for inventory tracking and idempotency matching. Never shown to buyers.

**Formula:**
```
{scryfall_id}-{condition}-{foil_flag}
```

| Token | Example |
|---|---|
| `scryfall_id` | `d3140a7c-f96a-4857-9d0c-c9fe0f43ad7c` |
| `condition` | `NM` / `LP` / `MP` / `HP` / `DMG` |
| `foil_flag` | `F` if foil, `N` if non-foil |

**Example:** `d3140a7c-f96a-4857-9d0c-c9fe0f43ad7c-NM-F`

---

### 1.4 Quantity (`ItemModel.Quantity`)

Seller input. Minimum `1`. GTC listings decrement stock on each sale — no action needed from the skill.

---

## Section 2 — Pricing (Strategy Stub)

The listing template sets these fields but does **not** define the values. The pricing strategy service owns that decision. This section documents the wiring only.

| `ItemModel` field | Meaning | Who sets it |
|---|---|---|
| `StartPrice.text` | Buy It Now price in AUD | `{{PRICING_STRATEGY.buy_it_now_price_aud}}` |
| `StartPrice.currencyID` | Always `"AUD"` | Constant |
| `Currency` | Always `"AUD"` | Constant |
| `BestOfferDetails` | `None` (Best Offer disabled — fixed-price only per scope) | Constant |

**Pricing strategy inputs the service will receive (for context):**
- `scryfall_cards.name`, `scryfall_cards.set_code`, `scryfall_cards.foil`
- Condition tier (NM/LP/MP/HP/DMG)
- MTGStock market price for the card (from `pricing.*` schema)
- `{{PRICING_STRATEGY.margin_profile}}` — a per-seller markup configuration

The pricing service is outside the scope of this document. See future spec: `docs/superpowers/specs/*-ebay-pricing-strategy.md`.

---

## Section 3 — Condition

Seller selects one condition at listing time. The skill maps it to the eBay AU condition system.

### 3.1 Condition ID mapping (`ItemModel.ConditionID`)

eBay AU uses numeric condition IDs for the trading cards collectibles category. Verify these via `GetCategoryFeatures` API call for category `{{EBAY_AU_MTG_CATEGORY_ID}}` before production use — eBay can update IDs.

| Seller condition | eBay `ConditionID` | eBay display name |
|---|---|---|
| NM (Near Mint) | `3000` | Near Mint or Better |
| LP (Lightly Played) | `4000` | Very Good |
| MP (Moderately Played) | `5000` | Good |
| HP (Heavily Played) | `6000` | Acceptable |
| DMG (Damaged) | `7000` | Poor |

### 3.2 Condition Description (`ItemModel.ConditionDescription`)

Free-text field shown to buyers. The skill auto-generates a base description; sellers can override.

**Default templates per tier:**

| Condition | Default `ConditionDescription` |
|---|---|
| NM | `Card is Near Mint. No visible play wear. Stored in sleeve from opening.` |
| LP | `Card is Lightly Played. Minimal edge wear or light surface scratches. Does not affect gameplay.` |
| MP | `Card is Moderately Played. Noticeable wear on edges or surface. Fully playable.` |
| HP | `Card is Heavily Played. Significant wear. Suitable for casual play or proxy use.` |
| DMG | `Card is Damaged. Creases, tears, or markings present. Sold as-is.` |

**Rule:** Sellers may append a personal note after the default text. The listing skill should expose an optional `condition_note` input that, when provided, appends: ` Seller note: {condition_note}`.

---

## Section 4 — Description Variants

The `ItemModel.Description` field accepts HTML. Two templates are provided.

### 4.1 Minimal Description

Use for bulk listings or when speed matters. No images, no branding.

```html
<div style="font-family: Arial, sans-serif; font-size: 14px; color: #333;">
  <h2>{card_name}</h2>
  <p><strong>Set:</strong> {set_name} ({set_code_upper})</p>
  <p><strong>Condition:</strong> {condition_label} — {condition_description_text}</p>
  <p><strong>Language:</strong> {language_label}</p>
  {foil_line}
  <hr/>
  <p><em>{oracle_text}</em></p>
</div>
```

**Variable mapping:**

| Template variable | Source |
|---|---|
| `card_name` | `scryfall_cards.name` |
| `set_name` | `scryfall_sets.name` |
| `set_code_upper` | `scryfall_sets.code.upper()` |
| `condition_label` | e.g., `"Near Mint (NM)"` |
| `condition_description_text` | Section 3.2 default text |
| `language_label` | ISO language name (e.g., `"English"`, `"Japanese"`) |
| `foil_line` | `<p><strong>Finish:</strong> Foil</p>` if foil, else omit |
| `oracle_text` | `scryfall_cards.oracle_text` (replace `\n` with `<br/>`) |

---

### 4.2 Full Card Profile Description (Default)

Use for all standard listings. Includes card image, full text, and brand header/footer.

```html
{{BRAND.header_html}}

<div style="font-family: Arial, sans-serif; font-size: 14px; color: #333; max-width: 640px; margin: 0 auto;">

  <!-- Card image -->
  <div style="text-align: center; margin-bottom: 16px;">
    <img src="{image_url}" alt="{card_name}" style="max-width: 260px; border-radius: 8px;" />
  </div>

  <!-- Identity block -->
  <h2 style="color: {{BRAND.accent_color}};">{card_name}</h2>
  <table style="width: 100%; border-collapse: collapse; margin-bottom: 12px;">
    <tr><td style="padding: 4px 8px; font-weight: bold;">Set</td><td style="padding: 4px 8px;">{set_name} ({set_code_upper}) #{collector_number}</td></tr>
    <tr style="background:#f9f9f9;"><td style="padding: 4px 8px; font-weight: bold;">Type</td><td style="padding: 4px 8px;">{type_line}</td></tr>
    <tr><td style="padding: 4px 8px; font-weight: bold;">Rarity</td><td style="padding: 4px 8px;">{rarity_display}</td></tr>
    <tr style="background:#f9f9f9;"><td style="padding: 4px 8px; font-weight: bold;">Language</td><td style="padding: 4px 8px;">{language_label}</td></tr>
    <tr><td style="padding: 4px 8px; font-weight: bold;">Finish</td><td style="padding: 4px 8px;">{finish_label}</td></tr>
    <tr style="background:#f9f9f9;"><td style="padding: 4px 8px; font-weight: bold;">Condition</td><td style="padding: 4px 8px;">{condition_label}</td></tr>
  </table>

  <!-- Oracle text -->
  <div style="border-left: 3px solid {{BRAND.accent_color}}; padding-left: 12px; margin-bottom: 12px;">
    <p style="margin: 0;"><em>{oracle_text_html}</em></p>
  </div>

  <!-- Flavor text (if present) -->
  {flavor_block}

  <!-- Mana cost / stats -->
  {stats_block}

  <!-- Condition note -->
  <div style="background: #fff8e1; border: 1px solid #ffe082; border-radius: 4px; padding: 10px; margin-bottom: 12px;">
    <strong>Condition:</strong> {condition_label}<br/>
    {condition_description_text}
    {seller_condition_note_block}
  </div>

  <!-- Shipping & policies -->
  <div style="font-size: 12px; color: #666; border-top: 1px solid #eee; padding-top: 10px;">
    {{BRAND.footer_html}}
  </div>

</div>
```

**Additional variable mapping (beyond Section 4.1):**

| Template variable | Source |
|---|---|
| `image_url` | `scryfall_cards.image_uris.normal` (prefer `large` if available) |
| `type_line` | `scryfall_cards.type_line` |
| `rarity_display` | `scryfall_cards.rarity` capitalised |
| `finish_label` | `"Foil"` if foil, else `"Non-Foil"` |
| `oracle_text_html` | `scryfall_cards.oracle_text` with `\n` → `<br/>`, `{T}` → `[T]` etc. |
| `flavor_block` | `<p style="font-style:italic; color:#777;">{flavor_text}</p>` if `flavor_text` exists, else `""` |
| `stats_block` | Power/toughness line if creature, loyalty if planeswalker, else `""` |
| `seller_condition_note_block` | `<br/><em>Seller note: {condition_note}</em>` if provided, else `""` |

**Brand slots in this template:**

| Slot | Purpose | Default (no brand service) |
|---|---|---|
| `{{BRAND.header_html}}` | Store banner/logo HTML at top of description | `""` (empty) |
| `{{BRAND.footer_html}}` | Shipping/returns boilerplate, store links | See Section 4.3 |
| `{{BRAND.accent_color}}` | Hex color for headings and borders | `"#1a73e8"` (neutral blue) |

---

### 4.3 Default Footer HTML (no brand service)

When `{{BRAND.footer_html}}` is not yet defined, use this fallback:

```html
<p>✅ Fast dispatch from Australia · Tracked postage available · Combined shipping on multiple orders</p>
<p>Cards are shipped in a sleeve inside a rigid toploader, then bubble-wrapped for protection.</p>
<p>Returns accepted within 30 days if item not as described. Please message before opening a case.</p>
```

Brand service will replace this entirely with its own registered footer.

---

## Section 5 — Category & Item Specifics

### 5.1 eBay AU Category (`ItemModel.PrimaryCategory`)

| Field | Value |
|---|---|
| `PrimaryCategory.CategoryID` | `"38292"` — Toys, Hobbies & Collectibles → Collectible Card Games → Magic: The Gathering → Individual Cards (eBay AU). **Verify via `GetCategories` before production.** |

**Verification command (Trading API):**
Call `GetSuggestedCategories` with query `"Magic the Gathering single card"` on eBay AU (site `15`) to confirm the leaf category ID is still `38292`. Category trees shift during eBay catalogue updates.

---

### 5.2 Item Specifics (`ItemModel.ItemSpecifics`)

eBay AU requires specific attributes in the MTG category. Missing required specifics cause listing failures or suppressed search visibility.

**Required specifics:**

| Specific name | Source | Example value |
|---|---|---|
| `Game` | Constant | `"Magic: The Gathering"` |
| `Card Name` | `scryfall_cards.name` | `"Sheoldred, the Apocalypse"` |
| `Set` | `scryfall_sets.name` | `"Dominaria United"` |
| `Rarity` | `scryfall_cards.rarity` mapped (see below) | `"Mythic Rare"` |
| `Language` | `scryfall_cards.lang` mapped (see below) | `"English"` |
| `Finish` | Derived from `scryfall_cards.foil` | `"Foil"` / `"Regular"` |
| `Graded` | Constant (raw cards only) | `"No"` |

**Recommended specifics (improve search visibility):**

| Specific name | Source | Example value |
|---|---|---|
| `Card Number` | `scryfall_cards.collector_number` | `"107"` |
| `Type` | First segment of `scryfall_cards.type_line` | `"Legendary Creature"` |
| `Colour` | Derived from `scryfall_cards.colors` (see below) | `"Black"` |
| `Mana Cost` | `scryfall_cards.mana_cost` | `"{2}{B}{B}"` |

**Rarity mapping (Scryfall → eBay display):**

| Scryfall `rarity` | eBay Item Specific value |
|---|---|
| `common` | `"Common"` |
| `uncommon` | `"Uncommon"` |
| `rare` | `"Rare"` |
| `mythic` | `"Mythic Rare"` |
| `special` | `"Special"` |
| `bonus` | `"Special"` |

**Language mapping (Scryfall `lang` ISO → eBay display):**

| `lang` | eBay value |
|---|---|
| `en` | `"English"` |
| `ja` | `"Japanese"` |
| `de` | `"German"` |
| `fr` | `"French"` |
| `it` | `"Italian"` |
| `es` | `"Spanish"` |
| `pt` | `"Portuguese"` |
| `ru` | `"Russian"` |
| `ko` | `"Korean"` |
| `zhs` | `"Chinese Simplified"` |
| `zht` | `"Chinese Traditional"` |
| `he` | `"Hebrew"` |
| `ar` | `"Arabic"` |
| `grc` | `"Ancient Greek"` |
| `la` | `"Latin"` |
| other | `"Other"` |

**Color mapping (Scryfall `colors` list → eBay single value):**

| `colors` | eBay `Colour` value |
|---|---|
| `[]` | `"Colorless"` |
| `["W"]` | `"White"` |
| `["U"]` | `"Blue"` |
| `["B"]` | `"Black"` |
| `["R"]` | `"Red"` |
| `["G"]` | `"Green"` |
| 2 colors | `"Multi-Color"` |
| 3+ colors | `"Multi-Color"` |

**How to populate `ItemModel.ItemSpecifics`:**

`ItemSpecifics` is a `dict` in the model. The Trading API expects it as a `NameValueList` structure in XML. Use this shape:

```python
item.ItemSpecifics = {
    "NameValueList": [
        {"Name": "Game", "Value": "Magic: The Gathering"},
        {"Name": "Card Name", "Value": card_name},
        {"Name": "Set", "Value": set_name},
        {"Name": "Rarity", "Value": rarity_display},
        {"Name": "Language", "Value": language_label},
        {"Name": "Finish", "Value": finish_label},
        {"Name": "Graded", "Value": "No"},
        # recommended:
        {"Name": "Card Number", "Value": collector_number},
        {"Name": "Type", "Value": type_line_short},
        {"Name": "Colour", "Value": color_value},
    ]
}
```

---

## Section 6 — Shipping Defaults

MTG singles are small, light, and standardised. These defaults suit the eBay AU letter/large letter rate.

### 6.1 Shipping type (`ItemModel.ShippingDetails.ShippingType`)

```
"Flat"
```

Flat-rate shipping — same cost regardless of buyer location within AU.

### 6.2 Domestic shipping service

| `ItemModel` field | Value |
|---|---|
| `ShippingDetails.ShippingServiceOptions[0].ShippingService` | `"AU_StandardDelivery"` |
| `ShippingDetails.ShippingServiceOptions[0].ShippingServiceCost.text` | `{{PRICING_STRATEGY.domestic_shipping_cost_aud}}` — brand/strategy slot. Default: `"0.00"` (free shipping, price baked in) |
| `ShippingDetails.ShippingServiceOptions[0].ShippingServicePriority` | `1` |
| `ShippingDetails.ShippingServiceOptions[0].ExpeditedService` | `False` |

**Tracked option (optional second service):**

| Field | Value |
|---|---|
| `ShippingService` | `"AU_RegisteredParcelPost"` |
| `ShippingServiceCost.text` | `{{BRAND.tracked_shipping_cost_aud}}` — default: `"4.50"` |
| `ShippingServicePriority` | `2` |
| `ExpeditedService` | `True` |

### 6.3 Package dimensions (`ItemModel.ShippingDetails` / ship package)

For a single card in sleeve + toploader:

| Attribute | Value |
|---|---|
| `ShippingPackage` | `"Letter"` |
| `WeightMajor` | `0` (kg) |
| `WeightMinor` | `50` (grams) |

For 2–20 cards (lot): use `"LargeEnvelope"`, `WeightMinor = 150`.
For 20+ cards: use `"PackageThickEnvelope"`, `WeightMinor = 300`.

### 6.4 Dispatch time (`ItemModel.DispatchTimeMax`)

`{{BRAND.dispatch_days}}` — brand service slot. Default: `3` (business days).

### 6.5 Ship-to locations (`ItemModel.ShipToLocations`)

`"AU"` — Australia only by default. Brand service can expand to `"Worldwide"` for international selling.

---

## Section 7 — Policies

### 7.1 Return Policy (`ItemModel.ReturnPolicy`)

| Field | Value |
|---|---|
| `ReturnsAcceptedOption` | `"ReturnsAccepted"` |
| `ReturnsWithinOption` | `"Days_30"` |
| `RefundOption` | `"MoneyBack"` |
| `ShippingCostPaidByOption` | `"Buyer"` (buyer pays return shipping) |
| `Description` | `{{BRAND.return_policy_description}}` — default: `"Returns accepted within 30 days if item is not as described. Please message us before opening a case."` |

### 7.2 Seller Profiles (`ItemModel.SellerProfiles`)

Seller account–level profiles managed in eBay Business Policies. These IDs are set once per seller account and reused on every listing.

| Field | Value |
|---|---|
| `SellerShippingProfileID` | `{{BRAND.seller_shipping_profile_id}}` |
| `SellerReturnProfileID` | `{{BRAND.seller_return_profile_id}}` |
| `SellerPaymentProfileID` | `{{BRAND.seller_payment_profile_id}}` |

When SellerProfiles are set, `ShippingDetails` and `ReturnPolicy` fields on the item are overridden by the profile. Set **either** inline policies (Sections 6 + 7.1) **or** SellerProfiles — not both. The skill should check whether `{{BRAND.seller_shipping_profile_id}}` is populated and use SellerProfiles if so, inline policies otherwise.

---

## Section 8 — Other Required Fields

These fields must be set on every listing but have no MTG-specific complexity.

| `ItemModel` field | Value | Notes |
|---|---|---|
| `ListingType` | `"FixedPriceItem"` | Fixed-price scope |
| `ListingDuration` | `"GTC"` | Good Till Cancelled — standard for fixed-price |
| `Country` | `"AU"` | Seller location country |
| `PostalCode` | `{{BRAND.seller_postcode}}` | Required by eBay AU for location display |
| `Location` | `{{BRAND.seller_location_display}}` | Human-readable, e.g., `"Sydney, NSW"` |
| `Site` | `"Australia"` | eBay site name (Trading API string for site 15) |
| `Currency` | `"AUD"` | |
| `PaymentMethods` | `["PayPal"]` | Legacy eBay AU accounts only. Managed Payments sellers (post-2023 onboarding) must **omit** this field entirely — supplying it causes an API error. |
| `AutoPay` | `True` | Required for GTC fixed-price |

---

## Brand Service Contract

When the brand service is implemented, it must supply the following key-value pairs (stored in a seller profile record in the DB):

| Key | Type | Description |
|---|---|---|
| `BRAND.store_name` | `str` | Store display name |
| `BRAND.store_tagline` | `str` | Short tagline for subtitle (max 20 chars) |
| `BRAND.title_suffix` | `str \| None` | Optional tag appended to listing title |
| `BRAND.accent_color` | `str` | Hex color for description styling (e.g., `"#c0392b"`) |
| `BRAND.header_html` | `str` | Full HTML block for top of description |
| `BRAND.footer_html` | `str` | Full HTML block for bottom of description |
| `BRAND.return_policy_description` | `str` | Return policy plain-text |
| `BRAND.dispatch_days` | `int` | DispatchTimeMax in business days |
| `BRAND.tracked_shipping_cost_aud` | `str` | Cost for tracked option, e.g., `"4.50"` |
| `BRAND.seller_postcode` | `str` | Seller's AU postcode |
| `BRAND.seller_location_display` | `str` | Human-readable location string |
| `BRAND.seller_shipping_profile_id` | `int \| None` | eBay Business Policy shipping profile ID |
| `BRAND.seller_return_profile_id` | `int \| None` | eBay Business Policy return profile ID |
| `BRAND.seller_payment_profile_id` | `int \| None` | eBay Business Policy payment profile ID |

A `None` value for profile IDs means inline policies (Sections 6 + 7.1) are used instead.

---

## Pricing Strategy Contract

When the pricing strategy service is implemented, it must supply:

| Key | Type | Description |
|---|---|---|
| `PRICING_STRATEGY.buy_it_now_price_aud` | `Decimal` | Final AUD price for the listing |
| `PRICING_STRATEGY.domestic_shipping_cost_aud` | `Decimal` | Domestic standard shipping cost (0.00 = free) |

The strategy service receives: `scryfall_id`, condition tier, foil flag, language, MTGStock market price, and a margin profile from the brand configuration.

---

## Checklist for the Listing Skill

A future skill implementing this template should complete these steps in order:

1. Resolve card data from `card_catalog.*` using `scryfall_id`
2. Validate seller inputs: condition (NM/LP/MP/HP/DMG), quantity ≥ 1
3. Load brand slots from seller profile record (or use defaults)
4. Call pricing strategy service → receive `buy_it_now_price_aud`, `domestic_shipping_cost_aud`
5. Build `ItemModel`:
   - Section 1: Identity fields (title, subtitle, SKU, quantity)
   - Section 2: Pricing fields
   - Section 3: ConditionID + ConditionDescription
   - Section 4: Description (full variant by default, minimal if `description_mode="minimal"`)
   - Section 5: PrimaryCategory + ItemSpecifics
   - Section 6: ShippingDetails
   - Section 7: ReturnPolicy or SellerProfiles (not both)
   - Section 8: Required constants
6. Call `create_listing` service with the built `ItemModel` + a fresh `idempotency_key` (UUID4)
7. Store returned `ItemID` in the local DB against the card/inventory record
