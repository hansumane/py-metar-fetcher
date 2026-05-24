#!/usr/bin/env python3

import os
import sys
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from typing import Any
from metar_parser import Metar


def get_metar(airports: list[str], verbose=None) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({
        "ids": ",".join(a for a in airports),
        "format": "json"
    })

    url = f"https://aviationweather.gov/api/data/metar?{query}"

    req = urllib.request.Request(url, headers={
        "Accept": "application/json"
    })

    try:
        with urllib.request.urlopen(req) as resp:
            metars = json.load(resp)
    except urllib.error.HTTPError as e:
        print(f"Failed API Request: {e}", file=sys.stderr, end=f"{os.linesep * 2}")
        return []

    if verbose is True:
        print(json.dumps(metars, indent=4))
        print()

    metars = [(m["icaoId"], m) for m in metars]
    metars.sort(key=lambda im: airports.index(im[0]))
    metars = [m for _, m in metars]

    if verbose == "RAW":
        for metar in metars:
            print(f"Debug      {metar['rawOb']}")
        print()

    return metars


def main(airports: list[str]):
    verbose = None
    processed_raw_metars = set()
    while True:
        new_processed_metars = []
        while len(metars := get_metar(airports, verbose=verbose)) != len(airports):
            pass
        for metar in metars:
            raw_metar = metar["rawOb"]
            if raw_metar not in processed_raw_metars:
                new_processed_metars.append(raw_metar)
                print(f"DEBUG: {raw_metar}")
        if len(new_processed_metars) > 0:
            print()
        for raw_metar in new_processed_metars:
            try:
                print(str(Metar(raw_metar)))
            except ValueError as e:
                print(f"ERROR: {e}")
            processed_raw_metars.add(raw_metar)
        if len(new_processed_metars) > 0:
            print()
        time.sleep(2 * 60)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: <airport_icao> [airport_icao [airport_icao ...]]", file=sys.stderr)
    else:
        main([e.upper() for e in sys.argv[1:]])
