#!/usr/bin/env python3
import json
import random
import string
import requests
import urllib3
from datetime import date as date_module
from typing import Optional


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


def main():
    print("Fetching new titles from JustWatch...")
    titles = fetch_new_titles()
    
    results = [extract_title_info(node) for node in titles]
    
    output_file = f"new_titles_{date_module.today().isoformat()}.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"Saved {len(results)} titles to {output_file}")


if __name__ == "__main__":
    main()

