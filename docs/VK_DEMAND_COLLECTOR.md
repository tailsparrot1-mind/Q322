# VK selected-content importer

This adapter normalizes VK posts/comments that the user has explicitly selected and exported into a local JSON file. It does **not** automate VK browsing or scrape search results.

## Why this is manual for now

VK's published platform/API rules include restrictions on automated collection and on commercial transfer, resale, analytics or scoring using user data without VK's express permission. A third-party mirror of the API rules reproduces these restrictions; the official VK developer schema points to VK's rules as the API terms. Until Vkus has explicit permission for the intended commercial use, do not enable automated collection or upload VK-derived personal data into the shared demand database.

Sources:
- VK developer schema references the API terms: https://github.com/VKCOM/vk-api-schema/blob/master/apps/methods.json
- Rules text mirror (verify current wording with VK before relying on it): https://mb4.ru/social-network/vk/1077-vk-dev-rules.html

## Input format

Prepare a JSON file containing only items you are authorized to process. The file may be a JSON array or an object with an `items` array. Each item can contain:

- `url`: original public VK post URL (`https://vk.ru/...` or `https://vk.com/...`)
- `text` or `comment_text`: selected text
- `kind`: `post` or `comment`
- `author_name` or `username`: optional visible author label
- `date_ts`: optional Unix timestamp in milliseconds

Example:

```json
{
  "items": [
    {
      "url": "https://vk.ru/wall-123_456",
      "text": "Ищу мастера для ремонта стиральной машины",
      "kind": "post",
      "author_name": "Имя автора",
      "date_ts": 1795300000000
    }
  ]
}
```

## Normalize and review

From the Q322 repository root:

```bash
python -m vkus.vk_demand_collector --input-json vk_selected.json --city "Орск" --region "Оренбургская область" --json-out vk_review.json
```

Default behavior is review-only. The importer deduplicates records and applies conservative phrase rules. Heuristic confidence is 0.68, below the backend's 0.70 activation threshold, so these records remain in `review` instead of being auto-activated.

## Backend upload

Upload requires `--upload` and all three environment variables on the machine running the importer:

- `VKUS_SUPABASE_URL` — Supabase project URL.
- `VKUS_SOURCE_ID` — approved source UUID.
- `VKUS_COLLECTOR_TOKEN` — opaque collector token; never commit it or place it in source code.

The backend independently checks the token hash, source binding, revocation state, source enabled state, and terms-review timestamp. The current VK source remains disabled and has no terms-review timestamp; upload is intentionally rejected. No token has been issued.

The service-role key is never used by this importer. It remains server-side in the Supabase Edge Function.

## Backend and files

- `supabase/migrations/20261122_vk_collector_auth.sql` records the collector-token schema and source registration.
- The corresponding schema and Edge Function changes are applied to the connected Supabase project.
- `tests/test_vk_demand_collector.py` covers intent classification and normalization. It does not test VK collection or backend upload.

## Not implemented

- Automated VK scraping/browser collection: intentionally withheld pending express permission from VK for this commercial use.
- Live VK/Firefox DOM validation.
- Upload to Supabase: blocked until the source is formally approved and enabled.
- Desktop UI integration: not yet wired into a new Vkus control.