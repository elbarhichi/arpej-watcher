# Run your own watcher on GitHub Actions

Your computer can be off after setup. Each person needs their own repository,
own watchlist and own ntfy topic. The project does not require Netlify or Telegram.

## 1. Fork and configure

Click **Fork** on this repository and create a copy in your account. Work in your
copy from now on. Its default branch must contain the workflow files.

Choose residences using [docs/RESIDENCES.md](docs/RESIDENCES.md), and commit
`config.json` to your default branch. You may clone your fork locally and use
the helper, or copy the helper's two JSON fields into GitHub's file editor.
The original eight residences are only the default example.

## 2. Create your own ntfy topic

1. Install the ntfy mobile app using the links in the
   [official subscription guide](https://docs.ntfy.sh/subscribe/phone/).
2. In your local checkout, run `python setup_ntfy.py`. This generates an
   unpredictable topic and saves its URL in the ignored `secrets.json` file.
   It prints `WEB_URL` and `APP_URL` locally and publishes a test message.
3. In the app, subscribe using server `https://ntfy.sh` and the topic name
   (the part after the final `/` in `WEB_URL`). Allow notifications. You can
   also open the web URL and subscribe in a supported browser.
4. Run `python arpej_checker.py --test-notification` after subscribing. Confirm
   receipt on your phone; a successful HTTP request alone does not prove that
   the phone subscription is working.

No-local-Python option: generate a long random name with a password generator
(20–64 characters, using letters, numbers, `_` and `-`), subscribe to that topic
on `ntfy.sh`, and use `https://ntfy.sh/YOUR-RANDOM-TOPIC` in step 3 below.
This project supports unreserved topics on `ntfy.sh`; authenticated or self-hosted
ntfy servers require code changes.

On the public ntfy server, knowledge of the topic permits reading/publishing to
it. Treat it like a password; see [ntfy's topic guidance](https://docs.ntfy.sh/publish/#picking-a-topic).
Never commit the URL, `secrets.json`, or a screenshot containing it. `.gitignore`
already excludes `secrets.json`, `data/`, Python caches and virtual environments.
Forks **do not inherit GitHub secrets**, so everybody supplies their own URL.

## 3. Add the GitHub secret

In **your fork**: **Settings → Secrets and variables → Actions → New repository secret**.

- Name: `ARPEJ_NTFY_TOPIC_URL`
- Value: the full `https://ntfy.sh/...` URL generated in step 2.

The environment secret takes precedence over a local secrets file. Never paste
the topic into `config.json` or the workflow YAML.

## 4. Enable workflows and journal commits

Open **Actions** and enable workflows if GitHub asks you to enable them for the
fork. Under **Settings → Actions → General**, ensure Actions are allowed and
the workflow token may write repository contents. The workflows request
`contents: write` to publish the journal/state. Organization policy or branch
protection may prevent direct bot commits; use a personal fork whose default
branch allows the workflow's commits.

Open **Actions → Surveillance ARPEJ automatique** and enable the workflow if
it is disabled. Only the default branch receives scheduled runs.

## 5. Verify delivery, then a real check

1. Open **Actions → Surveillance ARPEJ manuelle → Run workflow**.
2. Choose your default branch and check **Envoyer uniquement une notification ntfy de test**.
3. Run it, confirm a green result and receipt of the test on your device.
4. Run again with that checkbox **unchecked** to perform a real check immediately.
   This bypasses active hours. A full residence produces a journal entry, not an alert.
5. Open `arpej_checker.log` to see the real-check result.

The manual workflow remains available for tests; the automatic workflow only
uses `schedule`. If a local Windows task exists, pause it with
`.\manage_task.ps1 pause` once the cloud test works.

## Schedule, changes and stopping

The default schedule is `2-57/5 6-17 * * *` in UTC (minutes 2, 7, …, 57). It
requests a start every five minutes over the window that covers Paris
08:00–18:59 in both summer and winter. `TZ: Europe/Paris` and `active_hours` in
`config.json` apply the actual local-hours filter. The hourly state prevents
additional ARPEJ checks after the first success in each hour.

To change active hours or timezone, change `config.json` and the workflow's
`TZ`/UTC cron coverage together. `end: 18` means through **18:59**, not precisely
18:00. Changes to the watchlist take effect at the next check; use a manual check
to verify them immediately if the current hour is already locked.

To stop automatic execution, open the automatic workflow's **… → Disable workflow**.
Enable it again to resume. Disabling does not cancel an already running job;
cancel that run separately if needed. No local background process is required.

## Troubleshooting and limits

| Symptom | Check |
| --- | --- |
| No runs | Actions/workflow enabled, YAML on default branch, active UTC window |
| Late/missing hour | GitHub can delay or drop scheduled events; examine actual run times |
| Green run, no journal change | The gate may have skipped a locked hour or an out-of-hours run; inspect the gate step |
| Green real check, no alert | All selected residences may be full; read the notification decision in the journal |
| Missing ntfy secret | Add `ARPEJ_NTFY_TOPIC_URL` in your fork, not the upstream repository |
| ntfy request succeeds, phone silent | Check subscription/topic, app permissions and the official ntfy troubleshooting guide |
| Expected ID missing | Verify selected city IDs and list the residences again; do not assume full occupancy |
| Journal push fails | Check token write permissions, branch protection and overlapping edits |
| Job never starts, no steps/logs | GitHub may have failed to assign a runner; the script did not execute |

The supported shortest schedule interval is five minutes. GitHub documents
possible delays/dropped jobs and automatic disabling of scheduled workflows in
public repositories after 60 days without repository activity. See the
[official schedule documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
Repeated schedule requests improve retry opportunities but do not guarantee an
hourly check. There is no automatic rerun of hours missed entirely.

Logs in `arpej_checker.log` remain in Git history; per-run downloadable logs expire
after 30 days. A fork includes upstream history. You can clear the current root
journal and reset `scheduler_state.json` to `{"last_successful_hour": null}` in
your fork for a fresh start; this does not erase historical commits. Do not
publish your local `data/` directory or secrets when sharing your copy.
