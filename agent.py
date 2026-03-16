"""
Access to Justice Daily Digest Agent
-------------------------------------
Searches the web for access to justice news/research, summarizes with Claude Haiku,
and sends a daily email digest via Gmail SMTP.

Requirements:
    pip install anthropic tavily-python requests

Environment variables (set in GitHub Actions secrets or .env):
    ANTHROPIC_API_KEY   - Your Anthropic API key
    TAVILY_API_KEY      - Your Tavily API key (free tier: 1000 searches/month)
    GMAIL_ADDRESS       - Gmail address to send FROM
    GMAIL_APP_PASSWORD  - Gmail App Password (not your login password)
    RECIPIENT_EMAIL     - Email address to receive the digest
"""

import os
import smtplib
import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import anthropic
from tavily import TavilyClient


# ── Config ────────────────────────────────────────────────────────────────────

SEARCH_QUERIES = [
    "access to justice report 2024 2025 2026",
    "legal aid funding research",
    "pro bono legal services news",
    "rule of law access courts",
    "legal empowerment low income",
    "justice gap study findings",
]

ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"   # cheapest, fast enough for digests

MAX_RESULTS_PER_QUERY = 3   # keeps API costs minimal


# ── Search ────────────────────────────────────────────────────────────────────

def search_articles() -> list[dict]:
    """Run all search queries via Tavily and deduplicate by URL."""
    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    seen_urls = set()
    articles = []

    for query in SEARCH_QUERIES:
        try:
            response = client.search(
                query=query,
                search_depth="basic",
                max_results=MAX_RESULTS_PER_QUERY,
                include_answer=False,
            )
            for result in response.get("results", []):
                url = result.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    articles.append({
                        "title":   result.get("title", "Untitled"),
                        "url":     url,
                        "snippet": result.get("content", "")[:400],
                        "source":  result.get("url", "").split("/")[2],
                    })
        except Exception as e:
            print(f"Search error for '{query}': {e}")

    return articles


# ── Summarise ─────────────────────────────────────────────────────────────────

def summarise_articles(articles: list[dict]) -> str:
    """Ask Claude Haiku to curate and summarise the articles into a digest."""
    if not articles:
        return "No articles found today."

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    articles_text = "\n\n".join(
        f"[{i+1}] {a['title']}\nSource: {a['source']}\nURL: {a['url']}\nSnippet: {a['snippet']}"
        for i, a in enumerate(articles)
    )

    prompt = f"""You are an editor for a daily digest on Access to Justice.
Below are search results collected today. Your job:

1. Remove duplicates or low-quality results (press releases, paywalled pages with no content).
2. Group the remaining items into up to 4 thematic sections (e.g. "Research & Reports", "Policy & Funding", "Tech & Innovation", "Global News").
3. For each item write a 2-sentence plain-English summary that conveys the key finding or development.
4. Keep a professional, neutral tone suitable for lawyers, policymakers, and advocates.
5. Return the digest as clean HTML (no <html>/<body> wrapper) ready to embed in an email.
   Use <h2> for section headers, <h3> for article titles, <p> for summaries, <a href="..."> for links.
   End with a short <p> footer noting this digest was AI-curated.

Today's date: {datetime.date.today().strftime("%B %d, %Y")}

RAW ARTICLES:
{articles_text}
"""

    message = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )

    return message.content[0].text


# ── Email ─────────────────────────────────────────────────────────────────────

def send_email(html_body: str) -> None:
    """Send the digest via Gmail SMTP."""
    today = datetime.date.today().strftime("%B %d, %Y")
    subject = f"⚖️ Access to Justice Digest — {today}"

    gmail_address   = os.environ["GMAIL_ADDRESS"]
    app_password    = os.environ["GMAIL_APP_PASSWORD"]
    recipient_email = os.environ["RECIPIENT_EMAIL"]

    # Wrap in a minimal but readable email shell
    full_html = f"""
    <html><body style="font-family: Georgia, serif; max-width: 680px; margin: auto;
                       color: #1a1a1a; line-height: 1.7; padding: 24px;">
      <div style="border-bottom: 3px solid #1a3c5e; padding-bottom: 12px; margin-bottom: 24px;">
        <h1 style="margin:0; color:#1a3c5e; font-size:22px;">⚖️ Access to Justice Digest</h1>
        <p style="margin:4px 0 0; color:#666; font-size:14px;">{today}</p>
      </div>
      {html_body}
    </body></html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = gmail_address
    msg["To"]      = recipient_email
    msg.attach(MIMEText(full_html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_address, app_password)
        server.sendmail(gmail_address, recipient_email, msg.as_string())
        print(f"✅ Digest sent to {recipient_email}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("🔍 Searching for articles...")
    articles = search_articles()
    print(f"   Found {len(articles)} unique articles.")

    print("🤖 Summarising with Claude Haiku...")
    digest_html = summarise_articles(articles)

    print("📧 Sending email...")
    send_email(digest_html)


if __name__ == "__main__":
    main()
