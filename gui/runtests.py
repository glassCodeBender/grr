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

"""This is a selenium test harness used interactively with Selenium IDE."""
import copy
import os
import socket
import sys
import threading
import urllib
from wsgiref import simple_server



from django.conf import settings
from django.core.handlers import wsgi

from grr.client import conf
from grr.client import conf as flags
import logging

from grr.lib import data_store

from grr.lib import ipshell
from grr.lib import registry
from grr.lib import server_plugins  # pylint: disable=W0611
from grr.lib import test_lib


flags.DEFINE_integer("port", 8000,
                     "port to listen on for selenium tests.")

FLAGS = flags.FLAGS

DJANGO_SETTINGS = {
    "SECRET_KEY": "TEST KEY 1234567890",         # Used for XSRF protection.
    "ROOT_URLCONF": "grr.gui.urls",
    "TEMPLATE_DIRS": ("grr/gui/templates",),
    # Don't use the database for sessions, use a file.
    "SESSION_ENGINE": "django.contrib.sessions.backends.file",
}


class DjangoThread(threading.Thread):
  """A class to run the wsgi server in another thread."""

  keep_running = True

  def __init__(self, **kwargs):
    super(DjangoThread, self).__init__(**kwargs)
    self.base_url = "http://%s:%d" % (socket.getfqdn(), FLAGS.port)

  def run(self):
    """Run the django server in a thread."""
    logging.info("Base URL is %s", self.base_url)

    # Make a simple reference implementation WSGI server
    server = simple_server.make_server("0.0.0.0", FLAGS.port,
                                       wsgi.WSGIHandler())
    while self.keep_running:
      server.handle_request()

  def Stop(self):
    self.keep_running = False
    # Force a request so the socket leaves accept()
    urllib.urlopen(self.base_url + "/quitmenow").read()
    self.join()


class RunTestsInit(registry.InitHook):

  pre = ["AFF4InitHook", "ViewsInit"]

  # We cache all the AFF4 objects created by this fixture so its faster to
  # recreate it between tests.
  fixture_cache = None

  def Run(self):
    """Run the hook setting up fixture and security mananger."""
    # Install the mock security manager so we can trap errors in interactive
    # mode.
    data_store.DB.security_manager = test_lib.MockSecurityManager()
    self.token = data_store.ACLToken("Test", "Make fixtures.")
    self.token.supervisor = True

    if data_store.DB.__class__.__name__ == "FakeDataStore":
      self.RestoreFixtureFromCache()
    else:
      self.BuildFixture()

  def BuildFixture(self):
    logging.info("Making fixtures")

    # Make 10 clients
    for i in range(0, 10):
      test_lib.ClientFixture("C.%016X" % i, token=self.token)

  def RestoreFixtureFromCache(self):
    if RunTestsInit.fixture_cache is None:
      # Make a data store snapshot.
      db = data_store.DB.subjects
      data_store.DB.subjects = {}

      self.BuildFixture()
      (RunTestsInit.fixture_cache,
       data_store.DB.subjects) = (data_store.DB.subjects, db)

    # Restore the fixture from the cache
    data_store.DB.subjects.update(copy.deepcopy(RunTestsInit.fixture_cache))


def main(_):
  """Run the main test harness."""
  # Tests run the fake data store
  FLAGS.storage = FLAGS.test_data_store

  # Django does not like to be reconfigured - just ignore it.
  try:
    settings.configure(**DJANGO_SETTINGS)
  except RuntimeError:
    pass

  # Load up the tests after the environment has been configured.
  # pylint: disable=C6204,W0612
  from grr.gui.plugins import tests

  # We cannot import plugins until we have initialized Django, and we cannot
  # initialize Django until we have the flags. So we do this here.
  from grr.gui import gui_plugins
  # pylint: enable=C6204

  