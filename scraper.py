import time
import json
import re
import requests

BASE_URL = "https://issues.apache.org/jira/rest/api/2"
PAGE_SIZE = 50
MAX_RETRIES = 5

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Apache-Jira-Scraper/1.0"
}

# ---------------------------------------------------------
# BASIC HTTP + RETRY LAYER
# ---------------------------------------------------------

def get_with_retry(url, params=None):
    """HTTP GET with retries and 429/5xx handling."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=20)

            if resp.status_code == 200:
                return resp.json()

            if resp.status_code == 429:  # rate limit
                wait = int(resp.headers.get("Retry-After", 2))
                time.sleep(wait)
                continue

            if 500 <= resp.status_code < 600:
                time.sleep(1 + attempt)
                continue

            # any other client error → return None
            return None

        except requests.exceptions.RequestException:
            time.sleep(1 + attempt)

    return None


# ---------------------------------------------------------
# SCRAPER FUNCTIONS
# ---------------------------------------------------------

def search_issues(project_key, start_at=0, max_results=50):
    url = f"{BASE_URL}/search"
    jql = f"project = {project_key} ORDER BY created ASC"
    params = {
        "jql": jql,
        "startAt": start_at,
        "maxResults": max_results,
        "fields": "*all"
    }
    return get_with_retry(url, params=params)


def fetch_single_issue(key):
    url = f"{BASE_URL}/issue/{key}"
    return get_with_retry(url)


# ---------------------------------------------------------
# TRANSFORMATION LAYER (LLM FORMAT)
# ---------------------------------------------------------

def clean_text(x):
    if not x:
        return ""
    x = re.sub(r"<[^>]+>", " ", x)
    x = re.sub(r"\s+", " ", x)
    return x.strip()


def extract_comments(fields):
    comments = []
    cblock = fields.get("comment", {})
    for c in cblock.get("comments", []):
        comments.append({
            "author": c.get("author", {}).get("displayName"),
            "created": c.get("created"),
            "body": clean_text(c.get("body", ""))
        })
    return comments


def summarize(text, max_len=300):
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_len:
        return text
    cut = text[:max_len]
    p = cut.rfind(".")
    if p > 50:
        return cut[:p+1]
    s = cut.rfind(" ")
    return cut[:s] + "..."


def generate_qna(issue):
    qna = []
    title = issue.get("title", "")
    desc = issue.get("description", "")

    if title:
        qna.append({
            "question": "What is this issue about?",
            "answer": title
        })

    if desc:
        sent = re.split(r"[.!?]", desc)[0]
        qna.append({
            "question": "What details are provided in the issue description?",
            "answer": sent.strip()
        })

    return qna


def transform_issue(raw):
    fields = raw.get("fields", {})

    issue = {
        "id": raw.get("id"),
        "key": raw.get("key"),
        "project": fields.get("project", {}).get("key"),
        "title": fields.get("summary", ""),
        "status": fields.get("status", {}).get("name"),
        "priority": fields.get("priority", {}).get("name"),
        "type": fields.get("issuetype", {}).get("name"),
        "reporter": fields.get("reporter", {}).get("displayName"),
        "assignee": fields.get("assignee", {}).get("displayName") if fields.get("assignee") else None,
        "labels": fields.get("labels", []),
        "created": fields.get("created"),
        "updated": fields.get("updated"),

        # plain text fields
        "description": clean_text(fields.get("description", "")),
        "comments": extract_comments(fields)
    }

    # text blob for summary
    blob = (
        issue["title"] + "\n\n" +
        issue["description"] + "\n\n" +
        " ".join([c["body"] for c in issue["comments"]])
    ).strip()

    issue["derived"] = {
        "summary": summarize(blob),
        "classification": {
            "priority": issue["priority"],
            "type": issue["type"],
            "labels": issue["labels"]
        },
        "qna": generate_qna(issue)
    }

    return issue


# ---------------------------------------------------------
# MAIN SCRAPER LOOP
# ---------------------------------------------------------

def scrape_project(project_key, limit=None):
    all_issues = []
    start_at = 0

    while True:
        page = search_issues(project_key, start_at=start_at, max_results=PAGE_SIZE)
        if not page:
            break

        issues = page.get("issues", [])
        total = page.get("total", 0)

        if not issues:
            break

        for item in issues:
            key = item["key"]
            raw = fetch_single_issue(key)
            if raw:
                transformed = transform_issue(raw)
                all_issues.append(transformed)

            if limit and len(all_issues) >= limit:
                return all_issues

        start_at += PAGE_SIZE
        if start_at >= total:
            break

    return all_issues


# ---------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------

if __name__ == "__main__":
    PROJECTS = ["HADOOP", "HIVE", "ZOOKEEPER"]

    for p in PROJECTS:
        print(f"\nScraping project {p}...")
        data = scrape_project(p, limit=None)  # remove limit to scrape full project

        out_file = f"{p}_dataset.jsonl"
        with open(out_file, "w", encoding="utf8") as f:
            for obj in data:
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")

        print(f"Saved {len(data)} transformed issues → {out_file}")
