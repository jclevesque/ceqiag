#!/usr/bin/env python3
"""
AI News Digest
---------------
Fetches recent articles from RSS feeds, asks Claude to write a summary
tailored to your stated interests, and emails you a nicely formatted
HTML digest.

Setup:
  pip install anthropic feedparser --break-system-packages

Environment variables (set these, don't hardcode secrets):
  ANTHROPIC_API_KEY   - your Claude API key
  DIGEST_EMAIL_FROM   - sender email address
  DIGEST_EMAIL_TO     - recipient email address
  DIGEST_EMAIL_PASS   - app password for the sender account (e.g. Gmail App Password)

Run manually:
  python3 news_digest.py

Schedule with cron (runs every day at 7am):
  crontab -e
  0 7 * * * /usr/bin/python3 /path/to/news_digest.py >> /path/to/digest.log 2>&1
"""

import os
import re
import json
import html
import shutil
import smtplib
import urllib.request
from itertools import zip_longest
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import feedparser
from anthropic import Anthropic

# ----------------------------------------------------------------------
# CONFIG — edit this section
# ----------------------------------------------------------------------

# RSS feed URLs to pull from. Add/remove as you like.
RSS_FEEDS = [
    "https://news.ycombinator.com/rss",
    "https://ici.radio-canada.ca/info/rss/info/a-la-une",
]

# Describe what you personally care about — this steers the summary.
MY_INTERESTS = """
I'm a software engineer interested in AI/ML developments, especially
agentic systems and developer tools. I also want a quick pulse on major
world/economic news, but only the headlines. Skip celebrity gossip,
sports, and routine corporate earnings unless something is surprising.

For anything related to Generative AI, also write a one-paragraph summary
of the news if it is a major item. If comment/discussion data is provided
for that item, summarize the gist of the discussion too in one sentence.
"""

# How far back to look for "new" articles.
LOOKBACK_HOURS = 24

# Caps. MAX_ARTICLES_PER_FEED keeps any single busy feed (e.g. Hacker News)
# from crowding out the others before the overall cap is applied.
MAX_ARTICLES_PER_FEED = 20
MAX_ARTICLES = 40

# How many top-level HN comments to pull in for Hacker News items (0 to disable).
MAX_HN_COMMENTS = 10
MAX_TOKENS = 5000

# Model — check https://docs.claude.com for the current recommended model name.
MODEL = "claude-sonnet-5"

# ----------------------------------------------------------------------


def fetch_hn_comments(comments_url, limit=MAX_HN_COMMENTS):
    """Best-effort fetch of a couple of top-level comments for a Hacker News
    discussion, via the public Algolia HN API. Returns [] on any failure —
    this is a nice-to-have, not something the rest of the script depends on.
    """
    if limit <= 0 or not comments_url:
        return []
    match = re.search(r"id=(\d+)", comments_url)
    if not match:
        return []
    item_id = match.group(1)
    try:
        with urllib.request.urlopen(
            f"https://hn.algolia.com/api/v1/items/{item_id}", timeout=5
        ) as resp:
            data = json.load(resp)
    except Exception:
        return []

    children = data.get("children") or []
    comments = []
    for child in children:
        text = child.get("text")
        if text:
            clean = re.sub(r"<[^>]+>", " ", html.unescape(text)).strip()
            clean = re.sub(r"\s+", " ", clean)
            if clean:
                comments.append(clean[:400])
        if len(comments) >= limit:
            break
    return comments


def fetch_recent_articles():
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    per_feed_lists = []

    for url in RSS_FEEDS:
        feed = feedparser.parse(url)
        feed_articles = []
        for entry in feed.entries:
            published = entry.get("published_parsed") or entry.get("updated_parsed")
            if published:
                pub_dt = datetime(*published[:6], tzinfo=timezone.utc)
                if pub_dt < cutoff:
                    continue

            article = {
                "title": entry.get("title", "Untitled"),
                "summary": entry.get("summary", "")[:400],
                "link": entry.get("link", ""),
                "source": feed.feed.get("title", url),
            }

            comments_url = entry.get("comments")
            if comments_url and "news.ycombinator.com" in comments_url:
                comments = fetch_hn_comments(comments_url)
                if comments:
                    article["comments"] = comments

            feed_articles.append(article)
            if len(feed_articles) >= MAX_ARTICLES_PER_FEED:
                break

        per_feed_lists.append(feed_articles)

    # Interleave round-robin across feeds so one large feed can't crowd out
    # the others before the overall MAX_ARTICLES cap is applied.
    combined = []
    for group in zip_longest(*per_feed_lists):
        for item in group:
            if item is not None:
                combined.append(item)

    return combined[:MAX_ARTICLES]


def build_prompt(articles):
    entries = []
    for a in articles:
        block = f"[{a['source']}] {a['title']}\n{a['summary']}\n{a['link']}"
        if a.get("comments"):
            joined = "\n".join(f"- {c}" for c in a["comments"])
            block += f"\nTop comments:\n{joined}"
        entries.append(block)
    listing = "\n\n".join(entries)

    return f"""Here is a batch of recent news articles (title, snippet, link, source,
and occasionally top comments):

{listing}

My interests:
{MY_INTERESTS}

Write today's digest as clean HTML for an email body. Rules:

- Output ONLY the inner HTML (no <html>, <head>, or <body> tags, no markdown
  code fences).
- Use inline CSS "style" attributes on every element — do not rely on a
  <style> block, since many email clients strip those.
- Structure the digest with these sections, IN THIS ORDER, and include all 
  sections even if a section ends up with just one line saying nothing
  notable happened. 
    1. "AI & Developer Tools" — the most detail-rich section.
    2. "World & Economic Headlines" — one line per item, headline only,
       no elaboration. AT MOST two items.
- Aim for no more than 5 items total across all sections. When in doubt, 
  leave it out.
- Section headers: <h2 style="font-family:Arial,sans-serif;font-size:18px;
  color:#111827;border-bottom:2px solid #e5e7eb;padding-bottom:6px;
  margin-top:28px;">
- Each item: a <div style="margin-bottom:14px;"> containing a linked title
  (<a href="LINK" style="color:#2563eb;text-decoration:none;
  font-weight:600;font-size:15px;">TITLE</a>), a small source line
  (<div style="color:#6b7280;font-size:12px;margin-top:2px;">SOURCE</div>),
  and a one- or two-sentence summary
  (<p style="margin:6px 0 0;color:#374151;font-size:14px;
  line-height:1.5;">...</p>).
- For Generative AI items specifically that are major news: add an extra
  paragraph of deeper analysis inside a highlighted box
  (<div style="background:#f3f4f6;border-left:3px solid #2563eb;
  padding:10px 14px;margin-top:8px;border-radius:4px;">). Only mention
  discussion/comments if comment data was actually provided above for that
  item — never invent or assume comments exist.
- Skip celebrity gossip, sports, and routine corporate earnings unless
  genuinely surprising.
- Use plain, everyday language for summaries — no fluff, no filler
  transitions."""


def strip_html_for_plaintext(html_body):
    text = re.sub(r"<br\s*/?>", "\n", html_body, flags=re.IGNORECASE)
    text = re.sub(r"</(div|p|h[1-6])>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def get_summary(prompt):
    # print(prompt)
    client = Anthropic()  # reads ANTHROPIC_API_KEY from env automatically
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    # Strip stray markdown fences in case the model adds them despite instructions.
    text = re.sub(r"^```(?:html)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text.strip())
    return text.strip(), response


def wrap_email_html(inner_html, date_str):
    return f"""<div style="max-width:640px;margin:0 auto;font-family:Arial,sans-serif;
background:#ffffff;padding:24px;">
  <div style="border-bottom:3px solid #111827;padding-bottom:12px;margin-bottom:8px;">
    <h1 style="font-size:22px;color:#111827;margin:0;">Your News Digest</h1>
    <div style="color:#6b7280;font-size:13px;margin-top:4px;">{date_str}</div>
  </div>
  {inner_html}
  <div style="margin-top:32px;padding-top:12px;border-top:1px solid #e5e7eb;
  color:#9ca3af;font-size:11px;">
    Generated automatically from your RSS feeds. Adjust MY_INTERESTS in
    news_digest.py to change what shows up here.
  </div>
</div>"""


def send_email(subject, html_body, plaintext_body):
    sender = os.environ["DIGEST_EMAIL_FROM"]
    recipient = os.environ["DIGEST_EMAIL_TO"]
    password = os.environ["DIGEST_EMAIL_PASS"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient

    # Attach plain text first, HTML last — clients that support HTML will
    # render the last part; others fall back to plain text.
    msg.attach(MIMEText(plaintext_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.sendmail(sender, [recipient], msg.as_string())


def log_output(prompt, output_html, output, response):
    output_dir = "runs"
    runs = os.listdir(output_dir)
    next_run = max([int(run) for run in runs]) + 1

    output_dir = os.path.join(output_dir, str(next_run))
    os.makedirs(output_dir)

    shutil.copy(os.path.realpath(__file__), os.path.join(output_dir, "script.py"))

    with open(output_dir + "/prompt.txt", "wt") as fp:
        fp.write(prompt)

    with open(output_dir + "/output.txt", "wt") as fp:
            fp.write(output)

    with open(output_dir + "/output.html", "wt") as fp:
            fp.write(output_html)


def main():
    articles = fetch_recent_articles()
    if not articles:
        print("No recent articles found — skipping this run.")
        return

    prompt = build_prompt(articles)
    inner_html, response = get_summary(prompt)

    today = datetime.now().strftime("%Y-%m-%d")
    full_html = wrap_email_html(inner_html, today)
    plaintext = strip_html_for_plaintext(full_html)
    log_output(prompt=prompt, output=plaintext, output_html=full_html, response=response)
    
    print(plaintext)
    print(response.stop_reason)

    send_email(f"Your News Digest — {today}", full_html, plaintext)
    print(f"Digest sent successfully ({len(articles)} articles considered).")


if __name__ == "__main__":
    main()
