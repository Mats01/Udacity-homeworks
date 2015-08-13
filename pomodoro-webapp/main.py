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

from google.appengine.ext import ndb

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader=jinja2.FileSystemLoader(template_dir), autoescape=True)

# the functions below are part of the manually built authentification sistem

SECRET = 'nfjavfafgjlffoeuvlaqewret'


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


USER_RE = re.compile(r"^[a-zA-Z0-9_-]{3,20}$")


def valid_username(username):
    return USER_RE.match(username)


PASS_RE = re.compile(r"^.{3,20}$")


def valid_password(password):
    return PASS_RE.match(password)


EMAIL_RE = re.compile(r"^[\S]+@[\S]+\.[\S]+$")


def valid_email(email):
    return EMAIL_RE.match(email)


# end of authentification functions

# creating classes for entities

class User(ndb.Model):
    username = ndb.StringProperty(required=True)
    password = ndb.StringProperty(required=True)
    email = ndb.StringProperty(required=True)
    joined = ndb.IntegerProperty(required=True)
    # time in seconds since 1970 (easiest way to calculate when
    # to send monthly report)


class Pomodoro(ndb.Model):
    duration = ndb.IntegerProperty(required=True)
    task = ndb.StringProperty(required=True)
    owner = ndb.StringProperty(required=True)
    created = ndb.StringProperty(required=True)
    # created will be a sting containing the date (easy to match
    # for showing todays pomodors, and can be parsed to get the monthly ones)


class Settings(ndb.Model):
    pomodoro_lenght = ndb.IntegerProperty(required=True)
    short_break = ndb.IntegerProperty(required=True)
    long_break = ndb.IntegerProperty(required=True)
    auto_start_new = ndb.BooleanProperty()


class Handler(webapp2.RequestHandler):
    def write(self, *a, **kw):
        self.response.out.write(*a, **kw)

    def render_str(self, template, **params):
        t = jinja_env.get_template(template)
        return t.render(params)

    def render(self, template, **kw):
        self.write(self.render_str(template, **kw))

    def user_in(self):
        user_id = self.request.cookies.get('user_id')
        if user_id:
            val = check_secure_val(user_id)
            if val:
                return User.get_by_id(int(val))



class MainHandler(Handler):
    def get(self):
        self.render('pomodoro.html')


class LogInHandler(Handler):
    def render_error(self, error):
        self.render('login.html', error=error)

    def get(self):
        self.render('login.html', user=self.user_in())

    def post(self):
        input_email = self.request.get('email')
        user_pw = self.request.get('password')
        users = User.query()
        nr_users = 0
        nr_loops = 0
        for i in users:
            nr_users = nr_users + 1
        for i in users:
            nr_loops = nr_loops + 1
            if i.email == input_email:
                s_pw = i.password
                s = s_pw.split('|')[1]
                h = make_pw_hash(user_pw)
                if valid_pw(user_pw, h):
                    if make_pw_hash(user_pw, s) == i.password:
                        new_cookie = make_secure_val(str(i.key.id()))
                        self.response.headers.add_header('Set-Cookie', 'user_id=%s; Path=/' % new_cookie)
                        self.redirect('/')
            elif nr_users == nr_loops:
                self.render_error('Invalid email or password!')

class SignUpHandler(Handler):
    def re_render(self, username, username_error,
                  username_exsists, password_error,
                  verification_error, email, email_error):
        self.render('signup.html', username=username, username_error=username_error,
                    username_exsists=username_exsists, password_error=password_error,
                    verification_error=verification_error, email=email, email_error=email_error)

    def get(self):
        self.render("signup.html")

    def post(self):
        username = valid_username(self.request.get('username'))
        password = valid_password(self.request.get('password'))
        verify_password = self.request.get('verify')
        email = valid_email(self.request.get('email'))
        input_username = self.request.get('username')
        input_email = self.request.get('email')

        passwords_match = False
        username_exsists = ''
        users = User.query()
        for i in users:
            if i.username == input_username:
                username_exsists = 'That username already exsists!'
        if self.request.get('password') == verify_password:
            passwords_match = True
        check = False
        email_error = ''
        if not email:
            check = True
            email_error = 'Invalid email'
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
                u = User(username=input_username, password=make_pw_hash(verify_password),
                         email=input_email, joined=int(time.time()))
                u.put()
                new_cookie = make_secure_val(str(u.key.id()))
                self.response.headers.add_header('Set-Cookie', 'user_id=%s; Path=/' % new_cookie)
                self.redirect('/')

class LogOutHandler(Handler):
    def get(self):
        self.response.headers.add_header('Set-Cookie', 'user_id=; expires=Tue, 09 Nov 1999 00:00:00 GMT, Path=/')
        #previos metod was to just clear the cookie, but by setting the
        #expiration date in the pasr the cookie gets compleatly delited
        self.redirect('/')



app = webapp2.WSGIApplication([
    ('/', MainHandler),
    ('/login', LogInHandler),
    ('/signup', SignUpHandler),
    ('/logout', LogOutHandler)
], debug=True)