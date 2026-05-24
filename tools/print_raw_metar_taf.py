#!/usr/bin/env python3

import sys
import urllib.error
import urllib.parse
import urllib.request

from os import linesep as nl


def get_metar_tafs(airports: list[str]) -> str:
    query = urllib.parse.urlencode({
        "ids": ",".join(a.upper() for a in airports),
        "sep": 1,
        "taf": 1
    })

    url = f"https://aviationweather.gov/api/data/metar?{query}"

    try:
        with urllib.request.urlopen(url) as resp:
            metar_tafs = resp.read().decode("utf8")
    except urllib.error.HTTPError as e:
        print(f"Failed API Request: {e}", file=sys.stderr)
        return ""

    return metar_tafs


def main(airports: list[str]):
    while not (metar_tafs := get_metar_tafs(airports)):
        pass
    print(f"{nl}{metar_tafs}{nl}")


if __name__ == "__main__":
    main(sys.argv[1:])
