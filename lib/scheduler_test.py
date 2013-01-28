#!/usr/bin/env python
# Copyright 2010 Google Inc.
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

"""Tests the data store abstraction."""


import time


from grr.client import conf
from grr.client import conf as flags
from grr.lib import data_store
# pylint: disable=unused-import
from grr.lib import rdfvalue
from grr.lib import rdfvalues
# pylint: enable=unused-import
from grr.lib import scheduler
from grr.lib import stats
from grr.lib import test_lib
from grr.proto import jobs_pb2

FLAGS = flags.FLAGS


class SchedulerTest(test_lib.GRRBaseTest):
  """Test the Task Scheduler abstraction."""

  def setUp(self):
    stats.STATS.Set("grr_task_retransmission_count", 0)

    test_lib.GRRBaseTest.setUp(self)
    self._current_mock_time = 1000.015
    self.old_time = time.time
    time.time = lambda: self._current_mock_time

  def tearDown(self):
    time.time = self.old_time

  def testSchedule(self):
    """Test the ability to schedule a task."""
    test_queue = "fooSchedule"
    task = scheduler.SCHEDULER.Task(queue=test_queue, ttl=5,
                                    value=jobs_pb2.GrrMessage(
                                        session_id="Test"))

    scheduler.SCHEDULER.Schedule([task], token=self.token)

    self.assert_(task.id > 0)
    self.assert_(task.id & 0xffffffff > 0)
    self.assertEqual((long(self._current_mock_time * 1000) & 0xffffffff) << 32,
                     task.id & 0xffffffff00000000)
    self.assertEqual(task.ttl, 5)
    value, ts = data_store.DB.Resolve(test_queue,
                                      "task:%08d" % task.id, token=self.token)

    self.assertEqual(value, task.SerializeToString())
    self.assert_(ts > 0)

    # Get a lease on the task
    tasks = scheduler.SCHEDULER.QueryAndOwn(
        test_queue, lease_seconds=100, token=self.token,
        limit=100, decoder=jobs_pb2.GrrMessage)

    self.assertEqual(len(tasks), 1)
    self.assertEqual(tasks[0].ttl, 4)

    self.assertEqual(tasks[0].value.session_id, "Test")

    # If we try to get another lease on it we should fail
    self._current_mock_time += 10
    tasks = scheduler.SCHEDULER.QueryAndOwn(
        test_queue, lease_seconds=100, token=self.token,
        limit=100, decoder=jobs_pb2.GrrMessage)

    self.assertEqual(len(tasks), 0)

    # However after 100 seconds this should work again
    self._current_mock_time += 110
    tasks = scheduler.SCHEDULER.QueryAndOwn(
        test_queue, lease_seconds=100, token=self.token,
        limit=100, decoder=jobs_pb2.GrrMessage)

    self.assertEqual(len(tasks), 1)
    self.assertEqual(tasks[0].ttl, 3)

    # Check now that after a few retransmits we drop the message
    for i in range(2, 0, -1):
      self._current_mock_time += 110
      tasks = scheduler.SCHEDULER.QueryAndOwn(
          test_queue, lease_seconds=100, token=self.token)

      self.assertEqual(len(tasks), 1)
      self.assertEqual(tasks[0].ttl, i)

    # The task is now gone
    self._current_mock_time += 110
    tasks = scheduler.SCHEDULER.QueryAndOwn(
        test_queue, lease_seconds=100, token=self.token)
    self.assertEqual(len(tasks), 0)

  def testTaskRetransmissionsAreCorrectlyAccounted(self):
    test_queue = "fooSchedule"
    task = scheduler.SCHEDULER.Task(queue=test_queue,
                                    value=jobs_pb2.GrrMessage(
                                        session_id="Test"))

    scheduler.SCHEDULER.Schedule([task], token=self.token)

    # Get a lease on the task
    tasks = scheduler.SCHEDULER.QueryAndOwn(
        test_queue, lease_seconds=100, token=self.token,
        limit=100, decoder=jobs_pb2.GrrMessage)

    self.assertEqual(len(tasks), 1)
    self.assertEqual(tasks[0].ttl, 4)

    self.assertEqual(stats.STATS.Get("grr_task_retransmission_count"), 0)

    # Get a lease on the task 100 seconds later
    self._current_mock_time += 110
    tasks = scheduler.SCHEDULER.QueryAndOwn(
        test_queue, lease_seconds=100, token=self.token,
        limit=100, decoder=jobs_pb2.GrrMessage)

    self.assertEqual(len(tasks), 1)
    self.assertEqual(tasks[0].ttl, 3)

    self.assertEqual(stats.STATS.Get("grr_task_retransmission_count"), 1)

  def testDelete(self):
    """Test that we can delete tasks."""

    test_queue = "fooDelete"
    task = scheduler.SCHEDULER.Task(queue=test_queue,
                                    value=jobs_pb2.GrrMessage(
                                        session_id="Test"))

    scheduler.SCHEDULER.Schedule([task], token=self.token)

    # Get a lease on the task
    tasks = scheduler.SCHEDULER.QueryAndOwn(
        test_queue, lease_seconds=100, token=self.token,
        limit=100, decoder=jobs_pb2.GrrMessage)

    self.assertEqual(len(tasks), 1)

    self.assertEqual(tasks[0].value.session_id, "Test")

    # Now delete the task
    scheduler.SCHEDULER.Delete(test_queue, tasks, token=self.token)

    # Should not exist in the table
    value, ts = data_store.DB.Resolve(test_queue,
                                      "task:%08d" % task.id, token=self.token)

    self.assertEqual(value, None)
    self.assertEqual(ts, 0)

    # If we try to get another lease on it we should fail - even after
    # expiry time.
    self._current_mock_time += 1000
    tasks = scheduler.SCHEDULER.QueryAndOwn(
        test_queue, lease_seconds=100, token=self.token,
        limit=100, decoder=jobs_pb2.GrrMessage)

    self.assertEqual(len(tasks), 0)

  def testReSchedule(self):
    """Test the ability to re-schedule a task."""
    test_queue = "fooReschedule"
    task = scheduler.SCHEDULER.Task(queue=test_queue, value=jobs_pb2.GrrMessage(
        session_id="Test"))

    scheduler.SCHEDULER.Schedule([task], token=self.token)

    # Get a lease on the task
    tasks = scheduler.SCHEDULER.QueryAndOwn(
        test_queue, lease_seconds=100, token=self.token,
        limit=100, decoder=jobs_pb2.GrrMessage)

    self.assertEqual(len(tasks), 1)

    # Record the task id
    original_id = tasks[0].id

    # If we try to get another lease on it we should fail
    tasks_2 = scheduler.SCHEDULER.QueryAndOwn(
        test_queue, lease_seconds=100, token=self.token,
        limit=100, decoder=jobs_pb2.GrrMessage)

    self.assertEqual(len(tasks_2), 0)

    # Now we reschedule it
    scheduler.SCHEDULER.Schedule(tasks, token=self.token)

    # The id should not change
    self.assertEqual(tasks[0].id, original_id)

    # If we try to get another lease on it we should not fail
    tasks = scheduler.SCHEDULER.QueryAndOwn(
        test_queue, lease_seconds=100, token=self.token,
        limit=100, decoder=jobs_pb2.GrrMessage)

    self.assertEqual(len(tasks), 1)

    # But the id should not change
    self.assertEqual(tasks[0].id, original_id)

  def testPriorityScheduling(self):
    test_queue = "fooReschedule"

    tasks = []
    for i in range(10):
      msg = jobs_pb2.GrrMessage(
          session_id="Test%d" % i,
          priority=i%3)

      tasks.append(scheduler.SCHEDULER.Task(queue=test_queue, value=msg))

    scheduler.SCHEDULER.Schedule(tasks, token=self.token)

    tasks = scheduler.SCHEDULER.QueryAndOwn(
        test_queue, lease_seconds=100, token=self.token,
        limit=3, decoder=jobs_pb2.GrrMessage)

    self.assertEqual(len(tasks), 3)
    for task in tasks:
      self.assertEqual(task.priority, 2)

    tasks = scheduler.SCHEDULER.QueryAndOwn(
        test_queue, lease_seconds=100, token=self.token,
        limit=3, decoder=jobs_pb2.GrrMessage)

    self.assertEqual(len(tasks), 3)
    for task in tasks:
      self.assertEqual(task.priority, 1)

    tasks = scheduler.SCHEDULER.QueryAndOwn(
        test_queue, lease_seconds=100, token=self.token,
        limit=100, decoder=jobs_pb2.GrrMessage)

    self.assertEqual(len(tasks), 4)
    for task in tasks:
      self.assertEqual(task.priority, 0)

    # Now for Query.
    tasks = scheduler.SCHEDULER.Query(
        test_queue, token=self.token,
        limit=100, decoder=jobs_pb2.GrrMessage)
    self.assertEqual(len(tasks), 10)
    self.assertEqual([task.priority for task in tasks],
                     [2, 2, 2, 1, 1, 1, 0, 0, 0, 0])


def main(argv):
  test_lib.main(argv)


if __name__ == "__main__":
  conf.StartMain(main)
