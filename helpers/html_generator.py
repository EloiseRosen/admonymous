#!/usr/bin/env python
# encoding: utf-8
"""
html_generator.py

Created by Nevin Freeman on 2009-04-24.
Copyright (c) 2009 RIABiz. All rights reserved.
"""

from helpers.textile import textile
import re
import logging
import string
import unicodedata

# HCOUNT = 1
# QUOTES_DICT= { 0x2018:0x27, 0x2019:0x27, 0x201C:0x22, 0x201D:0x22 } <-- probably don't need this.

def de_microsoft_wordify(text):
  text = re.sub('&#8220;', '"', text)
  text = re.sub('&#8221;', '"', text)
  text = re.sub('&#8216;', "'", text)
  text = re.sub('&#8217;', "'", text)
  text = re.sub('&#8260;', '/', text)
  text = re.sub('&#8211;', '--', text)
  return text

def slugify(inStr, spacechar='-'):
  removelist = ["a", "an", "as", "at", "before", "but", "by", "for","from","is", "in", "into", "like", "of", "off", "on", "onto","per","since", "than", "the", "this", "that", "to", "up", "via","with"];
  import re
  for a in removelist:
    aslug = re.sub(r'\b'+a+r'\b','',inStr)
  aslug = re.sub('[^\w\s-]', '', aslug).strip().lower()
  aslug = re.sub('\s+', spacechar, aslug)
  return aslug

def title_html_character_fix(text):
  text = re.sub('&[\s]', '&amp; ', text)
  text = re.sub('\"', '&quot;', text)
  text = re.sub('\'', '&#39;', text)
  text = re.sub('<', '&lt;', text)
  text = re.sub('>', '&gt;', text)
  text = re.sub('&amp;#', '&#', text)
  text = re.sub('&amp;quot;', '&quot;', text)
  return text
  
def title_escaped_quotes_character_fix(text):
  text = re.sub('\"', '\\\"', text)
  text = re.sub('\'', '\\\'', text)
  text = re.sub('&amp;#39;', '\\\'', text)
  text = re.sub('&amp;quot;', '\\\"', text)
  return text

def scrub_characters(text):
  return unicodedata.normalize('NFKD', unicode(text)).encode('ascii','xmlcharrefreplace')
  
def safe_html(text):
  text = re.sub('&(?!amp;)', '&amp;', text)
  text = scrub_characters(text)
  return textile.textile(text)

def generate_body_parts(body, article_id):
  """generates body html from textile string"""
  # safe_body = body.translate(QUOTES_DICT).encode('ascii', 'xmlcharrefreplace') <-- probably don't need this
  # body = re.sub('&(?!amp;)', '&amp;', body)
  html = safe_html(body)
  # html = textile.textile(body)
  if '<jump>' in html:
    if '<p><jump></p>' in html:
      logging.debug('___<jump> is included on it\'s own line')
      html = re.sub('<p><jump></p>', '<span id="jump"></span>', html) # re.sub('<h2>', sub_incrimentally(article_id), html)
    elif '<p><jump>' in html:
      logging.debug('___<jump> is included at the beginning of a paragraph')
      html = re.sub('<p><jump>', '<span id="jump"></span><p>', html) # re.sub('<h2>', sub_incrimentally(article_id), html)
    elif '<jump></p>' in html:
      logging.debug('___<jump> is included at the end of a paragraph')
      html = re.sub('<jump></p>', '</p><span id="jump"></span>', html) # re.sub('<h2>', sub_incrimentally(article_id), html)
    else:
      logging.debug('___<jump> is included in the middle of a paragraph')
      html = re.sub('<jump>', '</p><span id="jump"></span>', html) # re.sub('<h2>', sub_incrimentally(article_id), html)
  else:
    logging.debug('___<jump> NOT included, inserting it')
    html_array = re.split('(\n\n\t)', html)
    jump_index = 0
    paragraphs = 0
    for group in html_array:
      if paragraphs < 4:
        jump_index += 1
        if '<p>' in group:
          paragraphs += 1
    html_array.insert(jump_index, '<span id="jump"></span>')
    html = ''.join(html_array)
    # logging.info(str(html_array))
    # logging.debug('jump_index: '+str(jump_index))
  result = html.partition('<span id="jump"></span>')
  if result[2] == '':
    rsult = [None, '', result[0]]
  return result
  
def generate_feed_body(html):
  return re.sub('<p>', '', re.sub('</p>', '', re.sub('<span id="jump"></span>', '', re.sub('h2', 'h4', html))))

# def sub_incrimentally(article_id):
#   """assign an id incrimentally to the given heading"""
#   global HCOUNT
#   header_with_id = '<h2 id="subhead_'+str(HCOUNT)+'_'+str(article_id)+'">'
#   HCOUNT += 1
#   return header_with_id
  
# def generate_subhead_list(html):
#   """creates list of headings"""
#   subheads = []
#   for h2 in re.findall('<h2 id="(?P<id>.*)">(?P<text>.*)</h2>', html):
#     subheads.append(h2[1])
#   return subheads
  
# def generate_teaser(html):
#   """generates a teaser by extracting only the text that appears before the <jump>"""
#   if string.find(html, '<span id="jump"></span>') == -1:
#     return None
#   else:
#     return html.partition('<span id="jump"></span>')[0]
