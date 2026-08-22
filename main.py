#!/usr/bin/env python
"""
Django, Cloud NDB, Google OAuth 2.0 
"""
import sys
import os
import re
import html
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
from collections import deque
from feedback_topics import (
    MAX_FEEDBACK_TOPICS_INPUT_LENGTH,
    FeedbackTopicsValidationError,
    canonicalize_feedback_topics,
)

PER_PAGE = 10
MAX_PER_PAGE = 100
MAX_FEEDBACK_BODY_LENGTH = 5_000
MAX_FEEDBACK_AUTHOR_LENGTH = 100
MAX_PROFILE_NAME_LENGTH = 100
MAX_USERNAME_LENGTH = 50
MAX_PROFILE_MESSAGE_LENGTH = 2_000
MAX_FEEDBACK_HTML_BYTES = 64 * 1024
MAX_INDEXED_STRING_BYTES = 1_500

FEEDBACK_HTML_TAGS = frozenset({
    'p', 'br', 'strong', 'em', 'b', 'i',
    'ul', 'ol', 'li', 'blockquote', 'pre', 'code',
    'del', 'ins', 'sup', 'sub',
})

FORM_LIMITS = {
    'max_feedback_body_length': MAX_FEEDBACK_BODY_LENGTH,
    'max_feedback_author_length': MAX_FEEDBACK_AUTHOR_LENGTH,
    'max_profile_name_length': MAX_PROFILE_NAME_LENGTH,
    'max_username_length': MAX_USERNAME_LENGTH,
    'max_profile_message_length': MAX_PROFILE_MESSAGE_LENGTH,
}
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
    DEBUG=False,
    SECRET_KEY=django_secret_key,
    ALLOWED_HOSTS=['*'],
    ROOT_URLCONF=__name__,
    USE_TZ=False,
    INSTALLED_APPS=[
        'django.contrib.sessions',
        'django.middleware.common',
    ],
    MIDDLEWARE=[
        'django.middleware.security.SecurityMiddleware',
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

    SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'),
    USE_X_FORWARDED_HOST=True,
)

django.setup()


class User(ndb.Model): 
    username = ndb.StringProperty()
    name = ndb.StringProperty()
    google_account_str = ndb.StringProperty() # legacy version google_account, new version google_account_str
    create_date = ndb.DateTimeProperty(auto_now_add=True)
    update_date = ndb.DateTimeProperty(auto_now=True)
    message = ndb.TextProperty()  #
    feedback_topics = ndb.TextProperty()  # one topic per line

    def message_html(self):
        if not self.message:
            return ""
        msg = self.message.replace("\r\n", "\n").replace("\r", "\n")
        return msg.replace("\n", "<br/>\n")

    def feedback_topics_list(self):
        if not self.feedback_topics:
            return []
        topics = self.feedback_topics.replace("\r\n", "\n").replace("\r", "\n")
        return [topic.strip() for topic in topics.split("\n") if topic.strip()]

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
MAX_TRACKED_IPS = 10_000
MAX_TRACKED_MESSAGES = 10_000

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
    appengine_ip = request.META.get("HTTP_X_APPENGINE_USER_IP")
    if appengine_ip:
        return appengine_ip.strip() or None
    xff = request.META.get("HTTP_X_FORWARDED_FOR") or request.META.get("X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip() or None
    return request.META.get("HTTP_X_REAL_IP") or request.META.get("REMOTE_ADDR") or None

class _SlidingWindow:
    def __init__(
        self,
        window_seconds=WINDOW_SECONDS,
        max_keys=MAX_TRACKED_MESSAGES,
        max_events_per_key=MESSAGE_LIMIT,
        sweep_interval=300,
    ):
        self.window = window_seconds
        self.max_keys = max_keys
        self.max_events_per_key = max_events_per_key
        self.sweep_interval = sweep_interval
        self._by_key = {}
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
        if now is None:
            now = time.time()
        with self._lock:
            self._maybe_sweep(now)

            dq = self._by_key.get(key)
            if dq is not None:
                self._prune_dq(dq, now)
                if not dq:
                    self._by_key.pop(key, None)
                    dq = None

            if dq is None:
                if len(self._by_key) >= self.max_keys:
                    return self.max_events_per_key + 1
                dq = deque()
                self._by_key[key] = dq

            if len(dq) >= self.max_events_per_key:
                return self.max_events_per_key + 1

            dq.append(now)
            return len(dq)

class Filter:
    def __init__(self, window_seconds=WINDOW_SECONDS, message_limit=MESSAGE_LIMIT, ip_limit=IP_LIMIT):
        self.window = window_seconds
        self.message_limit = message_limit
        self.ip_limit = ip_limit
        self._by_message = _SlidingWindow(
            window_seconds,
            max_keys=MAX_TRACKED_MESSAGES,
            max_events_per_key=message_limit,
        )
        self._by_ip = _SlidingWindow(
            window_seconds,
            max_keys=MAX_TRACKED_IPS,
            max_events_per_key=ip_limit,
        )

    def decide(self, ip, raw_message):
        """
        Returns True if allowed, False if blocked.
        """
        now = time.time()
        ip_key = _hash_hmac(ip) if ip else ""
        if ip_key:
            ip_count = self._by_ip.increment_and_count(ip_key, now=now)
            if ip_count > self.ip_limit:
                return False

        canon = _canonicalize_text(raw_message)
        if len(canon) < 10:
            return True

        msg_key = _hash_hmac(canon)
        msg_count = self._by_message.increment_and_count(msg_key, now=now)
        return msg_count <= self.message_limit

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

def prepare_responses_for_display(responses):
    for response in responses:
        response.response_id = response.key.id()
        create_date = response.create_date
        if create_date and create_date.tzinfo is not None:
            create_date = create_date.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        response.create_date_utc_iso = create_date.strftime('%Y-%m-%dT%H:%M:%SZ') if create_date else ''

def get_current_user(request):
    """Return the NDB User object for logged in user (from session)."""
    user_key_urlsafe = request.session.get('user_key')
    if not user_key_urlsafe:
        return None
    key = ndb.Key(urlsafe=user_key_urlsafe)
    return key.get()

def sanitize_user_input(dirty_text):
    return bleach.clean(dirty_text or "", tags=[], attributes={}, strip=True)  # (tags is for allowing certain tags to stay)


def sanitize_single_line_user_input(dirty_text):
    cleaned = sanitize_user_input(dirty_text)
    return re.sub(r'[\x00-\x1f\x7f]+', ' ', cleaned).strip()


def sanitize_feedback_html(dirty_html):
    return bleach.clean(
        dirty_html or "",
        tags=FEEDBACK_HTML_TAGS,
        attributes={},
        protocols=frozenset(),
        strip=True,
        strip_comments=True,
    )


def get_profile_form_values(user):
    return {
        'name_form_value': html.unescape(user.name or ''),
        'username_form_value': html.unescape(user.username or ''),
        'message_form_value': html.unescape(user.message or ''),
        'feedback_topics_form_value': html.unescape(user.feedback_topics or ''),
    }


def render_user_template(request, target_user, current_user, status=200, **values):
    template_values = {
        'target_user': target_user,
        'target_user_first_name': target_user.first_name() if target_user else '',
        'user': current_user,
        'feedback_body_form_value': '',
        'feedback_author_form_value': 'anonymous',
    }
    template_values.update(FORM_LIMITS)
    template_values.update(values)
    return render(request, 'user.html', template_values, status=status)


def get_user_by_username(username):
    if len(username.encode('utf-8')) > MAX_INDEXED_STRING_BYTES:
        return None
    return User.query(User.username == username).get()


def normalize_username(value, spacechar='_'):
    slug = re.sub(r'[^\w\s-]', '', value).strip().lower()
    return re.sub(r'\s+', spacechar, slug)


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

    older_offset = None
    newer_offset = None

    if offset > 0:
        older_offset = max(0, offset - per_page)

    if len(responses) == (per_page + 1):
        responses.pop()
        newer_offset = offset + per_page

    prepare_responses_for_display(responses)

    template_values = {
        'user': user,
        'responses': responses,
        'older_offset': older_offset,
        'newer_offset': newer_offset,
    }
    template_values.update(FORM_LIMITS)
    template_values.update(get_profile_form_values(user))

    return render(request, 'home.html', template_values)

def home_post(request):
    user = get_current_user(request)
    if not user:
        return render(request, 'home.html', {'login_url': '/login'})

    raw_name = request.POST.get('name', '')
    raw_username = request.POST.get('username', '')
    raw_message = request.POST.get('message', '')
    raw_feedback_topics = request.POST.get('feedback_topics', '')

    name_error = None
    username_error = None
    message_error = None
    feedback_topics_error = None

    if len(raw_name) > MAX_PROFILE_NAME_LENGTH:
        name_error = f'Name must be {MAX_PROFILE_NAME_LENGTH} characters or fewer.'
    if len(raw_username) > MAX_USERNAME_LENGTH:
        username_error = f'Username must be {MAX_USERNAME_LENGTH} characters or fewer.'
    if len(raw_message) > MAX_PROFILE_MESSAGE_LENGTH:
        message_error = (
            f'Your note must be {MAX_PROFILE_MESSAGE_LENGTH:,} characters or fewer.'
        )

    feedback_topics = None
    try:
        feedback_topics = canonicalize_feedback_topics(
            raw_feedback_topics,
            sanitize_user_input,
        )
    except FeedbackTopicsValidationError as error:
        feedback_topics_error = str(error)

    username = None
    username_taken = False
    success = None
    profile_saved = False

    if not username_error:
        username = normalize_username(raw_username)
        if not username:
            username_error = 'Enter a username containing letters, numbers, underscores, or hyphens.'
        elif len(username) > MAX_USERNAME_LENGTH:
            username_error = f'Username must be {MAX_USERNAME_LENGTH} characters or fewer.'

    has_validation_error = any((
        name_error,
        username_error,
        message_error,
        feedback_topics_error,
    ))

    if not has_validation_error:
        existing = User.query(User.username == username).get()
        if existing and existing.key != user.key:
            username_taken = username

        if not username_taken:
            success = True if user.username else None
            user.username = username
            user.name = sanitize_single_line_user_input(raw_name)
            user.message = sanitize_user_input(raw_message)
            user.feedback_topics = feedback_topics
            user.put()
            profile_saved = True

    if profile_saved:
        form_values = get_profile_form_values(user)
    else:
        form_values = {
            'name_form_value': raw_name[:MAX_PROFILE_NAME_LENGTH],
            'username_form_value': raw_username[:MAX_USERNAME_LENGTH],
            'message_form_value': raw_message[:MAX_PROFILE_MESSAGE_LENGTH],
            'feedback_topics_form_value': raw_feedback_topics[:MAX_FEEDBACK_TOPICS_INPUT_LENGTH],
        }

    template_values = {
        'user': user,
        'success': success,
        'username_taken': username_taken,
        'name_error': name_error,
        'username_error': username_error,
        'message_error': message_error,
        'feedback_topics_error': feedback_topics_error,
    }
    template_values.update(FORM_LIMITS)
    template_values.update(form_values)

    per_page = get_bounded_int_value(request.POST.get('per_page'), PER_PAGE, 1, MAX_PER_PAGE)
    offset = get_bounded_int_value(request.POST.get('offset'), 0, 0)

    query = Response.query(Response.user == user.key).order(-Response.create_date)
    responses = query.fetch(per_page + 1, offset=offset)

    older_offset = None
    newer_offset = None

    if offset > 0:
        older_offset = max(0, offset - per_page)

    if len(responses) == (per_page + 1):
        responses.pop()
        newer_offset = offset + per_page

    prepare_responses_for_display(responses)

    template_values.update({
        'responses': responses,
        'older_offset': older_offset,
        'newer_offset': newer_offset,
    })

    return render(request, 'home.html', template_values)

def user_page(request, username):
    target_user = get_user_by_username(username)
    if (username == 'admonymous') and not target_user:
        target_user = User(username='admonymous', name='Admonymous')
        target_user.put()

    current_user = get_current_user(request)
    status = 200 if target_user else 404
    return render_user_template(request, target_user, current_user, status=status)

def user_page_post(request, username):
    target_user = get_user_by_username(username)
    current_user = get_current_user(request)
    if not target_user:
        return render_user_template(request, None, current_user, status=404)

    email_flag = request.POST.get('email', '')
    if email_flag:
        return render_user_template(
            request,
            target_user,
            current_user,
            success=True,
        )

    author_raw = request.POST.get('author', 'anonymous')
    body_raw = request.POST.get('body', '')

    form_values = {
        'feedback_author_form_value': author_raw[:MAX_FEEDBACK_AUTHOR_LENGTH],
        'feedback_body_form_value': body_raw[:MAX_FEEDBACK_BODY_LENGTH],
    }

    def validation_error(message, field):
        return render_user_template(
            request,
            target_user,
            current_user,
            status=400,
            feedback_error=message,
            feedback_error_field=field,
            **form_values,
        )

    if len(author_raw) > MAX_FEEDBACK_AUTHOR_LENGTH:
        return validation_error(
            f'Your name must be {MAX_FEEDBACK_AUTHOR_LENGTH} characters or fewer.',
            'author',
        )
    if len(body_raw) > MAX_FEEDBACK_BODY_LENGTH:
        return validation_error(
            f'Feedback must be {MAX_FEEDBACK_BODY_LENGTH:,} characters or fewer.',
            'body',
        )
    if not body_raw.strip():
        return validation_error('Enter feedback before submitting.', 'body')

    author = sanitize_single_line_user_input(author_raw) or 'anonymous'
    body_stripped = sanitize_user_input(body_raw)
    if not body_stripped.strip():
        return validation_error('Enter feedback before submitting.', 'body')

    client_ip = get_client_ip(request)
    if not filt.decide(client_ip, body_stripped):
        return render_user_template(
            request,
            target_user,
            current_user,
            success=True,
        )

    textile_html = force_str(textile(smart_str(body_stripped)))
    processed_body_html = sanitize_feedback_html(textile_html)
    if len(processed_body_html.encode('utf-8')) > MAX_FEEDBACK_HTML_BYTES:
        return validation_error(
            'That feedback creates too much formatted content. Use less formatting.',
            'body',
        )

    visible_body = html.unescape(
        bleach.clean(
            processed_body_html,
            tags=[],
            attributes={},
            strip=True,
        )
    ).strip()
    if not visible_body:
        return validation_error('Enter feedback before submitting.', 'body')

    response_entity = Response(
        body=processed_body_html,
        author=author,
        user=target_user.key,
        revealed=True
    )
    response_entity.put()

    if target_user.google_account_str:
        target_email = target_user.google_account_str
    elif target_user.username == 'admonymous':
        target_email = 'eloise.rosen@gmail.com'
    else:
        target_email = None

    if target_email:
        subject_author = 'Someone' if author == 'anonymous' else author
        notification = email.EmailMessage(
            sender='Admonymous <notify@admonymous.co>',
            to=target_email,
            subject=f'{subject_author} left you a response on Admonymous'
        )
        notification.render_and_send('notification', {
            'target_user': target_user,
            'author': None if author == 'anonymous' else author,
            'body_html': processed_body_html,
            'body_txt': body_raw
        })

    return render_user_template(
        request,
        target_user,
        current_user,
        success=True,
    )

def contact(request):
    user = get_current_user(request)
    return render(request, 'contact.html', {'user': user})

def suggestions(request):
    user = get_current_user(request)
    args = request.GET.dict()
    all_topics = [
        {'name': 'giving', 'description': 'Giving feedback'},
        {'name': 'receiving', 'description': 'Receiving feedback'},
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

def _external_base_url(request):
    """
    Return canonical external base URL.
    Forces https for non-local hosts; allows http only for localhost.
    Can be overridden with EXTERNAL_BASE_URL (e.g., a specific staging host).
    """
    override = os.getenv('EXTERNAL_BASE_URL')
    if override:
        return override.rstrip('/')

    host = request.get_host().split(',')[0]
    if host.startswith('localhost') or host.startswith('127.0.0.1'):
        scheme = 'http'
    else:
        scheme = 'https'
    return f"{scheme}://{host}"

def _https_absolute_uri(request, path_or_fullpath):
    base = _external_base_url(request)
    if path_or_fullpath.startswith('/'):
        return f"{base}{path_or_fullpath}"
    return f"{base}/{path_or_fullpath.lstrip('/')}"


# Google OAuth 2.0 login flow
def login_view(request):
    config = load_oauth_config()
    flow = google_auth_oauthlib.flow.Flow.from_client_config(config, scopes=SCOPES)
    
    flow.redirect_uri = _https_absolute_uri(request, reverse('oauth_callback'))

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

    flow.redirect_uri = _https_absolute_uri(request, request.path)

    authorization_response = _https_absolute_uri(request, request.get_full_path())
    flow.fetch_token(authorization_response=authorization_response)

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

        name_raw = force_str(userinfo.get('name') or '')
        bounded_name = name_raw[:MAX_PROFILE_NAME_LENGTH]
        name_clean = sanitize_single_line_user_input(bounded_name)

    except Exception:
        logging.exception("Failed to fetch user info from Google OAuth")
        return HttpResponse("Google sign-in failed. Please try again.", status=500)

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
        placeholder_username = (
            normalize_username(bounded_name, spacechar='-')[:MAX_USERNAME_LENGTH]
            or 'user'
        )

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
