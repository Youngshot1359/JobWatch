import csv
import html
import io
import os
import smtplib
from datetime import date
from email.message import EmailMessage

E = html.escape


def _chips(items, bg, fg, limit=12):
    return "".join(
        f'<span style="display:inline-block;background:{bg};color:{fg};border-radius:10px;padding:2px 8px;margin:2px 3px 2px 0;font-size:12px">{E(i)}</span>'
        for i in items[:limit])


def _card(r) -> str:
    j = r.job
    colour = "#1a7f37" if r.score >= 90 else "#9a6700" if r.score >= 80 else "#57606a"
    meta = " &middot; ".join(E(x) for x in [j.company, j.location or "n/a", r.family, j.source] if x)
    extra = f' &middot; {E(j.salary)}' if j.salary else ""
    notes = "".join(f'<div style="color:#9a6700;font-size:12px">&#9888; {E(n)}</div>' for n in r.notes)
    return f'''
<div style="border:1px solid #d0d7de;border-radius:8px;padding:12px 14px;margin:10px 0;font-family:-apple-system,Segoe UI,Arial,sans-serif">
  <table width="100%" cellspacing="0" cellpadding="0"><tr>
    <td><a href="{E(j.url)}" style="font-size:16px;font-weight:600;color:#0969da;text-decoration:none">{E(j.title)}</a>
        <div style="color:#57606a;font-size:13px;margin-top:2px">{meta}{extra}</div></td>
    <td align="right" valign="top" style="font-size:22px;font-weight:700;color:{colour};white-space:nowrap">{r.score:.0f}%</td>
  </tr></table>
  <div style="margin-top:6px"><b style="font-size:12px;color:#57606a">You have:</b> {_chips(r.matched, "#dafbe1", "#116329") or "&mdash;"}</div>
  <div><b style="font-size:12px;color:#57606a">Adjacent:</b> {_chips(r.adjacent, "#fff8c5", "#7d4e00") or "&mdash;"}</div>
  <div><b style="font-size:12px;color:#57606a">Gaps:</b> {_chips(r.missing, "#ffebe9", "#a40e26") or "&mdash;"}</div>
  {notes}
  <div style="margin-top:6px"><a href="{E(j.url)}" style="font-size:13px">Apply &rarr;</a></div>
</div>'''


def render(top, near, fallback, stats, min_score):
    n = len(top)
    if n:
        b = top[0]
        subject = f"JobWatch {date.today():%b %d}: {n} new {min_score:.0f}%+ match{'es' if n != 1 else ''} (best: {b.score:.0f}% {b.job.company} - {b.job.title})"[:150]
    else:
        subject = f"JobWatch {date.today():%b %d}: no new {min_score:.0f}%+ matches today"
    parts = [f'<div style="max-width:720px;margin:auto;font-family:-apple-system,Segoe UI,Arial,sans-serif">'
             f'<h2 style="margin-bottom:2px">Daily job matches</h2>'
             f'<div style="color:#57606a;font-size:13px">Scanned {stats["fetched"]} postings &middot; {stats["scored"]} scored &middot; {stats["new"]} new since last email</div>']
    def section(title, rows):
        if rows:
            parts.append(f'<h3 style="margin-top:22px">{title}</h3>' + "".join(_card(r) for r in rows))
    section(f"Top matches (&ge;{min_score:.0f}%)", top)
    section("Worth a look", near)
    if not top and not near and fallback:
        parts.append('<p style="margin-top:20px">Nothing cleared your threshold. Closest new postings:</p>')
        section("Closest matches", fallback)
    if not (top or near or fallback):
        parts.append("<p>No new postings matched today.</p>")
    parts.append('<p style="color:#8c959f;font-size:12px;margin-top:24px">Full scorecard attached (CSV). Tune skills/thresholds in config/.</p></div>')

    lines = [f"Daily job matches - scanned {stats['fetched']}, new {stats['new']}"]
    for r in top + near + (fallback if not (top or near) else []):
        lines.append(f"\n[{r.score:.0f}%] {r.job.title} - {r.job.company} ({r.job.location})\n  {r.job.url}\n  have: {', '.join(r.matched[:10])}\n  gaps: {', '.join(r.missing[:6]) or '-'}")
    return subject, "".join(parts), "\n".join(lines)


def scorecard_csv(results) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["score", "title", "company", "location", "source", "family", "posted", "salary", "have", "adjacent", "gaps", "notes", "url"])
    for r in sorted(results, key=lambda x: -x.score):
        j = r.job
        w.writerow([r.score, j.title, j.company, j.location, j.source, r.family, j.posted, j.salary,
                    "; ".join(r.matched), "; ".join(r.adjacent), "; ".join(r.missing), "; ".join(r.notes), j.url])
    return buf.getvalue()


def send(subject, html_body, text_body, csv_text):
    user, pw = os.environ["EMAIL_USER"], os.environ["EMAIL_APP_PASSWORD"]
    to = os.getenv("EMAIL_TO", user)
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    msg.add_attachment(csv_text.encode(), maintype="text", subtype="csv", filename=f"scorecard_{date.today()}.csv")
    with smtplib.SMTP_SSL(os.getenv("SMTP_HOST", "smtp.gmail.com"), int(os.getenv("SMTP_PORT", "465"))) as s:
        s.login(user, pw)
        s.send_message(msg)
