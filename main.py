#!/usr/bin/env python

from helpers import email
from google.appengine.ext import webapp, db
from google.appengine.ext.webapp import util, template
from google.appengine.api import users
import datetime

PER_PAGE = 10
MAX_PER_PAGE = 100

class User(db.Model):
  username = db.StringProperty()
  name = db.StringProperty()
  google_account = db.UserProperty(auto_current_user_add=True)
  create_date = db.DateTimeProperty(auto_now_add=True)
  update_date = db.DateTimeProperty(auto_now=True)
  # image = db.BlobProperty
  
class Response(db.Model):
  user = db.ReferenceProperty(User)
  create_date = db.DateTimeProperty(auto_now_add=True)
  body = db.TextProperty()
  author = db.StringProperty()
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
    google_account = users.get_current_user()
    if google_account:
      user = User.all().filter('google_account', google_account).get()
      if not user:
        user = User()
      template_values = {
        'user':user,
        'logout_url':users.create_logout_url('/')
      }
      per_page = get_bounded_int_value(self.request.get('per_page'), PER_PAGE, 1, MAX_PER_PAGE)
      offset = get_bounded_int_value(self.request.get('offset'), 0, 0)
      responses = Response.all().filter('user', user).order('-create_date').fetch(limit=per_page+1, offset=offset) if user.is_saved() else []
      if offset > 0:
        template_values['older_offset'] = max(0, offset - per_page)
      if len(responses) == per_page+1:
        responses.pop()
        template_values['newer_offset'] = offset + per_page
      template_values['responses'] = responses
    else:
      template_values = {'login_url':users.create_login_url('/')}
    path = 'templates/home.html'
    page = template.render(path, template_values, debug=(True if 'local' in self.request.host_url or users.is_current_user_admin() else False))
    self.response.out.write(page)

  def post(self):
    google_account = users.get_current_user()
    if google_account:
      user = User.all().filter('google_account', google_account).get()
      user_with_username_key = User.all(keys_only=True).filter('username', self.request.get('username')).get()
      if user:
        username_taken = True if user_with_username_key != None and user_with_username_key != user.key() else False
      else:
        username_taken = True if user_with_username_key != None else False
        user = User()
      if not username_taken:
        if user.username:
          success = True
        else:
          success = None
        user.username = self.request.get('username')
      else:
        success = False
      user.name = self.request.get('name')
      user.put()
      template_values = {
        'user':user,
        'success':success,
        'username_taken':self.request.get('username') if username_taken else False,
        'logout_url':users.create_logout_url('/')
      }
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
    page = template.render(path, template_values, debug=(True if 'local' in self.request.host_url or users.is_current_user_admin() else False))
    self.response.out.write(page)

class UserPageHandler(webapp.RequestHandler):
  def get(self, username):
    target_user = User.all().filter('username', username).get()
    template_values = {
      'target_user':target_user, 
      'user':User.all().filter('google_account', users.get_current_user()).get(), 
      'logout_url':users.create_logout_url('/'), 
      'login_url':users.create_login_url('/')
    }
    path = 'templates/user.html'
    page = template.render(path, template_values, debug=(True if 'local' in self.request.host_url or users.is_current_user_admin() else False))
    self.response.out.write(page)
    
  def post(self, username):
    from helpers.textile import textile
    target_user = User.all().filter('username', username).get()
    template_values = {
      'target_user':target_user, 
      'user':User.all().filter('google_account', users.get_current_user()).get(), 
      'logout_url':users.create_logout_url('/'), 
      'login_url':users.create_login_url('/'),
      'success':True
    }
    author=self.request.get('author')
    body = self.request.get('body')
    response = Response(body=textile.textile(body), author=author, user=target_user, revealed=True)
    response.put()
    notification = email.EmailMessage(sender='Admonymous <notify@admonymous.com>', to=target_user.google_account.email(), subject='%s left you a response on Admonymous' % ('Someone' if not author else author))
    notification.render_and_send('notification', {
      'target_user':target_user,
      'author':None if author == 'anonymous' else author,
      'body_html':response.body,
      'body_txt':body
    })
    path = 'templates/user.html'
    page = template.render(path, template_values, debug=(True if 'local' in self.request.host_url or users.is_current_user_admin() else False))
    self.response.out.write(page)
    
class PrintablePageHandler(webapp.RequestHandler):
  def get(self):
    google_account = users.get_current_user()
    if google_account:
      user = User.all().filter('google_account', google_account).get()
      if not user:
        self.redirect('/')
      template_values = {'user':user}
    else:
      self.redirect('/')
    path = 'templates/print.html'
    page = template.render(path, template_values, debug=(True if 'local' in self.request.host_url or users.is_current_user_admin() else False))
    self.response.out.write(page)
    
class DeleteUserHandler(webapp.RequestHandler):
  def get(self):
    google_account = users.get_current_user()
    if google_account:
      user = User.all().filter('google_account', google_account).get()
      if not user:
        self.redirect('/')
      for r in user.response_set:
        r.delete() 
      user.delete()
      self.redirect('/')
    else:
      self.redirect('/')

def main():
    application = webapp.WSGIApplication([('/', HomeHandler), 
                                          ('/print', PrintablePageHandler),
                                          ('/delete_username', DeleteUserHandler),
                                          ('/([0-9a-zA-Z_\-]+)', UserPageHandler)],
                                         debug=True)
    util.run_wsgi_app(application)


if __name__ == '__main__':
    main()
