__all__ = [
    "Metar",
    "BadMetarError",
]


import re
from math import exp


wind_regex = r"\s+([\d\/]{3}|VRB)([\d\/]{2})(?:G(\d{2}))?(MPS|KT)"
wxs = r"VC|MI|PR|BC|DR|BL|SH|TS|FZ|DZ|RA|SN|SG|GS|GR|PL|IC|UP|FG|BR|HZ|VA|DU|FU|SA|PY|SQ|PO|DS|SS|FC"
weather_regex = rf"((?:\s+[\-\+]?(?:{wxs})+)*|\s+\/{{2}})"
cloud_regex = r"((?:\s+(?:(?:FEW|SCT|BKN|OVC|VV|\/{3})(?:\d{3}(?:TCU|CB|\/{3})?|\/{3})|CAVOK|SKC|NCD|CLR|NSC))*)"
metar_regex = re.compile(r"^" +
    # [0] => type
    r"(METAR|SPECI)" +
    # [1] => icao
    r"\s+([A-Z]{4})" +
    # [2,3,4] => UTC day, hour, minutes
    r"\s+(\d{2})(\d{2})(\d{2})Z" +
    # [5] => modifier flag
    r"(?:\s+(AUTO|COR))?" +
    # [6,7,8?,9] => wind direction, speed, gusts, units
    wind_regex +
    # [10?,11?] => variable wind directions
    r"(?:\s+(\d{3})V(\d{3}))?" +
    # [12?] => visibility string
    r"(?:\s+([\d\/]{4}(?:\s+\d{4}(?:N|NE|E|SE|S|SW|W|NW))*|(?:\d{1,2}\s+)?\d{1,2}(?:\/[24])?SM))?" +
    # [13?] => RVR string
    r"((?:\s+R\d{1,2}[LCR]?\/[MP]?\d{4}[DNU]?(?:V[MP]?\d{4}[DNU]?)?(?:FT)?)*)" +
    # [14?] => weather string
    weather_regex +
    # [15?] => cloud string
    cloud_regex +
    # [16?,17,18?,19] => temperature and dew point
    r"\s+(?:(M?)(\d{2})\/(M?)(\d{2}))" +
    # [20, 21] => pressure
    r"\s+(?:(Q|A)(\d{4}))" +
    # [22?] => recent most significant weather
   rf"(?:\s+RE((?:{wxs})+))?" +
    # [23?] => windshear string
    r"((?:\s+WS\s+R\d{1,2}[LCR]?)*)" +
    # [24?] => runway friction string
    r"((?:\s+R\d{1,2}[LCR]?\/(?:CLRD|\d{4})\d{2})*)" +
    # [25]? => trend group
    r"(?:\s+(TEMPO|BECMG)" +
        # [26?,27?,28?] => from, until, at
        r"(?:(?:\s+FM(\d{4}))?\s+TL(\d{4})|\s+AT(\d{4}))?" +
        # [29,30,31?,32]? => wind direction, speed, gusts, units
       rf"(?:{wind_regex})?" +
        # [33?] => visibility (simple)
        r"(?:\s+(\d{4}))?" +
        # [34?] => weather string
        weather_regex +
        # [35?] => cloud string
        cloud_regex +
    r")?")


class BadMetarError(ValueError):
    pass


def metar_parse(metar: str) -> tuple[str, ...]:
    matches = metar_regex.findall(metar)
    if len(matches) != 1:
        raise BadMetarError(f"Bad METAR/SPECI: '{metar}'")
    return matches[0]


def calc_humid(tc: int, tdc: int) -> float:
    # Source: https://bmcnoldy.earth.miami.edu/Humidity.html
    return 100.0 * (exp((17.625 * tdc) / (243.04 + tdc)) / exp((17.625 * tc) / (243.04 + tc)))


class Deg:
    def __init__(self, deg: int | float) -> None:
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
    if wspd == 0 or _wdir in ("VRB", "///"):
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


def fmt_wx_clouds(main: str, tempo: str, type: str) -> str:
    for part in tempo.split():
        main += f" {type[0]}:{part}"
    return main.lstrip()


class Metar:

    def __init__(self, metar: str):
        self.__raw: str = metar
        parsed = metar_parse(self.__raw)

        self.__type = parsed[0]
        self.__icao = parsed[1]
        self.__datetime = (int(parsed[2]), int(parsed[3]), int(parsed[4]))

        self.___modifier = parsed[5]

        self.__wdir = parsed[6]
        if parsed[7] == "//":
            self.__wspd = -1
        else:
            self.__wspd = int(parsed[7])

        # self.___wgust = parsed[8]   # 2-digit int or
        self.__wunit = parsed[9]      # "MPS" or "KT"
        # self.___wdir_var = (int(parsed[10]), int(parsed[11]))
        if self.__wunit == "MPS":
            self.__wspd *= 2

        # self.___vis = parsed[12]
        # self.___rvr = parsed[13].lstrip()
        self.___wxstr = parsed[14].lstrip()
        self.___clouds = parsed[15].lstrip()

        self.__tc = (-1 if parsed[16] == "M" else 1) * int(parsed[17])
        self.__tdc = (-1 if parsed[18] == "M" else 1) * int(parsed[19])
        self.__humid = calc_humid(self.__tc, self.__tdc)

        self.__altunit = parsed[20]
        self.__altval = parsed[21]

        self.___rewx = parsed[22]
        # self.___ws = parsed[23].lstrip()
        # self.___friction = parsed[24].lstrip()

        self.___trend = {
            "type": parsed[25],
            "_from": parsed[26],
            "_until": parsed[27],
            "_at": parsed[28],
            "_wind": {
                "wdir": parsed[29],
                "wspd": parsed[30],
                "_wgust": parsed[31],
                "wunit": parsed[32]
            },
            "_vis": parsed[33],
            "_wxstr": parsed[34].lstrip(),
            "_clouds": parsed[35].lstrip(),
        }

    @property
    def raw(self) -> str:
        return self.__raw

    def __str__(self) -> str:
        mod = self.___modifier[0] if self.___modifier else " "
        wd, wi = fmt_wind_dir(self.__wdir, self.__wspd)
        ws = "//" if self.__wspd < 0 else f"{self.__wspd:<2d}"
        humid = 99.0 if self.__humid >= 99.0 else self.__humid
        wx = fmt_wx_clouds(self.___wxstr, self.___trend["_wxstr"], self.___trend["type"])
        wx = " " + wx if wx else wx
        rewx = " RE:" + self.___rewx if self.___rewx else self.___rewx
        clouds = fmt_wx_clouds(self.___clouds, self.___trend["_clouds"], self.___trend["type"])
        clouds = " " + clouds if clouds else clouds
        return (f"[{self.__type[0]}{mod}] {self.__icao} " +
                f"day {self.__datetime[0]:02d} at {self.__datetime[1]:02d}:{self.__datetime[2]:02d} UTC: " +
                f"{wd} {wi} {ws} " +
                f"{self.__tc:>+3d}/{self.__tdc:<+3d} {humid:2.0f}% " +
                f"{self.__altunit}{self.__altval}" +
                f"{wx}{rewx}{clouds}")

    def __repr__(self) -> str:
        return str(self)
