# Bulk Email Sender — Setup Guide & Documentation

> ⚠️ **Important:** This tool is designed for **legitimate, permission-based email
> communication only** (newsletters, transactional emails, announcements to opted-in
> subscribers). Never send unsolicited email (spam). Misuse may violate your email
> provider's Terms of Service and applicable laws (CAN-SPAM, GDPR, CASL, etc.).

---

## Files

```
bulk_email_sender/
├── bulk_email_sender.py    ← Main application (run this)
├── requirements.txt        ← Dependency notes
├── recipients_example.csv  ← Example recipients file
├── SETUP.md                ← This guide
└── email_logs/             ← Created automatically on first run
```

---

## 1. Prerequisites

| Requirement | Details |
|---|---|
| Python | **3.11 or newer** — https://www.python.org/downloads/ |
| Tkinter | Bundled with Python on Windows & macOS. On Linux: `sudo apt install python3-tk` |
| Gmail / Outlook account | With an **App Password** (see §2) |

---

## 2. Generating an App Password

### Gmail
1. Go to your Google Account → **Security** → **2-Step Verification** (must be enabled).
2. Scroll down → **App passwords** → create one named e.g. `BulkEmailSender`.
3. Copy the 16-character password shown — you will only see it once.

> ℹ️ App Passwords only appear when 2-Step Verification is active.

### Outlook / Microsoft 365
1. Sign in → **Security** → **Advanced security options** → **App passwords**.
2. Create a new app password; copy it immediately.

### Yahoo Mail
1. Account Security → **Generate app password** → select "Other App".

---

## 3. Running the Application

```bash
# 1. (Recommended) Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate.bat       # Windows

# 2. Run
python bulk_email_sender.py
```

No `pip install` is needed — the app uses only Python standard-library modules.

---

## 4. Usage Walkthrough

### Tab 1 — Configuration
| Field | What to enter |
|---|---|
| SMTP Provider | Gmail, Outlook, Yahoo, or Custom |
| Sender Email | Your full email address |
| App Password | The app-specific password from §2 (never your main password) |
| Recipients File | Browse to a `.csv` or `.txt` file (see §5) |
| Attachments | Optionally add files to attach to every email |
| Delay Between Emails | Seconds to wait between sends. **Recommended: ≥ 1 s** to stay within provider rate limits |

### Tab 2 — Compose
- **Subject** — supports `{name}` placeholder.
- **Plain-Text Fallback** — shown in email clients that block HTML.
- **HTML Body** — full HTML email. Supports `{name}` placeholder.

### Tab 3 — Send
1. Tick the **consent confirmation** checkbox.
2. Click **Send to All**.
3. A second confirmation dialog appears for lists of 50+ recipients.
4. Watch per-recipient progress in the live log.
5. Click **Cancel** to stop cleanly after the current email finishes.

---

## 5. Recipients File Format

### CSV (recommended)

```
email,name,company
alice@example.com,Alice Johnson,Acme Corp
bob@example.com,Bob Smith,Widget Inc
```

- The `email` column is **required**; `name` is optional (used for `{name}` substitution).
- Extra columns are loaded but currently ignored (easy to extend).
- Invalid email addresses are skipped with a console warning.

### TXT (simple list)

```
alice@example.com
bob@example.com
# comment lines starting with # are skipped
```

---

## 6. Log Files

Each session creates a log file in `email_logs/`:

```
email_logs/session_20250611_143022.log
```

Log format:
```
2025-06-11 14:30:22,418 | INFO     | SESSION START | provider=Gmail ...
2025-06-11 14:30:24,012 | INFO     | SENT     | alice@example.com | Alice Johnson
2025-06-11 14:30:25,601 | WARNING  | REFUSED  | bad@invalid.tld   | Recipient refused
2025-06-11 14:30:25,602 | INFO     | SESSION END   | sent=1 failed=1
```

---

## 7. Common Errors & Fixes

| Error | Likely Cause | Fix |
|---|---|---|
| `Authentication failed` | Wrong password or App Password not set up | Generate a fresh App Password (§2) |
| `Could not connect to SMTP server` | Firewall / VPN blocking port 587 | Disable VPN; allow outbound TCP 587 |
| `Recipient refused` | Remote server rejected the address | Remove invalid/non-existent addresses |
| Tkinter not found (Linux) | Missing system package | `sudo apt install python3-tk` |
| `SyntaxError` on startup | Python < 3.11 | Upgrade Python |

---

## 8. Extending the Application

The code is structured into clear, documented functions. Common extension points:

- **Add CC/BCC** — modify `build_message()` to add `msg["Cc"]` / `msg["Bcc"]` headers.
- **Template variables** — extend the `{name}` substitution logic in `build_message()` to support any CSV column.
- **Retry on failure** — wrap `send_single_email()` in a retry loop with exponential back-off.
- **Test mode** — add a "Send to me only" button that sends one test email to the sender.
- **Export results** — write the per-recipient success/failure table to a CSV after the session.

---

## 9. Security Notes

- **Never hardcode passwords** — enter them in the GUI at runtime only.
- App Passwords are scoped to a single application; revoke them in your account settings if compromised.
- Log files record email addresses and statuses but **never passwords**.
- Consider encrypting the `email_logs/` folder if it contains sensitive recipient data.

---

## 10. Legal Compliance Checklist

Before each send, confirm:

- [ ] Every recipient explicitly opted in (double opt-in is best practice).
- [ ] An unsubscribe mechanism is present in the email body.
- [ ] Your sender name and physical address are included (CAN-SPAM requirement).
- [ ] You comply with local data-protection laws (GDPR, CASL, etc.).
