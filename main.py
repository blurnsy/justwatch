#!/usr/bin/env python3
import json
import os
import random
import string
import requests
import urllib3
from collections import defaultdict
from datetime import date as date_module
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

SUBSCRIBED_SERVICES = {
    "Amazon Prime": ["Amazon Prime Video", "Amazon Prime Video Free with Ads"],
    "Apple TV": ["Apple TV", "Apple TV+", "Apple TV Plus"],
    "Disney Plus": ["Disney Plus", "Disney+"],
    "HBO Max": ["HBO Max", "Max", "Max Amazon Channel", "HBO Max Amazon Channel"],
    "Hulu": ["Hulu"],
    "Netflix": ["Netflix"],
    "Peacock": ["Peacock Premium", "Peacock"],
}

def generate_device_id() -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=22))

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

GRAPHQL_URL = "https://apis.justwatch.com/graphql"
PROXY = None  

def get_headers() -> dict:
    return {
        "Host": "apis.justwatch.com",
        "sec-ch-ua-platform": '"macOS"',
        "sec-ch-ua": '"Chromium";v="131", "Not A(Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "App-Version": "3.13.0-web-web",
        "DEVICE-ID": generate_device_id(),
        "accept": "*/*",
        "content-type": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Origin": "https://www.justwatch.com",
        "Referer": "https://www.justwatch.com/",
    }

QUERY = """
query GetNewTitles($country: Country!, $date: Date!, $language: Language!, $filter: TitleFilter, $after: String, $first: Int! = 10, $priceDrops: Boolean!, $bucketType: NewDateRangeBucket, $pageType: NewPageType! = NEW, $platform: Platform!) {
  newTitles(
    country: $country
    date: $date
    filter: $filter
    after: $after
    first: $first
    priceDrops: $priceDrops
    bucketType: $bucketType
    pageType: $pageType
  ) {
    totalCount
    edges {
      cursor
      watchNowOffer: newOffer(platform: $platform) {
        package {
          clearName
        }
      }
      node {
        __typename
        ... on MovieOrSeason {
          id
          objectId
          objectType
          content(country: $country, language: $language) {
            title
            shortDescription
            scoring {
              imdbVotes
              imdbScore
              tmdbPopularity
              tmdbScore
              tomatoMeter
              certifiedFresh
            }
            runtime
            genres {
              translation(language: $language)
            }
            ... on SeasonContent {
              seasonNumber
            }
            isReleased
          }
          ... on Season {
            show {
              id
              objectId
              objectType
              content(country: $country, language: $language) {
                title
              }
            }
          }
        }
      }
    }
    pageInfo {
      endCursor
      hasPreviousPage
      hasNextPage
    }
  }
}
"""


def fetch_new_titles(
    country: str = "US",
    language: str = "en",
    date: str | None = None,
    packages: list[str] | None = None,
    page_size: int = 50,
) -> list[dict]:
    if date is None:
        date = date_module.today().isoformat()
    if packages is None:
        packages = []
    
    all_titles = []
    cursor: Optional[str] = None
    
    while True:
        variables = {
            "first": page_size,
            "pageType": "NEW",
            "date": date,
            "filter": {
                "ageCertifications": [],
                "excludeGenres": [],
                "excludeProductionCountries": [],
                "objectTypes": [],
                "productionCountries": [],
                "subgenres": [],
                "genres": [],
                "packages": packages,
                "excludeIrrelevantTitles": False,
                "presentationTypes": [],
                "monetizationTypes": [],
            },
            "language": language,
            "country": country,
            "priceDrops": False,
            "platform": "WEB",
        }
        
        if cursor:
            variables["after"] = cursor
        
        payload = {
            "operationName": "GetNewTitles",
            "variables": variables,
            "query": QUERY,
        }
        
        proxies = {"http": PROXY, "https": PROXY} if PROXY else None
        
        response = requests.post(
            GRAPHQL_URL, 
            headers=get_headers(), 
            json=payload,
            proxies=proxies,
            verify=False,
        )
        
        if not response.ok:
            print(f"Error {response.status_code}: {response.text}")
            response.raise_for_status()
        data = response.json()
        
        new_titles = data.get("data", {}).get("newTitles", {})
        edges = new_titles.get("edges", [])
        page_info = new_titles.get("pageInfo", {})
        total_count = new_titles.get("totalCount", 0)
        
        for edge in edges:
            node = edge.get("node", {})
            if node:
                offer = edge.get("watchNowOffer", {})
                streaming_service = offer.get("package", {}).get("clearName") if offer else None
                node["streaming_service"] = streaming_service
                all_titles.append(node)
        
        print(f"Fetched {len(all_titles)}/{total_count} titles...")
        
        if not page_info.get("hasNextPage", False):
            break
        
        cursor = page_info.get("endCursor")
        if not cursor:
            break
    
    return all_titles


def extract_title_info(node: dict) -> dict:
    content = node.get("content", {})
    show = node.get("show", {})
    show_content = show.get("content", {}) if show else {}
    
    return {
        "id": node.get("objectId"),
        "type": node.get("objectType"),
        "streaming_service": node.get("streaming_service"),
        "title": content.get("title"),
        "show_title": show_content.get("title") if show else None,
        "description": content.get("shortDescription"),
        "runtime": content.get("runtime"),
        "imdb_score": content.get("scoring", {}).get("imdbScore"),
        "genres": [g.get("translation") for g in content.get("genres", [])],
    }


def normalize_service_name(raw_service: str | None) -> str | None:
    if not raw_service:
        return None
    for normalized_name, variants in SUBSCRIBED_SERVICES.items():
        if raw_service in variants:
            return normalized_name
    return None


def filter_and_group_titles(titles: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for title in titles:
        normalized = normalize_service_name(title.get("streaming_service"))
        if normalized:
            grouped[normalized].append(title)
    return dict(grouped)


def format_title_line(title: dict) -> str:
    name = title.get("show_title") or title.get("title") or "Unknown"
    title_type = title.get("type", "")
    imdb = title.get("imdb_score")
    
    if title_type == "SHOW_SEASON" and title.get("title"):
        season_info = title.get("title")
        if season_info != name:
            name = f"{name} - {season_info}"
    
    if imdb:
        return f"• {name} *(IMDb: {imdb})*"
    return f"• {name}"


def build_combined_description(grouped_titles: dict[str, list[dict]]) -> str:
    sections = []
    
    for service_name in sorted(grouped_titles.keys()):
        titles = grouped_titles.get(service_name, [])
        if not titles:
            continue
        
        title_lines = [format_title_line(t) for t in titles[:10]]
        section = f"**{service_name}** ({len(titles)})\n" + "\n".join(title_lines)
        
        if len(titles) > 10:
            section += f"\n*...and {len(titles) - 10} more*"
        
        sections.append(section)
    
    return "\n\n".join(sections)


def send_to_discord(grouped_titles: dict[str, list[dict]]) -> None:
    if not DISCORD_WEBHOOK_URL:
        raise ValueError("DISCORD_WEBHOOK_URL environment variable is not set")
    
    total_titles = sum(len(t) for t in grouped_titles.values())
    if total_titles == 0:
        print("No titles to send")
        return
    
    description = build_combined_description(grouped_titles)
    
    embed = {
        "title": f"🎬 New Streaming Titles",
        "description": description,
        "color": 0x5865F2,
        "footer": {"text": f"{total_titles} new title(s) • {date_module.today().isoformat()}"},
    }
    
    payload = {"embeds": [embed]}
    
    response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
    if response.ok:
        print(f"✓ Sent combined embed ({total_titles} titles)")
    else:
        print(f"✗ Failed to send: {response.status_code} - {response.text}")


def load_from_json(filepath: str) -> list[dict]:
    with open(filepath, "r") as f:
        return json.load(f)


def process_and_send(results: list[dict]) -> None:
    grouped = filter_and_group_titles(results)
    
    print(f"\nFiltered to {sum(len(t) for t in grouped.values())} titles across {len(grouped)} services:")
    for service in sorted(grouped.keys()):
        print(f"  {service}: {len(grouped[service])} titles")
    
    print("\nSending to Discord...")
    send_to_discord(grouped)
    print("Done!")


def main():
    import sys
    
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
        print(f"Loading from {filepath}...")
        results = load_from_json(filepath)
    else:
        print("Fetching new titles from JustWatch...")
        titles = fetch_new_titles()
        results = [extract_title_info(node) for node in titles]
        
        output_file = f"new_titles_{date_module.today().isoformat()}.json"
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)
        print(f"Saved {len(results)} titles to {output_file}")
    
    process_and_send(results)


if __name__ == "__main__":
    main()

