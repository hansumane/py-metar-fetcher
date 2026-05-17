#!/usr/bin/env python3

import re
import sys
import json
import urllib.error
import urllib.parse
import urllib.request

from math import exp
from typing import Any
from datetime import datetime
from zoneinfo import ZoneInfo


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
        print(f"Failed API Request: {e}")
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


def parse_pres(metar: dict[str, Any]) -> str:
    for match in re.findall(r"[QA]\d{4}", metar["rawOb"]):
        return match
    return f"q{int(metar["altim"]):04d}"


def parse_wx(metar: dict[str, Any]) -> str:
    wx_builder = []
    if "wxString" in metar:
        wx_builder.append(metar["wxString"])
    if "rawOb" in metar:
        metar_split = metar["rawOb"].strip().split()[2:]
        after_tempo = False
        for e in metar_split:
            if e == "TEMPO":
                after_tempo = True
            for match in re.findall(r"[\-\+]?\b[A-Z]{4}\b", e):
                if after_tempo:
                    match = "TEMPO:" + match
                if match not in wx_builder:
                    wx_builder.append(match)
    if len(wx_builder) > 0:
        return " " + " ".join(wx_builder)
    else:
        return ""


class Deg:
    def __init__(self, deg: float) -> None:
        self.deg = float(deg) % 360

    def __str__(self) -> str:
        return f"Deg({self.deg})"

    def __repr__(self) -> str:
        return f"Deg<{self.deg}>"

    def __add__(self, other):
        return Deg(self.deg + other)

    def __sub__(self, other):
        return Deg(self.deg - other)

    def __lt__(self, other):
        if not isinstance(other, Deg):
            raise ValueError
        d = Deg(self.deg - other.deg)
        return self.deg != other.deg and d.deg > 180

    def __gt__(self, other):
        if not isinstance(other, Deg):
            raise ValueError
        d = Deg(self.deg - other.deg)
        return self.deg != other.deg and d.deg < 180


def fmt_wind_dir(_wdir: int | str, wspd: int) -> tuple[str, str]:
    if wspd == 0:
        return str(_wdir), " "
    if type(_wdir) is not int:
        if _wdir == "VRB":
            return str(_wdir), " "
        else:
            raise ValueError(f"Wrong wind direction: {_wdir = }")

    deg_rng = 360 / 8
    dirs = {}
    dirs["↓"] = Deg(0.0)
    dirs["↙"] = dirs["↓"] + deg_rng
    dirs["←"] = dirs["↙"] + deg_rng
    dirs["↖"] = dirs["←"] + deg_rng
    dirs["↑"] = dirs["↖"] + deg_rng
    dirs["↗"] = dirs["↑"] + deg_rng
    dirs["→"] = dirs["↗"] + deg_rng
    dirs["↘"] = dirs["→"] + deg_rng

    wdir = Deg(_wdir)
    for k, v in dirs.items():
        if v - deg_rng/2 < wdir < v + deg_rng/2:
            return f"{_wdir:>3d}", k

    raise ValueError(f"{wdir = } is wrong")


def calc_humid(tc: int, tdc: int) -> float:
    # Source: https://bmcnoldy.earth.miami.edu/Humidity.html
    humid = 100 * (exp((17.625 * tdc) / (243.04 + tdc)) / exp((17.625 * tc) / (243.04 + tc)))
    return 99.0 if humid >= 99.0 else humid


def main(airports: list[str]):
    verbose = "RAW"
    timezone = "UTC"

    for metar in get_metar(airports, verbose=verbose):
        icao = metar["icaoId"]
        cat = metar["fltCat"]
        sep1 = ' ' * (5 - len(cat))

        time = datetime \
            .fromisoformat(metar["reportTime"]) \
            .astimezone(ZoneInfo(timezone))
        time = time.strftime(f"on %m/%d at %H:%M {time.tzname()}")

        (wd, wi), ws = fmt_wind_dir(metar["wdir"], metar["wspd"]), metar["wspd"]

        tc, tdc = metar["temp"], metar["dewp"]
        humid = calc_humid(tc, tdc)

        pres = parse_pres(metar)

        clouds = ",".join(f"FL{c['base'] // 100}({c['cover']})" for c in metar["clouds"])
        if len(clouds) > 0:
            clouds = " " + clouds

        wx = parse_wx(metar)

        print(f"{icao}[{cat}]{sep1}{time}: {wd} {wi} {ws:<2d} {tc:+03d}/{tdc:+03d} {humid:.0f}% {pres}{clouds}{wx}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: <airport_icao> [airport_icao [airport_icao ...]]", file=sys.stderr)
    else:
        main([e.upper() for e in sys.argv[1:]])
