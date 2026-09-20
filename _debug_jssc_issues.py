from pathlib import Path
import sys
import time

from utils import retrying_post

API = "https://ieeexplore.ieee.org/rest/search"


def fetch_all_for_year(year: int):
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
                "punumber": "4",  # JSSC
                "ranges": [f"{year}_{year}_Year"],
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
    year = 2024
    recs = fetch_all_for_year(year)
    sys.stdout.write(f"Year {year}: {len(recs)} records\n")
    # Show distinct isnumber / issue fields.
    issues = {}
    for r in recs:
        isnum = r.get("isNumber")
        issue = r.get("issue") or ""
        issues.setdefault(isnum, {"count": 0, "title": r.get("publicationTitle", ""), "issue": issue})
        issues[isnum]["count"] += 1
    for isnum, meta in issues.items():
        sys.stdout.write(f"isNumber={isnum}, count={meta['count']}, issue={meta['issue']}, pubTitle={meta['title']}\n")

    # Dump keys from first article.
    if recs:
        sys.stdout.write("\nKeys of first record:\n")
        for k in sorted(recs[0].keys()):
            v = recs[0][k]
            vs = str(v)
            if len(vs) > 80:
                vs = vs[:77] + "..."
            sys.stdout.write(f"  {k}: {vs}\n")


if __name__ == "__main__":
    main()
