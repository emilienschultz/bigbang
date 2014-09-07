import urllib2
import urllib
import gzip
import re
import os
import parse
import urlparse
import logging
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
import email
import email.parser
import mailbox
import time
import mailman

class W3cMailingListArchivesParser(email.parser.Parser):
  parse = None
  # doesn't yet implement the file version
  
  # takes the full HTML of a single message page; returns an email Message
  # currently returns an mboxMessage, with appropriate From separator line
  # TODO: parse To, CC (Archived-At?, others?) headers
  # TODO: support headersonly option
  def parsestr(self, text, headersonly=None):
    soup = BeautifulSoup(text)
    body = unicode(soup.select('#body')[0].get_text()).encode('utf-8')
    msg = MIMEText(body,'plain','utf-8')
    
    from_text = self._parse_dfn_header(unicode(soup.select('#from')[0].get_text()).encode('utf-8'))
    from_name = from_text.split('<')[0].strip()
    from_address = unicode(soup.select('#from a')[0].get_text()).encode('utf-8')
    
    from_addr = email.utils.formataddr((from_name, from_address))
    msg['From'] = from_addr
    
    subject = unicode(soup.select('h1')[0].get_text()).encode('utf-8')
    msg['Subject'] = subject
    
    message_id = self._parse_dfn_header(unicode(soup.select('#message-id')[0].get_text().strip()).encode('utf-8'))
    msg['Message-ID'] = message_id.strip()
    
    message_date = self._parse_dfn_header(unicode(soup.select('#date')[0].get_text().strip()).encode('utf-8'))
    msg['Date'] = message_date.strip()
    
    mbox_message = mailbox.mboxMessage(msg)
    mbox_message.set_from(from_address, email.utils.parsedate(message_date))
    
    return mbox_message
    
  def _parse_dfn_header(self, header_text):
    return header_text.split(':',1)[1]

def collect_from_url(url,base_arch_dir="archives"):
    list_name = mailman.get_list_name(url)
    logging.info("Getting W3C list archive for %s" % list_name)

    response = urllib2.urlopen(url)
    html = response.read()    
    soup = BeautifulSoup(html)

    time_period_indices = list()
    rows = soup.select('tbody tr')
    for row in rows:
      link = row.select('td:nth-of-type(1) a')[0].get('href')
      logging.info("Found time period archive page: %s" % link)
      time_period_indices.append(link)

    # directory for downloaded files
    arc_dir = mailman.archive_directory(base_arch_dir,list_name)
    
    for link in time_period_indices:
      link_url = urlparse.urljoin(url, link)
      response = urllib2.urlopen(link_url)
      html = response.read()    
      soup = BeautifulSoup(html)
      
      message_links = list()
      messages = list()
      
      anchors = soup.select('div.messages-list a')
      for anchor in anchors:
        if anchor.get('href'):
          message_url = urlparse.urljoin(link_url, anchor.get('href'))
          message_links.append(message_url)
      
      for message_link in message_links:
        response = urllib2.urlopen(message_link)
        html = response.read()    
        
        message = W3cMailingListArchivesParser().parsestr(html)
        messages.append(message)
        time.sleep(1) # wait between loading messages, for politeness
      
      year_month_mbox = time.strftime('%Y-%m', email.utils.parsedate(messages[0]['Date'])) + '.mbox'
      mbox_path = os.path.join(arc_dir, year_month_mbox)
      mbox = mailbox.mbox(mbox_path)
      mbox.lock()
      
      try:
        for message in messages:
          mbox.add(message)
        mbox.flush()
      finally:
        mbox.unlock()
      
      logging.info('Saved ' + year_month_mbox)