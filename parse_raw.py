#!/usr/bin/env python3

import os
import sys
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request

from typing import Any

try:
    import re2 as re
except ImportError:
    import re
    print("Warning: Using 're' instead of 'pyre2'", file=sys.stderr, end=f"{os.linesep * 2}")


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


def fmt_wind_dir(_wdir: str, wspd: int) -> tuple[str, str]:
    if wspd == 0:
        return _wdir, " "
    if _wdir == "VRB":
        return _wdir, " "

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

    int_wdir = int(_wdir)
    wdir = Deg(int_wdir)
    for k, v in dirs.items():
        if v - deg_rng/2 < wdir < v + deg_rng/2:
            return f"{int_wdir:>3d}", k

    raise ValueError(f"{wdir = } is wrong")


wxs = "VC|RE|MI|PR|BC|DR|BL|SH|TS|FZ|DZ|RA|SN|SG|GS|GR|PL|IC|UP|FG|BR|HZ|VA|DU|FU|SA|PY|SQ|PO|DS|SS|FC"
metar_regex = re.compile(r"^" +
    # [0] => type
    r"(METAR|SPECI)" +
    # [1] => icao
    r"\s+([A-Z]{4})" +
    # [2,3,4] => UTC day, hour, minutes
    r"\s+(\d{2})(\d{2})(\d{2})Z" +
    # [ ] => auto metar flag (not used)
    r"(?:\s+AUTO)?" +
    # [5,6,7?,8] => wind direction, speed, gusts, units
    r"\s+(\d{3}|VRB)(\d{2})(?:G(\d{2}))?(MPS|KT)" +
    # [9?,10?] => variable wind directions
    r"(?:\s+(\d{3})V(\d{3}))?" +
    # [11?] => visibility
    r"(?:\s+(\d{4}(?:\s+\d{4}(?:N|NE|E|SE|S|SW|W|NW))*|(?:\d{1,2}\s+)?\d{1,2}(?:\/[24])?SM))?" +
    # [12?] => RVR string
    r"((?:\s+R\d{1,2}[LCR]?\/[MP]?\d{4}(?:V\d{4})?[DNU]?)*)" +
    # [13?] => weather string
   rf"((?:\s+[\-\+]?(?:{wxs})+)*)" +
    # [14?] => cloud string
    r"((?:\s+(?:(?:FEW|SCT|BKN|OVC|VV)(?:\d{3}(?:TCU|CB)?(?:\/{3})?|\/{3})|\/{2}|CAVOK|SKC|NCD|CLR|NSC))*)" +
    # [15?,16,17?,18] => temperature and dew point
    r"\s+(?:(M?)(\d{2})\/(M?)(\d{2}))" +
    # [19, 20] => pressure
    r"\s+(?:(Q|A)(\d{4}))" +
    # [21?] => windshear
    r"(?:\s+(WS\s+R\d{1,2}[LCR]?))?")


def metar_parse(metar: str) -> tuple[str, ...]:
    matches = metar_regex.findall(metar)
    if len(matches) != 1:
        raise ValueError(f"Bad METAR/SPECI: '{metar}'")
    return matches[0]


def calc_humid(tc: int, tdc: int) -> float:
    # Source: https://bmcnoldy.earth.miami.edu/Humidity.html
    return 100.0 * (math.exp((17.625 * tdc) / (243.04 + tdc)) / math.exp((17.625 * tc) / (243.04 + tc)))


class Metar:

    def __init__(self, metar: str):
        self.__raw: str = metar
        parsed = metar_parse(self.__raw)

        self.__type = parsed[0]
        self.__icao = parsed[1]
        self.__datetime = (int(parsed[2]), int(parsed[3]), int(parsed[4]))

        self.__wdir = parsed[5]       # 3-digit int or "VRB"
        self.__wspd = int(parsed[6])  # 2-digit int
        # self.___wgust = parsed[7]   # 2-digit int or
        self.__wunit = parsed[8]      # "MPS" or "KT"
        # self.___wdir_var = (int(parsed[9]), int(parsed[10]))
        if self.__wunit == "MPS":
            self.__wspd *= 2

        # self.___vis = parsed[11]
        # self.___rvr = parsed[12].lstrip()
        self.___wxstr = parsed[13].lstrip()
        self.___clouds = parsed[14].lstrip()

        self.__tc = (-1 if parsed[15] == "M" else 1) * int(parsed[16])
        self.__tdc = (-1 if parsed[17] == "M" else 1) * int(parsed[18])
        self.__humid = calc_humid(self.__tc, self.__tdc)

        self.__altunit = parsed[19]
        self.__altval = parsed[20]

        # self.___ws = parsed[21]

    @property
    def raw(self) -> str:
        return self.__raw

    def __str__(self) -> str:
        wd, wi = fmt_wind_dir(self.__wdir, self.__wspd)
        humid = 99.0 if self.__humid >= 99.0 else self.__humid
        wx = " " + self.___wxstr if self.___wxstr else self.___wxstr
        clouds = " " + self.___clouds if self.___clouds else self.___clouds
        return (f"[{self.__type[0]}] {self.__icao} day {self.__datetime[0]:02d} at {self.__datetime[1]:02d}:{self.__datetime[2]:02d} UTC: " +
                f"{wd} {wi} {self.__wspd:<2d} " +
                f"{self.__tc:+03d}/{self.__tdc:+03d} {humid:2.0f}% " +
                f"{self.__altunit}{self.__altval}" +
                f"{wx}{clouds}")

    def __repr__(self) -> str:
        return str(self)


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
