#!/usr/bin/env python

from helpers import email
from google.appengine.ext import webapp, db
from google.appengine.ext.webapp import util, template
from google.appengine.api import users
import datetime, urllib, logging

from django.utils import encoding

PER_PAGE = 10
MAX_PER_PAGE = 100

# def redirect(handler_method):
#   def redirect_if_needed(self, *args, **kwargs):
#     if 'www' not in self.request.referrer and 'admonymous' in self.request.referrer:
#       try:
#         self.redirect(re.sub('admonymous.co', 'www.admonymous.co', self.request.referrer))
#       except:
#         handler_method(self, *args, **kwargs)
#     else:
#       handler_method(self, *args, **kwargs)
#   return redirect_if_needed

class User(db.Model):
  username = db.StringProperty()
  name = db.StringProperty()
  google_account = db.UserProperty(auto_current_user_add=True)
  create_date = db.DateTimeProperty(auto_now_add=True)
  update_date = db.DateTimeProperty(auto_now=True)
  message = db.TextProperty()
  # image = db.BlobProperty
  
  def message_html(self):
    from helpers.textile import textile
    return textile.textile(self.message)

  @classmethod
  def get_current(cls):
    google_account = users.get_current_user()
    if not google_account:
      return
    user = cls.all().filter('google_account', google_account).get()
    return user
  
  def first_name(self):
    import re
    return re.split(self.name, ' ')[0]

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
  # @redirect
  def get(self):
    google_account = users.get_current_user()
    if google_account:
      user = User.all().filter('google_account', google_account).get()
      if not user:
        user = User()
      template_values = {
        'user':user,
      }
      per_page = get_bounded_int_value(self.request.get('per_page'), PER_PAGE, 1, MAX_PER_PAGE)
      offset = get_bounded_int_value(self.request.get('offset'), 0, 0)
      responses = Response.all().filter('user', user).order('-create_date').fetch(limit=per_page+1, offset=offset) if user.is_saved() else []
      if offset > 0:
        template_values['older_offset'] = max(0, offset - per_page)
      if len(responses) == per_page+1:
        responses.pop()
        template_values['newer_offset'] = offset + per_page
      for response in responses:
          response.response_id = response.key().id()
      template_values['responses'] = responses
    else:
      template_values = {}
    path = 'templates/home.html'
    page = template.render(path, template_values, debug=(True if 'local' in self.request.host_url or users.is_current_user_admin() else False))
    self.response.out.write(page)

  def post(self):
    
    def namify(inStr, spacechar='_'):
      import re
      aslug = re.sub('[^\w\s-]', '', inStr).strip().lower()
      aslug = re.sub('\s+', spacechar, aslug)
      return aslug
    
    google_account = users.get_current_user()
    if google_account:
      user = User.all().filter('google_account', google_account).get()
      username = namify(self.request.get('username'))
      user_with_username_key = User.all(keys_only=True).filter('username', username).get()
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
        user.username = username
      else:
        success = False
      user.name = self.request.get('name')
      user.message = self.request.get('message')
      user.put()
      template_values = {
        'user':user,
        'success':success,
        'username_taken':username if username_taken else False,
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
    if (username == 'admonymous') and not target_user:
      admonymous_user = User(username = 'admonymous',
                             name = 'Admonymous',
                             google_account = None)
      admonymous_user.put()
      target_user = admonymous_user
    template_values = {
      'target_user':target_user,
      'target_user_first_name':target_user.first_name,
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
    if self.request.get('email') != '':
      notification = email.EmailMessage(sender='Admonymous <notifications@admonymous.co>', to='eloise.rosen@gmail.com', subject='BOT left someone a response on Admonymous')
      notification.render_and_send('notification', {
        'target_user':target_user,
        'author':None if author == 'anonymous' else author,
        'body_html':response.body,
        'body_txt':body
      })
    else:
      response = Response(body=encoding.force_unicode(textile.textile(encoding.smart_str(body), encoding='utf-8', output='utf-8')), author=author, user=target_user, revealed=True)
      response.put()
      if target_user.google_account:
        target_email = target_user.google_account.email()
      elif target_user.username == 'admonymous':
        target_email = 'eloise.rosen@gmail.com'
        
      if response.body:
        notification = email.EmailMessage(sender='Admonymous <notifications@admonymous.co>', to=target_email, subject='%s left you a response on Admonymous' % ('Someone' if not author else author))
        notification.render_and_send('notification', {
          'target_user':target_user,
          'author':None if author == 'anonymous' else author,
          'body_html':response.body,
          'body_txt':body
        })
    path = 'templates/user.html'
    page = template.render(path, template_values, debug=(True if 'local' in self.request.host_url or users.is_current_user_admin() else False))
    self.response.out.write(page)

class ContactHandler(webapp.RequestHandler):
  def get(self):
    user = User.get_current()
    page = template.render('templates/contact.html', {'user':user})
    self.response.out.write(page)

class SuggestionsHandler(webapp.RequestHandler):
  def get(self):
    user = User.get_current()
    args = self.request.arguments()
    all_topics = [{'name': 'giving', 'description': 'Giving admonition'},
                  {'name': 'receiving', 'description': 'Receiving admonition'},
                  {'name': 'anonymity', 'description': 'Maintaining anonymity'},
                  {'name': 'faq', 'description': 'Frequently Asked Questions'}]
    page = template.render('templates/suggestions.html', {'user':user, 'topic':args, 'topic_list': all_topics})
    self.response.out.write(page)

class PrintablePageHandler(webapp.RequestHandler):
  def get(self):
    google_account = users.get_current_user()
    if google_account:
      user = User.all().filter('google_account', google_account).get()
      if not user:
        self.redirect('/')
      encoded_url = urllib.quote("https://www.admonymous.co/%s"%(user.username))
      template_values = {'user':user, 'encoded_url':encoded_url}
    else:
      self.redirect('/')
    path = 'templates/print.html'
    page = template.render(path, template_values, debug=(True if 'local' in self.request.host_url or users.is_current_user_admin() else False))
    self.response.out.write(page)
    
class DeleteResponseHandler(webapp.RequestHandler):
    def get(self):
        google_account = users.get_current_user()
        if google_account:
            user = User.all().filter('google_account', google_account).get()
            if not user:
                self.redirect('/')
                #self.response.out.write("Must be logged in to delete response.")
                return
            args = self.request.arguments()
            response_id = self.request.get('id','')
            try:
                response_id = long(response_id)
            except InputError:
                self.redirect('/')
                #self.response.out.write("Bad response id.")
                return
            r = Response.get(db.Key.from_path('Response', response_id))
            if not r:
                self.redirect('/')
                return
            if not r.user.key().id() == user.key().id():
                self.redirect('/')
                #self.response.out.write("Not allowed to delete.")
                return
            r.delete()
            #self.response.out.write("Response deleted.")
            #return
            self.redirect('/')
        else:
            self.redirect('/')

class LogoutHandler(webapp.RequestHandler):
  def get(self):
    self.redirect(users.create_logout_url('/'))

class LoginHandler(webapp.RequestHandler):
  def get(self):
    google_account = users.get_current_user()
    if google_account:
      self.redirect('/')
    else:
      self.redirect(users.create_login_url('/'))

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
                                          ('/logout', LogoutHandler),
                                          ('/login', LoginHandler),
                                          ('/contact', ContactHandler),
                                          ('/print', PrintablePageHandler),
                                          ('/suggestions', SuggestionsHandler),
                                          ('/delete_username', DeleteUserHandler),
                                          ('/delete_admonition', DeleteResponseHandler),
                                          ('/([0-9a-zA-Z_\-]+)', UserPageHandler)],
                                         debug=True)
    util.run_wsgi_app(application)


if __name__ == '__main__':
    main()
