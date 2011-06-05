#!/usr/bin/env python
#
# Copyright 2007 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
from google.appengine.ext import webapp, db
from google.appengine.ext.webapp import util
from google.appengine.api import users
import datetime

PER_PAGE = 10
MAX_PER_PAGE = 100

class User(db.Model):
  username = db.StringProperty
  name = db.StringProperty
  user = db.UserProperty
  create_date = db.DateTimeProperty(auto_now_add=True)
  update_date = db.DateTimeProperty(auto_now=True)
  image = db.BlobProperty
  
class Response(db.Model):
  user = db.ReferenceProperty(User)
  create_date = db.DateTimeProperty(auto_now_add=True)
  body = db.TextProperty
  author = db.StringProperty
  reveal_datetime = db.DateTimeProperty(default=datetime.datetime.now())
  revealed = db.BooleanProperty(default=False)

def get_bounded_int_value(s, default, lower_bound = None, upper_bound = None):
  if s:
    try:
      value = int(s)
      if lower_bound and value < lower_bound:
        value = lower_bound
      if upper_bound and value > upper_bound:
        value = upper_bound
    except ValueError:
      value = default
  else:
    value = default
  return value

class HomeHandler(webapp.RequestHandler):
  def get(self):
    user = users.get_current_user()
    if user:
      template_values = {'user':user}
      per_page = get_bounded_int_value(self.request.get('per_page'), PER_PAGE, 1, MAX_PER_PAGE)
      offset = get_bounded_int_value(self.request.get('offset'), 0, 0)
      responses = Response.all().filter('user', user).order('-create_date').fetch(limit=per_page+1, offset=offset)
      if offset > 0:
        template_values['older_offset'] = max(0, offset - per_page)
      if len(responses) == per_page+1:
        responses.pop()
        template_values['newer_offset'] = offset + per_page
      template_values['responses'] = responses
    else:
      template_values = {'login_url':users.create_login_url()}
    path = 'templates/home.html'
    page = template.render(path, template_values, debug=(True if self.request.host_url == 'http://localhost:8081' or user_is_admin else False))
    self.response.out.write(page)

class UserPageHandler(webapp.RequestHandler):
  def get(self, username):
    pass
    
class PrintablePageHandler(webapp.RequestHandler):
  def get(self, username):
    pass

def main():
    application = webapp.WSGIApplication([('.*', HomeHandler), 
                                          ('/([0-9a-zA-Z_\-]+)', UserPageHandler),
                                          ('/([0-9a-zA-Z_\-]+)/print', PrintablePageHandler)],
                                         debug=True)
    util.run_wsgi_app(application)


if __name__ == '__main__':
    main()
