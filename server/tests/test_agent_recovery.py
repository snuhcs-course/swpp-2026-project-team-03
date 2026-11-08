"""A temporary kubectl outage must not turn a running Pod into a failed song."""

import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


AGENT = Path(__file__).resolve().parents[1] / "agent" / "rocky_agent.py"
spec = importlib.util.spec_from_file_location("rocky_agent_recovery", AGENT)
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


class RecoveryTests(unittest.TestCase):
    def test_pod_lookup_retries_temporary_connection_failure(self):
        class Kubectl(agent.Kubectl):
            def __init__(self):
                self.calls = 0

            def run(self, *args, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    return subprocess.CompletedProcess(args, 1, "", "Unable to connect to the server")
                return subprocess.CompletedProcess(args, 0, '{"status":{"phase":"Running"}}', "")

        kube = Kubectl()
        with patch.object(agent.time, "sleep"):
            self.assertEqual(kube.pod("song")["status"]["phase"], "Running")
        self.assertEqual(kube.calls, 2)

    def test_unknown_pod_state_is_handed_off_without_deletion(self):
        class Api:
            done_calls = 0

            def done(self, *args):
                self.done_calls += 1
                return True

        class Kubectl:
            deleted = False

            def pod(self, name):
                raise RuntimeError("Unable to connect to the server")

            def delete(self, name):
                self.deleted = True

        api, kube = Api(), Kubectl()
        request = {"rid": "r", "job_id": "j", "kind": "midi", "pod": {"metadata": {"name": "song"}}}
        agent.handle(api, kube, request, 0, 0)
        self.assertEqual(api.done_calls, 0)
        self.assertFalse(kube.deleted)

    def test_confirmed_terminal_pod_is_deleted(self):
        class Api:
            def done(self, *args):
                return True

        class Kubectl:
            deleted = False

            def pod(self, name):
                return {"status": {"phase": "Succeeded"}}

            def logs(self, name):
                return "finished"

            def delete(self, name):
                self.deleted = True

        kube = Kubectl()
        request = {"rid": "r", "job_id": "j", "kind": "midi", "pod": {"metadata": {"name": "song"}}}
        agent.handle(Api(), kube, request, 0, 0)
        self.assertTrue(kube.deleted)

    def test_cancel_signal_deletes_pod_before_acknowledgement(self):
        events = []

        class Api:
            def heartbeat(self, rid, note):
                raise agent.PodCancellationRequested

            def done(self, rid, phase, log):
                events.append(("done", phase))
                return True

        class Kubectl:
            def pod(self, name):
                return {"status": {"phase": "Running"}}

            def delete(self, name):
                events.append(("delete", name))

        request = {"rid": "r", "job_id": "j", "kind": "midi", "pod": {"metadata": {"name": "song"}}}
        agent.handle(Api(), Kubectl(), request, 0, 0)
        self.assertEqual(events, [("delete", "song"), ("done", "Cancelled")])


if __name__ == "__main__":
    unittest.main()
