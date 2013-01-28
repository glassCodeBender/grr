#!/usr/bin/env python
# Copyright 2012 Google Inc.
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


"""Tests for grr.lib.flows.general.services."""



from grr.lib import aff4
from grr.lib import rdfvalue
from grr.lib import test_lib


class ServicesTest(test_lib.FlowTestsBaseclass):

  def testEnumerateRunningServices(self):

    class ClientMock(object):
      def EnumerateRunningServices(self, _):
        service = rdfvalue.Service(label='org.openbsd.ssh-agent',
                                   args='/usr/bin/ssh-agent -l')
        service.osx_launchd.sessiontype = 'Aqua'
        service.osx_launchd.lastexitstatus = 0
        service.osx_launchd.timeout = 30
        service.osx_launchd.ondemand = 1

        return [service]

    # Run the flow in the emulated way.
    for _ in test_lib.TestFlowHelper(
        'EnumerateRunningServices', ClientMock(), client_id=self.client_id,
        token=self.token):
      pass

    # Check the output file is created
    fd = aff4.FACTORY.Open(rdfvalue.RDFURN(self.client_id)
                           .Add('analysis/Services'),
                           token=self.token)

    self.assertEqual(fd.__class__.__name__, 'RDFValueCollection')
    jobs = list(fd)

    self.assertEqual(len(fd), 1)
    self.assertEqual(jobs[0].label, 'org.openbsd.ssh-agent')
    self.assertEqual(jobs[0].args, '/usr/bin/ssh-agent -l')
    self.assertIsInstance(jobs[0], rdfvalue.Service)
