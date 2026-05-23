# Creating campaigns from scratch

`scripts/create_campaign.py` builds an entire campaign tree (campaign → ad sets → creatives → ads) in one call from a spec JSON. This is a write operation — read `write-actions.md` first; the "Campaign creation" section at the bottom of that file is mandatory before you call `--confirm` for the first time in a session.

## The workflow

1. Write a spec JSON that describes the campaign you want.
2. Run `--dry-run`. This reads the spec, queries Meta for account currency, resolves interest names to IDs, and prints the plan — no writes.
3. Walk the plan back to the user. They name the change to confirm.
4. Run `--confirm`. The script creates everything PAUSED by default and writes a state JSON with every ID.
5. If the user wants to activate: they toggle ACTIVE in Ads Manager (or via the API). Never flip ACTIVE programmatically as part of creation — that removes the final checkpoint.

## Spec format (minimum viable)

```json
{
  "campaign_name": "My Campaign - Q2 Flight",
  "objective": "OUTCOME_TRAFFIC",
  "status": "PAUSED",
  "special_ad_categories": [],
  "identity": {
    "page_id": "1234567890",
    "instagram_user_id": "17841400000000000"
  },
  "landing_url": "https://example.com",
  "ad_sets": [
    {
      "name": "Angle A — Broad",
      "daily_budget": 50.00,
      "optimization_goal": "LINK_CLICKS",
      "billing_event": "LINK_CLICKS",
      "targeting": {
        "countries": ["IL"],
        "age_min": 25,
        "age_max": 45,
        "interests": ["Artificial intelligence", "Productivity"],
        "publisher_platforms": ["instagram"],
        "instagram_positions": ["stream", "story", "reels"]
      },
      "image_path": "./creative/angle_a.png",
      "ads": [
        {
          "name": "A1_Direct",
          "message": "Primary body copy — can be multi-line.",
          "headline": "Short punchy headline",
          "description": "Optional secondary line",
          "cta": "LEARN_MORE"
        }
      ]
    }
  ]
}
```

## Field reference

### Top level

| Field | Required | Notes |
|---|---|---|
| `campaign_name` | yes | Shows up in Ads Manager exactly as typed. Put identifiers (e.g. test name, date) in here for sanity later. |
| `objective` | yes | Meta's modern objectives: `OUTCOME_TRAFFIC`, `OUTCOME_AWARENESS`, `OUTCOME_ENGAGEMENT`, `OUTCOME_LEADS`, `OUTCOME_SALES`, `OUTCOME_APP_PROMOTION`. For courses/products without a pixel, use `OUTCOME_TRAFFIC`. For courses/products with a pixel firing Purchase, use `OUTCOME_SALES`. |
| `status` | no | Default `PAUSED`. Only override with `ACTIVE` if you're absolutely sure — you lose the review step. |
| `special_ad_categories` | no | Default `[]`. Required `["CREDIT"]`, `["EMPLOYMENT"]`, `["HOUSING"]`, `["ISSUES_ELECTIONS_POLITICS"]`, or `["FINANCIAL_PRODUCTS_SERVICES"]` for those regulated verticals. Wrong category here can get the whole campaign rejected. |
| `buying_type` | no | Default `AUCTION`. `RESERVED` is for Reach & Frequency (needs account eligibility). |
| `identity.page_id` | yes | The Facebook Page running the ads. Discover via `GET /me/accounts` or `GET /act_.../promote_pages`. |
| `identity.instagram_user_id` | no | The IG account running the ads (discover via the page's `instagram_business_account` field). Required if you want ads to show with your IG handle instead of a generic "Sponsored by Page Name". |
| `landing_url` | yes for traffic | Where clicks go. |

### Ad set level

| Field | Required | Notes |
|---|---|---|
| `name` | yes | Descriptive. Good habits: include angle + audience descriptor, e.g. "Angle 1 — Broad IL 25-45 AI". |
| `daily_budget` | one of | Major units in account currency (50.00 for ₪50). Script queries the currency, converts to minor units (agorot/cents). |
| `lifetime_budget` + `end_time` | one of | Use when you want a total spend cap instead of daily pacing. `end_time` is ISO 8601. |
| `billing_event` | no | Default `LINK_CLICKS`. `IMPRESSIONS` if optimizing for reach. |
| `optimization_goal` | no | Default `LINK_CLICKS`. Common: `LANDING_PAGE_VIEWS`, `OFFSITE_CONVERSIONS` (needs pixel), `REACH`, `IMPRESSIONS`. |
| `bid_strategy` | no | Default `LOWEST_COST_WITHOUT_CAP`. Use `COST_CAP` with `bid_amount` when you want to hold a CPA ceiling. |
| `bid_amount` | conditional | Major units. Required if `bid_strategy=COST_CAP` or `LOWEST_COST_WITH_BID_CAP`. |
| `status` | no | Default `PAUSED`. |
| `targeting.countries` | yes | ISO-2 list, e.g. `["IL"]`. Or use full `geo_locations` dict for regions/cities. |
| `targeting.age_min` / `age_max` | no | Defaults to Meta's (18-65). Narrow deliberately. |
| `targeting.genders` | no | `[1]` male, `[2]` female, omit for all. |
| `targeting.interests` | no | List of names — script resolves to IDs via `/search?type=adinterest`. Names with no match are dropped and warned. For stability across runs, use `interest_ids` instead. |
| `targeting.interest_ids` | no | Pre-resolved numeric IDs. Bypasses the search lookup. |
| `targeting.publisher_platforms` | no | Default `["instagram"]`. Add `"facebook"`, `"messenger"`, `"audience_network"`. |
| `targeting.instagram_positions` | no | Default `["stream", "story", "reels"]`. |
| `targeting.facebook_positions` | no | Default `["feed", "story", "video_feeds"]` when facebook is in publisher_platforms. |
| `targeting.advantage_audience` | no | Default `true`. Allows Meta to expand beyond your interests when it finds high-intent users outside them. Turn off with `false` for strict targeting tests. |
| `targeting.custom_audiences` | no | List of `{"id": "..."}`. |
| `targeting.excluded_custom_audiences` | no | Same shape. Useful for excluding existing customers. |
| `image_path` | one of | Path to image file, uploaded to `/act_.../adimages` once per ad set. Recommended: 4:5 or 1:1, PNG, under 4 MB. |
| `image_hash` | one of | Pre-uploaded image hash (skip upload). |

### Ad level

Each ad inside an ad set uses the ad set's image.

| Field | Required | Notes |
|---|---|---|
| `name` | yes | Ad is named `Ad_<name>` and its creative `Creative_<name>`. Keep short and unique within the campaign. |
| `message` | yes | Primary body text. Multi-line allowed. No length limit enforced by the API, but Meta truncates in-feed around 125 characters before "See More". |
| `headline` | yes | Bold headline below the image. Keep under 40 characters for mobile. |
| `description` | no | Small gray line below headline. Often cut by placements. |
| `cta` | no | Default `LEARN_MORE`. Others: `SIGN_UP`, `SHOP_NOW`, `DOWNLOAD`, `GET_OFFER`, `GET_QUOTE`, `SUBSCRIBE`, `CONTACT_US`, `APPLY_NOW`, `WATCH_MORE`, `INSTALL_MOBILE_APP`, `USE_APP`, `MESSAGE_PAGE`, `WHATSAPP_MESSAGE`, `NO_BUTTON`. |
| `image_path` | conditional | Per-ad primary image (4:5 or 1:1 recommended). Overrides the ad-set-level image. Required if the ad set has no `image_path`/`image_hash`. |
| `secondary_image_path` | no | Path to a second image (9:16 recommended) for placement-specific delivery. When provided, the script switches from `object_story_spec` to `asset_feed_spec` and uploads both images. Meta automatically serves the primary image on Feed and the secondary image on Stories/Reels. Use this whenever you prepare separate assets for vertical placements — it guarantees correct framing instead of relying on Meta's auto-crop. |
| `url` | no | Per-ad landing URL override. Use for UTM-tagged URLs unique to each creative. Falls back to the spec's top-level `landing_url`. |
| `standard_enhancements` | no | Default `false` (opts out). Meta's auto-enhancements alter the creative — brightness, cropping, text overlays. Leave opt-out if you care about pixel-for-pixel fidelity. |
| `status` | no | Default `PAUSED`. |

#### Two-image workflow (4:5 + 9:16)

When a campaign targets Advantage+ Placements (which includes both Feed and Stories/Reels), prepare two image files per ad and use both fields:

```json
{
  "name": "my-ad",
  "headline": "Your headline",
  "message": "Body copy...",
  "image_path": "/path/to/my-ad-4x5.png",
  "secondary_image_path": "/path/to/my-ad-9x16.png",
  "url": "https://example.com/?utm_content=my-ad",
  "cta": "LEARN_MORE"
}
```

The script uploads both files, then attempts an `asset_feed_spec` creative with `"ad_formats": ["SINGLE_IMAGE"]`. Meta matches each image to its optimal placement automatically — no manual step in Ads Manager required.

**App permission required:** `asset_feed_spec` needs the Meta app to have the dynamic-creative capability enabled in Meta Business Manager. If the app lacks it, the script automatically falls back to `object_story_spec` (4:5 primary image only) and logs a warning. In fallback mode, Meta's Advantage+ Creative auto-adapts the 4:5 image for Stories/Reels placements. To unlock native multi-image creatives, grant the app the dynamic-creative capability: Business Manager → Apps → [your app] → Capabilities.

Without `secondary_image_path`, the script always uses the original `object_story_spec` (single-image) path.

## Carousel ads

Use `carousel_cards` on the ad to create a multi-card carousel. Each card has its own image, headline, description, and URL.

```json
{
  "name": "Carousel_WebinarAngles",
  "message": "Primary text shown above the carousel — same for all cards.",
  "cta": "LEARN_MORE",
  "carousel_cards": [
    {
      "image_path": "./creative/card1.png",
      "headline": "Card 1 — First benefit",
      "description": "Short supporting line",
      "url": "https://example.com/?card=1"
    },
    {
      "image_path": "./creative/card2.png",
      "headline": "Card 2 — Second benefit",
      "description": "Short supporting line",
      "url": "https://example.com/?card=2"
    },
    {
      "image_path": "./creative/card3.png",
      "headline": "Card 3 — Third benefit",
      "url": "https://example.com/?card=3"
    }
  ]
}
```

**Field reference for carousel_cards items:**

| Field | Required | Notes |
|---|---|---|
| `image_path` | yes | Path to the card's image. Square (1:1) recommended for carousels. |
| `headline` | yes | Bold text below each card. Keep under 40 characters. |
| `description` | no | Small gray line below the headline. Often truncated on mobile. |
| `url` | no | Per-card destination URL. Falls back to the ad-level `url` or spec-level `landing_url`. |

**Optional carousel-level flags on the ad:**

| Field | Default | Notes |
|---|---|---|
| `multi_share_optimized` | `true` | Meta re-orders cards by performance. Set `false` to lock card order. |
| `multi_share_end_card` | `false` | Adds a final "See more at [Page]" card. Usually off for direct-response. |

Minimum 2 cards, maximum 10.

## Multiple body text and headlines (DCO)

Use `messages` (list) and/or `headlines` (list) instead of the singular `message`/`headline` to enable Dynamic Creative Optimization. Meta automatically tests all combinations and surfaces the best-performing ones.

```json
{
  "name": "Ad_DCO_Test",
  "image_path": "./creative/main.png",
  "messages": [
    "First body text — problem angle. Multi-line supported.",
    "Second body text — solution angle.",
    "Third body text — social proof angle."
  ],
  "headlines": [
    "Headline option A",
    "Headline option B"
  ],
  "cta": "SIGN_UP",
  "url": "https://example.com"
}
```

Meta can test up to **5 body variants** and **5 headline variants** per ad (25 combinations max). More variants = more A/B signal, but requires sufficient impressions to be statistically meaningful.

**DCO + two images:** Combine `messages`/`headlines` with `secondary_image_path` — the `asset_feed_spec` will include both images along with all text variants.

**Fallback:** If the Meta app lacks the `dynamic-creative` capability, the script falls back to `object_story_spec` using the first message and first headline only. A warning is logged. To enable DCO natively, grant the app dynamic-creative capability in Meta Business Manager → Apps → Capabilities.

## Currency handling

The script queries `/act_.../?fields=currency` once at the start and converts `daily_budget` / `lifetime_budget` / `bid_amount` from major units to whatever minor unit the account uses:

- ILS / USD / EUR / GBP etc. → × 100 (agorot, cents, pence)
- JPY / KRW / VND / ISK / TWD / XAF / XOF / CLP → × 1 (no minor unit)

Write budgets in major units only. Never try to pre-convert.

## Interest resolution

`targeting.interests` names are resolved via Meta's `/search?type=adinterest` endpoint. The script takes the top-ranked hit per name. This is convenient for readable specs but has two caveats:

1. The search ranking can change. A spec that resolved to "Productivity" today might resolve to "Productivity (software category)" tomorrow.
2. Search can return no match. Those names are dropped with a `[warn]` log.

For specs you'll re-run months later and want identical targeting, do one dry-run, copy the `resolved_interests` IDs into `interest_ids`, and delete `interests`. Now the targeting is frozen.

## State file and rollback

Every `--confirm` run writes `<spec>_state_<timestamp>.json` with every object ID:

```json
{
  "ok": true,
  "campaign_id": "120...",
  "ad_sets": [
    {"adset_id": "120...", "image_hash": "...", "ads": [{"ad_id": "120...", "creative_id": "120..."}]}
  ],
  "objects": [{"type": "campaign", "id": "120...", "name": "..."}, ...]
}
```

`scripts/rollback_creation.py --state <file> --pause` pauses everything. `--delete` permanently deletes in reverse order (ads → creatives are orphaned → adsets → campaign). Prefer `--pause` unless you really want the objects gone from Ads Manager history.

## Common errors and how to handle them

**`error_subcode 1885036` — Ad account is unsettled.** The campaign objects get created fine but nothing will deliver until the account balance is paid. Don't block on this at creation time; surface it to the user and continue.

**`The ad creative spec is invalid`.** Usually missing `page_id` or a malformed `call_to_action` value. Double-check the `cta` is in `VALID_CTAS` and the landing URL is fully qualified (`https://...`).

**`Invalid parameter` on `flexible_spec`.** Means an interest ID is stale. Re-run the dry-run so search re-resolves names, or remove the offending interest.

**`special_ad_categories` mismatch.** If your ad is in a regulated vertical and you forgot to mark it, Meta rejects the whole ad set. Reviewable in the ad set's `delivery_info` in Ads Manager.

**Account not admin of page.** The ad account owner must have advertiser-or-higher role on the Facebook Page. Fix in Business Settings → Pages → assign.

**Instagram identity missing.** If `instagram_user_id` is omitted, ads still run on Instagram placements but show "Sponsored by <Page Name>" instead of your IG handle. Almost always you want to set it.

## When to NOT use this script

- **You only want to duplicate an existing ad.** Use `scripts/duplicate_ad.py` — it copies targeting, creative, and settings in one shot and is one API call instead of six.
- **You're iterating on creative for an existing ad set.** Creating a new campaign per iteration pollutes Ads Manager. Add new ads to the existing ad set via a partial spec or do it in the UI.
- **You want dynamic creative / catalog ads / collection ads.** Those have different creative shapes (`asset_feed_spec`, `product_set_id`, `template_data`). This script only handles single-image link ads. Extend it or build a sibling script.
