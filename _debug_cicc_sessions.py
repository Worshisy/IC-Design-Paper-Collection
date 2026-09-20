from pathlib import Path
import sys
import time

from utils import retrying_post

API = "https://ieeexplore.ieee.org/rest/search"


def fetch_all(punumber: str):
    all_recs = []
    page = 1
    total = 1
    while page <= total:
        time.sleep(1.5)
        data = retrying_post(
            API,
            {
                "newsearch": True,
                "queryText": "",
                "highlight": False,
                "returnType": "SEARCH",
                "matchPubs": True,
                "punumber": punumber,
                "sortType": "vol-only-seq",
                "pageNumber": page,
                "rowsPerPage": 100,
            },
        )
        total = data.get("totalPages", 1)
        all_recs.extend(data.get("records", []))
        page += 1
    return all_recs


def main():
    # Change punumber here to inspect different CICC years.
    # 2004: 9389  |  2024: 10528947
    punumber = "9389"
    recs = fetch_all(punumber)
    sys.stdout.write(f"Total records: {len(recs)}\n")
    for i, r in enumerate(recs):
        title = (r.get("articleTitle") or "").strip()
        tl = title.lower()
        if "session" in tl or "track" in tl or "cicc" in tl:
            sys.stdout.write(f"[{i:3d}] {title}\n")


if __name__ == "__main__":
    main()
