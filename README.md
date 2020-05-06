# crawler
Crawls into a website and collects pages. It can traverse the site to specified n levels deep and stops.

## How To Set Up Environment To Run Crawler
Must have either Firefox or Chrome browser installed.

For Windows:
1. Download and install latest Python 2.7 (not version 3)
   a. Go to https://www.python.org/downloads
   b. Install 32 or 64 bit depending on your system
   c. During set up, when you get to the screen that says "Customize Python..."
        Look for the option: "Add python.exe to Path",
        Change selection to -> "Entire feature will be installed on local hard drive".
2. Install MS C++ Compiler for Python 2.7 http://www.microsoft.com/en-us/download/confirmation.aspx?id=44266
3. Install python modules: pdfkit, beautifulsoup4, selenium, tld
   a. Open Windows command prompt and execute the following pip command.
```sh
$ pip install pdfkit beautifulsoup4 selenium tld Pillow
```

## How To Obtain and Install the Crawler.

If you received the crawler as a zip archive:
1. Place the folder somewhere on the hard drive (eg: C:\crawler).
   a. Check to make sure it contains chromedriver.exe and geckodriver.exe.
   b. Unzip the geckodriver*.zip for 32bit or 64bit depending on your system.


If you did not receive the crawler as a zip archive:
Follow these instructions to download latest source (must have access to repository).
1. Install git (git for Windows if on a Windows system).
2. Pull down source.  Eg:
```sh
$ git clone https://github.com/dcheun/crawler.git
```

3. Download the latest chromedriver and put the executable inside the same folder as the
   crawler.py script. This is needed if using Chrome as the crawler browser.
4. Download the latest geckodriver (32bit or 64bit depending on your system). Put it in
   the same folder as the crawler.py script. This is needed if using Firefox as the crawler browser.

## How To Run The Crawler.
NOTE: Everything is run through the command line.

To run script:
1. Change directory to the location of the script.  Eg:
```sh
$ cd C:\crawler
```
2. The main script is: crawler.py
   There are three required arguments: START_URL, ALLOWED_DOMAINS, and OUTPUT_DIR.
   Use the -h option for a help screen.
```sh
$ python crawler.py -h
```
   The syntax is: python crawler.py <options>...
   Example for crawling test website:
```sh
$ python crawler.py -s https://www.crawler-test.com -a crawler-test.com -o C:\crawler-test -l 1
```
   Explanation:
   -s argument specifies the starting URL.
   -a argument specifies the allowed domain(s).  Please only use the top level domain here.
      For sub-domain filtering, see -b option in help screen.
   -o argument specifies the output directory to save all exports.  The crawler will save exports to
      web pages to this output directory under a subfolder corresponding to its level.
   -l argument specifies how many levels of links to dive into website.  In this case, we specified 1.

3. Once the crawler starts running, monitor the process.  By default, the crawler uses Firefox as the
   browser to crawl with.  To specify Chrome, use the "--chrome" command line option. See the help page
   for more info. Eg:
```sh
$ python crawler.py -s http://www.crawler-test.com -a crawler-test.com -o C:\crawler-test -l 1 --chrome
```

NOTE 1: When the browser is first launched, it opens the starting URL, and waits 60 secs before starting collection.
        This wait time is used to input any login credentials required to access the website.

NOTE 2: If the Website gives a popup window for the user to enter credentials, then in general the
        browser windows that the crawler launches will wait for the dialog box to be dismissed before
        continuing.


## How To Run Crawler with Special Parameters.

1. The "--get-source" collects the HTML page source, which is useful to have in some cases.
```sh
$ python crawler.py -s http://www.crawler-test.com -a crawler-test.com -o C:\crawler-test -l 1 --get-source
```
2. Check the help page for even more parameters.

