"""
Bulk Email Sender - A production-ready Tkinter GUI application
for permission-based bulk email sending via SMTP (Gmail/Outlook).

Author: Generated template — modify for your use case.
Usage: python bulk_email_sender.py
License: MIT — for legitimate, permission-based email use only.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import smtplib
import ssl
import csv
import os
import re
import time
import logging
import threading
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path


# ---------------------------------------------------------------------------
# CONSTANTS & CONFIGURATION
# ---------------------------------------------------------------------------

SMTP_PROVIDERS = {
    "Gmail":   {"host": "smtp.gmail.com",  "port": 587},
    "Outlook": {"host": "smtp.office365.com", "port": 587},
    "Yahoo":   {"host": "smtp.mail.yahoo.com", "port": 587},
    "Custom":  {"host": "",                "port": 587},
}

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9\-.]+$")
LOG_DIR = Path("email_logs")
LOG_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# LOGGING SETUP
# ---------------------------------------------------------------------------

def setup_logger(session_id: str) -> logging.Logger:
    """Create a timestamped log file for this sending session."""
    log_file = LOG_DIR / f"session_{session_id}.log"
    logger = logging.getLogger(session_id)
    logger.setLevel(logging.DEBUG)

    # File handler — full detail
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s"))

    # Avoid duplicate handlers if function is called more than once
    if not logger.handlers:
        logger.addHandler(fh)

    return logger, log_file


# ---------------------------------------------------------------------------
# EMAIL VALIDATION
# ---------------------------------------------------------------------------

def is_valid_email(address: str) -> bool:
    """Return True if `address` looks like a valid e-mail address."""
    return bool(EMAIL_REGEX.match(address.strip()))


# ---------------------------------------------------------------------------
# RECIPIENT LOADING
# ---------------------------------------------------------------------------

def load_recipients_from_file(filepath: str) -> list[dict]:
    """
    Load recipients from a .csv or .txt file.

    CSV format (with header row):
        email, name, [extra_field, ...]

    TXT format (one e-mail address per line):
        user@example.com

    Returns a list of dicts: [{"email": ..., "name": ..., "raw": ...}, ...]
    Skips rows with invalid e-mail addresses and logs a warning.
    """
    recipients = []
    filepath = Path(filepath)
    ext = filepath.suffix.lower()

    if ext == ".csv":
        with open(filepath, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            # Normalise header names to lowercase
            for row in reader:
                row = {k.strip().lower(): v.strip() for k, v in row.items()}
                email = row.get("email", "").strip()
                name  = row.get("name", "").strip()
                if is_valid_email(email):
                    recipients.append({"email": email, "name": name, "extra": row})
                else:
                    print(f"[SKIP] Invalid e-mail in CSV: {email!r}")

    elif ext == ".txt":
        with open(filepath, encoding="utf-8") as f:
            for line in f:
                email = line.strip()
                if not email or email.startswith("#"):
                    continue
                if is_valid_email(email):
                    recipients.append({"email": email, "name": "", "extra": {}})
                else:
                    print(f"[SKIP] Invalid e-mail in TXT: {email!r}")
    else:
        raise ValueError(f"Unsupported file type: {ext}. Use .csv or .txt")

    return recipients


# ---------------------------------------------------------------------------
# EMAIL CONSTRUCTION
# ---------------------------------------------------------------------------

def build_message(
    sender_email: str,
    recipient: dict,
    subject: str,
    body_html: str,
    body_plain: str,
    attachments: list[str],
) -> MIMEMultipart:
    """
    Construct a MIME e-mail message.

    Supports:
    - HTML + plain-text alternative (proper multipart/alternative)
    - Multiple file attachments
    - {name} placeholder substitution in subject and body
    """
    name = recipient.get("name", "")
    to_email = recipient["email"]

    # Substitute {name} placeholder if present
    subject_rendered = subject.replace("{name}", name)
    html_rendered    = body_html.replace("{name}", name)
    plain_rendered   = body_plain.replace("{name}", name)

    msg = MIMEMultipart("mixed")
    msg["From"]    = sender_email
    msg["To"]      = to_email
    msg["Subject"] = subject_rendered

    # Body: multipart/alternative wraps HTML + plain text
    alt_part = MIMEMultipart("alternative")
    alt_part.attach(MIMEText(plain_rendered, "plain", "utf-8"))
    alt_part.attach(MIMEText(html_rendered,  "html",  "utf-8"))
    msg.attach(alt_part)

    # Attachments
    for filepath in attachments:
        filepath = Path(filepath)
        if not filepath.is_file():
            continue
        with open(filepath, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="{filepath.name}"',
        )
        msg.attach(part)

    return msg


# ---------------------------------------------------------------------------
# SMTP SENDING
# ---------------------------------------------------------------------------

def send_single_email(
    smtp_conn: smtplib.SMTP,
    sender_email: str,
    recipient: dict,
    subject: str,
    body_html: str,
    body_plain: str,
    attachments: list[str],
    logger: logging.Logger,
) -> tuple[bool, str]:
    """
    Send one e-mail via an open SMTP connection.

    Returns (success: bool, message: str).
    """
    to_email = recipient["email"]
    try:
        msg = build_message(
            sender_email, recipient, subject,
            body_html, body_plain, attachments
        )
        smtp_conn.sendmail(sender_email, to_email, msg.as_string())
        logger.info(f"SENT     | {to_email} | {recipient.get('name', '')}")
        return True, "Sent"
    except smtplib.SMTPRecipientsRefused as e:
        detail = f"Recipient refused: {e}"
        logger.warning(f"REFUSED  | {to_email} | {detail}")
        return False, detail
    except smtplib.SMTPException as e:
        detail = f"SMTP error: {e}"
        logger.error(f"ERROR    | {to_email} | {detail}")
        return False, detail
    except Exception as e:
        detail = f"Unexpected error: {e}"
        logger.error(f"FAILED   | {to_email} | {detail}")
        return False, detail


def create_smtp_connection(
    host: str,
    port: int,
    email: str,
    password: str,
) -> smtplib.SMTP:
    """
    Open a TLS-upgraded SMTP connection and log in.
    Raises smtplib.SMTPException on failure.
    """
    context = ssl.create_default_context()
    smtp = smtplib.SMTP(host, port, timeout=30)
    smtp.ehlo()
    smtp.starttls(context=context)
    smtp.ehlo()
    smtp.login(email, password)
    return smtp


# ---------------------------------------------------------------------------
# BULK SEND ORCHESTRATOR
# ---------------------------------------------------------------------------

def bulk_send(
    provider: str,
    custom_host: str,
    custom_port: int,
    sender_email: str,
    app_password: str,
    recipients: list[dict],
    subject: str,
    body_html: str,
    body_plain: str,
    attachments: list[str],
    delay_seconds: float,
    progress_callback,   # callable(index, total, email, success, message)
    done_callback,       # callable(sent, failed, log_file)
    cancel_event: threading.Event,
    logger: logging.Logger,
    log_file: Path,
):
    """
    Send emails to all recipients sequentially.
    Runs in a background thread to keep the GUI responsive.

    progress_callback(i, total, email, success, detail) — called after each send.
    done_callback(sent, failed, log_path)               — called when finished.
    cancel_event.set()                                  — signals early stop.
    """
    cfg  = SMTP_PROVIDERS.get(provider, SMTP_PROVIDERS["Custom"])
    host = custom_host if provider == "Custom" else cfg["host"]
    port = custom_port if provider == "Custom" else cfg["port"]

    sent = 0
    failed = 0
    smtp_conn = None

    try:
        logger.info(f"SESSION START | provider={provider} host={host}:{port} sender={sender_email} recipients={len(recipients)}")
        smtp_conn = create_smtp_connection(host, port, sender_email, app_password)

        for i, recipient in enumerate(recipients):
            if cancel_event.is_set():
                logger.warning("Session cancelled by user.")
                break

            success, detail = send_single_email(
                smtp_conn, sender_email, recipient,
                subject, body_html, body_plain, attachments, logger
            )
            if success:
                sent += 1
            else:
                failed += 1

            progress_callback(i + 1, len(recipients), recipient["email"], success, detail)

            # Respect configured delay between sends (skip after last)
            if delay_seconds > 0 and i < len(recipients) - 1:
                time.sleep(delay_seconds)

    except smtplib.SMTPAuthenticationError:
        err = "Authentication failed. Check your e-mail address and App Password."
        logger.error(err)
        progress_callback(0, len(recipients), sender_email, False, err)
    except (smtplib.SMTPConnectError, OSError) as e:
        err = f"Could not connect to SMTP server: {e}"
        logger.error(err)
        progress_callback(0, len(recipients), sender_email, False, err)
    except Exception as e:
        err = f"Unexpected error during bulk send: {e}"
        logger.error(err)
        progress_callback(0, len(recipients), sender_email, False, err)
    finally:
        if smtp_conn:
            try:
                smtp_conn.quit()
            except Exception:
                pass
        logger.info(f"SESSION END   | sent={sent} failed={failed}")
        done_callback(sent, failed, log_file)


# ---------------------------------------------------------------------------
# GUI APPLICATION
# ---------------------------------------------------------------------------

class BulkEmailApp(tk.Tk):
    """Main Tkinter application window."""

    def __init__(self):
        super().__init__()
        self.title("Bulk Email Sender — Permission-Based Only")
        self.resizable(True, True)
        self.minsize(780, 660)

        self.recipients: list[dict] = []
        self.attachments: list[str] = []
        self.cancel_event = threading.Event()
        self.sending = False

        self._build_ui()

    # ------------------------------------------------------------------
    # UI CONSTRUCTION
    # ------------------------------------------------------------------

    def _build_ui(self):
        """Assemble all widgets."""
        pad = {"padx": 8, "pady": 4}

        # ---- Notebook (tabs) ----
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        self.tab_config  = ttk.Frame(nb)
        self.tab_compose = ttk.Frame(nb)
        self.tab_send    = ttk.Frame(nb)

        nb.add(self.tab_config,  text="  ⚙ Configuration  ")
        nb.add(self.tab_compose, text="  ✉ Compose  ")
        nb.add(self.tab_send,    text="  🚀 Send  ")

        self._build_config_tab(pad)
        self._build_compose_tab(pad)
        self._build_send_tab(pad)

    # ---- Configuration Tab ----

    def _build_config_tab(self, pad):
        f = self.tab_config
        row = 0

        # Provider
        ttk.Label(f, text="SMTP Provider:").grid(row=row, column=0, sticky="w", **pad)
        self.var_provider = tk.StringVar(value="Gmail")
        cb = ttk.Combobox(f, textvariable=self.var_provider,
                          values=list(SMTP_PROVIDERS.keys()), state="readonly", width=18)
        cb.grid(row=row, column=1, sticky="w", **pad)
        cb.bind("<<ComboboxSelected>>", self._on_provider_change)
        row += 1

        # Custom host/port (hidden unless "Custom" selected)
        self.frame_custom = ttk.LabelFrame(f, text="Custom SMTP Server")
        self.frame_custom.grid(row=row, column=0, columnspan=3, sticky="ew", **pad)
        self.frame_custom.grid_remove()

        ttk.Label(self.frame_custom, text="Host:").grid(row=0, column=0, sticky="w", **pad)
        self.var_custom_host = tk.StringVar()
        ttk.Entry(self.frame_custom, textvariable=self.var_custom_host, width=30).grid(
            row=0, column=1, sticky="w", **pad)

        ttk.Label(self.frame_custom, text="Port:").grid(row=0, column=2, sticky="w", **pad)
        self.var_custom_port = tk.StringVar(value="587")
        ttk.Entry(self.frame_custom, textvariable=self.var_custom_port, width=6).grid(
            row=0, column=3, sticky="w", **pad)
        row += 1

        # Sender email
        ttk.Label(f, text="Sender Email:").grid(row=row, column=0, sticky="w", **pad)
        self.var_email = tk.StringVar()
        ttk.Entry(f, textvariable=self.var_email, width=38).grid(
            row=row, column=1, columnspan=2, sticky="ew", **pad)
        row += 1

        # App password
        ttk.Label(f, text="App Password:").grid(row=row, column=0, sticky="w", **pad)
        self.var_password = tk.StringVar()
        ttk.Entry(f, textvariable=self.var_password, show="•", width=38).grid(
            row=row, column=1, columnspan=2, sticky="ew", **pad)
        row += 1

        ttk.Separator(f, orient="horizontal").grid(
            row=row, column=0, columnspan=3, sticky="ew", pady=8)
        row += 1

        # Recipients file
        ttk.Label(f, text="Recipients File\n(.csv or .txt):").grid(
            row=row, column=0, sticky="w", **pad)
        self.var_recip_file = tk.StringVar()
        ttk.Entry(f, textvariable=self.var_recip_file, width=30).grid(
            row=row, column=1, sticky="ew", **pad)
        ttk.Button(f, text="Browse…", command=self._browse_recipients).grid(
            row=row, column=2, sticky="w", **pad)
        row += 1

        self.lbl_recip_count = ttk.Label(f, text="No file loaded.", foreground="gray")
        self.lbl_recip_count.grid(row=row, column=1, columnspan=2, sticky="w", **pad)
        row += 1

        ttk.Separator(f, orient="horizontal").grid(
            row=row, column=0, columnspan=3, sticky="ew", pady=8)
        row += 1

        # Attachments
        ttk.Label(f, text="Attachments:").grid(row=row, column=0, sticky="nw", **pad)
        self.listbox_attach = tk.Listbox(f, height=4, width=38)
        self.listbox_attach.grid(row=row, column=1, sticky="ew", **pad)
        btn_frame = ttk.Frame(f)
        btn_frame.grid(row=row, column=2, sticky="nw", **pad)
        ttk.Button(btn_frame, text="Add",    command=self._add_attachment).pack(fill="x", pady=2)
        ttk.Button(btn_frame, text="Remove", command=self._remove_attachment).pack(fill="x", pady=2)
        row += 1

        # Delay
        ttk.Label(f, text="Delay Between\nEmails (sec):").grid(
            row=row, column=0, sticky="w", **pad)
        self.var_delay = tk.DoubleVar(value=1.5)
        spin = ttk.Spinbox(f, from_=0, to=60, increment=0.5,
                           textvariable=self.var_delay, width=8)
        spin.grid(row=row, column=1, sticky="w", **pad)
        ttk.Label(f, text="(0 = no delay; recommended ≥ 1 s)").grid(
            row=row, column=2, sticky="w", **pad)

        f.columnconfigure(1, weight=1)

    # ---- Compose Tab ----

    def _build_compose_tab(self, pad):
        f = self.tab_compose

        ttk.Label(f, text="Subject:").grid(row=0, column=0, sticky="w", **pad)
        self.var_subject = tk.StringVar()
        ttk.Entry(f, textvariable=self.var_subject, width=60).grid(
            row=0, column=1, sticky="ew", **pad)

        ttk.Label(f, text="Plain-Text\nFallback:").grid(row=1, column=0, sticky="nw", **pad)
        self.txt_plain = scrolledtext.ScrolledText(f, height=6, wrap="word", font=("Consolas", 10))
        self.txt_plain.grid(row=1, column=1, sticky="nsew", **pad)

        ttk.Label(f, text="HTML Body\n(or plain):").grid(row=2, column=0, sticky="nw", **pad)
        self.txt_html = scrolledtext.ScrolledText(f, height=14, wrap="word", font=("Consolas", 10))
        self.txt_html.grid(row=2, column=1, sticky="nsew", **pad)
        self.txt_html.insert("1.0", self._default_html())

        ttk.Label(f, text="Tip: Use {name} as a placeholder for the recipient's name.",
                  foreground="steelblue").grid(row=3, column=1, sticky="w", **pad)

        f.columnconfigure(1, weight=1)
        f.rowconfigure(2, weight=1)

    # ---- Send Tab ----

    def _build_send_tab(self, pad):
        f = self.tab_send

        # Confirmation checkbox
        self.var_confirmed = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            f,
            text="I confirm that all recipients have given explicit permission to receive this email.",
            variable=self.var_confirmed,
        ).grid(row=0, column=0, columnspan=3, sticky="w", **pad)

        # Buttons
        btn_row = ttk.Frame(f)
        btn_row.grid(row=1, column=0, columnspan=3, sticky="w", **pad)

        self.btn_send = ttk.Button(btn_row, text="▶  Send to All",
                                   command=self._on_send_all, style="Accent.TButton")
        self.btn_send.pack(side="left", padx=4)

        self.btn_cancel = ttk.Button(btn_row, text="⏹  Cancel",
                                     command=self._on_cancel, state="disabled")
        self.btn_cancel.pack(side="left", padx=4)

        ttk.Button(btn_row, text="🗑  Clear Log",
                   command=self._clear_log).pack(side="left", padx=4)

        # Progress bar
        self.var_progress = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(f, variable=self.var_progress,
                                            maximum=100, length=500)
        self.progress_bar.grid(row=2, column=0, columnspan=3, sticky="ew", **pad)

        self.lbl_progress = ttk.Label(f, text="Ready.")
        self.lbl_progress.grid(row=3, column=0, columnspan=3, sticky="w", **pad)

        # Log area
        ttk.Label(f, text="Send Log:").grid(row=4, column=0, sticky="nw", **pad)
        self.log_area = scrolledtext.ScrolledText(
            f, height=18, state="disabled", font=("Consolas", 9), wrap="none"
        )
        self.log_area.grid(row=5, column=0, columnspan=3, sticky="nsew", **pad)

        # Tag colours for log
        self.log_area.tag_config("ok",   foreground="#2a9d2a")
        self.log_area.tag_config("fail", foreground="#cc2222")
        self.log_area.tag_config("info", foreground="#555555")
        self.log_area.tag_config("warn", foreground="#cc7700")

        f.columnconfigure(0, weight=1)
        f.rowconfigure(5, weight=1)

    # ------------------------------------------------------------------
    # EVENT HANDLERS
    # ------------------------------------------------------------------

    def _on_provider_change(self, _event=None):
        if self.var_provider.get() == "Custom":
            self.frame_custom.grid()
        else:
            self.frame_custom.grid_remove()

    def _browse_recipients(self):
        path = filedialog.askopenfilename(
            title="Select recipients file",
            filetypes=[("CSV/TXT files", "*.csv *.txt"), ("All files", "*.*")]
        )
        if not path:
            return
        self.var_recip_file.set(path)
        try:
            self.recipients = load_recipients_from_file(path)
            self.lbl_recip_count.config(
                text=f"✔ {len(self.recipients)} valid recipient(s) loaded.",
                foreground="green"
            )
            self._log(f"Loaded {len(self.recipients)} recipients from: {Path(path).name}\n", "info")
        except Exception as e:
            self.lbl_recip_count.config(text=f"Error: {e}", foreground="red")
            messagebox.showerror("Load Error", str(e))

    def _add_attachment(self):
        paths = filedialog.askopenfilenames(title="Select attachment(s)")
        for p in paths:
            if p not in self.attachments:
                self.attachments.append(p)
                self.listbox_attach.insert("end", Path(p).name)

    def _remove_attachment(self):
        sel = self.listbox_attach.curselection()
        for i in reversed(sel):
            self.listbox_attach.delete(i)
            del self.attachments[i]

    def _on_send_all(self):
        # ---- Safeguard: explicit confirmation ----
        if not self.var_confirmed.get():
            messagebox.showwarning(
                "Confirmation Required",
                "Please tick the confirmation checkbox before sending.\n\n"
                "Only send to recipients who have explicitly opted in."
            )
            return

        # ---- Validate inputs ----
        email    = self.var_email.get().strip()
        password = self.var_password.get()
        subject  = self.var_subject.get().strip()
        body_html  = self.txt_html.get("1.0", "end-1c").strip()
        body_plain = self.txt_plain.get("1.0", "end-1c").strip()
        provider   = self.var_provider.get()

        errors = []
        if not is_valid_email(email):
            errors.append("• Enter a valid sender email address.")
        if not password:
            errors.append("• App password cannot be empty.")
        if not self.recipients:
            errors.append("• Load a recipients file first.")
        if not subject:
            errors.append("• Subject line cannot be empty.")
        if not body_html:
            errors.append("• Email body cannot be empty.")
        if provider == "Custom":
            if not self.var_custom_host.get().strip():
                errors.append("• Custom SMTP host is required.")
            try:
                int(self.var_custom_port.get())
            except ValueError:
                errors.append("• Custom SMTP port must be a number.")

        if errors:
            messagebox.showerror("Validation Errors", "\n".join(errors))
            return

        # ---- Final confirm for large sends ----
        n = len(self.recipients)
        if n > 50:
            if not messagebox.askyesno(
                "Confirm Large Send",
                f"You are about to send {n} emails.\n\nProceed?"
            ):
                return

        # ---- Prepare logger & UI ----
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        logger, log_file = setup_logger(session_id)

        self.cancel_event.clear()
        self.sending = True
        self.btn_send.config(state="disabled")
        self.btn_cancel.config(state="normal")
        self.var_progress.set(0)
        self.lbl_progress.config(text=f"Sending 0 / {n}…")
        self._log(f"─── Session {session_id} ─── {n} recipients ───\n", "info")

        # ---- Run in background thread ----
        custom_host = self.var_custom_host.get().strip()
        custom_port = int(self.var_custom_port.get()) if provider == "Custom" else 587
        delay = self.var_delay.get()

        thread = threading.Thread(
            target=bulk_send,
            kwargs=dict(
                provider=provider,
                custom_host=custom_host,
                custom_port=custom_port,
                sender_email=email,
                app_password=password,
                recipients=self.recipients,
                subject=subject,
                body_html=body_html,
                body_plain=body_plain,
                attachments=self.attachments,
                delay_seconds=delay,
                progress_callback=self._progress_callback,
                done_callback=self._done_callback,
                cancel_event=self.cancel_event,
                logger=logger,
                log_file=log_file,
            ),
            daemon=True,
        )
        thread.start()

    def _on_cancel(self):
        if self.sending:
            self.cancel_event.set()
            self._log("⏹ Cancel requested — finishing current email…\n", "warn")

    def _clear_log(self):
        self.log_area.config(state="normal")
        self.log_area.delete("1.0", "end")
        self.log_area.config(state="disabled")

    # ------------------------------------------------------------------
    # THREAD CALLBACKS (must schedule via after() — thread-safe)
    # ------------------------------------------------------------------

    def _progress_callback(self, index, total, email, success, detail):
        """Called from worker thread — reschedule onto main thread."""
        self.after(0, self._update_progress, index, total, email, success, detail)

    def _done_callback(self, sent, failed, log_file):
        self.after(0, self._on_done, sent, failed, log_file)

    def _update_progress(self, index, total, email, success, detail):
        pct = (index / total * 100) if total else 0
        self.var_progress.set(pct)
        self.lbl_progress.config(text=f"Sending {index} / {total}…")
        if success:
            self._log(f"✔ {email}  →  {detail}\n", "ok")
        else:
            self._log(f"✘ {email}  →  {detail}\n", "fail")

    def _on_done(self, sent, failed, log_file):
        self.sending = False
        self.btn_send.config(state="normal")
        self.btn_cancel.config(state="disabled")
        self.var_progress.set(100 if failed == 0 else self.var_progress.get())
        summary = f"Done — ✔ {sent} sent, ✘ {failed} failed. Log: {log_file}\n"
        self.lbl_progress.config(text=summary.strip())
        self._log(f"─── {summary}", "info")
        messagebox.showinfo("Send Complete",
                            f"Finished!\n\n✔ Sent:   {sent}\n✘ Failed: {failed}\n\nLog saved to:\n{log_file}")

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def _log(self, message: str, tag: str = "info"):
        """Append a line to the on-screen log area."""
        self.log_area.config(state="normal")
        self.log_area.insert("end", message, tag)
        self.log_area.see("end")
        self.log_area.config(state="disabled")

    @staticmethod
    def _default_html() -> str:
        return """\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; font-size: 14px; color: #333;">
  <p>Hello {name},</p>
  <p>Your message goes here.</p>
  <p>Best regards,<br>Your Name</p>
</body>
</html>"""


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = BulkEmailApp()
    app.mainloop()
