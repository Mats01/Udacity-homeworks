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
__author__ = 'Matej'

import os
import webapp2
import jinja2
import re
import hashlib
import hmac
import random
import string
import time
import json

from google.appengine.api import memcache
from google.appengine.ext import db

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader=jinja2.FileSystemLoader(template_dir), autoescape=True)

SECRET = 'imsosecret'


def hash_str(s):
    return hmac.new(SECRET, s).hexdigest()


def make_secure_val(s):
    return "%s|%s" % (s, hash_str(s))


def check_secure_val(h):
    val = h.split('|')[0]
    if h == make_secure_val(val):
        return val


def make_salt():
    return ''.join(random.choice(string.letters) for x in range(5))


salt = ''


def make_pw_hash(pw, salt=None):
    if not salt:
        salt = make_salt()
    h = hashlib.sha256(pw + salt).hexdigest()
    return '%s|%s' % (h, salt)


def valid_pw(pw, h):
    salt = h.split('|')[1]
    if h == make_pw_hash(pw, salt=salt):
        return h


def render_str(template, **params):
    t = jinja_env.get_template(template)
    return t.render(params)


def blog_key(name='default'):
    return db.Key.from_path('blogs', name)


USER_RE = re.compile(r"^[a-zA-Z0-9_-]{3,20}$")


def valid_username(username):
    return USER_RE.match(username)


PASS_RE = re.compile(r"^.{3,20}$")


def valid_password(password):
    return PASS_RE.match(password)


EMAIL_RE = re.compile(r"^[\S]+@[\S]+\.[\S]+$")


def valid_email(email):
    return EMAIL_RE.match(email)


class BlogPost(db.Model):
    subject = db.StringProperty(required=True)
    content = db.TextProperty(required=True)
    author = db.StringProperty()
    created = db.DateTimeProperty(auto_now_add=True)

    def render(self):
        self._render_text = self.content.replace('\n', '<br>')
        return render_str("post1.html", p=self)

    def as_dict(self):
        time_fmt = '%c'
        d = {'subject': self.subject,
             'content': self.content,
             'created': self.created.strftime(time_fmt)}
        return d


class User(db.Model):
    username = db.StringProperty(required=True)
    password = db.StringProperty(required=True)
    email = db.EmailProperty(required=False)


class Handler(webapp2.RequestHandler):
    def write(self, *a, **kw):
        self.response.out.write(*a, **kw)

    def render_str(self, template, **params):
        t = jinja_env.get_template(template)
        return t.render(params)

    def render(self, template, **kw):
        self.write(self.render_str(template, **kw))

    def render_json(self, d):
        json_txt = json.dumps(d)
        self.response.headers['Content-Type'] = 'application/json; charset=UTF-8'
        self.write(json_txt)

start_time = 0
def front_content(update = False):
    global start_time
    key = 'front'
    posts = memcache.get(key)
    if posts is None or update:
        start_time = time.time()
        posts = BlogPost.all().order('-created')
        posts = list(posts)
        memcache.set(key, posts)
    return posts

class MainHandler(Handler):
    def render_post(self, posts, hidden, lhidden, user, quired):
        #posts = db.GqlQuery("SELECT * FROM BlogPost ORDER BY created DESC")
        posts = front_content()

        self.render('blogs.html', posts=posts, hidden=hidden, lhidden=lhidden, user=user, quired=quired)

    def get(self):
        posts = front_content()
        user_id = self.request.cookies.get('user_id')

        if self.request.url.endswith('.json'):
            self.format = 'json'
        else:
            self.format = 'html'

        if self.format == 'html':
            quired = 'Queried %.1f seconds ago' % (time.time() - start_time)
            if user_id:
                id = check_secure_val(user_id)
                key = db.Key.from_path('User', int(id))
                if key:
                    a = User.get_by_id(int(id))
                    self.render_post('', '', lhidden='none', user=str(a.username), quired=quired)
            else:
                self.render_post(posts=None, hidden='none', lhidden='', user=None, quired=quired)
        else:
            return self.render_json([p.as_dict() for p in posts])


class PostHandler(Handler):
    def render_error(self, subject, content, error):
        self.render('post.html', subject=subject, content=content, error=error)

    def get(self):
        user_id = self.request.cookies.get('user_id')
        if user_id:
            id = check_secure_val(user_id)
            key = db.Key.from_path('User', int(id))
            if key:
                self.render('post.html')
        else:
            self.redirect('/blog/login')


    def post(self):
        subject = self.request.get('subject')
        content = self.request.get('content')

        if subject and content:
            user_id = self.request.cookies.get('user_id')
            if user_id:
                id = check_secure_val(user_id)
                a = User.get_by_id(int(id))
            else:
                a_username = None
            p = BlogPost(parent=blog_key(), subject=subject, content=content, author=a.username)
            p.put()
            time.sleep(.1)
            front_content(True)
            time.sleep(.1)
            self.redirect('/blog/%s' % str(p.key().id()))
        else:
            error = 'You need to both write a title and post in order to blog!'
            self.render_error(subject, content, error)

new_start_time = 0
def newpost_cache(post_id):
    global new_start_time
    k = str(db.Key.from_path('BlogPost', int(post_id), parent=blog_key()))
    post = memcache.get(k)
    if post is None:
        new_start_time = time.time()
        key = db.Key.from_path('BlogPost', int(post_id), parent=blog_key())
        post = db.get(key)
        memcache.set(k, post)
    return post


class PostPage(Handler):
    def get(self, post_id):
        post = newpost_cache(post_id)

        if not post:
            self.error(404)
            return

        if self.request.url.endswith('.json'):
            self.format = 'json'
        else:
            self.format = 'html'

        if self.format == 'html':
            queried = 'Queried %.1f seconds ago' % (time.time() - new_start_time)
            self.render("permalink.html", post = post, queried=queried)
        else:
            self.render_json(post.as_dict())


class SingUpHandler(Handler):
    def re_render(self, username, username_error,
                  username_exsists, password_error,
                  verification_error, email, email_error):
        self.render('singup.html', username=username, username_error=username_error,
                    username_exsists=username_exsists, password_error=password_error,
                    verification_error=verification_error, email=email, email_error=email_error)

    def get(self):
        self.render("singup.html")

    def post(self):
        username = valid_username(self.request.get('username'))
        password = valid_password(self.request.get('password'))
        verify_password = self.request.get('verify')
        email = valid_email(self.request.get('email'))
        input_username = self.request.get('username')

        passwords_match = False
        check = False
        email_error = ''
        input_email = self.request.get('email')
        username_exsists = ''
        users = db.GqlQuery("SELECT * FROM User")
        for i in users:
            if i.username == input_username:
                username_exsists='That username already exsists!'
        if self.request.get('email'):
            if not email:
                check = True
                email_error = 'Invalid email'
        if self.request.get('password') == verify_password:
            passwords_match = True
        if not (username and password and passwords_match):
            if not username:
                if not password:
                    self.re_render(username=input_username, username_error="Invalid username",
                                   password_error="That's not a valid password", verification_error='',
                                   email=input_email, email_error=email_error, username_exsists=username_exsists)
                elif not passwords_match:
                    self.re_render(username=input_username, username_error="Invalid username",
                                   password_error='',
                                   verification_error="Passwords don't match",
                                   email=input_email, email_error=email_error, username_exsists=username_exsists)
                else:
                    self.re_render(username=input_username, username_error="Invalid username",
                                   password_error='', verification_error='',
                                   email=input_email, email_error=email_error, username_exsists=username_exsists)
            elif not password:
                self.re_render(username=input_username, password_error="That's not a valid password",
                               verification_error='', username_error='',
                               email=input_email, email_error=email_error, username_exsists=username_exsists)
            elif not passwords_match:
                self.re_render(username=input_username, verification_error="Passwords don't match",
                               username_error='', password_error='',
                               email=input_email, email_error=email_error, username_exsists=username_exsists)
        else:
            if check:
                self.re_render(username=input_username, email=input_email, email_error=email_error,
                               username_error='', password_error='', verification_error='',
                               username_exsists=username_exsists)
            elif username_exsists:
                self.re_render(username=input_username, email=input_email, email_error=email_error,
                               username_error='', password_error='', verification_error='',
                               username_exsists=username_exsists)
            else:
                if not input_email:
                    input_email = None
                u = User(username=input_username, password=make_pw_hash(verify_password), email=input_email)
                u.put()
                new_cookie = make_secure_val(str(u.key().id()))
                self.response.headers.add_header('Set-Cookie', 'user_id=%s; Path=/' % new_cookie)
                self.redirect('/blog/welcome')



class WelcomeHandler(Handler):
    def get(self):
        user_id = self.request.cookies.get('user_id')
        if user_id:
            id = check_secure_val(user_id)
            key = db.Key.from_path('User', int(id))
            if key:
                user = db.get(key)
                self.render('welcome.html', welcome='Welcome, %s!' % user.username)
        else:
            self.redirect('/blog/signup')

class LogInHandler(Handler):
    def render_error(self, error):
        self.render('login.html', error=error)
    def get(self):
        self.render('login.html')

    def post(self):
        input_username = self.request.get('username')
        user_pw = self.request.get('password')
        users = db.GqlQuery("SELECT * FROM User")
        nr_users = 0
        nr_loops = 0
        for i in users:
            nr_users = nr_users + 1
        for i in users:
            nr_loops = nr_loops + 1
            if i.username == input_username:
                s_pw = i.password
                s = s_pw.split('|')[1]
                h = make_pw_hash(user_pw)
                if valid_pw(user_pw, h):
                    if make_pw_hash(user_pw, s) == i.password:
                        new_cookie = make_secure_val(str(i.key().id()))
                        self.response.headers.add_header('Set-Cookie', 'user_id=%s; Path=/' % new_cookie)
                        self.redirect('/blog/welcome')
            elif nr_users == nr_loops:
                self.render_error(error='Invalid username or password!')

class LogOutHandler(Handler):
    def get(self):
        self.response.headers.add_header('Set-Cookie', 'user_id=; Path=/')
        self.redirect('/blog/signup')

class FlushHandler(Handler):
    def get(self):
        memcache.flush_all()
        self.redirect('/blog')


app = webapp2.WSGIApplication([
    ('/blog/?(?:.json)?', MainHandler), ('/blog/newpost', PostHandler), ('/blog/([0-9]+)(?:.json)?', PostPage),
    ('/blog/signup', SingUpHandler), ('/blog/welcome', WelcomeHandler), ('/blog/login', LogInHandler),
    ('/blog/logout', LogOutHandler), ('/blog/flush', FlushHandler)
], debug=True)
