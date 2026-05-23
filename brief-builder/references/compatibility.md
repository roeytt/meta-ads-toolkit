# Meta Ads Compatibility Matrix

Claude reads this file to determine which questions to ask and which options to show,
based on the campaign objective chosen in Q2. Never offer an incompatible option.
Never ask an irrelevant question. If the user requests something incompatible — explain
why and suggest the correct alternative.

---

## 1. Ad Format by Objective

| פורמט | AWARENESS | TRAFFIC | ENGAGEMENT | LEADS | SALES | APP |
|--------|:---------:|:-------:|:----------:|:-----:|:-----:|:---:|
| Single Image | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Single Video | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Carousel | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Existing Post | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |

> **⚠️ Script limitation:** `create_campaign.py` and `run_clone.py` currently support
> **Single Image only**. If the user requests Video or Carousel, note that manual creation
> in Ads Manager is required, or the scripts need to be extended.

**Existing Post — why it fails for LEADS/SALES/APP:**
- LEADS: the ad must contain a Lead Form attachment — existing posts cannot have one added
- SALES: the creative must be linked to the pixel and a specific landing URL — post boosts don't support this
- APP: must link to the App Store — existing posts can't be modified to do so

---

## 2. Conversion Location by Objective

Only ask about conversion location for the objectives below.
For AWARENESS → no conversion location question.

| מיקום המרה | TRAFFIC | ENGAGEMENT | LEADS | SALES | APP |
|------------|:-------:|:----------:|:-----:|:-----:|:---:|
| Website (אתר) | ✅ | ✅ | ✅ | ✅ | ❌ |
| Instant Form (טופס פייסבוק) | ❌ | ❌ | ✅ | ❌ | ❌ |
| Messenger | ✅ | ✅ | ✅ | ✅ | ❌ |
| WhatsApp (CTWA) | ✅ | ✅ | ✅ | ✅ | ❌ |
| Calls (שיחות) | ✅ | ❌ | ✅ | ✅ | ❌ |
| App | ✅ | ✅ | ✅ | ✅ | ✅ (only) |
| Catalog (DPA) | ❌ | ❌ | ❌ | ✅ | ❌ |

**Instant Form:** Only available for LEADS. If chosen → skip landing page URL question.
**WhatsApp (CTWA):** Ask for WhatsApp number + opening message instead of landing page.
**App:** Must have App ID. Skip pixel question.
**Catalog (DPA):** Not supported by current scripts — mention manual setup required.

---

## 3. Pixel & Conversion Event

Ask about pixel ONLY when conversion location = Website or App (with app SDK).

| אובייקטיב | פיקסל נדרש? |
|-----------|:-----------:|
| AWARENESS | ❌ |
| TRAFFIC | ❌ (optional for optimization) |
| ENGAGEMENT | ❌ |
| LEADS → Website | ✅ |
| LEADS → Instant Form | ❌ (Meta handles it internally) |
| SALES → Website | ✅ mandatory |
| SALES → App | App SDK instead |
| APP_PROMOTION | App SDK instead |

**If SALES + no pixel:** Do NOT proceed with OUTCOME_SALES.
Tell user: "קמפיין מכירות ללא פיקסל פעיל לא יעבוד — מטא אין לה מה לאופטמז.
נמליץ לעבור ל-OUTCOME_TRAFFIC עד שהפיקסל מוכן."

---

## 4. Bidding Strategy by Objective

Only offer strategies that make sense for the chosen objective.

| אסטרטגיה | AWARENESS | TRAFFIC | ENGAGEMENT | LEADS | SALES | APP |
|----------|:---------:|:-------:|:----------:|:-----:|:-----:|:---:|
| Highest Volume (ברירת מחדל) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Cost Cap | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| Bid Cap | ❌ | ✅ | ❌ | ✅ | ✅ | ✅ |
| ROAS Goal | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |

**Default for most campaigns:** Highest Volume (LOWEST_COST_WITHOUT_CAP).
**Cost Cap:** Ask for target CPA only when objective = LEADS / SALES / APP.
**ROAS Goal:** Ask only for SALES campaigns with established purchase history.

---

## 5. Advantage+ Creative (Auto Enhancements)

**Hebrew campaigns — what works and what doesn't:**

| פיצ'ר | עברית? | הערה |
|-------|:------:|------|
| Image brightness / contrast | ✅ | עובד — שינוי ויזואלי בלבד |
| Smart crop (aspect ratio adapt) | ✅ | עובד |
| Image expansion to 9:16 | ✅ | עובד |
| Text overlay on image | ⚠️ | עובד טכנית, אבל יכול לחסום RTL טקסט |
| 3D animation | ✅ | עובד |
| Music addition (video) | ✅ | עובד |
| AI text improvements | ❌ | **לא מוצע לעברית** — מטא לא מייצר עברית טובה |
| Alternative copy variations | ❌ | **לא מוצע לעברית** |

**Rule:** For Hebrew campaigns, offer only visual enhancements (rows 1-4).
Do NOT offer "AI text improvements" or "alternative copy variations" — these produce
poor Hebrew output and can override the user's carefully written copy.

**When to ask about enhancements:**
- AWARENESS: ✅ (image/video focused)
- TRAFFIC: ✅
- ENGAGEMENT: ✅
- LEADS: ✅ (visual only)
- SALES: ✅
- APP: ✅

---

## 6. Placements by Objective

All objectives support **Advantage+ Placements (automatic)** — always offer this as default.
Manual placement restrictions:

| מיקום | AWARENESS | TRAFFIC | ENGAGEMENT | LEADS | SALES | APP |
|-------|:---------:|:-------:|:----------:|:-----:|:-----:|:---:|
| Facebook Feed | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Instagram Feed | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Facebook Stories | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Instagram Stories | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Reels (FB+IG) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Marketplace | ❌ | ✅ | ❌ | ❌ | ✅ | ❌ |
| Search (FB) | ❌ | ✅ | ❌ | ✅ | ✅ | ❌ |
| Audience Network | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Messenger Inbox | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ |

**Reels format requirement:** Video only. If user selects Reels manually + image format → warn.

---

## 7. Campaign Structure Constraints

| | AWARENESS | TRAFFIC | ENGAGEMENT | LEADS | SALES | APP |
|-|:---------:|:-------:|:----------:|:-----:|:-----:|:---:|
| CBO (campaign-level budget) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Ad set-level budget | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Multiple ad sets | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Multiple body texts per ad (1-5) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Multiple headlines per ad (1-5) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

**Note on body text count:** Meta's DCO (Dynamic Creative) works with 1-5 body variants
and 1-5 headlines. More variations = more A/B data, but requires more creatives from user.

---

## 8. Quick Decision Rules (summary for Claude)

When user selects objective, **automatically**:

**AWARENESS →**
- Remove: pixel question, conversion location, bidding strategies except Highest Volume
- Remove: Instant Form, WhatsApp destination, App destination
- Remove: Existing Post question (allowed but unusual — only ask if user brings it up)
- Show: Reach / Impressions / Video Views as performance goal options

**TRAFFIC →**
- Ask: conversion location (Website / App / Messaging / Calls)
- Pixel: optional (if Website and user wants LPV optimization)
- Bidding: Highest Volume default; offer Bid Cap if user wants CPC control

**ENGAGEMENT →**
- Ask: where (Messaging / On Ad / Website / FB Page)
- If Messaging → ask WhatsApp or Messenger
- Remove: pixel question (unless website engagement)
- Existing Post: ✅ supported and common

**LEADS →**
- Ask: conversion location (Website / Instant Form / Messenger / Calls)
- If Website → ask pixel + event (Lead / Complete Registration / etc.)
- If Instant Form → skip landing URL
- Remove: Existing Post option
- Bidding: offer Cost Cap (ask for target CPL)

**SALES →**
- Pixel mandatory — check first, block if missing
- Ask: conversion event (Purchase / AddToCart / InitiateCheckout)
- Remove: Existing Post option
- Bidding: offer Cost Cap (target CPA) + ROAS Goal if advanced user

**APP →**
- Ask: App ID + store link
- Remove: pixel, existing post, website URL
- Ask: optimization event (Installs / In-App Purchase / Registration)
