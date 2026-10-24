# Select your own ARPEJ residences

## 1. Generate the search link

Open [ARPEJ's residence search](https://www.arpej.fr/fr/nos-residences/), choose
your cities and include full residences so they can be watched for future openings.
Copy the address after the search updates. It should contain `related_city=...`.
Do not use an individual residence-detail URL.

The original search was:

```text
https://www.arpej.fr/fr/nos-residences/?related_city=52768%2C54167%2C52722%2C54157%2C52740%2C52782%2C53935&show_if_full=true
```

`%2C` is an encoded comma: this URL selects seven cities, which originally
contained eight residences. City IDs and residence IDs are different numbers.

Palaiseau can be searched on its own with city ID `52726`:

```text
https://www.arpej.fr/fr/nos-residences/?related_city=52726&show_if_full=true
```

To combine searches, select all cities in the website or put the city IDs in the
same `related_city` parameter separated by commas. Keep the URL in quotes in
terminal commands so `&` is not interpreted by the shell.

## 2. List the names and residence IDs

In a checkout of your fork, run (replace the example URL with your own):

```sh
python configure_residences.py "https://www.arpej.fr/fr/nos-residences/?related_city=52726&show_if_full=true"
```

Windows may use `py -3`; Linux/macOS may use `python3`.
The helper calls ARPEJ once, prints each residence's ID/name/city/count, and
prints the two JSON fields needed in `config.json`. It does **not** send an alert,
touch the hourly lock or write history. IDs should be taken from fresh output;
the returned residence list can change.

Only **cities** are imported from the URL. Price, radius, housing type and other
website filters are not imported. The API query always includes full residences
and does not impose a hardcoded price limit. Choose the exact IDs you want from
the helper's results. These are residence-level alerts, not per-unit criteria.

## 3. Save all returned residences or a subset

Watch all residences returned by that search at configuration time:

```sh
python configure_residences.py "https://www.arpej.fr/fr/nos-residences/?related_city=52726&show_if_full=true" --write
```

Or select only Claudie Haigneré (example residence ID `61037`):

```sh
python configure_residences.py "https://www.arpej.fr/fr/nos-residences/?related_city=52726&show_if_full=true" --residence-ids 61037 --write
```

For several residences, put spaces between the IDs after `--residence-ids`.
Omitting `--write` always previews without saving. Unknown IDs, empty results or
a failed API request leave the configuration unchanged. The helper updates only
`city_ids` and `expected_residence_ids`, preserving hours and notification settings.

The exact selected set is fixed until you edit it again. Residences outside that
set are excluded from summaries, history and notifications even if the API returns
them. If any selected residence disappears, the check fails visibly, so you can
investigate instead of receiving a misleading "none available" result.

## 4. Publish your configuration and test

Commit/push **only `config.json`** from the setup process to your own default branch,
or use GitHub's editor to replace its two selection fields with the preview output.
Never commit `secrets.json` or `data/`. For example, with a local clone:

```sh
git add config.json
git commit -m "Choose my ARPEJ residences"
git push
```

Follow [the GitHub setup guide](../GITHUB_SETUP.md) for your personal ntfy secret.
Run the manual workflow with the test checkbox unchecked to verify the watchlist.
Locally, `python arpej_checker.py --force` performs the same real check and can
send an alert if something is available. Read the summary to confirm the names.

## Manual configuration

If you already know the city and residence IDs, edit the existing `config.json`:

```json
{
  "city_ids": ["52726"],
  "expected_residence_ids": [61037]
}
```

This snippet shows **only the fields to change**; retain the other settings in
the file. Include every selected residence's city in `city_ids`.

If the website stops putting city IDs in its URL, open browser developer tools,
go to **Network**, repeat the search and inspect the `wp-json/sn/residences`
request. Its `related_city[]` values are city IDs. The JSON response contains
`residences[].ID`, `title`, `link`, `extra_data.city` and
`extra_data.available_rooms`. Never infer an ID from a residence's name or slug.

## Other operators / websites

This helper and checker support **ARPEJ only**. The API host is validated and the
parser expects ARPEJ's JSON schema. A residence operated by a different company
will need another fetch/parser implementation; replacing `api_url` is insufficient.
See [the code review and extension notes](REVIEW.md#extending-to-another-operator).
