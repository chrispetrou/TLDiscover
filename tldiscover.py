#!/usr/bin/env python
# -*- coding:utf-8 -*-

__description__ = 'TLDiscover: A top-level-domain fuzzer!'
__version__     = '1.5'

import sys
reload(sys)
sys.setdefaultencoding('utf8')
import time
import json
import folium
import logging
import requests
from validators import (
    url as valid_url, 
    domain as valid_domain,
)
from tldata import tlds
from Queue import Queue
from threading import Thread
from bs4 import BeautifulSoup
from urlparse import urlparse
from datetime import datetime
from socket import gethostbyname
from collections import defaultdict
from fake_useragent import UserAgent
from colorama import Fore,Back,Style
from argparse import ArgumentParser, RawTextHelpFormatter, ArgumentTypeError


BASE_URL, USER_AGENT = None, 'tldiscover_user_agent_v{}'.format(__version__)
TLDS = Queue()
TIMEOUT = 10
DOMAINS, WORKERS = [], []
VERBOSITY, LOG = False, False
INITIAL_SIZE = 0

# console colors
F, S, BT, UN, IT = Fore.RESET, Style.RESET_ALL, Style.BRIGHT, '\033[4m', '\033[3m' 
FG, FR, FC, FY, BR, FB, FM = Fore.GREEN, Fore.RED, Fore.CYAN, Fore.YELLOW, Back.RED, Fore.BLUE, Fore.MAGENTA


def console():
    """argument parser"""
    parser = ArgumentParser(description="{0}{1}TLD{2}{0}discover{2} Top level domain discovery.".format(BT,FB,S),formatter_class=RawTextHelpFormatter)
    parser._optionals.title = "{}arguments{}".format(BT,S)
    parser.add_argument('-u', "--url", required=True, type=validateDomain,
                        help='Specify a domain to start with.', metavar='')
    parser.add_argument('-t', "--threads", required=False, type=int, default=None, metavar='', 
                        help="Specify number of threads to use [{0}default:{2}{1} None{2}]".format(BT,FG,S))
    parser.add_argument('-v', "--verbose", action='store_true',
                        help="Enable verbosity [{0}default {2}{1}False{2}]".format(BT,FR,S))
    parser.add_argument('-a', "--useragent", action='store_true',
                        help="User a random user-agent [{0}default {2}{1}False{2}]".format(BT,FR,S))
    parser.add_argument('-l', "--log", action='store_true',
                        help="Save the results in a log file [{0}Default:{2} {1}False{2}]".format(BT, FR, S))
    parser.add_argument('-m', "--map", action='store_true',
                        help="Create a map [{0}Default:{2} {1}False{2}]".format(BT, FR, S))
    parser.add_argument("--timeout", type=int, default=10,
                        help="Specify HTTP connection timeout [{0}default {2}{1}10 sec{2}]".format(BT,FG,S), metavar='')
    args = parser.parse_args()
    return args


def ret(t):
    sys.stdout.write("\033[F")
    sys.stdout.write("\033[K")
    time.sleep(t)


def getNetloc(url):
    """returns url netloc"""
    return urlparse(url).netloc


def getBase(url):
    """returns the base url"""
    parsed = urlparse(url)
    return "://".join([parsed.scheme, parsed.netloc.rsplit('.',1)[0]])


def validateDomain(url):
    """check if the url is valid"""
    try:
        if not valid_url(url):
            raise ArgumentTypeError('\n{}[x] Invalid url.{}\n'.format(BR, S))
        elif not valid_domain(getNetloc(url)):
            raise ArgumentTypeError('\n{}[x] Invalid domain.{}\n'.format(BR, S))
        else:
            return url
    except Exception, e:
        print e
        sys.exit(0)


def get_progress(size):
    """returns progress so far..."""
    return  '{0:.2f}'.format(100 * (1 - float(size)/INITIAL_SIZE))


def getUA():
    """returns a fake random user-agent"""
    user_agent = UserAgent()
    return str(user_agent.random)


def get_title(content):
    """retrieves websites title"""
    try:
        title = BeautifulSoup(content, 'html.parser').title.string.strip()
        return title if title else 'Unknown title'
    except:
        return 'Unknown title'


def resolve_ip(domain):
    '''returns the IP responding to a given domain name'''
    try:
        return gethostbyname(domain)
    except Exception, e:
        return None


def craft_map(geo_info):
    """creates a simple map based on the lat,lon & domain provided"""
    try:
        map_osm = folium.Map(zoom_start=13)
        for ip,info in geo_info.items():
            marker_icon = folium.Icon(color='green') if ',' in info[2] else folium.Icon(color='blue')
            folium.Marker([info[0],info[1]],popup=info[2],icon=marker_icon).add_to(map_osm)
        filename = '{}.html'.format(getNetloc(BASE_URL))
        map_osm.save(filename)
        return filename
    except Exception, e:
        ret(.1)
        print "{}[x] Unfortunately map couldnt be created!{}".format(BR,S)
        sys.exit(0)


def geolocate(ip):
    """get lat, lon of an ip"""
    resolver = "http://ip-api.com/json/{}".format(ip)
    response = json.loads(requests.get(resolver).text)
    if response['status']=="success":
        lat, lon = response['lat'], response['lon']
        if lat!=None and lon!=None:
            return lat,lon
        else:
            return None,None
    else: return None, None


def onExit(start_time, create_map):
    """prints some basic information while exiting"""
    print '\n{0}[+]{1} Found {0}{2}{1} domains!'.format(FG,S,len(DOMAINS))
    print '{0}[+]{1} Total duration: {0}{2}{1}'.format(FG,S,datetime.now()-start_time)
    # create map if specified
    if create_map:
        print "{}[*]{} Creating map, please wait...".format(FY,S)
        ips = defaultdict(list)
        for domain in DOMAINS:
            ip = resolve_ip(getNetloc(domain))
            if ip:
                ips[ip].append(getNetloc(domain))
        if ips:
            geo_info = {}
            for ip, domains in ips.items():
                lat, lon = geolocate(ip)
                if lat and lon:
                    geo_info[ip] = [lat, lon, ', '.join(domains)]
            filename = craft_map(geo_info)
            ret(.1)
            ret(.1)
            print "{0}[+]{1} Map: {0}{2}{1} successfully created!".format(FG,S,filename)
        else:
            ret(.1)
            print '{}[x] Unfortunately no IPs resolved.{}\n'.format(BR,S)
    sys.exit(0)


def check(domain):
    """checks if a domain exists..."""
    try:
        res = requests.get(domain, timeout=TIMEOUT, headers={'User-Agent':USER_AGENT})
        if res.history:
            DOMAINS.append(res.url)
            title = get_title(res.text)
            print "{0}[+]{2} Found: {4} → {1}{3}{2} ({5})".format(FG,BT,S, res.url, domain, IT+title+S)
            if LOG:
                logging.info('Found: {1} → {0} Title: {2}'.format(res.url,domain,title))
        else:
            DOMAINS.append(domain)
            title = get_title(res.text)
            print "{1}[+]{2} Found: {0}{3}{2} ({4})".format(BT,FG,S, domain, IT+title+S)
            if LOG:
                logging.info('Found: {0} Title: {1}'.format(domain,title))
    except requests.exceptions.ConnectionError:
        if VERBOSITY:
            print "{0}[{3}%]{1} Connection error for: {2}".format(FR,S,domain,get_progress(TLDS.qsize()))
            ret(.1)
        else: pass
    except requests.exceptions.TooManyRedirects:
        if VERBOSITY:
            print "{0}[{3}%]{1} Too many redirects for: {2}".format(FB,S,domain,get_progress(TLDS.qsize()))
            ret(.1)
        else: pass
    except requests.exceptions.Timeout:
        if VERBOSITY:
            print "{0}[{3}%]{1} Timeout error for: {2}".format(FY,S,domain,get_progress(TLDS.qsize()))
            ret(.1)
        else: pass
    

def discover():
    while not TLDS.empty():
        check(TLDS.get())


if __name__ == '__main__':
    user = console()
    # global variables configuration
    BASE_URL = getBase(user.url)
    if user.useragent: USER_AGENT = getUA()
    if user.verbose:   VERBOSITY = True
    if user.timeout:   TIMEOUT = user.timeout
    if user.log:
        LOG = True
        logging.getLogger().setLevel(logging.INFO)
        logging.basicConfig(filename='{}{}'.format(getNetloc(user.url).split()[0], '.log'), format='%(asctime)s %(message)s')
    print "{}[*]{} Threads: {}".format(FC,S,FG+str(user.threads)+S)
    
    
    for tld in tlds:
        TLDS.put(BASE_URL+'.'+tld)
    INITIAL_SIZE = TLDS.qsize()
    start_time = datetime.now()

    # threaded mode...
    if user.threads:
        if user.threads > TLDS.qsize():
            print "{0}[x]{1} Invalid number of threads...".format(FR,S)
            sys.exit(0)
        print '{0}[+]{2} Multi-threaded mode: {1}ON{2}\n'.format(FC,FG,S)
        for _ in range(user.threads):
            t = Thread(target=discover)
            t.daemon = True
            WORKERS.append(t)
            t.start()
        try:
            scanning = True
            while scanning:
                scanning = False
                for _ in WORKERS:
                    if _.isAlive():
                        scanning = True
                        time.sleep(.1)
        except KeyboardInterrupt:
            for worker in WORKERS:
                worker.join(.1)
        finally:
            onExit(start_time, user.map)
    # non threaded mode ...
    else:
        try:
            print '{0}[+]{2} Multi-threaded mode: {1}OFF{2}\n'.format(FC,FR,S)
            discover()
        except KeyboardInterrupt:
            print '{}[!] Quiting...{}'.format(BR,S)
        finally:
            onExit(start_time, user.map)
# -EOF