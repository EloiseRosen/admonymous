import re
import string
import base_dir
import os
import logging
from google.appengine.api import mail
from google.appengine.ext.webapp import template

class EmailMessage(mail.EmailMessage):
  
  def render_and_send(self, template_name, additional_template_values):
    DEBUG = os.environ['SERVER_SOFTWARE'].startswith('Dev')
    template_values = {
      'full_width':620,
      'link_style':'style="text-decoration:none;color:#000099;"',
    }
    template_values.update(additional_template_values)
    template_values['host_url'] = ('http://localhost:8080' if DEBUG else 'https://www.admonymous.co')
    path_html = os.path.join(base_dir.base_dir(), 'templates', '_email', template_name+'.html')
    path_txt = os.path.join(base_dir.base_dir(), 'templates', '_email', template_name+'.txt')
    self.html = template.render(path_html, template_values, debug=False)
    self.body = template.render(path_txt, template_values, debug=False)
    if DEBUG:
      logging.info("""
      
      HTML Version:
      
      %s
      
      TXT Version:
      
      %s
      
      """ % (self.html, self.body))
    else:
      self.send()
      
  def render(self, template_name, additional_template_values):
    DEBUG = os.environ['SERVER_SOFTWARE'].startswith('Dev')
    template_values = {
      'full_width':620,
      'link_style':'style="text-decoration:none;color:#000099;"',
    }
    template_values.update(additional_template_values)
    template_values['host_url'] = ('http://localhost:8080' if DEBUG else 'https://www.admonymous.co')
    path_html = os.path.join(base_dir.base_dir(), 'templates', '_email', template_name+'.html')
    path_txt = os.path.join(base_dir.base_dir(), 'templates', '_email', template_name+'.txt')
    return {'html':template.render(path_html, template_values, debug=False), 'txt':template.render(path_txt, template_values, debug=False)}

def rot_13_encrypt(line):
  """Rotate 13 encryption"""
  rot_13_trans = string.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz','NOPQRSTUVWXYZABCDEFGHIJKLMnopqrstuvwxyzabcdefghijklm')
  line = line.translate(rot_13_trans)
  line = re.sub('(?=[\\"])', r'\\', line)
  line = re.sub('\n', r'\n', line)
  line = re.sub('@', r'\\100', line)
  line = re.sub('\.', r'\\056', line)
  line = re.sub('/', r'\\057', line)
  return line

def js_obfuscated_text(text):
  "ROT 13 encryption embedded in Javascript code to decrypt in the browser."
  return """<script type="text/javascript">document.write(
"%s".replace(/[a-zA-Z]/g, function(c){return String.fromCharCode((c<="Z"?90:122)>=(c=c.charCodeAt(0)+13)?c:c-26);})
);
</script>""" % rot_13_encrypt(text)

def js_obfuscated_mailto(email, displayname=None):
  "ROT 13 encryption within an Anchor tag w/ a mailto: attribute"
  if not displayname:
      displayname = email
  return js_obfuscated_text("""<a href="mailto:%s">%s</a>""" % (
      email, displayname
  ))
