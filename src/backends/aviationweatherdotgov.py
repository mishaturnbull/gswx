#!/usr/bin/python3
# -*- coding: utf-8 -*-

"""
This backend facilitates fetching data from the NOAA NWS Aviation Weather
Center (AWC) text data server (TDS) v 1.3.

Documentation can be found at https://www.aviationweather.gov/dataserver

Provided services include METAR and TAF data, with the possibility of AIRMET,
SIGMET, and PIREPs in the future.  (that data is available on the TDS, but not
implemented here)
"""

import urllib.request
import xml.etree.cElementTree
import functools

METAR_URL_BASE = "https://www.aviationweather.gov/adds/dataserver_current/httpparam?datasource=metars&requestType=retrieve&format=xml&"
METAR_URL_ARGS = {
        "station": "stationString={}",
        "history": "hoursBeforeNow={}",
        "timerng_start": "startTime={}",
        "timerng_end": "endTime={}",
}

STATION_URL_BASE = "https://www.aviationweather.gov/adds/dataserver_current/httpparam?dataSource=stations&requestType=retrieve&format=xml&"
STATION_URL_ARGS = {
        "station": "stationString={}",
}

def _make_request(url):
    """
    Equivalent to curl'ing the URL and reading the results.
    """
    with urllib.request.urlopen(url) as resp:
        data = resp.read()
    return data.decode('ascii')


class Station(object):
    """
    Data structure for returning information about a station.
    """

    def __init__(self, station_id):
        self.station_id = station_id
        self.lat = None
        self.lon = None
        self.alt = None
        self.country = None
        self.state = None
        self.site = None


@functools.lru_cache(maxsize=32)
def get_station_coords(station_id):
    """
    Determines the latitude, longitude, and altitude coordinates for a given
    station.  Requires internat access until the station can be cached.
    """
    # download the data and strip it to what we want
    url = STATION_URL_BASE
    url += STATION_URL_ARGS['station'].format(station_id)
    xmldoc = _make_request(url)
    tree = xml.etree.cElementTree.fromstring(xmldoc)
    data = tree.find('data').find('Station')

    # now we make the station
    site = Station(station_id)
    site.lat = float(data.find('latitude').text)
    site.lon = float(data.find('longitude').text)
    site.alt = float(data.find('elevation_m').text)
    site.site = data.find('site').text
    site.country = data.find('country').text
    site.state = data.find('state').text

    return site


def get_metars(station_id,
        hours_before_now=None,
        start_time=None,
        end_time=None):
    """
    Gets METAR(s) for a specific station.  Returns as a list of strings.  If
    no METARs exist for the specified time period, the list will be empty.
    """
    # download the data, and find the data section
    url = METAR_URL_BASE
    url += METAR_URL_ARGS['station'].format(station_id)
    if hours_before_now:
        url += "&" + METAR_URL_ARGS['history'].format(hours_before_now)
    if start_time:
        url += "&" + METAR_URL_ARGS['timerng_start'].format(start_time)
    if end_time:
        url += "&" + METAR_URL_ARGS['timerng_end'].format(end_time)
    xmldoc = _make_request(url)
    print(xmldoc)
    tree = xml.etree.cElementTree.fromstring(xmldoc)
    data = tree.find('data')

    # there could be multiple metars, and all we want is the string
    metars = data.findall('METAR')
    metar_strings = []
    for metar in metars:
        metar_strings.append(metar.find('raw_text').text)

    return metar_strings

