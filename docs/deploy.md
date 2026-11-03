# Running Distill on the Mac Mini

Distill runs as one always-on process on the Mac Mini: `distill serve --schedule` serves the app
and, in a background thread, fetches/discovers/classifies every 2 hours and backs up the
database every night. Your phone reaches it over [Tailscale](https://tailscale.com), a private
network between your own devices: nothing is exposed to the internet and there's no login page.

## 1. Move your data off this Mac

Your triage, history and settings live in two files that aren't in git. On **this** Mac:

```bash
uv run distill backup ~/Desktop/distill-transfer
```

That writes a consistent copy of the database even while the app is running. Copy it and
`.env` to the Mac Mini (AirDrop is fine). `.env` holds your API keys, so don't put it anywhere
public.

## 2. Set up the Mac Mini

1. Install [Homebrew](https://brew.sh) and the [Tailscale app](https://tailscale.com/download), and
   sign in to Tailscale.
2. In the [Tailscale admin console](https://login.tailscale.com/admin/dns), turn on **MagicDNS**
   and **HTTPS Certificates** (needed for a proper `https://` address; iPhones only install web
   apps from HTTPS).
3. Clone the repo somewhere outside iCloud (iCloud sync broke the virtualenv on this Mac):

   ```bash
   git clone https://github.com/joshua0624/Distill.git ~/Distill
   ```

4. Put the files from step 1 in place: `~/Distill/.env` and `~/Distill/data/distill.db`
   (rename the backup file to `distill.db`).
5. Run the setup script:

   ```bash
   ~/Distill/scripts/setup-mac-mini.sh
   ```

   It installs uv and Node if needed, builds the app, installs a LaunchAgent that keeps
   `distill serve --schedule` running (restarted if it stops, started at login), and publishes it
   on your tailnet with `tailscale serve`. At the end it prints your address, like
   `https://mac-mini.your-tailnet.ts.net`.

6. In System Settings (the script doesn't touch these):
   - **Energy**: prevent automatic sleeping, and start up automatically after a power failure.
   - **Users & Groups**: automatic login for this user, so Distill comes back after a reboot.

Stop using Distill on the old Mac after the move: the two copies of the database don't sync.

## 3. Install it on your iPhone

1. Install Tailscale on the iPhone and sign in with the same account. Leave it connected (it
   uses very little battery).
2. Open the `https://….ts.net` address in **Safari**, then **Share → Add to Home Screen**.

## Check YouTube Premium on the iPhone

This is the one thing that can't be tested from a desk, and there's a real chance it doesn't
work. Distill uses the normal youtube.com embedded player so Premium can apply, but Safari
blocks cookies inside embedded players from other sites, and the home-screen app has its own
storage separate from Safari. Either can leave the player signed out, which means ads.

To check: play a video from a channel that usually runs pre-roll ads, a few times, in both the
home-screen app and a Safari tab. If you see ads in both, the fix is an **Open in YouTube**
setting for phones that hands playback to the YouTube app (Premium, background play) at the
cost of Distill's resume and end screen. Say the word and it can be added.

On the Mac's desktop browser Premium works as long as you're signed in to YouTube in that browser.

## Day to day

- **Update after a `git pull`:** run `~/Distill/scripts/setup-mac-mini.sh` again. It rebuilds and restarts.
- **Logs:** `~/Library/Logs/Distill/serve.log` (each scheduled update logs a summary line).
- **Restart:** `launchctl kickstart -k gui/$(id -u)/net.distill.serve`
- **Stop for good:** `launchctl bootout gui/$(id -u)/net.distill.serve`
- **Backups:** `~/Distill/data/backups/`, the newest 14 nightly copies. To restore one, stop the
  service, copy it over `data/distill.db`, and start it again.
- **Schedule:** `ingest_every_h`, `backup_hour` and `backup_keep` in `config/settings.yaml`.
- **Quota:** a scheduled day uses roughly 3,000–4,000 of the 10,000 daily YouTube units
  (discovery searches are most of it); LLM spend shows on the Hidden page and in `distill usage`.
