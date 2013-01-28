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

"""Test the webhistory flows."""

import os

from grr.client import client_utils_linux
from grr.client import client_utils_osx
from grr.client.client_actions import standard
from grr.lib import aff4
from grr.lib import rdfvalue
from grr.lib import test_lib
from grr.lib import utils


class TestWebHistory(test_lib.FlowTestsBaseclass):
  """Test the browser history flows."""

  def setUp(self):
    super(TestWebHistory, self).setUp()
    # Set up client info
    self.client = aff4.FACTORY.Open(self.client_id, mode="rw", token=self.token)
    self.client.Set(self.client.Schema.SYSTEM("Linux"))

    user_list = self.client.Schema.USER()
    user_list.Append(rdfvalue.User(username="test",
                                   full_name="test user",
                                   homedir="/home/test/",
                                   last_logon=250))
    self.client.AddAttribute(self.client.Schema.USER, user_list)
    self.client.Close()

    self.client_mock = test_lib.ActionMock("ReadBuffer", "HashFile",
                                           "TransferBuffer", "StatFile", "Find",
                                           "ListDirectory")

    # Mock the client to make it look like the root partition is mounted off the
    # test image. This will force all flow access to come off the image.
    def MockGetMountpoints():
      return {
          "/": (os.path.join(self.base_path, "test_img.dd"), "ext2")
          }
    self.orig_linux_mp = client_utils_linux.GetMountpoints
    self.orig_osx_mp = client_utils_osx.GetMountpoints
    client_utils_linux.GetMountpoints = MockGetMountpoints
    client_utils_osx.GetMountpoints = MockGetMountpoints

    # We wiped the data_store so we have to retransmit all blobs.
    standard.HASH_CACHE = utils.FastStore(100)

  def tearDown(self):
    super(TestWebHistory, self).tearDown()
    client_utils_linux.GetMountpoints = self.orig_linux_mp
    client_utils_osx.GetMountpoints = self.orig_osx_mp

  def testChromeHistoryFetch(self):
    """Test that downloading the Chrome history works."""
    # Run the flow in the simulated way
    for _ in test_lib.TestFlowHelper(
        "ChromeHistory", self.client_mock, check_flow_errors=False,
        client_id=self.client_id, username="test", token=self.token,
        output="analysis/testfoo", pathtype=rdfvalue.RDFPathSpec.Enum("TSK")):
      pass

    # Now check that the right files were downloaded.
    fs_path = "/home/test/.config/google-chrome/Default/History"

    # Check if the History file is created.
    output_path = aff4.ROOT_URN.Add(self.client_id).Add(
        "fs/tsk").Add(self.base_path.replace("\\", "/")).Add(
            "test_img.dd").Add(fs_path.replace("\\", "/"))

    fd = aff4.FACTORY.Open(output_path, token=self.token)
    self.assertTrue(fd.size > 20000)

    # Check for analysis file.
    output_path = aff4.ROOT_URN.Add(self.client_id).Add(
        "analysis/testfoo")
    fd = aff4.FACTORY.Open(output_path, token=self.token)
    self.assertTrue(fd.size > 20000)
    self.assertTrue(fd.Read(5000).find("funnycats.exe") != -1)

  def testFirefoxHistoryFetch(self):
    """Test that downloading the Firefox history works."""
    # Run the flow in the simulated way
    for _ in test_lib.TestFlowHelper(
        "FirefoxHistory", self.client_mock, check_flow_errors=False,
        client_id=self.client_id, username="test", token=self.token,
        output="analysis/ff_out", pathtype=rdfvalue.RDFPathSpec.Enum("TSK")):
      pass

    # Now check that the right files were downloaded.
    fs_path = "/home/test/.mozilla/firefox/adts404t.default/places.sqlite"
    # Check if the History file is created.
    output_path = aff4.ROOT_URN.Add(self.client_id).Add(
        "fs/tsk").Add("/".join([self.base_path.replace("\\", "/"),
                                "test_img.dd"])).Add(fs_path.replace("\\", "/"))
    fd = aff4.FACTORY.Open(output_path, token=self.token)
    self.assertTrue(fd.size > 20000)
    self.assertEquals(fd.read(15), "SQLite format 3")

    # Check for analysis file.
    output_path = aff4.ROOT_URN.Add(self.client_id).Add(
        "analysis/ff_out")
    fd = aff4.FACTORY.Open(output_path, token=self.token)
    self.assertTrue(fd.size > 400)
    data = fd.Read(1000)
    self.assertTrue(data.find("Welcome to Firefox") != -1)
    self.assertTrue(data.find("sport.orf.at") != -1)

  def testCacheGrep(self):
    """Test the Cache Grep plugin."""
    # Run the flow in the simulated way
    for _ in test_lib.TestFlowHelper(
        "CacheGrep", self.client_mock, check_flow_errors=False,
        client_id=self.client_id, grep_users=["test"],
        data_regex="ENIAC", output="analysis/cachegrep/{u}",
        pathtype=rdfvalue.RDFPathSpec.Enum("TSK"), token=self.token):
      pass

    # Check if the collection file was created.
    output_path = aff4.ROOT_URN.Add(self.client_id).Add(
        "analysis/cachegrep").Add("test")

    fd = aff4.FACTORY.Open(output_path, required_type="RDFValueCollection",
                           token=self.token)

    # There should be one hit.
    self.assertEquals(len(fd), 1)

    # Get the first hit.
    hits = list(fd)

    self.assertIsInstance(hits[0], rdfvalue.StatEntry)

    self.assertEquals(hits[0].pathspec.last.path,
                      "/home/test/.config/google-chrome/Default/Cache/data_1")
