#!/usr/bin/python3
# -*- coding: utf-8 -*-

"""
This file defines the basic classes and data structures for parsing current
and future weather.

Handles only METARs at this time, TAF's maybe in the future if I want to hate
myself enough.
"""

import datetime
import re


# format is:
# "metar code": (name, is_severe)
METAR_WXCODES = {
        "BR": ("mist", False),
        "DS": ("dust storm", True),
        "DU": ("widespread dust", False),
        "DZ": ("drizzle", False),
        "FG": ("fog", False),
        "FC": ("tornado", True),
        "FU": ("smoke", False),
        "GR": ("hail", True),
        "GS": ("small hail", False),
        "HZ": ("haze", False),
        "IC": ("ice crystals", False),
        "PL": ("ice pellets", False),
        "PO": ("dust devils", True),
        "RA": ("rain", False),
        "SA": ("sand", False),
        "SG": ("snow grains", False),
        "SH": ("shower", False),
        "SN": ("snow", False),
        "SQ": ("squall", True),
        "SS": ("sandstorm", True),
        "TS": ("thunderstorm", True),
        "VA": ("volcanic ash", True),
        "UP": ("unidentified precip", False)
}

# format is
# "metar code": ("name", order)
# where order determines placement with other modifiers.  weather descriptions
# themselves are all order 0 and sorted alphabetic
METAR_WXMODS = {
    "+": ("heavy", 100),
    "-": ("slight", 100),
    "BC": ("patches", -5),
    "BL": ("blowing", 5),
    "DR": ("low drifting", 4),
    "FZ": ("freezing", 6),
    "MI": ("shallow", 3),
    "VC": ("in vicinity", -6),
    "RE": ("recent", 2),
}

# format is
# "type": ("name", octas),
CLOUDS = {
    "SKC": ("clear", 0),
    "NSC": ("no significant clouds", 0),
    "FEW": ("few", 1.5),
    "SCT": ("scattered", 3.5),
    "BKN": ("broken", 6),
    "OVC": ("overcase", 8),
    "CB": ("cumulonimbus", -1),
    "TCU": ("thunderstorm", -1),
}


def conv_f_to_c(deg_f):
    """
    Farenheight to celsius conversion.
    """
    return (deg_f - 32) * 5.0/9.0


def conv_c_to_f(deg_c):
    """
    Celsius to farenheight conversion.
    """
    return (deg_c * 9.0/5.0) + 32


class PointMETAR(object):
    """
    Basic representation of a METAR.
    Stores location, date, time, etc etc.
    """

    def __init__(self, metar_string):
        """
        Handles setup and parsing of a metar string into more useful, unpacked
        data.
        """
        self.metar_string = metar_string
        self.temp = None
        self.dewpt = None
        self.windspd = None
        self.winddir = None
        self.windgust = None
        self.clouds = []
        self.vis = None
        self.press = None
        self.auto = None
        self.location = (None, None, None),
        self.loc_code = None
        self.timestamp = None
        self.weather = None
        self.remarks = None  # fuck that
        self.parse()

    def parse(self):
        """
        The meat of the METAR parser lives here."
        """
        parts = self.metar_string.split(' ')

        # a few metar examples:
        # KGFK 262353Z 24011KT 10SM BKN100 BKN120 BKN140 20/03 A2945 RMK AO2
        #  PK WND 24026/2324 SLP972 T02000033 10250 20200 51009
        # KGFK 262253Z 24012KT 10SM FEW055 SCT075 BKN110 21/03 A2945 RMK AO2
        #  SLP972 T02110033

        # the easy parts:
        self.loc_code = parts[0]
        self.auto = 'AUTO' in parts
        try:
            self.remarks = parts[parts.index('RMK'):]
        except ValueError:
            # 'RMK' is not in list, we don't have remarks
            self.remarks = []

        # timestamps are always this format:
        # AABBCCZ
        # AA is the date of the current month, BB is hours of day, CC is
        # minute of hour.  Z is a literal Z.  All times are zulu.
        timestamp = [p for p in parts if p.endswith('Z')][0]
        # we have to force the timezone, so we'll just throw it in with some
        # string magic!
        timestamp = timestamp[:-1] + "+0000"
        d = datetime.date.today()
        prefix = d.strftime("%Y%m")
        timestamp = prefix + timestamp
        self.timestamp = datetime.datetime.strptime(timestamp, "%Y%m%d%H%M%z")

        # wind!  accounts for gusts too.
        wind_segment = [p for p in parts if 'KT' in p][0][:-2]
        self.windgust = 0
        if 'G' in wind_segment:
            _ = wind_segment.split('G')
            self.windgust = int(_[1])
            wind_segment = _[0]
        self.winddir = wind_segment[:3]
        try:
            self.winddir = int(self.winddir)
        except ValueError:
            # most likely VRB05KT, variable direction, we can just leave it
            # as is and show to the user
            pass
        self.windspd = int(wind_segment[3:])

        # temperature time!
        tempre = re.compile("M?[0-9]{2}/M?[0-9]{2}")
        tempgroup = None
        for part in parts:
            if tempre.match(part):
                tempgroup = part
                break
        left, right = tempgroup.split('/')
        if 'M' in left:
            self.temp = -int(left[1:])
        else:
            self.temp = int(left)
        if 'M' in right:
            self.dewpt = -int(right[1:])
        else:
            self.dewpt = int(right)

        self.parse_cav(parts)

    def parse_cav(self, parts):
        """
        Sub-parser for dealing with ceiling, visibility, and weather groups.
        This is easier to make separate because of the CAVOK term, which can
        eliminate all three groups in one shot.
        """

        if "CAVOK" in parts:
            self.clouds = []
            self.vis = 10
            self.weather = ""
            return

        # whelp, no cavok... time for FuN pArSiNg!
        # let's do clouds first, because why not
        self.parse_ceil(parts)
        self.parse_vis(parts)
        self.parse_wx(parts)

    def parse_ceil(self, parts):
        """
        Much like having a sub-parser for CAV is easier, this is easier for
        specific to ceilings.
        """

        if ("NSC" in parts) or ("SKC" in parts):
            self.clouds = []
            return

        # now that that's out of the way...
        clayers = []
        for part in parts:
            for cldtype in CLOUDS.keys():
                if cldtype in part:
                    clayers.append(part)
                    break  # breaks inner loop, continue's outer loop
        # we have our list of cloud layers now, in clayers
        # we can't just hurl this into the self.clouds, have to actually do
        # stuff
        fmt = "{} at {}"
        self.clouds = []
        for layer in clayers:
            cloud, alt = layer[:3], layer[3:]
            part1 = CLOUDS[cloud][0]
            alt = str(int(alt) * 100)
            self.clouds.append(fmt.format(part1, alt))

    def parse_vis(self, parts):
        """
        Sub-sub-parser for visibility.
        """
        # we just need to find the field with SM in it, visibility is the only
        # one with that.  filter to the first one only just in case
        visf = [p for p in parts if p.endswith("SM")][0]
        numpt = visf[:-2]
        try:
            self.vis = int(numpt)
        except ValueError:
            # there's a / in it >:(
            a, b = numpt.split('/')
            self.vis = float(a) / float(b)

    def parse_wx(self, parts):
        """
        Sub-sub-parser for the weather codes.  This could be a doozy...
        """
        # first step: identify the weather field.  It'll be one long string
        # comprised of one or more weather codes and zero or more modifiers
        wx_field = None
        for part in parts:
            for wxc in METAR_WXCODES:
                if wxc in part:
                    wx_field = part
                    break
            if wx_field:
                break
        # check to make sure we actually found it... it's allowed to not have
        # a wx code, so in that situation we just set an empty string and done
        if wx_field is None:
            self.weather = "nothing!"
            return

        # ok, we actually have to do work
        # first, let's strip all the modifiers out
        codes = []
        modifiers = [None]
        gobbling = ""
        for c in wx_field:
            gobbling += c
            if gobbling in METAR_WXCODES.keys():
                codes.append(gobbling)
                gobbling = ""
            elif gobbling in METAR_WXMODS.keys():
                modifiers.append(gobbling)
                gobbling = ""

        # now, replace all the weather codes with their english names
        for i in range(len(codes)):
            codes[i] = METAR_WXCODES[codes[i]][0]
        # and do the same for modifiers.  we have to sort these first, though
        k = lambda m: -METAR_WXMODS[m][1] if m else 0
        modifiers.sort(key=k)
        for i in range(len(modifiers)):
            try:
                modifiers[i] = METAR_WXMODS[modifiers[i]][0]
            except KeyError:
                continue  # that's the None

        # now we inject the weather codes where the none is, flattening the
        # list in the process
        output = []
        for mod in modifiers:
            if mod is not None:
                output.append(mod)
            else:
                for wx in codes:
                    output.append(wx)

        self.weather = " ".join(output)

