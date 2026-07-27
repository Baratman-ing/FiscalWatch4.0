#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin

import feedparser
import requests
import yaml
from bs4 import BeautifulSoup

USER_AGENT = "FiscalWatch4.0/0.1 (+https://github.com/)"


@dataclass(frozen=True)
class Item:
    source: str
    title: str
    url: str
    summary: str = ""
    published: str = ""

    @property
    def uid(self) -> str:
        raw = f"{self.source}|{self.url}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


def clean_text(value: str) -> str:
    value = BeautifulSoup(value or "", "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def fetch_html(source: dict, max_items: int) -> list[Item]:
    response = requests.get(
        source["url"], headers={"User-Agent": USER_AGENT}, timeout=30
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    patterns = [p.lower() for p in source.get("include_link_patterns", [])]
    items: list[Item] = []
    seen_urls: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = urljoin(source["url"], anchor["href"].strip())
        title = clean_text(anchor.get_text(" ", strip=True))
        if not title:
            title = clean_text(anchor.get("title", ""))
        haystack = f"{title} {href}".lower()
        if patterns and not any(pattern in haystack for pattern in patterns):
            continue
        if href in seen_urls or href.startswith("javascript:"):
            continue
        seen_urls.add(href)
        parent_text = clean_text(anchor.parent.get_text(" ", strip=True)) if anchor.parent else title
        items.append(Item(source=source["name"], title=title or href, url=href, summary=parent_text))
        if len(items) >= max_items:
            break
    return items


def fetch_rss(source: dict, max_items: int) -> list[Item]:
    feed = feedparser.parse(source["url"], agent=USER_AGENT)
    if feed.bozo and not feed.entries:
        raise RuntimeError(f"Feed non leggibile: {feed.bozo_exception}")
    items = []
    for entry in feed.entries[:max_items]:
        items.append(
            Item(
                source=source["name"],
                title=clean_text(entry.get("title", "")),
                url=entry.get("link", ""),
                summary=clean_text(entry.get("summary", entry.get("description", ""))),
                published=entry.get("published", entry.get("updated", "")),
            )
        )
    return items


def score_item(item: Item, config: dict) -> tuple[int, list[str]]:
    text = f"{item.title} {item.summary} {item.url}".lower()
    score = 0
    matches: list[str] = []
    for keyword in config["keywords"]["strong"]:
        if keyword.lower() in text:
            score += int(config["matching"]["strong_score"])
            matches.append(keyword)
    for keyword in config["keywords"]["related"]:
        if keyword.lower() in text:
            score += int(config["matching"]["related_score"])
            matches.append(keyword)
    return score, sorted(set(matches))


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"seen": {}, "initialized": False}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"seen": {}, "initialized": False}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def create_github_issue(matches: list[dict]) -> None:
    token = os.getenv("GITHUB_TOKEN")
    repository = os.getenv("GITHUB_REPOSITORY")
    if not token or not repository or not matches:
        return

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    title = f"Fiscal Watch: {len(matches)} nuova/e segnalazione/i - {today}"
    body_lines = ["## Nuovi documenti rilevanti", ""]
    for match in matches:
        item = match["item"]
        body_lines.extend(
            [
                f"### [{item['title']}]({item['url']})",
                f"- **Fonte:** {item['source']}",
                f"- **Punteggio:** {match['score']}",
                f"- **Corrispondenze:** {', '.join(match['keywords'])}",
                "",
            ]
        )
    response = requests.post(
        f"https://api.github.com/repos/{repository}/issues",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={"title": title, "body": "\n".join(body_lines), "labels": ["fiscal-watch"]},
        timeout=30,
    )
    response.raise_for_status()


def main() -> int:
    config_path = Path(sys.argv[1] if len(sys.argv) > 1 else "config.yml")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    state_path = Path(config["project"]["state_file"])
    state = load_state(state_path)
    initialized = bool(state.get("initialized"))
    seen: dict[str, dict] = state.setdefault("seen", {})
    all_new: list[dict] = []
    errors: list[str] = []

    for source in config["sources"]:
        try:
            if source["type"] == "rss":
                items = fetch_rss(source, config["project"]["max_items_per_source"])
            elif source["type"] == "html":
                items = fetch_html(source, config["project"]["max_items_per_source"])
            else:
                raise ValueError(f"Tipo sorgente non supportato: {source['type']}")
        except Exception as exc:  # keep other sources running
            errors.append(f"{source['name']}: {exc}")
            continue

        for item in items:
            if item.uid in seen:
                continue
            score, keywords = score_item(item, config)
            seen[item.uid] = {
                "first_seen": datetime.now(timezone.utc).isoformat(),
                "source": item.source,
                "title": item.title,
                "url": item.url,
            }
            if initialized and score >= int(config["matching"]["minimum_score"]):
                all_new.append({"item": asdict(item), "score": score, "keywords": keywords})

    state["initialized"] = True
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    save_state(state_path, state)

    Path("data/latest_matches.json").write_text(
        json.dumps(all_new, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if all_new:
        create_github_issue(all_new)
        print(json.dumps(all_new, ensure_ascii=False, indent=2))
    else:
        print("Nessun nuovo documento rilevante.")
    if errors:
        print("Errori non bloccanti:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
