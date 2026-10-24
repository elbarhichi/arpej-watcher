# ARPEJ residence availability watcher

A small Python script that checks selected ARPEJ residences and sends **ntfy**
notifications when accommodation is available. GitHub Actions can run it while
your computer is off. Python 3.10+ is required locally; there are no third-party
Python dependencies. The workflows use Python 3.12.

The notification service is [ntfy](https://ntfy.sh).
This project is independent of ARPEJ; it does not reserve accommodation.

## Start with your own copy

1. **Fork** this repository into your own GitHub account.
2. Choose your residences using [the selection guide](docs/RESIDENCES.md).
   Commit your updated `config.json` to the default branch of your copy.
3. Create your own ntfy topic and add its URL as the GitHub Actions secret
   `ARPEJ_NTFY_TOPIC_URL`. Never reuse someone else's topic.
4. Follow [GITHUB_SETUP.md](GITHUB_SETUP.md) to enable Actions, test notifications,
   and activate automatic checks.

For a local checkout of **your fork**:

```sh
git clone https://github.com/YOUR-USERNAME/arpej-watcher.git
cd arpej-watcher
python setup_ntfy.py
python arpej_checker.py --test-notification
python arpej_checker.py --force
```

Use `python3` on Linux/macOS or `py -3` on Windows if `python` is unavailable.
Before running `setup_ntfy.py`, read the subscription steps in
[GITHUB_SETUP.md](GITHUB_SETUP.md#2-create-your-own-ntfy-topic). It prints the new
topic locally and sends a test; subscribe and test again to verify receipt.

## Choose what to watch

The search starts at **[ARPEJ's residence finder](https://www.arpej.fr/fr/nos-residences/)**.
Choose your cities and include full residences, then copy the resulting search URL.
The helper translates the city IDs into a list of residences:

```sh
python configure_residences.py "https://www.arpej.fr/fr/nos-residences/?related_city=52726&show_if_full=true"
```

It prints IDs, names, cities and current availability without changing anything.
Choose IDs from that output, then save, for example:

```sh
python configure_residences.py "https://www.arpej.fr/fr/nos-residences/?related_city=52726&show_if_full=true" --residence-ids 61037 --write
```

This example selects Claudie Haigneré in Palaiseau. Availability is live and can
change. Omit `--residence-ids` to select **all residences returned at setup time**.
New residences are not added automatically; rerun the helper to include them.
Full instructions, multiple-city examples and manual configuration are in
[docs/RESIDENCES.md](docs/RESIDENCES.md).

The repository's default `config.json` retains the original eight residences:
Charles Frederick Worth, Louis Blériot, Raymond Aron, Guy de Maupassant,
Louis Faure-Dujarric, Jacques-Henri Lartigue, Neuilly-Roule and Chanzy.
These are examples, not a limit of eight. Only the IDs you select are monitored.

## What happens on each check

The script queries the public JSON API used by ARPEJ's website:
`https://www.arpej.fr/wp-json/sn/residences`. It reads each residence's
`extra_data.available_rooms`; Selenium and browser automation are unnecessary.

- At least one selected residence has availability: send an ntfy alert with its
  exact name, city, available-unit count and direct link. An alert is sent on
  **each successful check** while availability remains, even if unchanged.
- All selected residences are full: log the result, send no alert.
- A selected residence disappears, the response changes, the network fails, or
  sending an alert fails: report an error rather than claim there is no availability.

`--test-notification` is the explicit exception: it sends a test without checking
availability. The count is whatever ARPEJ publishes; it does not describe an
individual room's rent, size or eligibility, or guarantee that you can book it.

## Automatic execution and history

The automatic workflow requests a start every five minutes, offset from the top
of the hour. Its UTC window covers the configured default hours in both summer
and winter. The script checks the local Paris time and allows one successful
check per clock hour between **08:00 and 18:59 inclusive**, every day.

`scheduler_state.json` records the successful hour. Later starts in that hour
skip the ARPEJ request, notifications and journal commit. Failed checks leave the
hour open for retries. A manual run with `--force` deliberately bypasses the
active-hours filter and does not acquire the hourly lock.

GitHub schedules can be delayed or dropped. This is a personal monitoring tool,
not a guarantee of eleven checks every day. See the scheduling limitations and
troubleshooting in [GITHUB_SETUP.md](GITHUB_SETUP.md).

| File / location | Purpose |
| --- | --- |
| `config.json` | Your cities, exact residence IDs and active hours; safe to commit |
| `arpej_checker.log` | Journal published by GitHub Actions; readable in the repository |
| `scheduler_state.json` | Last successful automatic-check hour |
| Actions tab | Run results and downloadable per-run logs (30-day retention) |
| `data/` | Local logs and SQLite history; excluded from Git |
| `secrets.json` | Local ntfy URL; excluded from Git |

GitHub runners are temporary: the SQLite database is not preserved across runs.
The root journal and scheduler state are preserved through commits. A fork starts
with the upstream journal/state; those are historical records, not your own checks.
Avoid sharing Actions logs or screenshots from `setup_ntfy.py` that contain a topic.

## Local Windows scheduling (optional)

If you prefer running on your own PC, open PowerShell in the project directory:

```powershell
.\install_hourly_task.ps1
.\manage_task.ps1 status
.\manage_task.ps1 pause
.\manage_task.ps1 resume
.\manage_task.ps1 run
```

The Windows installer schedules 08:00–18:00 hourly, in the PC's local time. Your PC
must be on and connected; the session may be locked. If you change `active_hours`
in `config.json`, also adjust the hours in `install_hourly_task.ps1` and reinstall.
Use one scheduler for your copy to avoid duplicate alerts. To remove the local task:

```powershell
Unregister-ScheduledTask -TaskName "ARPEJ - Verification des disponibilites"
```

## Development and reuse

```sh
python -m unittest discover -s tests -v
```

Tests use mocked network responses and never send real notifications. GitHub runs
them on code pushes and pull requests. [docs/REVIEW.md](docs/REVIEW.md) explains
the reviewed guarantees, limitations and where to change the code for another
housing operator. Other ARPEJ residences use configuration; **other websites
require an implementation change**, not just a replacement URL.

Shared under the [MIT license](LICENSE).
