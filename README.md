# naukri-profile-refresher

> Automatically keeps your Naukri.com profile active and visible to recruiters by periodically updating your resume headline.

Naukri boosts recently updated profiles in search rankings. This tool toggles a trailing `.` in your resume headline on a schedule, so Naukri always sees your profile as freshly updated.

---

## How It Works

1. Opens your Naukri profile in a headless Chrome browser
2. Clicks the Resume Headline edit button
3. Toggles a trailing `.` (adds if missing, removes if present)
4. Saves - Naukri registers this as a profile update

Every run makes a real change, so the update timestamp is always fresh.

---

## Prerequisites

- Docker installed on your machine/server

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/hritikkanojiya/naukri-profile-refresher.git
cd naukri-profile-refresher
```

### 2. Create your `.env` file

```bash
cp .env.example .env
nano .env
```

Fill in your credentials:

```env
NAUKRI_EMAIL=you@example.com
NAUKRI_PASSWORD=yourpassword
```

### 3. Build the Docker image

```bash
docker build -t naukri-profile-refresher:latest .
```

### 4. Run manually to test

```bash
docker run --rm \
  --env-file .env \
  --volume $(pwd)/naukri_chrome_session:/app/naukri_chrome_session \
  --shm-size="256mb" \
  naukri-profile-refresher:latest
```

---

## Schedule with Cron

Run automatically on a schedule using your host's crontab:

```bash
crontab -e
```

Add this line (runs twice daily at 9 AM and 6 PM):

```cron
0 9,18 * * * docker run --rm --env-file /path/to/naukri-profile-refresher/.env --volume /path/to/naukri-profile-refresher/naukri_chrome_session:/app/naukri_chrome_session --shm-size=256mb naukri-profile-refresher:latest >> /var/log/naukri-cron.log 2>&1
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `NAUKRI_EMAIL` | ✅ | - | Your Naukri login email |
| `NAUKRI_PASSWORD` | ✅ | - | Your Naukri password |
| `PROFILE_DIR` | | `naukri_chrome_session` | Chrome session folder name |
| `LOG_LEVEL` | | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `LOG_FILE` | | `/var/log/naukri.log` | Log file path inside container |
| `PAGE_LOAD_TIMEOUT` | | `60` | Seconds before page load fails |
| `ELEMENT_WAIT_TIMEOUT` | | `25` | Seconds before element lookup fails |
| `USER_AGENT` | | Chrome 131 Linux UA | Browser user-agent string |
| `CHROME_BIN` | | auto-detected | Chrome binary path override |
| `CHROMEDRIVER_BIN` | | auto-detected | ChromeDriver path override |
| `NAUKRI_PROFILE_URL` | | naukri.com/mnjuser/profile | Profile page URL |
| `NAUKRI_LOGIN_URL` | | naukri.com/nlogin/login | Login page URL |

---

## Debugging

```bash
docker run --rm \
  --env-file .env \
  -e LOG_LEVEL=DEBUG \
  --volume $(pwd)/naukri_chrome_session:/app/naukri_chrome_session \
  --shm-size="256mb" \
  naukri-profile-refresher:latest
```

---

## Persistent Login

Chrome session cookies are stored in `./<PROFILE_DIR>/` on the host and mounted into the container. After the first successful login, all subsequent runs skip the login step - making runs faster.

If the session expires, just delete the folder and let it log in fresh:

```bash
rm -rf ./naukri_chrome_session
```

---

## Security

- Never commit your `.env` file - it is gitignored
- Credentials are passed only via environment variables
- The Chrome session folder is gitignored and never committed

---

## Tech Stack

- **Python 3** + **Selenium 4**
- **Google Chrome** (headless) via `selenium/standalone-chrome` Docker image
- **Akamai bot bypass** via CDP `navigator.webdriver` patch + spoofed user-agent

---

## Contributing

Pull requests are welcome! If Naukri updates their UI and the selectors break, feel free to open an issue or submit a fix.

---

## License

MIT © [Hritik Kanojiya](https://github.com/hritikkanojiya)