#!/usr/bin/env python

"""Web Crawler.

crawler digs into a website and exports the pages it references for the
given domain as png images.  It also accepts a levels argument which
informs crawler to go n levels down on the website.

@requires: bs4, pdfkit, requests, selenium, tld, Pillow

"""

from cStringIO import StringIO
import csv
import getopt
import mimetypes
import os
from PIL import Image
import pickle
import re
import shutil
from subprocess import Popen, PIPE
import sys
import time
from textwrap import dedent
import traceback
import urllib2
import urlparse
import uuid

from bs4 import BeautifulSoup
import pdfkit
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from tld import get_tld


__author__ = "Danny Cheun"
__credits__ = ["Danny Cheun"]
__version__ = "1.3.0"
__maintainer__ = "Danny Cheun"
__email__ = "dcheun@gmail.com"


# Export on *
__all__ = []

# Globals
# Store script_args passed to script.
script_args = {}
logfile = None

item_mgr = None
browser = None
browser_profile = None
browser_type = None

start_url = None
allowed_domains = []
sub_urls = []
parent_output_dir = None
export_to_pdf = False
search_result_links = False
windows_filenames = False

dry_run = False


class BrowserType(object):
    
    """Enumeration of the backup types."""
    
    FIREFOX = 1
    CHROME = 2


class Item(object):
    
    """Structure to hold relevant crawled data."""
    
    def __init__(self):
        self.level = 0
        self.title = None
        self.url = None
        self.text = None
        self.referrer = None
        self.response = None
        self.page_source = None
        self.onclick_id = None
        # Some wiki page related.
        self.pdf_export_link = None
        self.processed = False
        self.generated_next = False
        self.next_level_links = None
        self.data_type = None
    
    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__,self.url)
    
    def __str__(self):
        return ('level=%s, url=%s, onclick=%s, referrer=%s' %
                (self.level,self.url,self.onclick_id, self.referrer))


class ItemMgr(object):
    
    """Manages items and progress."""
    
    def __init__(self, output_dir):
        self.output_dir = output_dir
        # self.items = {'level': [item, item, ...], ...}
        self.cnt = 0
        self.items = {}
        self.items_save_file = os.path.join(output_dir,'items.csv')
        self.dup_cnt = 0
        self.dup_urls = {}
        self.dups_save_file = os.path.join(output_dir,'dups.csv')
        self.invalid_cnt = 0
        self.invalid_urls = {}
        self.invalids_save_file = os.path.join(output_dir,'invalids.csv')
        self.non_domain_cnt = 0
        self.non_domain_urls = {}
        self.non_domain_save_file = os.path.join(output_dir,'non_domain.csv')
        self.timeout_cnt = 0
        self.timeout_urls = {}
        self.timeout_save_file = os.path.join(output_dir,'timeout.csv')
        self.error_cnt = 0
        self.error_urls = {}
        self.errors_save_file = os.path.join(output_dir,'errors.csv')
        self.logfile = logfile
        self._TAG = self.__class__.__name__
    
    def save(self):
        """Saves progress.
        
        This enables resume capability if crawler was to stop prematurely.
        
        """
        log('INFO',self.logfile,'SAVING TO SAVE FILES...',TAG=self._TAG)
        with open(self.items_save_file,'w') as f:
            csv_writer = csv.writer(f, quoting=csv.QUOTE_ALL, lineterminator='\n')
            # Write the count first, then the header.
            self.writerow(csv_writer, ['COUNT',self.cnt])
            header = ['LEVEL','TITLE','URL','REFERRER','RESPONSE','ONCLICK_ID','PDF_EXPORT_LINK','PROCESSED','GENERATED_NEXT']
            self.writerow(csv_writer, header)
            for k in sorted(self.items.keys()):
                v = self.items[k]
                for item in v:
                    row = [item.level,item.title,item.url,item.referrer,
                           item.response,item.onclick_id,item.pdf_export_link,
                           item.processed,item.generated_next]
                    self.writerow(csv_writer, row)
        with open(self.dups_save_file,'w') as f:
            csv_writer = csv.writer(f, quoting=csv.QUOTE_ALL, lineterminator='\n')
            # Write the count first, then the header.
            self.writerow(csv_writer, ['DUP_COUNT',self.dup_cnt])
            header = ['URL','ONCLICK_ID','COUNT','DUP_SEC_CNT']
            self.writerow(csv_writer, header)
            for k in sorted(self.dup_urls.keys()):
                v = self.dup_urls[k]
                for k2 in sorted(v):
                    v2 = v[k2]
                    row = [k,k2,v2['cnt'],v2['sec_cnt']]
                    self.writerow(csv_writer, row)
        with open(self.invalids_save_file,'w') as f:
            csv_writer = csv.writer(f, quoting=csv.QUOTE_ALL, lineterminator='\n')
            # Write the count first, then the header.
            self.writerow(csv_writer, ['INVALID_COUNT',self.invalid_cnt])
            header = ['URL','COUNT']
            self.writerow(csv_writer, header)
            for k,v in self.invalid_urls.iteritems():
                row = [k,v]
                self.writerow(csv_writer, row)
        with open(self.non_domain_save_file,'w') as f:
            csv_writer = csv.writer(f, quoting=csv.QUOTE_ALL, lineterminator='\n')
            # Write the count first, then the header.
            self.writerow(csv_writer, ['NON_DOMAIN_COUNT',self.non_domain_cnt])
            header = ['URL','COUNT']
            self.writerow(csv_writer, header)
            for k,v in self.non_domain_urls.iteritems():
                row = [k,v]
                self.writerow(csv_writer, row)
        with open(self.timeout_save_file,'w') as f:
            csv_writer = csv.writer(f, quoting=csv.QUOTE_ALL, lineterminator='\n')
            # Write the count first, then the header.
            self.writerow(csv_writer, ['TIMEOUT_COUNT',self.timeout_cnt])
            header = ['URL','COUNT']
            self.writerow(csv_writer, header)
            for k,v in self.timeout_urls.iteritems():
                row = [k,v]
                self.writerow(csv_writer, row)
        with open(self.errors_save_file,'w') as f:
            csv_writer = csv.writer(f, quoting=csv.QUOTE_ALL, lineterminator='\n')
            # Write the count first, then the header.
            self.writerow(csv_writer, ['ERROR_COUNT',self.error_cnt])
            header = ['URL','COUNT']
            self.writerow(csv_writer, header)
            for k,v in self.non_domain_urls.iteritems():
                row = [k,v]
                self.writerow(csv_writer, row)
    
    def load(self):
        """Loads from save files."""
        if os.path.exists(self.items_save_file):
            log('INFO', self.logfile, ('FOUND SAVE FILE: %s, LOADING...' %
                                       self.items_save_file), TAG=self._TAG)
            with open(self.items_save_file,'rb') as f:
                csv_reader = csv.reader(f, delimiter=',', quotechar='"')
                # Assume first line is count, then header.
                try:
                    self.cnt = int(self.translate_row(csv_reader.next())[1])
                except Exception:
                    log('WARNING', self.logfile,
                        'Unable to read cnt.\n' + traceback.format_exc(),
                        TAG=self._TAG)
                csv_reader.next()
                for row in csv_reader:
                    item = Item()
                    [level, item.title, item.url, item.referrer,
                     item.response, item.onclick_id, item.pdf_export_link,
                     item.processed, item.generated_next] = self.translate_row(row)
                    item.level = int(level)
                    if level in self.items:
                        self.items[level].append(item)
                    else:
                        self.items[level] = [item]
        if os.path.exists(self.dups_save_file):
            log('INFO', self.logfile, ('FOUND SAVE FILE: %s, LOADING...' %
                                       self.dups_save_file), TAG=self._TAG)
            with open(self.dups_save_file,'rb') as f:
                csv_reader = csv.reader(f, delimiter=',', quotechar='"')
                # Assume first line is count, then header.
                try:
                    self.dup_cnt = int(self.translate_row(csv_reader.next())[1])
                except Exception:
                    log('WARNING', self.logfile,
                        'Unable to read dup_cnt.\n' + traceback.format_exc(),
                        TAG=self._TAG)
                csv_reader.next()
                for row in csv_reader:
                    [url,onclick_id,count,sec_cnt] = self.translate_row(row)
                    if not onclick_id:
                        onclick_id = None
                    if url in self.dup_urls:
                        self.dup_urls[url].update({onclick_id:{'cnt':int(count),
                                                               'sec_cnt':int(sec_cnt)}})
                    else:
                        self.dup_urls[url] = {onclick_id:{'cnt':int(count),
                                                          'sec_cnt':int(sec_cnt)}}
        if os.path.exists(self.invalids_save_file):
            log('INFO', self.logfile, ('FOUND SAVE FILE: %s, LOADING...' %
                                       self.invalids_save_file), TAG=self._TAG)
            with open(self.invalids_save_file,'rb') as f:
                csv_reader = csv.reader(f, delimiter=',', quotechar='"')
                # Assume first line is count, then header.
                try:
                    self.invalid_cnt = int(self.translate_row(csv_reader.next())[1])
                except Exception:
                    log('WARNING', self.logfile,
                        'Unable to read invalid_cnt.\n' + traceback.format_exc(),
                        TAG=self._TAG)
                csv_reader.next()
                for row in csv_reader:
                    [url,count] = self.translate_row(row)
                    self.invalid_urls[url] = int(count)
        if os.path.exists(self.non_domain_save_file):
            log('INFO', self.logfile, ('FOUND SAVE FILE: %s, LOADING...' %
                                       self.non_domain_save_file), TAG=self._TAG)
            with open(self.non_domain_save_file,'rb') as f:
                csv_reader = csv.reader(f, delimiter=',', quotechar='"')
                # Assume first line is count, then header.
                try:
                    self.non_domain_cnt = int(self.translate_row(csv_reader.next())[1])
                except Exception:
                    log('WARNING', self.logfile,
                        'Unable to read non_domain_cnt.\n' + traceback.format_exc(),
                        TAG=self._TAG)
                csv_reader.next()
                for row in csv_reader:
                    [url,count] = self.translate_row(row)
                    self.non_domain_urls[url] = int(count)
        if os.path.exists(self.timeout_save_file):
            log('INFO', self.logfile, ('FOUND SAVE FILE: %s, LOADING...' %
                                       self.timeout_save_file), TAG=self._TAG)
            with open(self.timeout_save_file,'rb') as f:
                csv_reader = csv.reader(f, delimiter=',', quotechar='"')
                # Assume first line is count, then header.
                try:
                    self.timeout_cnt = int(self.translate_row(csv_reader.next())[1])
                except Exception:
                    log('WARNING', self.logfile,
                        'Unable to read timeout_cnt.\n' + traceback.format_exc(),
                        TAG=self._TAG)
                csv_reader.next()
                for row in csv_reader:
                    [url,count] = self.translate_row(row)
                    self.timeout_urls[url] = int(count)
        if os.path.exists(self.errors_save_file):
            log('INFO', self.logfile, ('FOUND SAVE FILE: %s, LOADING...' %
                                       self.errors_save_file), TAG=self._TAG)
            with open(self.errors_save_file,'rb') as f:
                csv_reader = csv.reader(f, delimiter=',', quotechar='"')
                # Assume first line is count, then header.
                try:
                    self.error_cnt = int(self.translate_row(csv_reader.next())[1])
                except Exception:
                    log('WARNING', self.logfile,
                        'Unable to read error_cnt.\n' + traceback.format_exc(),
                        TAG=self._TAG)
                csv_reader.next()
                for row in csv_reader:
                    [url,count] = self.translate_row(row)
                    self.error_urls[url] = int(count)
    
    def writerow(self, csv_writer, row):
        """Encode everything into UTF-8 before writing to csv.
        
        @param csv_writer: The csv writer object, fetched from csv.writer().
        @param row: The row to write.
        
        """
        encoded_row = [x.encode('utf-8') if isinstance(x,str) or
                       isinstance(x,unicode) else x for x in row]
        try:
            csv_writer.writerow(encoded_row)
        except UnicodeEncodeError:
            print 'encoded_row=%s' % encoded_row
            raise
    
    def translate_row(self, row, empty_to_none=True):
        """Translate python specific keywords found in row.
        
        @param row: The row to translate.
        @keyword empty_to_none: Translates empty strings to None.
        @return: Translated row.
        
        """
        translated_row = []
        for x in row:
            if x == 'True':
                translated_row.append(True)
            elif x == 'False':
                translated_row.append(False)
            elif empty_to_none and not x:
                translated_row.append(None)
            else:
                translated_row.append(x)
        return translated_row
    
    def print_results(self):
        log('INFO',self.logfile,'')
        log('INFO',self.logfile, 'Processed %s documents.' % self.cnt)
        log('INFO',self.logfile, 'Number of Duplicates: %s' % self.dup_cnt)
        if self.dup_urls:
            log('INFO',self.logfile, '=======================')
            for k,v in self.dup_urls.iteritems():
                for k2,v2 in v.iteritems():
                    if v2['cnt'] > 0:
                        log('INFO',self.logfile,
                            '%s (onclick=%s): cnt=%s,sec_cnt=%s' %
                            (k,k2,v2['cnt'],v2['sec_cnt']))
            log('INFO',self.logfile,'')
        log('INFO',self.logfile, 'Number of Invalid URLs: %s' % self.invalid_cnt)
        if self.invalid_urls:
            log('INFO',self.logfile, '=======================')
            for k,v in self.invalid_urls.iteritems():
                log('INFO',self.logfile, '%s: %s' % (k,v))
            log('INFO',self.logfile,'')
        log('INFO',self.logfile, 'Number of Non-Domain URLs: %s' % self.non_domain_cnt)
        if self.non_domain_urls:
            log('INFO',self.logfile, '=======================')
            for k,v in self.non_domain_urls.iteritems():
                log('INFO',self.logfile, '%s: %s' % (k,v))
            log('INFO',self.logfile,'')
        log('INFO',self.logfile, 'Number of Timeout URLs: %s' % self.timeout_cnt)
        if self.timeout_urls:
            log('INFO',self.logfile, '=======================')
            for k,v in self.timeout_urls.iteritems():
                log('INFO',self.logfile, '%s: %s' % (k,v))
            log('INFO',self.logfile,'')
        log('INFO',self.logfile, 'Number of Errors: %s' % self.error_cnt)
        if self.error_urls:
            log('INFO',self.logfile, '=======================')
            for k,v in self.error_urls.iteritems():
                log('INFO',self.logfile, '%s: %s' % (k,v))
            log('INFO',self.logfile,'')
        log('INFO',self.logfile, 'DONE')


class BrowserMgr(object):
    
    """Manages Browsers."""
    
    _start_url = None
    # Cookies are global for all browsers.
    _cookies = None
    
    def __init__(self, start_url=None, cookies=None):
        """Constructs a Browser Manager instance.
        
        @param start_url: The start URL to load on the browsers.
        @param cookies: The cookies to use on the browsers.
        
        """
        # {level: browser, ...}
        self.browsers = {}
        self._cookies = cookies
    
    def set_browser_cookies(self, browser, url, cookies):
        """Sets cookies on the browser at the requested url page.
        
        @param browser: The browser to set the cookie.
        @param url: The URL to load on the browser.
        @param cookies: The cookies to load on the browser.
        
        """
        if not any([url,cookies]):
            return
        # Load cookies.
        browser.get(url)
        time.sleep(0.2)
        cookies = pickle.load(open(script_args.get('cookies'),'rb'))
        for cookie in cookies:
            browser.add_cookie(cookie)
        # Re-load the page so the cookies will take effect.
        browser.get(url)
        time.sleep(0.2)
    
    @staticmethod
    def get_new_browser_profile(download_dir=None, browser_type=BrowserType.FIREFOX):
        """Gets a new Firefox Profile with some preferences set for
        automatically downloading files without prompting.
        
        http://yizeng.me/2014/05/23/download-pdf-files-automatically-in-firefox-using-selenium-webdriver/
        
        @keyword download_dir: The download directory to set.
        @return: A webdriver.FirefoxProfile.
        
        """
        if browser_type == BrowserType.CHROME:
            return BrowserMgr._get_new_chrome_profile(download_dir=download_dir)
        # Initialize browser profiles.
        # For now it is set on all browsers.
        profile = webdriver.FirefoxProfile()
        profile.set_preference('browser.download.folderList', 2)
        profile.set_preference('browser.download.manager.showWhenStarting', False)
        # Disable Firefox's built-in PDF viewer.
        profile.set_preference('pdfjs.disabled', True)
        # Disable Adobe Acrobat's PDF preview plugin.
        profile.set_preference('plugin.scan.plid.all', False)
        profile.set_preference('plugin.scan.Acrobat', '99.0')
        # Set download dir.
        if download_dir:
            profile.set_preference('browser.download.dir', download_dir)
        # MIME types to always save to disk (download_dir).
        # Try to set all of the Microsoft Office file types.
        types = ('application/pdf,application/octet-stream,text/calendar' +
                 MS_MimeTypes.get_unique_mime_types(as_string=True))
        profile.set_preference('browser.helperApps.neverAsk.saveToDisk', types)
        return profile
    
    @staticmethod
    def _get_new_chrome_profile(download_dir=None):
        profile = webdriver.ChromeOptions()
        prefs = {'download.prompt_for_download':False,
                 'download.directory_upgrade':True,
                 'plugins.plugins_disabled':['Chrome PDF Viewer'],
                 'extensions_to_open':'',
                 # Chrome 57 changed pdf settings.
                 'plugins.always_open_pdf_externally':True}
        if download_dir:
            prefs.update({'download.default_directory':download_dir})
        profile.add_experimental_option('prefs',prefs)
        return profile
    
    def _new_browser(self, start_url=None, cookies=None, download_dir=None):
        profile = self.get_new_browser_profile(download_dir=download_dir)
        browser = webdriver.Firefox(firefox_profile=profile)
        _cookies = cookies or self.cookies
        if start_url and _cookies:
            self.set_browser_cookies(browser, start_url, _cookies)
        if start_url:
            browser.get(start_url)
            time.sleep(0.3)
        return browser
    
    def get_browser(self, level, download_dir=None):
        """Gets the browser associated with the level.
        
        @param level: The level of the browser.
        @keyword download_dir: If browser have not been created yet, 
                uses this as the new download dir.
        
        """
        level = str(level)
        try:
            browser = self.browsers[level]
        except KeyError:
            browser = self._new_browser(start_url=self._start_url,
                                        cookies=self._cookies,
                                        download_dir=download_dir)
            self.browsers[level] = browser
        return browser
    
    def get_validation_browser(self):
        """Gets the validation browser (level 0)."""
        return self.get_browser(0)


class MS_MimeTypes(object):
    
    """All the Microsoft Office MIME types.
    
    http://filext.com/faq/office_mime_types.php
    
    """
    
    ms_map = {'.doc':'application/msword',
              '.dot':'application/msword',
              '.docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
              '.dotx':'application/vnd.openxmlformats-officedocument.wordprocessingml.template',
              '.docm':'application/vnd.ms-word.document.macroEnabled.12',
              '.dotm':'application/vnd.ms-word.template.macroEnabled.12',
              '.xls':'application/vnd.ms-excel',
              '.xlt':'application/vnd.ms-excel',
              '.xla':'application/vnd.ms-excel',
              '.xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
              '.xltx':'application/vnd.openxmlformats-officedocument.spreadsheetml.template',
              '.xlsm':'application/vnd.ms-excel.sheet.macroEnabled.12',
              '.xltm':'application/vnd.ms-excel.template.macroEnabled.12',
              '.xlam':'application/vnd.ms-excel.addin.macroEnabled.12',
              '.xlsb':'application/vnd.ms-excel.sheet.binary.macroEnabled.12',
              '.ppt':'application/vnd.ms-powerpoint',
              '.pot':'application/vnd.ms-powerpoint',
              '.pps':'application/vnd.ms-powerpoint',
              '.ppa':'application/vnd.ms-powerpoint',
              '.pptx':'application/vnd.openxmlformats-officedocument.presentationml.presentation',
              '.potx':'application/vnd.openxmlformats-officedocument.presentationml.template',
              '.ppsx':'application/vnd.openxmlformats-officedocument.presentationml.slideshow',
              '.ppam':'application/vnd.ms-powerpoint.addin.macroEnabled.12',
              '.pptm':'application/vnd.ms-powerpoint.presentation.macroEnabled.12',
              '.potm':'application/vnd.ms-powerpoint.template.macroEnabled.12',
              '.ppsm':'application/vnd.ms-powerpoint.slideshow.macroEnabled.12'
              }
    
    @classmethod
    def get_unique_mime_types(cls, as_string=False):
        """Get a list of unique MIME types.
        
        @keyword as_string: Return value is a comma separated string list.
                Default is to return values in a list.
        
        """
        if as_string:
            return ','.join(list(set(cls.ms_map.values())))
        else:
            return list(set(cls.ms_map.values()))


def wkhtmltopdf(item, filename, parent_dir, level):
    """Converts a url page to pdf.
    
    @deprecated: Not useful, use the PIL.image library instead.
    
    @param item: The Item object.
    @param filename: The name of the generated pdf file (just the filename).
    @param parent_dir: The parent directory where all output files
            will go under.  (Should specify parent_output_dir here).
    @param level: The current level.
    @keyword url: The URL to convert.
    @keyword body: A string to convert.
    
    """
    global logfile
    global item_mgr
    # Create directory if it doesn't exist.
    parent_path = os.path.join(parent_dir, str(level), 'pdf')
    if not os.path.isdir(parent_path):
        os.makedirs(parent_path, 0777)
    # Change filename extension to pdf.
    filename = '.'.join(filename.split('.')[:-1]) + '.pdf'
    filepath = os.path.join(parent_path, filename)
    log('INFO',logfile,'wkhtmltopdf: Exporting to pdf: filepath=%s' % filepath)
    try:
        pdfkit.from_url(item.url, filepath)
        time.sleep(0.5)
    except IOError:
        print traceback.format_exc()
        item_mgr.error_cnt += 1


def get_page_as_file(item, filename, parent_dir, level):
    global logfile, item_mgr
    try:
        _get_page_as_file(item, filename, parent_dir, level)
    except TimeoutException:
        log('ERROR',logfile,"Page='%s': EXC=%s" %
            (item.url,traceback.format_exc().splitlines()[-1]))
        log('ERROR',logfile,'SKIPPING PAGE (get_page_as_file)...')
        item_mgr.timeout_cnt += 1
        if item.url in item_mgr.timeout_urls:
            item_mgr.timeout_urls[item.url] += 1
        else:
            item_mgr.timeout_urls[item.url] = 1
        item_mgr.error_cnt += 1
        if item.url in item_mgr.error_urls:
            item_mgr.error_urls[item.url] += 1
        else:
            item_mgr.error_urls[item.url] = 1


def _get_page_as_file(item, filename, parent_dir, level):
    """Converts an Item to a png screenshot.
    
    Uses selenium's browser to take screenshot and export to file.
    
    @param item: The Item object.
    @param filename: The output filename (just file name).
    @param parent_dir: Specify parent_output_dir here.
    @param level: The current level.
    
    """
    global browser, logfile, item_mgr
    parent_path = os.path.join(parent_dir, str(level), 'screenshots')
    if not os.path.isdir(parent_path):
        os.makedirs(parent_path, 0777)
    filepath = os.path.join(parent_path, filename)
    # Check download type.  If downloadable, no need to get screenshot as
    # this will download the file again.
    if is_download_type(item):
        log('INFO',logfile,'%s is downloadable type, skipping screenshot...' % item.url)
        return
    log('INFO',logfile,'Exporting to filepath=%s' % filepath)
    if browser.current_url != item.url:
        browser.get(item.url)
        time.sleep(1)
        if item.onclick_id:
            time.sleep(0.5)
            browser.find_element_by_id(item.onclick_id).click()
            time.sleep(1)
        item.page_source = browser.page_source
#     browser.get_screenshot_as_file(filepath)
#     get_fullpage_screenshot(filepath)
    fullpage_screenshot(browser, filepath)
    time.sleep(0.5)
    found_fragment = re.search(r'#[^/]+$',item.url)
    if found_fragment:
        # The get_screenshot_as_file
        time.sleep(5)


def fullpage_screenshot(driver, filepath):
    """Takes a full page screenshot.
    
    This is a workaround for the Firefox/Chrome webdrivers that stopped
    support for full page screenshots. This function scrolls through the page
    taking screenshots and then stitching them together to produce the
    final full page.
    
    @note: Works for Firefox/Chrome.
    @note: Code from here with some internal modifications:
    https://stackoverflow.com/questions/41721734/taking-screenshot-of-full-page-with-selenium-python-chromedriver
    
    @param driver: The webdriver (eg: browser)
    @param filepath: The filepath to save the image to.
    
    """
    # Executes some javascript to get page dimensions and properties.
    total_width = driver.execute_script("return document.body.offsetWidth")
    total_height = driver.execute_script("return document.body.parentNode.scrollHeight")
    viewport_width = driver.execute_script("return document.body.clientWidth")
    viewport_height = driver.execute_script("return window.innerHeight")
    # Try to find the top navigation or header pane so the it is not
    # captured on every stitch.
    try:
        topnav = driver.find_element_by_id('topnav')
    except Exception:
        topnav = None
    try:
        header = driver.find_element_by_tag_name('header')
    except Exception:
        header = None
    if topnav is None and header is not None:
        topnav = header
    rectangles = []
    i = 0
    while i < total_height:
        ii = 0
        top_height = i + viewport_height
        if top_height > total_height:
            top_height = total_height
        while ii < total_width:
            top_width = ii + viewport_width
            if top_width > total_width:
                top_width = total_width
            rectangles.append((ii, i, top_width,top_height))
            ii = ii + viewport_width
        i = i + viewport_height
    
    stitched_image = None
    previous = None
    part = 0
    for rectangle in rectangles:
        # Modification note: Always scroll to the top first otherwise we get
        # parts of website stitched unevenly.
        driver.execute_script("window.scrollTo({0}, {1})".format(rectangle[0], rectangle[1]))
        time.sleep(0.2)
        if topnav is not None:
            # This is to hide the top navigation/header bars so that they don't
            # get captured on every stitch.
            driver.execute_script("arguments[0].setAttribute('style', 'position: absolute; top: 0px;');", topnav)
            time.sleep(0.2)
        time.sleep(0.2)
        file_name = '%s_part_%s.png' % (filepath,part)
        driver.get_screenshot_as_file(file_name)
        screenshot = Image.open(file_name)
        if rectangle[1] + viewport_height > total_height:
            offset = (rectangle[0], total_height - viewport_height)
        else:
            offset = (rectangle[0], rectangle[1])
        if stitched_image is None:
            stitched_image = Image.new('RGB', (screenshot.size[0], total_height))
        stitched_image.paste(screenshot, offset)
        del screenshot
        os.remove(file_name)
        part = part + 1
        previous = rectangle
    stitched_image.save(filepath)
    return True


def get_page_as_source(item, filename, parent_dir, level):
    global logfile, item_mgr
    try:
        _get_page_as_source(item, filename, parent_dir, level)
    except TimeoutException:
        log('ERROR',logfile,"Page='%s': EXC=%s" %
            (item.url,traceback.format_exc().splitlines()[-1]))
        log('ERROR',logfile,'SKIPPING PAGE (get_page_as_source)...')
        item_mgr.timeout_cnt += 1
        if item.url in item_mgr.timeout_urls:
            item_mgr.timeout_urls[item.url] += 1
        else:
            item_mgr.timeout_urls[item.url] = 1
        item_mgr.error_cnt += 1
        if item.url in item_mgr.error_urls:
            item_mgr.error_urls[item.url] += 1
        else:
            item_mgr.error_urls[item.url] = 1


def _get_page_as_source(item, filename, parent_dir, level):
    """Saves an Item's HTML source to a file.
    
    @param item: The Item object.
    @param filename: The output filename (just file name).
    @param parent_dir: Specify parent_output_dir here.
    @param level: The current level.
    
    """
    global browser, logfile, item_mgr
    parent_path = os.path.join(parent_dir, str(level), 'html_source')
    if not os.path.isdir(parent_path):
        os.makedirs(parent_path, 0777)
    filepath = os.path.join(parent_path, filename)
    # Check download type.  If downloadable, no need to get screenshot as
    # this will download the file again.
    if is_download_type(item):
        log('INFO',logfile,'%s is downloadable type, skipping collection of HTML source...' % item.url)
        return
    log('INFO',logfile,'Exporting to filepath=%s' % filepath)
    if browser.current_url != item.url:
        browser.get(item.url)
        time.sleep(1)
        if item.onclick_id:
            time.sleep(0.5)
            browser.find_element_by_id(item.onclick_id).click()
            time.sleep(1)
        item.page_source = browser.page_source
    # Check if page_source exists.
    if item.page_source is None:
        log('INFO',logfile,'%s no page_source found, skipping collection of HTML source...' % item.url)
        return
    # Save to file.
    with open(filepath,'wb') as f:
        f.write(item.page_source.encode('utf-8'))
    time.sleep(0.2)


def wget_file(item, filename, parent_dir, level):
    """Downloads a file via wget.
    
    @param item: The Item object.
    @param filename: The output filename (just file name).
    @param parent_dir: Specify parent_output_dir here.
    @param level: The current level.
    
    """
    global logfile
    global item_mgr
    parent_path = os.path.join(parent_dir, str(level))
    if not os.path.isdir(parent_path):
        os.makedirs(parent_path, 0777)
    filepath = os.path.join(parent_path, filename)
    log('INFO',logfile,'Downloading to %s' % filepath)
    cmd = ['wget', '-O', filepath, item.url]
    try:
        p = Popen(cmd,stdin=PIPE,stdout=PIPE,stderr=PIPE)
        (output,error) = p.communicate()
    except Exception:
        log('WARNING',logfile,traceback.format_exc())
        item_mgr.error_cnt += 1
    log('INFO',logfile,"[WGET] output='%s'" % output)
    log('ERROR',logfile,"[WGET] error='%s'" % error)


def download_file(url, filename, parent_dir, level, content_type):
    """Downloads the URL file.
    
    @param url: The url containing the file to download.
    @param filename: The output filename (just file name).
    @param parent_dir: Specify parent_output_dir here.
    @param level: The current level.
    @param content_type: The content type of the file.
    
    """
    global browser, logfile, item_mgr
    parent_path = os.path.join(parent_dir, str(level))
    if not os.path.isdir(parent_path):
        os.makedirs(parent_path, 0777)
    log('INFO',logfile,'Attempting to download %s' % url)
    try:
        browser.get(url)
        time.sleep(0.5)
    except TimeoutException:
        log('ERROR',logfile,"Page='%s': EXC=%s" %
            (url,traceback.format_exc().splitlines()[-1]))
        log('ERROR',logfile,'SKIPPING PAGE (get_page_as_file)...')
        item_mgr.timeout_cnt += 1 
        if url in item_mgr.timeout_urls:
            item_mgr.timeout_urls[url] += 1 
        else:
            item_mgr.timeout_urls[url] = 1
        item_mgr.error_cnt += 1 
        if url in item_mgr.error_urls:
            item_mgr.error_urls[url] += 1 
        else:
            item_mgr.error_urls[url] = 1
    except Exception:
        log('ERROR',logfile,traceback.format_exc())
        item_mgr.error_cnt += 1


def is_download_type(item, get_content_type=False,
                     get_content_type_if_true=False):
    """Checks if a URL contains a downloadable file.
    
    NOTE: "downloadable" here means if a URL is a link to a file
    that should be downloaded. (Eg: pdf, xls, doc).
    
    The downloadable type is not complete.
    
    @keyword get_content_type: Returns the content type.
    @keyword get_content_type_if_true: Returns the content type if downloadable.
    @return: True if downloadable, False otherwise.
    
    """
    # Check for attachment data type (NOTE: Might be client specific).
    if item.data_type and item.data_type == 'attachment':
        return True
    url = item.url
    f_type = mimetypes.guess_type(url)[0]
    if f_type is None:
        return False
    # Try to identify pdf files and vendor specific developed files.
    # vnd includes Microsoft file types.
    download_type = ['application/pdf','application/octet-stream','text/calendar'] + MS_MimeTypes.get_unique_mime_types()
    if get_content_type:
        return f_type
    for dt in download_type:
        if dt in f_type:
            if get_content_type_if_true:
                return f_type
            return True
    return False


def move_files(src_dir, dst_dir, wait_for_downloads=True, verbose=True, wait_secs=10):
    """Moves files from src_dir to dst_dir.
    
    @keyword wait_for_downloads: Wait for the downloads to complete
            before moving files.
    @keyword verbose: Prints info as it's doing operations.
    @keyword wait_secs: The wait interval if wait_for_downloads is True.
    
    """
    global logfile, browser_type, item_mgr
    if wait_for_downloads:
        if browser_type == BrowserType.CHROME:
            partial_download_ext = r'.crdownload$'
        else:
            partial_download_ext = r'.part$'
        incomplete = [x for x in os.listdir(src_dir) if re.search(partial_download_ext,x)]
        while incomplete:
            if verbose:
                log('INFO',logfile,'Waiting for downloads to complete...: %s' % incomplete)
            time.sleep(wait_secs)
            incomplete = [x for x in os.listdir(src_dir) if re.search(partial_download_ext,x)]
    for i in os.listdir(src_dir):
        i_path = os.path.join(src_dir,i)
        if verbose:
            log('INFO',logfile,'Moving %s to %s' % (i_path,dst_dir))
        if not os.path.isdir(dst_dir):
            os.makedirs(dst_dir, 0777)
        # Try up to three times to move the file.
        for i in range(1,4):
            try:
                shutil.move(i_path,dst_dir)
                break
            except shutil.Error:
                if 'already exists' in traceback.format_exc():
                    new_dst = os.path.sep.join([dst_dir,get_unique_filename(i_path)])
                    shutil.copy2(i_path,new_dst)
                    os.remove(i_path)
                    break
            except Exception:
                log('WARNING',logfile,
                    'Try %s: Unable to move file %s: %s' %
                    (i,i_path,traceback.format_exc().splitlines()[-1]))
                if i == 3:
                    log('ERROR',logfile,
                        'Tried %s times to move %s. Logging and skipping...' %
                        (i,i_path))
                    item_mgr.error_cnt += 1
                    if i_path in item_mgr.error_urls:
                        item_mgr.error_urls[i_path] += 1
                    else:
                        item_mgr.error_urls[i_path] = 1
                    break
                else:
                    log('WARNING',logfile,'Trying again in %s secs...' % wait_secs)
                    time.sleep(wait_secs)


def get_unique_filename(i_path):
    """Returns a unique filename.
    
    @param i_path: The pathname of the file.
    
    """
    fname_arr = os.path.basename(i_path).split('.')
    t_fname = '.'.join(fname_arr[:-1]) + '_' + str(uuid.uuid4())
    t_ext = fname_arr[-1]
    if t_ext:
        fname = t_fname + '.' + t_ext
    else:
        fname = t_fname
    return fname


def get_items(item, level=None):
    """Searches through an Item's html page source for hyperlinks.
    
    Searches for sub-links.
    
    @param item: The Item object.
    @keyword level: The current level.
    @return: A list of Items underneath the item passed in.
    
    """
    global allowed_domains, browser
    global sub_urls
    global logfile
    global dry_run, parent_output_dir, export_to_pdf
    global search_result_links, windows_filenames
    global item_mgr
    global script_args
    next_level_links = item.next_level_links
    if next_level_links is None:
        if item.page_source:
            soup = BeautifulSoup(item.page_source, 'html.parser')
            if search_result_links:
                next_level_links = [x for x in soup.find_all('a')
                                    if x.get('class')
                                    and 'search-result-link' in x.get('class')
                                    and 'visitable' in x.get('class')]
            else:
                next_level_links = soup.find_all('a')
        else:
            log('INFO',logfile,'Item does not have next level links nor page source, getting page source: %s, onclick_id=%s' % (item.url,item.onclick_id))
            browser.get(item.url)
            time.sleep(0.5)
            # Check onclick_id and follow that click.
            if item.onclick_id:
                time.sleep(0.5)
                browser.find_element_by_id(item.onclick_id).click()
                time.sleep(0.3)
            item.page_source = browser.page_source
            soup = BeautifulSoup(item.page_source, 'html.parser')
            if search_result_links:
                next_level_links = [x for x in soup.find_all('a')
                                    if x.get('class')
                                    and 'search-result-link' in x.get('class')
                                    and 'visitable' in x.get('class')]
            else:
                next_level_links = soup.find_all('a')
    for l in next_level_links:
        new_item = Item()
        link = l.get('href')
        # Check for attachment data types (specific for wiki.hulu.com).
        if l.get('data-type','') == 'attachment':
            try:
                link = '/download/attachments' + urllib2.unquote(link).split('preview=')[1] + '?download=true'
            except IndexError:
                pass
            new_item.data_type = 'attachment'
        # Get absolute link url.
        new_item.url = urlparse.urljoin(item.url, link).rstrip('/')
        new_item.referrer = item.url
        new_item.text = l.get_text()
        new_item.level = level
        # Check for onclick
        if link == '#' and l.get('onclick'):
            try:
                new_item.onclick_id = l.find('span').get('id')
            except AttributeError:
                m = re.search(r'goToSharedPage\((.*)\)',l.get('onclick'))
                if m:
                    link = m.groups()[0].strip("'")
                    new_item.url = urlparse.urljoin(item.url, link).rstrip('/')
        try:
            res = get_tld(new_item.url)
        except Exception:
            item_mgr.invalid_cnt += 1
            if new_item.url in item_mgr.invalid_urls:
                item_mgr.invalid_urls[new_item.url] += 1
            else:
                item_mgr.invalid_urls[new_item.url] = 1
            log('INFO',logfile,'INVALID URL FOUND (%s): %s' % (item_mgr.invalid_urls[new_item.url],new_item))
            continue
        if res not in allowed_domains:
            item_mgr.non_domain_cnt += 1
            if new_item.url in item_mgr.non_domain_urls:
                item_mgr.non_domain_urls[new_item.url] += 1
            else:
                item_mgr.non_domain_urls[new_item.url] = 1
            log('INFO',logfile,'NON DOMAIN URL FOUND (%s): %s' % (item_mgr.non_domain_urls[new_item.url],new_item))
            continue
        found_false_sub_url = False
        for sub_url in sub_urls:
            if sub_url not in new_item.url:
                item_mgr.non_domain_cnt += 1
                if new_item.url in item_mgr.non_domain_urls:
                    item_mgr.non_domain_urls[new_item.url] += 1
                else:
                    item_mgr.non_domain_urls[new_item.url] = 1
                log('INFO',logfile,'NON DOMAIN URL FOUND (%s): %s' % (item_mgr.non_domain_urls[new_item.url],new_item))
                found_false_sub_url = True
                break
        if found_false_sub_url:
            continue
        # Check if the url is a duplicate.
        found_dup, added_dup, found_section = False, False, False
        # Check for sections.
        try:
            (base_url,section) = re.search(r'(.*)/([#][^/]+)$',new_item.url).groups()
        except AttributeError:
            (base_url,section) = None,None
        if section:
            found_section = True
        if new_item.url in item_mgr.dup_urls:
            if new_item.onclick_id in item_mgr.dup_urls[new_item.url]:
                found_dup = True
            else:
                item_mgr.dup_urls[new_item.url].update({new_item.onclick_id:{'cnt':0,'sec_cnt':0}})
                added_dup = True
        if found_dup:
            item_mgr.dup_urls[new_item.url][new_item.onclick_id]['cnt'] += 1
            item_mgr.dup_cnt += 1
            log('INFO',logfile,'DUPLICATE URL FOUND (%s): %s' % (item_mgr.dup_urls[new_item.url],new_item))
            continue
        if section:
            if base_url not in item_mgr.dup_urls:
                item_mgr.dup_urls[base_url] = {new_item.onclick_id:{'cnt':0,'sec_cnt':0}}
            else:
                if new_item.onclick_id in item_mgr.dup_urls[base_url]:
                    # Add full new_item.url to dups.
                    item_mgr.dup_urls[new_item.url] = {new_item.onclick_id:{'cnt':0,'sec_cnt':0}}
                    # Then increment section counter of base_url.
                    item_mgr.dup_urls[base_url][new_item.onclick_id]['cnt'] += 1
                    item_mgr.dup_urls[base_url][new_item.onclick_id]['sec_cnt'] += 1
                    item_mgr.dup_cnt += 1
                    log('INFO',logfile,'DUPLICATE URL SECTION FOUND (%s): %s' % (item_mgr.dup_urls[new_item.url],new_item))
                    continue
                else:
                    item_mgr.dup_urls[base_url] = {new_item.onclick_id:{'cnt':0,'sec_cnt':0}}
        # Load URL (mostly to get page source), then add to duplicate definition.
        log('INFO',logfile,'Getting new item page source: %s, onclick_id=%s' % (new_item.url,new_item.onclick_id))
        
        try:
            browser.get(new_item.url)
        except TimeoutException:
            # Log and skip the page that times out.
            # Consider this an Error. Add to dup.
            log('ERROR',logfile,"Page='%s': EXC=%s" %
                (new_item.url,traceback.format_exc().splitlines()[-1]))
            log('ERROR',logfile,'SKIPPING PAGE, NEEDS MANUAL COLLECTION.')
            item_mgr.timeout_cnt += 1
            if new_item.url in item_mgr.timeout_urls:
                item_mgr.timeout_urls[new_item.url] += 1
            else:
                item_mgr.timeout_urls[new_item.url] = 1
            item_mgr.error_cnt += 1
            if new_item.url in item_mgr.error_urls:
                item_mgr.error_urls[new_item.url] += 1
            else:
                item_mgr.error_urls[new_item.url] = 1
            # Added to dup.
            if not added_dup:
                item_mgr.dup_urls[new_item.url] = {new_item.onclick_id:{'cnt':0,'sec_cnt':0}}
            # Skip.
            continue
        
        time.sleep(0.5)
        if new_item.onclick_id:
            time.sleep(0.5)
            browser.find_element_by_id(new_item.onclick_id).click()
            time.sleep(0.3)
        new_item.page_source = browser.page_source
        if not added_dup:
            item_mgr.dup_urls[new_item.url] = {new_item.onclick_id:{'cnt':0,'sec_cnt':0}}
        #######################################################################
        # Export this level items here for quicker processing.
        #######################################################################
        log('INFO',logfile,str(new_item))
        # Build the file name for the output file.
        filename = new_item.url.split('https://')[-1]
        filename = re.sub(r'[^a-z.A-Z0-9]','.-',filename.split('http://')[-1])
        if windows_filenames:
            if len(filename) > 255:
                # Strip out some characters from filename.
                filename = filename[:50] +'__'+ filename[-50:]
        png_filename = filename + '_%s.png' % item_mgr.cnt
        pdf_filename = filename + '_%s.pdf' % item_mgr.cnt
        html_filename = filename + '_%s.html' % item_mgr.cnt
        if export_to_pdf:
            exp_filename = pdf_filename
        else:
            exp_filename = png_filename
        if not script_args.get('only-downloadable'):
            log('INFO',logfile,'Getting snapshot of page %s...' % new_item.url)
            if not dry_run:
                get_page_as_file(new_item, exp_filename, parent_output_dir, level)
        if script_args.get('get-source'):
            log('INFO',logfile,'Getting HTML source of page %s...' % new_item.url)
            if not dry_run:
                get_page_as_source(new_item, html_filename, parent_output_dir, level)
        item_mgr.cnt += 1
        time.sleep(0.3)
        new_item.processed = True
        # Move any downloads to output level directory.
        move_files(os.path.join(parent_output_dir,'main'),
                   os.path.join(parent_output_dir,str(level)))
        # Get next level links and erase page source after processing to save memory.
        if new_item.page_source:
            soup = BeautifulSoup(new_item.page_source,'html.parser')
            new_item.next_level_links = soup.find_all('a')
        new_item.page_source = None
        # Append to items list.
        if str(level) in item_mgr.items:
            item_mgr.items[str(level)].append(new_item)
        else:
            item_mgr.items[str(level)] = [new_item]
        # Save after processing every 25 documents.
        if item_mgr.cnt > 0 and item_mgr.cnt % 25 == 0:
            item_mgr.save()
    item.generated_next = True
    # Clear page source and next level links to save memory.
    item.page_source = None
    item.next_level_links = None


def process(items, levels, current_level):
    """Main crawler function.
    
    This function is recursive.  It calls itself repeatedly
    until the desired depth (levels) is reached.
    
    Processing involves:
    1. Exporting page out to png/pdf/download file.
    2. Search html page source for next level hyperlinks.
    3. Recurse process for next level if needed.
    
    @param items: A list of Items to process.
    @param levels: The depth of the items to process.
    @param current_level: The current level.
    
    """
    global parent_output_dir
    global dry_run, export_to_pdf, logfile
    global item_mgr, windows_filenames
    global script_args
    if not items:
        return
    if levels < current_level:
        return
    if levels > current_level:
        generate_next = True
    else:
        generate_next = False
    
    # Process each item and generate next level.
    for item in items:
        if not item.processed:
            ###################################################################
            # Exporting Stage - export page as png or download associated file.
            ###################################################################
            log('INFO',logfile,str(item))
            # Build the file name for the output file.
            filename = item.url.split('https://')[-1]
            filename = re.sub(r'[^a-z.A-Z0-9]','.-',filename.split('http://')[-1])
            if windows_filenames:
                if len(filename) > 255:
                    # Strip out some characters from filename.
                    filename = filename[:50] +'__'+ filename[-50:]
            png_filename = filename + '_%s.png' % item_mgr.cnt
            pdf_filename = filename + '_%s.pdf' % item_mgr.cnt
            html_filename = filename + '_%s.html' % item_mgr.cnt
            if export_to_pdf:
                exp_filename = pdf_filename
            else:
                exp_filename = png_filename
            if not script_args.get('only-downloadable'):
                log('INFO',logfile,'Getting snapshot of page %s...' % item.url)
                if not dry_run:
                    get_page_as_file(item, exp_filename, parent_output_dir, current_level)
            if script_args.get('get-source'):
                log('INFO',logfile,'Getting HTML source of page %s...' % item.url)
                if not dry_run:
                    get_page_as_source(item, html_filename, parent_output_dir, current_level)
            time.sleep(0.3)
            item.processed = True
            item_mgr.cnt += 1
            # Move any downloads to output level directory.
            move_files(os.path.join(parent_output_dir,'main'),
                       os.path.join(parent_output_dir,str(current_level)))
            # Save after processing every 25 documents.
            if item_mgr.cnt > 0 and item_mgr.cnt % 25 == 0:
                item_mgr.save()
        # Get next level urls if needed.
        if generate_next and not item.generated_next:
            get_items(item, level=(current_level + 1))
        # Erase page source and next level links after processing to save memory.
        item.page_source = None
        item.next_level_links = None
    
    if levels == current_level:
        return
    
    time.sleep(0.2)
    # Recursively call process for next level items.
    next_level_items = item_mgr.items.get(str(current_level + 1),[])
    process(next_level_items, levels, current_level + 1)


def init_logfile(logfile):
    """Initializes logfile if needed.
    
    @param logfile: The absolute filename of the logfile.
    
    """
    # extract directory
    logdir = os.sep.join(logfile.split(os.sep)[:-1])
    # create files if they don't exist
    if not os.path.isdir(logdir):
        os.makedirs(logdir, 0777)
    if not os.path.isfile(logfile):
        open(logfile, 'a').close()
        os.chmod(logfile, 0666)


def log(logtype, logfile, message, print_stdout=True, TAG=None):
    """Log message to a log file.
    
    @param logtype: [INFO|ERROR] The message type.
    @param logfile: The logfile to print to.
    @param message: A string to print to the log.
    @keyword print_stdout: If True, message will be printed to stdout,
            unless logtype is 'ERROR', then the message will be printed
            to stderr (default=True).
    @keyword TAG: TAG directly prefixed to message, but after standard
            headers.
    
    """
    ct = time.time()
    msecs = (ct - long(ct)) * 1000
    t = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    date = "%s,%03d" % (t, msecs)
    
    prefix = '%s %s PID[%s]: ' % \
        (date, logtype, os.getpid())
    
    # Clean message
    logtxt = message.strip()
    # Add TAG if necessary.
    if TAG:
        logtxt = re.sub('^', str(TAG) + ': ', logtxt)
    # Add prefix to start of message.
    logtxt = re.sub('^', str(prefix), logtxt)
    logtxt = re.sub('\r\n', os.linesep + str(prefix), logtxt)
    logtxt = re.sub('\n', os.linesep + str(prefix), logtxt)
    logtxt = re.sub('\r', '\r' + str(prefix), logtxt)
    
    with open(logfile, 'a') as f:
        f.write(logtxt.rstrip() + os.linesep)
    
    if print_stdout:
        if logtype == 'ERROR':
            print >>sys.stderr, message
        else:
            print message


###############################################################################
# Main.
###############################################################################
def usage():
    """Print usage info."""
    program_name = os.path.basename(sys.argv[0])
    print 'Usage: %s <options>...' % program_name
    print dedent('''
    Required argument(s):
      -s <START_URL>, --start-url=<START_URL>
            The starting URL of the website to crawl.
            Eg: -s https://www.yahoo.com
      -a <ALLOWED_DOMAINS>, --allowed-domains=<ALLOWED_DOMAINS>
            Comma separated list of domains to allow crawling.
            NOTE: Only use the top level domain for this, if sub-domain
            filtering is desired, see -b <SUB_URL> option.
            Eg: -a yahoo.com
      -o <OUTPUT_DIR>, --output-dir=<OUTPUT_DIR>
            The output directory to save all exports.
            Eg: -o C:\\crawler\\site1
    
    Optional argument(s):
      -b <SUB_URLS>, --sub-urls=<SUB_URLS>
            Comma separated list of strings that must appear on the URL.
            Eg: -b campaigns.corp
            This means "campaigns.corp" must appear to in URL before that
            page is processed. URLs that look like subdomain.crawler-test.com will
            not be processed because it does not contain "campaigns.corp".
      -l <LEVELS>, --levels=<LEVELS>
            The number of levels to dive into website.
      -c <COOKIE_FILE>, --cookies=<COOKIE_FILE>
            The cookies file to load.
      --dry-run
            Lists out all the hyperlinks, and does not actually export
            or converts any pages.
      --export-to-pdf
            Exports screenshots of web pages to pdf format (default: png).
      --chrome
            Use chrome as the webdriver (default: firefox)
      --only-downloadable
            Does not collect screenshots, but only downloadable files.
            NOTE: "downloadable" here means if a URL is a link to a file
            that should be downloaded. (Eg: pdf, xls, doc).
      --get-source
            Collects the HTML source.
      --search-result-links
            Searches for links with class "search-result-link visitable"
      --windows-filenames
            Limits absolute filenames to 255 chars.
      -h, --help
            Displays this help screen.
    ''')


def handle_args():
    """Handle script's command line script_args."""
    global script_args
    
    try:
        opts, args = getopt.getopt(sys.argv[1:], 's:a:b:o:l:c:h',
                                   ['start-url=','allowed-domains=','output-dir'
                                    'sub-urls=','levels=','cookies=',
                                    'dry-run','export-to-pdf','chrome',
                                    'only-downloadable','get-source','search-result-links',
                                    'windows-filenames',
                                    'help','debug'])
    except getopt.GetoptError as e:
        # Print usage info and exit.
        print str(e)
        usage()
        sys.exit(2)
    
    for o, a in opts:
        if o == '-l' or o == '--levels':
            script_args['levels'] = a
        elif o == '-s' or o == '--start-url':
            script_args['start-url'] = a
        elif o == '-a' or o == '--allowed-domains':
            script_args['allowed-domains'] = a
        elif o == '-o' or o == '--output-dir':
            script_args['output-dir'] = a
        elif o == '-c' or o == '--cookies':
            script_args['cookies'] = a
        elif o == '-b' or o == '--sub-urls':
            script_args['sub-urls'] = a
        elif o == '-h' or o == '--help':
            script_args['help'] = a
        elif o == '--dry-run':
            script_args['dry-run'] = True
        elif o == '--export-to-pdf':
            script_args['export-to-pdf'] = True
        elif o == '--chrome':
            script_args['chrome'] = True
        elif o == '--only-downloadable':
            script_args['only-downloadable'] = True
        elif o == '--search-result-links':
            script_args['search-result-links'] = True
        elif o == '--windows-filenames':
            script_args['windows-filenames'] = True
        elif o == '--get-source':
            script_args['get-source'] = True
        elif o == '--debug':
            script_args['debug'] = True
        else:
            assert False, 'Unhandled option %s' % o
    
    # Check for help.
    if 'help' in script_args:
        usage()
        sys.exit(0)
    # Check if required arguments are set.
    if ('start-url' not in script_args or
        'allowed-domains' not in script_args or
        'output-dir' not in script_args):
        print >>sys.stderr, 'ERROR: Missing argument(s).'
        usage()
        sys.exit(2)


def main():
    global script_args, logfile
    global start_url, allowed_domains, sub_urls
    global browser, browser_profile, browser_type
    global parent_output_dir, dry_run, export_to_pdf
    global search_result_links, windows_filenames
    global item_mgr
    handle_args()
    
    # Set globals.
    levels = int(script_args.get('levels', 0))
    dry_run = script_args.get('dry-run', False)
    export_to_pdf = script_args.get('export-to-pdf', False)
    search_result_links = script_args.get('search-result-links', False)
    windows_filenames = script_args.get('windows-filenames', False)
    start_url = script_args['start-url']
    allowed_domains = script_args['allowed-domains'].split(',')
    parent_output_dir = script_args['output-dir']
    try:
        sub_urls = script_args['sub-urls'].split(',')
    except Exception:
        sub_urls = []
    
    # Initialize logfile.
    logfile = os.path.join(parent_output_dir,'crawler.log')
    init_logfile(logfile)
    
    log('INFO',logfile,'======= Processing =========',print_stdout=True)
    log('INFO',logfile,'URL=%s' % start_url,print_stdout=True)
    log('INFO',logfile,'Allowed domain=%s' % allowed_domains,print_stdout=True)
    log('INFO',logfile,'Constrained sub-domains=%s' % sub_urls,print_stdout=True)
    log('INFO',logfile,'Number of levels=%s' % levels,print_stdout=True)
    log('INFO',logfile,'============================',print_stdout=True)
    
    # Create main and validation folders.
    main_download_dir = os.path.join(parent_output_dir,'main')
    if not os.path.isdir(main_download_dir):
        os.makedirs(main_download_dir, 0777)
    
    # Initialize browser profiles.
    # The profile loaded are mainly used to save files automatically without
    # human intervention.
    log('INFO',logfile,'Loading browser...')
    if script_args.get('chrome'):
        browser_type = BrowserType.CHROME
        main_profile = BrowserMgr.get_new_browser_profile(download_dir=main_download_dir,
                                                          browser_type=browser_type)
        browser = webdriver.Chrome(chrome_options=main_profile)
    else:
        browser_type = BrowserType.FIREFOX
        main_profile = BrowserMgr.get_new_browser_profile(download_dir=main_download_dir)
        browser = webdriver.Firefox(firefox_profile=main_profile)
    
    browser.get(start_url)
    time.sleep(60)
    
    # Load cookies if applicable.
    if script_args.get('cookies'):
        log('INFO',logfile,'Loading cookies into browser...')
        cookies = pickle.load(open(script_args.get('cookies'),'rb'))
        for cookie in cookies:
            browser.add_cookie(cookie)
        if cookies:
            # Re-load the page so the cookies will take effect.
            browser.get(start_url)
            time.sleep(0.5)
    
    # Create Item Manager and reference it's attributes.
    item_mgr = ItemMgr(output_dir=parent_output_dir)
    
    # Check for saved files to load.
    item_mgr.load()
    
    current_level = 0
    if str(current_level) in item_mgr.items:
        item = item_mgr.items[str(current_level)][0]
        if item.url != browser.current_url.rstrip('/'):
            msg = ('Loaded level %s item.url (%s) does not match browser.current_url (%s).' %
                   (current_level,item.url,browser.current_url.rstrip('/')))
            log('ERROR', logfile, msg)
            raise Exception(msg)
    else:
        item = Item()
        item.url = browser.current_url.rstrip('/')
        item_mgr.items[str(current_level)] = [item]
        item_mgr.dup_urls[item.url] = {item.onclick_id:{'cnt':0,'sec_cnt':0}}
    item.page_source = browser.page_source
    item.level = current_level
    item.text = 'START URL'
    ###########################################################
    # Begin processing.
    ###########################################################
    try:
        process([item], levels, current_level)
    except Exception:
        log('ERROR',logfile,'\nERROR DETECTED: RESULTS MAY NOT BE COMPLETE!!!')
        log('ERROR',logfile,traceback.format_exc())
        raise
    finally:
        browser.close()
        ###########################################################
        # Save progess and print results.
        ###########################################################
        item_mgr.save()
        item_mgr.print_results()


if __name__ == '__main__':
    main()

