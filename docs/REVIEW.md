# Sharing and reliability review

Reviewed on 24 October 2026. This is a practical reuse review, not a formal security
audit or a service-availability guarantee.

## Assessment

The project is suitable to share as a small personal ARPEJ watcher once this
revision is installed. It has no Python package dependencies, uses the same
public JSON source as the website, and has tests for parsing, exact selection,
notification decisions and the hourly lock. The setup guide no longer depends
on the original author's machine, messaging bots or ntfy topic.

The live API returned the eight original residences during review. The Palaiseau
query also returned Claudie Haigneré (`61037`) with availability. That observation
tests the response shape, not a promise about future availability. Test cases
mock notification delivery and do not send to the owner's topic.

The previous schedule did not provide hourly coverage: on 23 October, the run
history showed real checks around 12:52 and 17:30 Paris time, plus an out-of-hours
skip around 21:30. The 12:52 check logged an ntfy alert for Chanzy. The supported
five-minute schedule in this revision still needs observation after deployment;
passing unit tests does not establish scheduler reliability.

## Changes made for sharing

- ntfy is the only notification channel; legacy Telegram/webhook configuration
  and Telegram setup scripts were removed. Existing local secret files are not
  rewritten, and unused legacy keys are ignored.
- Exact selection is now enforced. Previously, configured residence IDs only
  detected missing results, while unrelated results in the same cities could
  also produce alerts.
- `configure_residences.py` imports cities from a search URL, lists actual
  residence IDs, and previews or saves an explicit selection. No HTML editing
  or browser automation is needed.
- Removed the hidden €1,000 price cap and shared-housing exclusion from the API
  query. Explicit residence IDs determine what is monitored; unit-level budget
  and eligibility filtering are not implemented.
- Missing ntfy settings cause an available-residence check to fail, keeping the
  hour open for retry instead of recording successful monitoring without delivery.
- Replaced the unsupported one-minute scheduling request with five-minute
  requests, retaining one successful automatic check per local clock hour.
- Added setup/extension documentation, regression tests, a test workflow and
  an MIT license permitting reuse and modification.

## Remaining limitations

- GitHub may delay or drop schedules or fail to allocate a runner. There is no
  guaranteed hourly delivery or catch-up for a missed hour.
- The API is public but not a versioned contract maintained for this project.
  A changed schema or missing residence produces a visible failure.
- A successful ntfy publish does not prove a particular device displayed it.
  Each user must subscribe and verify a manual notification test.
- A public ntfy topic has no access control in this implementation. A long random
  topic acts as a shared secret; authenticated/self-hosted ntfy is not supported.
- Delivery and the Git state commit are separate operations. If delivery works
  but publishing the hourly state fails, a retry can send a duplicate alert.
- Separate repositories, external schedulers or local tasks do not share the
  GitHub concurrency group. Manual checks intentionally do not lock the hour.
- GitHub's root journal is append-only and grows over time. SQLite history is
  local to each runner, not persisted across cloud runs. Journal artifacts expire.
- Public forks include upstream commits and historic logs; Actions secrets are
  not copied. Every user must supply their own topic and configuration.
- Only residence-level available-unit counts are reported. Rent, room type,
  dates and application eligibility require checking the residence page.

## Extending to another operator

First inspect that operator's search page and its network requests. Determine
whether availability is exposed through a public JSON endpoint or only HTML,
and whether automated access is permitted. Use a browser only when a plain HTTP
request cannot obtain the necessary public data.

The current boundaries in `arpej_checker.py` are:

| Function / type | What a new operator needs |
| --- | --- |
| `load_config` | Validate the new operator's endpoint and selection fields |
| `build_api_url` / `fetch_payload` | Build/fetch its request, including pagination if present |
| `parse_residences` | Convert its response into `Residence` values; reject missing/invalid availability |
| `Residence` | Numeric ID, name, city, URL and nonnegative integer availability count |
| `format_availability_notification` | Replace the ARPEJ label and any operator-specific links |
| `configure_residences.py` | Replace ARPEJ search-URL parsing and ID discovery |

The ntfy publishing, logging and scheduler pattern can be reused. An operator
without numeric IDs or unit counts needs a deliberate data-model change; do not
turn unknown availability into zero. Start with saved-response tests covering
available, full, malformed, incomplete and paginated responses before adding a
new live scheduler. No multi-operator plugin framework has been added here.
