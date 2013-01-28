#!/usr/bin/env python
# Copyright 2011 Google Inc.
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

"""This is a development server for running the UI."""


import logging
import os
import socket
import SocketServer
from wsgiref import simple_server

import django
from django.conf import settings
from django.core.handlers import wsgi

from grr.client import conf
from grr.client import conf as flags
# TODO(user): Remove webauth import after change to CONFIG
from grr.gui import webauth   # pylint: disable=W0611
from grr.lib import config_lib
from grr.lib import registry
from grr.lib import server_plugins  # pylint: disable=W0611

flags.DEFINE_integer("port", 8000,
                     "port to listen on")

flags.DEFINE_string("bind", "::",
                    "interface to bind to.")

flags.DEFINE_bool("django_debug", False,
                  "Turn on to add django debugging")

flags.DEFINE_string("django_secret_key", "CHANGE_ME",
                    "This is a secret key that should be set in the server "
                    "config. It is used in XSRF and session protection.")

FLAGS = flags.FLAGS
CONFIG = config_lib.CONFIG
CONFIG.flag_sections.append("ServerFlags")


class DjangoInit(registry.InitHook):
  """Initialize the Django environment."""

  def RunOnce(self):
    """Configure the Django environment."""
    base_app_path = os.path.normpath(os.path.dirname(__file__))
    # Note that Django settings are immutable once set.
    django_settings = {
        "DEBUG": FLAGS.django_debug,
        "TEMPLATE_DEBUG": FLAGS.django_debug,
        "SECRET_KEY": FLAGS.django_secret_key,       # Used for XSRF protection.
        # Set to default as we don't supply an HTTPS server.
        # "CSRF_COOKIE_SECURE": not FLAGS.django_debug,  # Only send over HTTPS.
        "ROOT_URLCONF": "grr.gui.urls",           # Where to find url mappings.
        "TEMPLATE_DIRS": ("%s/templates" % base_app_path,),
        # Don't use the database for sessions, use a file.
        "SESSION_ENGINE": "django.contrib.sessions.backends.file"
    }

    # The below will use conf/global_settings/py from Django, we need to
    # override every variable we need to set.
    settings.configure(**django_settings)


class GuiPluginsInit(registry.InitHook):
  """Initialize the GUI plugins once Django is initialized."""

  pre = ["DjangoInit"]

  def RunOnce(self):
    """Import the plugins once only."""
    # pylint: disable=unused-variable,C6204
    from grr.gui import gui_plugins
    # pylint: enable=unused-variable,C6204


class ThreadingDjango(SocketServer.ThreadingMixIn, simple_server.WSGIServer):
  address_family = socket.AF_INET6


def main(_):
  """Run the main test harness."""
  registry.Init()

  if django.VERSION[0] == 1 and django.VERSION[1] < 4:
    msg = ("The installed Django version is too old. We need 1.4+. You can "
           "install a new version with 'sudo easy_install Django'.")
    logging.error(msg)
    raise RuntimeError(msg)

  if settings.SECRET_KEY == "CHANGE_ME":
    msg = "Please change the secret key in the settings module."
    logging.error(msg)

  # Start up a server in another thread
  base_url = "http://%s:%d" % (FLAGS.bind, FLAGS.port)
  logging.info("Base URL is %s", base_url)

  # Make a simple reference implementation WSGI server
  server = simple_server.make_server(FLAGS.bind, FLAGS.port,
                                     wsgi.WSGIHandler(),
                                     server_class=ThreadingDjango)

  server.serve_forever()


if __name__ == "__main__":
  conf.StartMain(main)
