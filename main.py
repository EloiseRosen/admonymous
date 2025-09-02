#!/usr/bin/env python
"""
Django, Cloud NDB, Google OAuth 2.0 
"""
import sys
import os
import re
import datetime
import urllib.parse
import logging
import django
from django.conf import settings
from django.core.wsgi import get_wsgi_application
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.urls import path
from django.urls import reverse
from google.cloud import ndb
from google.cloud import secretmanager
from django.utils.encoding import force_str, smart_str
from textile import textile
from helpers import email
import bleach
import google_auth_oauthlib.flow
import requests
import time
import hmac
import hashlib
import threading
import unicodedata
from collections import defaultdict, deque

PER_PAGE = 10
MAX_PER_PAGE = 100
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCOPES = [
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid"
]

def get_secret_value(secret_name):
    """
    Returns the secret from Secret Manager.
    """
    project_id = os.environ.get('GCP_PROJECT_ID', 'YOUR_PROJECT_ID')
    sm_client = secretmanager.SecretManagerServiceClient()
    resource_name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
    response = sm_client.access_secret_version(name=resource_name)
    payload = response.payload.data.decode("UTF-8")
    return payload

sendgrid_key_name = os.environ.get('SENDGRID_API_KEY_NAME', 'sendgrid-api-key')
real_sendgrid_key = get_secret_value(sendgrid_key_name)
os.environ['SENDGRID_API_KEY'] = real_sendgrid_key

django_secret_name = os.environ.get('DJANGO_SECRET_KEY_NAME', 'django-secret-key')
django_secret_key = get_secret_value(django_secret_name)

settings.configure(
    DEBUG=True,
    SECRET_KEY=django_secret_key,
    ALLOWED_HOSTS=['*'],
    ROOT_URLCONF=__name__,
    INSTALLED_APPS=[
        'django.contrib.sessions',
        'django.middleware.common',
    ],
    MIDDLEWARE=[
        'ndb_middleware.NDBMiddleware',
        'django.middleware.common.CommonMiddleware',
        'django.middleware.csrf.CsrfViewMiddleware',
        'django.middleware.clickjacking.XFrameOptionsMiddleware',
        'django.contrib.sessions.middleware.SessionMiddleware',
    ],
    TEMPLATES=[{
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': False,
        'OPTIONS': {},
    }],
    WSGI_APPLICATION='main.application',
    SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies",
)

django.setup()


class User(ndb.Model): 
    username = ndb.StringProperty()
    name = ndb.StringProperty()
    google_account_str = ndb.StringProperty() # legacy version google_account, new version google_account_str
    create_date = ndb.DateTimeProperty(auto_now_add=True)
    update_date = ndb.DateTimeProperty(auto_now=True)
    message = ndb.TextProperty()  # 

    def message_html(self):
        return self.message or ""

    def first_name(self):
        if not self.name:
            return ''
        return self.name.split(" ", 1)[0]

class Response(ndb.Model):
    user = ndb.KeyProperty(kind=User)
    create_date = ndb.DateTimeProperty(auto_now_add=True)
    body = ndb.TextProperty()
    author = ndb.StringProperty()
    reveal_datetime = ndb.DateTimeProperty(auto_now_add=True)
    revealed = ndb.BooleanProperty(default= False)

# --- In-memory filter ---

WINDOW_SECONDS = 24 * 60 * 60  # 24 hours
MESSAGE_LIMIT = 2 # allow first 2 identical (>=10 chars), block third+
IP_LIMIT = 10  # allow first 10 from an IP, block 11th+

_SALT = os.urandom(32)  # ephemeral per-process salt. nothing persisted

def _canonicalize_text(s):
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def _hash_hmac(text):
    return hmac.new(_SALT, text.encode("utf-8", "ignore"), hashlib.sha256).hexdigest()

def get_client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR") or request.META.get("X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip() or None
    return request.META.get("HTTP_X_REAL_IP") or request.META.get("REMOTE_ADDR") or None

class _SlidingWindow:
    def __init__(self, window_seconds=WINDOW_SECONDS, sweep_interval=300):
        self.window = window_seconds
        self.sweep_interval = sweep_interval
        self._by_key = defaultdict(deque)
        self._lock = threading.RLock()
        self._last_sweep = 0.0

    def _prune_dq(self, dq, now):
        cutoff = now - self.window
        while dq and dq[0] < cutoff:
            dq.popleft()

    def _maybe_sweep(self, now):
        if now - self._last_sweep < self.sweep_interval:
            return
        for key in list(self._by_key.keys()):
            dq = self._by_key.get(key)
            if dq is None:
                continue
            self._prune_dq(dq, now)
            if not dq:
                self._by_key.pop(key, None)
        self._last_sweep = now

    def increment_and_count(self, key, now=None):
        now = now or time.time()
        with self._lock:
            self._maybe_sweep(now)
            dq = self._by_key[key]
            self._prune_dq(dq, now)
            dq.append(now)
            return len(dq)

class Filter:
    def __init__(self, window_seconds=WINDOW_SECONDS, message_limit=MESSAGE_LIMIT, ip_limit=IP_LIMIT):
        self.window = window_seconds
        self.message_limit = message_limit
        self.ip_limit = ip_limit
        self._by_message = _SlidingWindow(window_seconds)
        self._by_ip = _SlidingWindow(window_seconds)

    def decide(self, ip, raw_message):
        """
        Returns True if allowed, False if blocked.
        """
        now = time.time()
        canon = _canonicalize_text(raw_message)
        long_enough = len(canon) >= 10

        ip_key = _hash_hmac(ip) if ip else ""
        msg_key = _hash_hmac(canon) if long_enough else None

        ip_count = self._by_ip.increment_and_count(ip_key) if ip_key else 0
        msg_count = self._by_message.increment_and_count(msg_key) if msg_key else 0

        reasons = []
        if ip_key and ip_count > self.ip_limit:
            reasons.append("ip_rate")
        if msg_key and msg_count > self.message_limit:
            reasons.append("msg_dup")
        return not reasons

filt = Filter()

def get_bounded_int_value(s, default, lower_bound=None, upper_bound=None):
    try:
        val = int(s)
    except (ValueError, TypeError):
        val = default
    if lower_bound is not None and val < lower_bound:
        val = lower_bound
    if upper_bound is not None and val > upper_bound:
        val = upper_bound
    return val

def get_current_user(request):
    """Return the NDB User object for logged in user (from session)."""
    user_key_urlsafe = request.session.get('user_key')
    if not user_key_urlsafe:
        return None
    key = ndb.Key(urlsafe=user_key_urlsafe)
    return key.get()

def sanitize_user_input(dirty_text):
    return bleach.clean(dirty_text or "", tags=[], attributes={}, strip=True)  # (tags is for allowing certain tags to stay)


def load_oauth_config():
    client_id_secret_name = os.environ.get('OAUTH_CLIENT_ID_SECRET_NAME', 'my-client-id')
    client_secret_secret_name = os.environ.get('OAUTH_CLIENT_SECRET_NAME', 'my-client-secret')

    real_client_id = get_secret_value(client_id_secret_name)
    real_client_secret = get_secret_value(client_secret_secret_name)

    redirect_uris = [
        "http://localhost:8080/oauth-callback",
        "https://crockersrules-hrd.appspot.com/oauth-callback",
        "https://www.admonymous.co/oauth-callback"
    ]

    config = {
        "web": {
            "client_id": real_client_id,
            "client_secret": real_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": redirect_uris
        }
    }
    return config

def home(request):
    user = get_current_user(request)
    if not user:
        return render(request, 'home.html', {})

    per_page = get_bounded_int_value(request.GET.get('per_page'), PER_PAGE, 1, MAX_PER_PAGE)
    offset = get_bounded_int_value(request.GET.get('offset'), 0, 0)

    query = Response.query(Response.user == user.key).order(-Response.create_date)
    responses = query.fetch(per_page + 1, offset=offset)

    template_values = {'user': user}
    if offset > 0:
        template_values['older_offset'] = max(0, offset - per_page)
    if len(responses) == (per_page + 1):
        responses.pop()
        template_values['newer_offset'] = offset + per_page

    for r in responses:
        r.response_id = r.key.id()
    template_values['responses'] = responses

    return render(request, 'home.html', template_values)

def home_post(request):
    user = get_current_user(request)
    if not user:
        return render(request, 'home.html', {'login_url': '/login'})

    def namey(inStr, spacechar='_'):
        aslug = re.sub(r'[^\w\s-]', '', inStr).strip().lower()
        aslug = re.sub(r'\s+', spacechar, aslug)
        return aslug

    username_input = request.POST.get('username', '')
    raw_slug = namey(username_input)
    username = sanitize_user_input(raw_slug)

    existing = User.query(User.username == username).get()
    username_taken = False
    if existing and existing.key != user.key:
        username_taken = True

    success = None
    if not username_taken:
        success = True if user.username else None
        user.username = username
    else:
        success = False

    raw_name = request.POST.get('name', '')
    user.name = sanitize_user_input(raw_name)
    user.message = sanitize_user_input(request.POST.get('message', ''))
    user.put()

    template_values = {
        'user': user,
        'success': success,
        'username_taken': username if username_taken else False
    }

    per_page = get_bounded_int_value(request.POST.get('per_page'), PER_PAGE, 1, MAX_PER_PAGE)
    offset = get_bounded_int_value(request.POST.get('offset'), 0, 0)

    query = Response.query(Response.user == user.key).order(-Response.create_date)
    responses = query.fetch(per_page + 1, offset=offset)

    if offset > 0:
        template_values['older_offset'] = max(0, offset - per_page)
    if len(responses) == (per_page + 1):
        responses.pop()
        template_values['newer_offset'] = offset + per_page

    for r in responses:
        r.response_id = r.key.id()
    template_values['responses'] = responses

    return render(request, 'home.html', template_values)

def user_page(request, username):
    target_user = User.query(User.username == username).get()
    if (username == 'admonymous') and not target_user:
        target_user = User(username='admonymous', name='Admonymous')
        target_user.put()

    current_user = get_current_user(request)
    return render(request, 'user.html', {
        'target_user': target_user,
        'target_user_first_name': target_user.first_name() if target_user else '',
        'user': current_user
    })

def user_page_post(request, username):
    target_user = User.query(User.username == username).get()
    current_user = get_current_user(request)

    author = sanitize_user_input(request.POST.get('author', 'anonymous'))
    body_raw = request.POST.get('body', '')
    emailFlag = request.POST.get('email', '')

    body_stripped = sanitize_user_input(body_raw)
    processed_body_html = force_str(textile(smart_str(body_stripped)))

    success = True
    if emailFlag == '':
        if body_stripped.strip():
            client_ip = get_client_ip(request)
            if filt.decide(client_ip, body_stripped):
                response_entity = Response(
                    body=processed_body_html,  # processed_body_html has already been sanitized and textile-ized
                    author=author,
                    user=target_user.key if target_user else None,
                    revealed=True
                )
                response_entity.put()

                if target_user and target_user.google_account_str:
                    target_email = target_user.google_account_str
                elif target_user and target_user.username == 'admonymous':
                    target_email = 'eloise.rosen@gmail.com'
                else:
                    target_email = None

                if target_email:
                    subj = '%s left you a response on Admonymous' % ('Someone' if author == 'anonymous' else author)
                    notification = email.EmailMessage(
                        sender='Admonymous <notify@admonymous.co>',
                        to=target_email,
                        subject=subj
                    )
                    notification.render_and_send('notification', {
                        'target_user': target_user,
                        'author': None if author == 'anonymous' else author,
                        'body_html': processed_body_html,
                        'body_txt': body_raw
                    })

    template_values = {
        'target_user': target_user,
        'user': current_user,
        'success': success
    }
    return render(request, 'user.html', template_values)

def contact(request):
    user = get_current_user(request)
    return render(request, 'contact.html', {'user': user})

def suggestions(request):
    user = get_current_user(request)
    args = request.GET.dict()
    all_topics = [
        {'name': 'giving', 'description': 'Giving admonition'},
        {'name': 'receiving', 'description': 'Receiving admonition'},
        {'name': 'anonymity', 'description': 'Maintaining anonymity'},
        {'name': 'faq', 'description': 'Frequently Asked Questions'},
    ]
    return render(request, 'suggestions.html', {
        'user': user,
        'topic': args.keys(),
        'topic_list': all_topics
    })

def delete_response(request):
    user = get_current_user(request)
    if not user:
        return redirect('/')
    resp_id = request.GET.get('id')
    if not resp_id:
        return redirect('/')
    try:
        resp_id = int(resp_id)
    except ValueError:
        return redirect('/')
    resp_key = ndb.Key(Response, resp_id)
    resp = resp_key.get()
    if not resp or resp.user != user.key:
        return redirect('/')
    resp.key.delete()
    return redirect('/')

def logout_view(request):
    request.session.flush()
    return redirect('/')

def delete_user(request):
    user = get_current_user(request)
    if not user:
        return redirect('/')
    user_resps = Response.query(Response.user == user.key).fetch()
    for r in user_resps:
        r.key.delete()
    user.key.delete()
    request.session.flush()
    return redirect('/')


# Google OAuth 2.0 login flow
def login_view(request):
    config = load_oauth_config()
    flow = google_auth_oauthlib.flow.Flow.from_client_config(config, scopes=SCOPES)
    
    # dynamically set redirect_uri based on the domain/path actually used (localhost vs appspot vs admonymous.co)
    flow.redirect_uri = request.build_absolute_uri(reverse('oauth_callback'))

    # request offline access so that google gives us a refresh token
    # 'include_granted_scopes' merges existing grants in case the user already gave consent
    authorization_url, state_bytes = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )
    if isinstance(state_bytes, bytes):
        state_str = state_bytes.decode('utf-8', errors='ignore')
    else:
        state_str = str(state_bytes)

    # store  OAuth state in the session so that it can be retrieved by oauth_callback
    request.session['oauth_state'] = state_str
    return redirect(authorization_url)


def oauth_callback(request):
    state = request.session.get('oauth_state')
    if not state:
        return HttpResponse("No OAuth state in session, please try again.", status=400)

    config = load_oauth_config()
    # create the Flow object with the same 'state' and 'scopes' as the original request.
    flow = google_auth_oauthlib.flow.Flow.from_client_config(
        config, 
        scopes=SCOPES, 
        state=state
    )

    # dynamically set redirect_uri based on the domain/path actually used (localhost vs appspot vs admonymous.co)
    # 'request.build_absolute_uri(request.path)' = scheme + domain + /oauth-callback
    flow.redirect_uri = request.build_absolute_uri(request.path)

    flow.fetch_token(authorization_response=request.build_absolute_uri())

    creds = flow.credentials
    if not creds or not creds.valid:
        return HttpResponse("Invalid credentials from Google OAuth", status=400)

    try:
        userinfo_resp = requests.get(
            'https://www.googleapis.com/oauth2/v3/userinfo',
            headers={'Authorization': f'Bearer {creds.token}'}
        )
        userinfo = userinfo_resp.json()
        email = userinfo.get('email')

        name_raw = userinfo.get('name', '')
        name_clean = sanitize_user_input(name_raw)

    except Exception as e:
        return HttpResponse(f"Failed to fetch user info: {e}", status=500)

    if not email:
        return HttpResponse("No email returned by Google OAuth", status=400)
    
    if hasattr(flow, '_credentials'):
        try:
            del flow._credentials
        except:
            pass

    if hasattr(flow, 'oauth2session') and flow.oauth2session:
        flow.oauth2session.token = {}

    existing_user = User.query(User.google_account_str == email).get()
    if not existing_user:
        placeholder_username_raw = re.sub(r'[^\w\s-]', '', name_clean.lower()).replace(' ', '-') or "user"
        placeholder_username = sanitize_user_input(placeholder_username_raw)

        new_user = User(
            google_account_str=email,
            name=name_clean,
            username=placeholder_username
        )
        new_user.put()
        existing_user = new_user

    request.session['user_key'] = existing_user.key.urlsafe().decode('utf-8')
    request.session.pop('oauth_state', None)
    return redirect('/')


urlpatterns = [
    path('', home, name='home'),
    path('post_home', home_post, name='home_post'),
    path('contact', contact, name='contact'),
    path('suggestions', suggestions, name='suggestions'),
    path('delete_username', delete_user, name='delete_user'),
    path('delete_admonition', delete_response, name='delete_response'),
    path('logout', logout_view, name='logout'),
    path('login', login_view, name='login'),
    path('oauth-callback', oauth_callback, name='oauth_callback'),
    path('<str:username>', user_page, name='user_page'),
    path('<str:username>/post', user_page_post, name='user_page_post'),
]

application = get_wsgi_application()

if __name__ == '__main__':
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
