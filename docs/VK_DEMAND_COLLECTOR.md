# VK public-demand collector (experimental)

This adapter reuses the existing `BrowserManager` and persistent Firefox profile. It is an opt-in collector, not a replacement for the existing VK search UI.

## Scope and safeguards
- Searches only results visible through the authenticated Firefox session and VK's public search interface.
- Does not access private communities/content, bypass login or access controls, send messages, invite users, or perform account actions.
- Manual VK login remains in the existing Firefox profile when needed.
- Search results are normalized into the Vkus external-demand schema.
- Intent classification is deliberately conservative: only clear request/offer phrases are labeled; ambiguous records remain `unknown` and go to review.
- Default mode is dry-run. No data is uploaded unless `--upload` is passed.
- The collector never receives or stores the Supabase service-role key.

## Run from the Q322 repository root
Install the existing project dependencies, make sure Firefox and geckodriver are available, then run:

```bash
python -m vkus.vk_demand_collector --query "ищу мастера" --city "Орск" --region "Оренбургская область" --limit 30 --json-out vk_review.json
```

To search comments:

```bash
python -m vkus.vk_demand_collector --query "нужен ремонт" --mode comments --city "Орск" --limit 20
```

The first run may open Firefox for manual VK login. The collector uses the same persistent profile as Vkus (`~/.vkus/firefox_profile`).

## Upload configuration
Upload is disabled until the VK source is approved in the Vkus backend and a collector token has been issued. Set these environment variables only on the machine running the collector:

- `VKUS_SUPABASE_URL` — Supabase project URL.
- `VKUS_SOURCE_ID` — approved source UUID.
- `VKUS_COLLECTOR_TOKEN` — opaque collector token; never commit it or place it in source code.

Then run with `--upload`:

```bash
python -m vkus.vk_demand_collector --query "ищу мастера" --city "Орск" --region "Оренбургская область" --limit 30 --upload
```

The server checks the token hash, source binding, revocation state, source enabled state, and terms-review timestamp. The source currently remains disabled pending review; upload will be rejected until that gate is completed. Do not mark terms reviewed without checking the current VK terms and the intended collection scope.

## Current limitations
- The existing Selenium DOM extraction is reused; VK can change its page structure and selectors. Real live VK extraction has not yet been validated after this adapter was added.
- Region/city are supplied as explicit command-line filters; this adapter does not infer a user's location from their profile.
- Intent classification is rule-based, not an ML classifier. Confidence 0.78 means a strong phrase match, not a guarantee that a person is a buyer.
- Author label is included only when exposed in the visible search result. No email, phone, or private contact details are collected.
- This is a collector module/CLI, not yet wired into a new desktop UI control.

## Test
```bash
python -m unittest discover -s tests -p 'test_vk_demand_collector.py' -v
```

The tests cover intent classification and normalization only. They do not test live Firefox, VK login, DOM selectors, network connectivity, or backend ingestion.