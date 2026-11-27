"""Behavior tests for the agent-review controller.

Real cooperating components: temporary Git repositories with a bare origin,
the controller's state, OS lock, registry, publication ledger, archive commits
and checks. Only the external model (Codex/Claude) and GitHub boundaries are
stubbed, and every stubbed response below is a labeled simulation, not a model
exchange.

Run: python -m unittest discover -s agent_review -p "test_*.py" -v
"""
import argparse
import contextlib
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import stat
import tempfile
import threading
import time
import uuid
import unittest
from unittest import mock
from pathlib import Path

# Importable both as a top-level module (discover -s agent_review, or the gate's script path) and as
# agent_review.test_* from the repository root (python -m unittest agent_review/test_*.py), where the folder would
# otherwise shadow the controller module as a namespace package.
_HERE = __import__("os").path.dirname(__import__("os").path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
if getattr(sys.modules.get("agent_review"), "__file__", None) is None:
    sys.modules.pop("agent_review", None)
import agent_review as ar

HERE = Path(__file__).resolve().parent
OPUS = "claude-opus-5-5"
FOREGROUND_SESSION = "fixture-foreground-session"


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout.strip()


def receipt_path(ctl, head, gate, extra=(), stamp=None):
    """Where the controller names a receipt for (gate definition, argument list, stamp)."""
    stamp = stamp or ar.dt.datetime.now(ar.dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    decl = ctl.cfg["gates"][gate]
    argv = [a.replace("{repo_root}", ctl.state["repo_root"]) for a in decl["argv"]] + list(extra)
    return ctl.dir / "evidence" / (f"gate-{gate}-{head[:12]}-d{ar.gate_definition_id(decl)}-a{ar.argv_id(argv)}"
                                   f"-{stamp}.json")


TID = "0199a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b"
TID2 = "0199a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5c"


class FakeGitHub:
    """Simulated GitHub boundary backed by the temporary bare origin."""

    def __init__(self, env):
        self.env, self.comments_list, self.next_id = env, [], 1000
        self.lose_next_response = 0
        self.fail_next = 0
        self.pr_overrides = {}
        self.body = ""
        self.required = []
        self.check_results = {}
        self.poster = "owner"
        self.on_post = None

    def viewer(self):
        return self.pr_overrides.get("viewer", "owner")

    def pr(self, number):
        head = git(self.env.origin, "rev-parse", f"refs/heads/{self.env.branch}")
        data = {"number": number, "url": f"https://github.com/owner/repo/pull/{number}", "state": "OPEN",
                "isDraft": True, "headRefName": self.env.branch, "headRefOid": head, "baseRefName": "master",
                "author": {"login": "owner"}, "reviewRequests": [], "body": self.body, "isCrossRepository": False,
                "headRepository": {"name": "repo"}, "headRepositoryOwner": {"login": "owner"}}
        data.update({k: v for k, v in self.pr_overrides.items() if k != "viewer"})
        return data

    def comments(self, number):
        return [dict(c) for c in self.comments_list]

    def comment(self, comment_id):
        return next((dict(c) for c in self.comments_list if c["id"] == comment_id), None)

    def post_comment(self, number, body_file):
        if self.fail_next:
            self.fail_next -= 1
            raise ar.NotDelivered("simulated transient GitHub failure (request rejected; nothing stored)")
        body = Path(body_file).read_text(encoding="utf-8")
        self.next_id += 1
        record = {"id": self.next_id, "user": self.poster, "body": body, "url": f"https://example.test/c/{self.next_id}"}
        self.comments_list.append(record)
        if self.on_post:
            self.on_post(record)
        if self.lose_next_response:
            self.lose_next_response -= 1
            raise TimeoutError("simulated lost response after the server stored the comment")
        return {"id": record["id"], "url": record["url"], "user": record["user"]}

    def required_checks(self, branch):
        return list(self.required)

    def commit_checks(self, sha):
        return list(self.check_results.get(sha, []))

    def edit_body(self, number, body_file):
        self.body = Path(body_file).read_text(encoding="utf-8")

    def headings(self):
        return [c["body"].splitlines()[1] for c in self.comments_list]


class FakeReviewer:
    """Simulated Codex boundary. Each scripted item is a labeled simulated response."""

    def __init__(self):
        self.script, self.calls, self.prov = [], [], {}
        self.during_run = None

    @property
    def requested(self):
        return {"model": "gpt-6.2-astra", "effort": "high", "sandbox": "read-only"}

    def run(self, prompt, workdir, schema, result_path, events_path, stderr_path, timeout_s, skip_git=False,
            on_start=None):
        if on_start:
            on_start(None)  # simulated: no OS process
        item = self.script.pop(0)
        request = json.loads((Path(result_path).parent / "request.json").read_text(encoding="utf-8"))
        inbox = Path(workdir) / ".agent-review-inputs"
        guidance = inbox / "owner-guidance.md"
        amendments = inbox / "owner-amendments.md"
        self.calls.append({"request": request, "prompt": prompt, "workdir": str(workdir),
                           "inbox": sorted(p.relative_to(inbox).as_posix() for p in inbox.rglob("*") if p.is_file()),
                           "transcript": (inbox / "developer-tool-transcript.md").read_text(encoding="utf-8"),
                           "guidance": guidance.read_bytes() if guidance.is_file() else None,
                           "amendments": amendments.read_bytes() if amendments.is_file() else None,
                           "mission": (inbox / "mission.md").read_bytes() if (inbox / "mission.md").is_file() else None,
                           "prior": json.loads((inbox / "prior-findings.json").read_text(encoding="utf-8"))})
        assert Path(workdir).is_dir() and git(workdir, "rev-parse", "HEAD") == request["H"]
        for name in ("feature.diff", "developer-report.json", "prior-findings.json", "developer-tool-transcript.md",
                     "mission.md"):
            assert (inbox / name).is_file(), f"{name} missing from the reviewer's workspace"
        if self.during_run:
            self.during_run()
        thread = f"thread-{len(self.calls)}"
        self.prov[thread] = {"rollout_found": True, "observed_model": item.get("model", "gpt-6.2-astra"),
                             "observed_effort": item.get("effort", "high"),
                             "turn_models": [item.get("model", "gpt-6.2-astra")],
                             "turn_efforts": item.get("turn_efforts", ["high"]), "sandbox": "read-only",
                             "approval_policy": "never", "network": "restricted", "cli_version": "simulated",
                             "usage": None, "plan_type": None, "subagent_suspected": False, "source": "SIMULATED"}
        Path(stderr_path).write_text(item.get("stderr", ""), encoding="utf-8")
        Path(events_path).write_text(json.dumps({"type": "thread.started", "thread_id": thread}) + "\n", encoding="utf-8")
        if "raw" in item:
            Path(result_path).write_text(item["raw"], encoding="utf-8")
        else:
            result = review_result(request, item["decision"], item.get("findings", []), item.get("assessments", []))
            for key, value in item.get("override", {}).items():
                result[key] = value
            for key in item.get("drop", []):
                result.pop(key)
            Path(result_path).write_text(json.dumps(result), encoding="utf-8")
        return {"exit_code": item.get("exit_code", 0), "timed_out": False, "thread_id": thread, "duration_s": 0.1,
                "completed": item.get("completed", True), "failed": False}

    def provenance(self, thread_id, since=None):
        return self.prov.get(thread_id, {"rollout_found": False})


def finding(fid, blocks=True, category="defect"):
    return {"id": fid, "priority": "P1", "category": category, "blocks_readiness": blocks,
            "blocking_rationale": "simulated", "title": f"simulated finding {fid}", "trigger": "t", "expected": "e",
            "actual": "a", "location": {"file": "feature.txt", "line": 1}, "acceptance_ids": ["X1"],
            "requested_correction": "c", "requested_evidence": "v"}


def review_result(request, decision, findings=(), assessments=()):
    return {"schema_version": "agent-review.review.v1", "request_id": request["request_id"], "round": request["round"],
            "checkpoint_id": request["checkpoint_id"], "checkpoint_type": request["checkpoint_type"],
            "candidate_commit": request["H"], "decision": decision, "decision_rationale": "simulated response",
            "findings": list(findings),
            "prior_finding_assessments": [{"finding_id": a[0], "assessment": a[1],
                                           "rationale": a[2] if len(a) > 2 else "simulated"}
                                          for a in assessments],
            "evidence_assessment": {"inspected": ["feature.txt"], "executed_verification": [],
                                    "source_inspection_only": ["feature.txt"], "required_gaps": [], "limitations": []},
            "summary": {"delivered_behavior": "simulated", "scope_reviewed": "simulated", "pending_later_phase_work": [],
                        "unresolved_questions": [], "remaining_owner_review": ["simulated visual check"]}}


class FakeDeveloper:
    """Simulated Claude boundary: scripted headless actions commit real changes."""

    def __init__(self, env):
        self.env, self.script, self.calls, self.sessions = env, [], [], set()
        self.foreground = {"models": [OPUS], "efforts": ["high"], "permission_modes": ["default"]}
        self.exe = "simulated-claude"  # SIMULATED executable (resolved before any charge)
        self.shown = []  # SIMULATED tool results in the foreground session's transcript: (timestamp, text, is_error)
        self.transcript_error = None  # SIMULATED: an OSError raised when the transcript is read

    @property
    def requested(self):
        return {"model": "opus", "effort": "high"}

    def session_exists(self, session_id):
        return session_id in self.sessions

    def session_provenance(self, session_id, since=None):
        return {"found": True, "session_id": session_id, "source": "SIMULATED", **self.foreground}

    def session_delivered_parts(self, session_id, needle_sets, since_iso):
        if self.transcript_error:
            raise self.transcript_error
        since = ar.parse_iso(since_iso)
        found = [None] * len(needle_sets)
        for stamp, text, is_error in self.shown:
            for i, needles in enumerate(needle_sets):
                fresh = not since or ar.parse_iso(stamp) >= since
                if found[i] is None and not is_error and fresh and all(n in text for n in needles):
                    found[i] = stamp
        return found

    def show(self, text, is_error=False):
        """Simulate a command's output reaching the foreground session (a CLI-recorded tool result)."""
        self.shown.append((ar.now_iso(), text, is_error))

    def tool_transcript(self, session_id, since_iso):
        return f"# Developer tool transcript (SIMULATED)\n\nsession {session_id} since {since_iso}\n"

    def run(self, prompt, session_id, resume, cwd, log_path, stderr_path, soft_deadline_s, on_start=None,
            on_soft_deadline=None, grace_s=0, protected=None):
        self.calls.append({"session_id": session_id, "resume": resume, "prompt": prompt})
        Path(stderr_path).write_text("", encoding="utf-8")
        self.sessions.add(session_id)
        action = self.script.pop(0)
        if on_start and getattr(action, "start_pid", None):  # opt-in: simulate the process-start callback
            on_start(action.start_pid)
        report = action(self.env)
        model = getattr(action, "model", OPUS)
        return {"init_model": model, "api_key_source": "none", "session_id": getattr(action, "session", session_id),
                "main_models": [model], "result": "", "structured_output": report, "permission_denials": [],
                "model_usage": {}, "cost_usd": 0.0, "is_error": False, "subtype": getattr(action, "subtype", "success"),
                "exit_code": getattr(action, "exit_code", 0), "deadline_exceeded": False, "terminated": False,
                "duration_s": 0.1, "observed_effort": getattr(action, "efforts", ["high"]),
                "transcript_models": getattr(action, "transcript_models", [model])}


def report(env, checkpoint, dispositions=(), status="checkpoint_ready", restoration="not_applicable", validation=None):
    return {"schema_version": "agent-review.developer.v1", "status": status, "checkpoint_id": checkpoint,
            "candidate_commit": git(env.work, "rev-parse", "HEAD"), "summary": "simulated developer report",
            "validation": validation or [{"command": "python -m unittest", "required": True, "result": "pass",
                                          "duration": "1s", "scope_and_limits": "simulated"}],
            "dispositions": list(dispositions), "evidence_refs": [], "runtime_restoration": restoration,
            "blocker": None, "owner_decision_needed": None}


def fixed(fid, sha):
    return {"finding_id": fid, "disposition": "fixed", "commits": [sha], "evidence": "simulated focused test"}


class Env:
    def __init__(self, mode="foreground", max_rounds=None, cfg_overrides=None, plan=None, mission_text=None,
                 extra_files=None, extra_wf_files=None):
        # Plain mkdir (inherited ACLs), not tempfile.mkdtemp: on Windows mkdtemp applies an owner-only
        # ACL that the Codex sandbox identity cannot read, which would make the live smoke unrepresentative.
        root = Path(tempfile.gettempdir()) / f"agent-review-test-{uuid.uuid4().hex[:10]}"
        root.mkdir()
        self.root = root
        self._saved_env = {k: os.environ.get(k) for k in ("AGENT_REVIEW_HOME", "AGENT_REVIEW_HOST_DIR",
                                                          "CLAUDE_CODE_SESSION_ID")}
        os.environ["AGENT_REVIEW_HOME"] = str(root / "home")
        os.environ["AGENT_REVIEW_HOST_DIR"] = str(root / "host")  # explicit test isolation of host-wide claims
        os.environ["CLAUDE_CODE_SESSION_ID"] = FOREGROUND_SESSION
        self.origin, self.work, self.branch = root / "origin.git", root / "work", "codex/feature"
        subprocess.run(["git", "init", "--quiet", "--bare", "-b", "master", str(self.origin)], check=True)
        subprocess.run(["git", "clone", "--quiet", str(self.origin), str(self.work)], check=True, capture_output=True)
        for key, value in (("user.name", "Test"), ("user.email", "test@example.invalid"), ("core.autocrlf", "false")):
            git(self.work, "config", key, value)
        git(self.work, "checkout", "--quiet", "-b", "master")
        self.base_root = self.commit("README.md", "base\n", "base")
        for name, text in (extra_files or {}).items():
            self.commit(name, text, f"add {name}")
        git(self.work, "push", "--quiet", "origin", "master")
        git(self.work, "checkout", "--quiet", "-b", self.branch)
        self.commit("feature.txt", "v1\n", "feature v1")
        self.push()
        self.wf = root / "wf"
        shutil.copytree(HERE, self.wf, ignore=shutil.ignore_patterns("__pycache__", "test_*"))
        cfg = ar.read_json(HERE / "projects" / "kingmaker-gunslinger.json")
        cfg.update(project_id="t", repository="owner/repo", expected_actor="owner",
                   allowed_remote_urls=[git(self.work, "remote", "get-url", "origin")],
                   push_command=["git", "-C", "{repo_root}", "push", "--quiet", "origin", "HEAD:refs/heads/{branch}"],
                   state_root=str(root / "state"), runtime_lock_paths=[str(root / "runtime.lock")])
        cfg["limits"].update(retry_backoff_seconds=[0, 0], uncertain_send_window_seconds=0)
        cfg["required_gates"] = []  # fixtures opt into gates through their plan (or override this explicitly)
        for key, value in (cfg_overrides or {}).items():
            cfg[key] = value
        for rel, data in (extra_wf_files or {}).items():
            ar.atomic_write_json(self.wf / rel, data)
        ar.atomic_write_json(self.wf / "projects" / "test.json", cfg)
        plan = plan or {"schema_version": "agent-review.plan.v1", "mission_id": "fixture", "title": "Fixture mission",
                        "checkpoints": [{"id": "phase-1", "type": "intermediate", "scope": "s", "exit_conditions": ["e"]},
                                        {"id": "final", "type": "final", "scope": "s", "exit_conditions": ["e"]}]}
        ar.atomic_write_json(self.wf / "plans" / "test.json", plan)
        self.mission = root / "mission.md"
        self.mission.write_text(mission_text or "# Fixture mission\n", encoding="utf-8")
        self.gh, self.reviewer, self.developer = FakeGitHub(self), FakeReviewer(), FakeDeveloper(self)
        self.dir, _ = ar.enroll(self.args(mode=mode, max_rounds=max_rounds), github=self.gh, root=self.wf,
                                developer=self.developer)

    def args(self, **overrides):
        base = dict(project=str(self.wf / "projects" / "test.json"), worktree=str(self.work),
                    plan=str(self.wf / "plans" / "test.json"), mission=str(self.mission), mode="foreground", pr=7,
                    title=None, target=None, max_rounds=None, state_root=None)
        base.update(overrides)
        return argparse.Namespace(**base)

    def controller(self, cls=ar.Controller):
        return cls(self.dir, github=self.gh, reviewer=self.reviewer, developer=self.developer,
                   sleep=lambda s: None, workflow_root=self.wf)

    def commit(self, name, text, message):
        path = self.work / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        git(self.work, "add", name)
        git(self.work, "commit", "--quiet", "-m", message)
        return git(self.work, "rev-parse", "HEAD")

    def push(self):
        git(self.work, "push", "--quiet", "origin", f"HEAD:refs/heads/{self.branch}")

    def cleanup(self):
        subprocess.run(["git", "-C", str(self.work), "worktree", "prune"], capture_output=True)
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        def _writable(func, path, _exc):
            os.chmod(path, stat.S_IWRITE)  # git marks object files read-only on Windows
            func(path)
        for attempt in range(20):  # a killed controller's orphaned git child can hold the directory briefly
            try:
                shutil.rmtree(self.root, onexc=_writable)
                break
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(0.5)


class Base(unittest.TestCase):
    mode = "foreground"

    def setUp(self):
        self.env = Env(self.mode)
        self.addCleanup(self.env.cleanup)

    def submit(self, ctl, checkpoint, dispositions=()):
        """Foreground developer: submit a report, then run one review round."""
        error = ctl.accept_report(report(self.env, checkpoint, dispositions))
        self.assertIsNone(error)
        ctl.transition("review", "test submit")
        return ctl.review_round()

    def to_finalize(self, ctl):
        self.env.reviewer.script += [{"decision": "checkpoint_passed"}, {"decision": "ready_for_owner_review"}]
        self.submit(ctl, "phase-1")
        self.assertEqual("ready_for_owner_review", self.submit(ctl, "final"))


def run_env(mode, fn):
    env = Env(mode)
    try:
        return fn(env)
    finally:
        env.cleanup()


class HeadlessCycleTests(Base):
    mode = "headless"

    def test_intermediate_advances_then_findings_fix_and_owner_handoff(self):
        """WF03 (fixture), WF12, WF09 positive, WF11: full simulated cycle with a correction round."""
        env = self.env
        fix = {}

        def phase1(e):
            e.commit("phase1.txt", "p1\n", "phase 1")
            e.push()
            return report(e, "phase-1")

        def final_work(e):
            e.commit("final.txt", "f\n", "final work")
            e.push()
            return report(e, "final")

        def correct(e):
            fix["sha"] = e.commit("final.txt", "fixed\n", "fix R2-F1")
            e.push()
            return report(e, "final", [fixed("R2-F1", fix["sha"])])
        env.developer.script = [phase1, final_work, correct]
        env.reviewer.script = [{"decision": "checkpoint_passed"},
                               {"decision": "changes_required", "findings": [finding("R2-F1")]},
                               {"decision": "ready_for_owner_review", "assessments": [("R2-F1", "fix_verified")]}]
        ctl = env.controller()
        self.assertEqual("AWAITING_OWNER_REVIEW", ctl.run_loop())

        s = ctl.state
        self.assertEqual({"phase-1": 1, "final": 2}, s["rounds_completed"])
        self.assertEqual([False, True, True], [c["resume"] for c in env.developer.calls])
        self.assertEqual(1, len({c["session_id"] for c in env.developer.calls}))
        self.assertEqual(3, s["developer"]["invocations"])
        self.assertIn("R2-F1", env.developer.calls[2]["prompt"])
        self.assertTrue(all(r["status"] == "accepted" for r in s["rounds"]))
        headings = env.gh.headings()
        expected = ["Claude Opus — review request — round 1", "Codex GPT-6.2 Astra — review — round 1",
                    "Claude Opus — review request — round 2", "Codex GPT-6.2 Astra — review — round 2",
                    "Claude Opus — finding dispositions — round 2", "Claude Opus — review request — round 3",
                    "Codex GPT-6.2 Astra — review — round 3", "Workflow — awaiting owner review"]
        self.assertEqual(len(expected), len(headings))
        for want, got in zip(expected, headings):
            self.assertIn(want, got)
        source = s["ready_review"]["H"]
        archive = git(env.work, "rev-parse", "HEAD")
        self.assertNotEqual(source, archive)
        self.assertEqual(archive, git(env.origin, "rev-parse", f"refs/heads/{env.branch}"))
        self.assertEqual((True, []), ar.check_archive_only(ar.Git(env.work), source, archive, "docs/agent-reviews", 7,
                                                           s["archived"]))
        records = sorted(p.name for p in (env.work / "docs/agent-reviews/pr-7").iterdir())
        self.assertEqual(10, len(records))  # 7 published bodies + 3 review envelopes; final receipt not archived
        self.assertTrue(records[0].startswith("001-r01-request"))
        self.assertIn(f"Reviewed source `{source}`", env.gh.body)
        self.assertIn("no required status checks", env.gh.comments_list[-1]["body"])
        self.assertEqual("done", s["phase"])

    def test_headless_invocation_identity_and_budget(self):
        """F17: wrong session or non-zero exit is not accepted; budget is charged before launch."""
        env = self.env

        def other_session(e):
            return report(e, "phase-1")
        other_session.session = "11111111-2222-3333-4444-555555555555"
        env.developer.script = [other_session]
        ctl = env.controller()
        with self.assertRaises(ar.Stop) as stop:
            ctl.develop_step()
        self.assertIn("not the enrolled", stop.exception.reason)

        def failed_exit(e):
            return report(e, "phase-1")
        failed_exit.exit_code = 1
        env.developer.script = [failed_exit]
        self.assertIn("exit 1", env.controller().develop_step())

        def crash(e):
            raise RuntimeError("simulated host crash during the invocation")
        env.developer.script = [crash]
        ctl = env.controller()
        before = ctl.state["developer"]["invocations"]
        with self.assertRaises(RuntimeError):
            ctl.develop_step()
        restarted = env.controller()
        self.assertEqual(before + 1, restarted.state["developer"]["invocations"])
        env.developer.script = [lambda e: report(e, "phase-1")]
        restarted.develop_step()
        self.assertIn("interrupted", env.developer.calls[-1]["prompt"])

    def test_wrong_developer_model_blocks(self):
        def sonnet(e):
            return report(e, "phase-1")
        sonnet.model = "claude-sonnet-5-5"
        self.env.developer.script = [sonnet]
        with self.assertRaises(ar.Stop) as stop:
            self.env.controller().develop_step()
        self.assertEqual("BLOCKED", stop.exception.status)
        self.assertIn("claude-sonnet-5-5", stop.exception.reason)


class ArchiveCheckTests(Base):
    def test_only_new_plain_records_are_exempt(self):
        """WF09: transcript-only exemption is path-, operation-, mode- and PR-checked."""
        env, g = self.env, ar.Git(self.env.work)
        h = git(env.work, "rev-parse", "HEAD")
        a1 = env.commit("docs/agent-reviews/pr-7/001-r01-review.md", "x\n", "archive")
        self.assertEqual((True, []), ar.check_archive_only(g, h, a1, "docs/agent-reviews", 7))
        cases = {
            "edit earlier record": lambda: env.commit("docs/agent-reviews/pr-7/001-r01-review.md", "changed\n", "edit"),
            "source change": lambda: env.commit("feature.txt", "sneaky\n", "src"),
            "bad name": lambda: env.commit("docs/agent-reviews/pr-7/notes.txt", "x\n", "name"),
            "outside dir": lambda: env.commit("docs/other/001-r01-review.md", "x\n", "dir"),
            "other PR": lambda: env.commit("docs/agent-reviews/pr-8/002-r01-review.md", "x\n", "pr"),
        }
        for label, make in cases.items():
            with self.subTest(label):
                git(env.work, "reset", "--quiet", "--hard", a1)
                bad = make()
                ok, reasons = ar.check_archive_only(g, h, bad, "docs/agent-reviews", 7)
                self.assertFalse(ok)
                self.assertTrue(reasons)
        git(env.work, "reset", "--quiet", "--hard", a1)
        path = env.work / "docs/agent-reviews/pr-7/002-r01-envelope.json"
        path.write_text("{}\n", encoding="utf-8")
        git(env.work, "add", str(path))
        git(env.work, "update-index", "--chmod=+x", str(path))
        git(env.work, "commit", "--quiet", "-m", "exec")
        ok, reasons = ar.check_archive_only(g, h, git(env.work, "rev-parse", "HEAD"), "docs/agent-reviews", 7)
        self.assertFalse(ok)
        self.assertIn("mode", reasons[0])
        self.assertFalse(ar.check_archive_only(g, a1, h, "docs/agent-reviews", 7)[0])  # not an ancestor

    def test_inventory_binds_exemption_to_controller_records(self):
        """F13: a well-named record the controller did not write is not exempt."""
        env, g = self.env, ar.Git(self.env.work)
        h = git(env.work, "rev-parse", "HEAD")
        a = env.commit("docs/agent-reviews/pr-7/001-r01-review.md", "forged\n", "forged record")
        self.assertTrue(ar.check_archive_only(g, h, a, "docs/agent-reviews", 7)[0])
        ok, reasons = ar.check_archive_only(g, h, a, "docs/agent-reviews", 7, {})
        self.assertFalse(ok)
        self.assertIn("not a record the controller wrote", reasons[0])
        ok, reasons = ar.check_archive_only(g, h, a, "docs/agent-reviews", 7,
                                            {"docs/agent-reviews/pr-7/001-r01-review.md": ar.sha256_text("real\n")})
        self.assertIn("content differs", reasons[0])

    def test_unapproved_transcript_in_candidate_blocks_review(self):
        env = self.env
        env.commit("docs/agent-reviews/pr-7/001-r01-review.md", "forged\n", "developer wrote a record")
        env.push()
        ctl = env.controller()
        ctl.accept_report(report(env, "phase-1"))
        ctl.transition("review", "t")
        with self.assertRaises(ar.Stop) as stop:
            ctl.review_round()
        self.assertIn("unapproved transcript", stop.exception.reason)


class ArchiveRecoveryTests(Base):
    def test_push_failure_then_resume_reuses_the_same_archive_commit(self):
        """F12: archive intent is persisted; a failed push is retried without duplicating records."""
        env = self.env
        ctl = env.controller()
        self.to_finalize(ctl)
        good_push = list(ctl.cfg["push_command"])
        ctl.cfg["push_command"] = ["git", "-C", "{repo_root}", "push", "--quiet", "no-such-remote", "HEAD"]
        with self.assertRaises(ar.Stop) as stop:
            ctl.finalize()
        self.assertIn("resume retries", stop.exception.reason)
        pending = ctl.state["archive_pending"]
        self.assertIsNotNone(pending["commit"])
        restarted = env.controller()
        restarted.cfg["push_command"] = good_push
        self.assertEqual("AWAITING_OWNER_REVIEW", restarted.finalize())
        self.assertEqual(pending["commit"], git(env.origin, "rev-parse", f"refs/heads/{env.branch}"))
        self.assertEqual(1, len(restarted.state["archive_commits"]))
        names = [p.name for p in (env.work / "docs/agent-reviews/pr-7").iterdir()]
        self.assertEqual(len(names), len({n[4:] for n in names}))  # no record archived twice

class StaleCandidateTests(Base):
    def test_head_moving_during_review_makes_result_historical(self):
        """WF04: a moved material head cannot reuse the result."""
        env = self.env
        env.reviewer.script = [{"decision": "checkpoint_passed"}]

        def other_writer():
            env.commit("feature.txt", "other\n", "concurrent push")
            env.push()
        env.reviewer.during_run = other_writer
        ctl = env.controller()
        with self.assertRaises(ar.Stop) as stop:
            self.submit(ctl, "phase-1")
        self.assertEqual("PAUSED", stop.exception.status)
        self.assertEqual("historical", ctl.state["rounds"][-1]["status"])
        self.assertEqual({}, ctl.state["rounds_completed"])
        self.assertEqual(0, ctl.state["checkpoint_index"])
        self.assertEqual("develop", ctl.state["phase"])
        self.assertIn("HISTORICAL", env.gh.headings()[-1])
        # F2: the next round needs a report bound to the new head.
        ctl.transition("review", "t")
        self.assertEqual("needs_report", ctl.review_round())

    def test_preserved_result_is_rechecked_on_resume(self):
        """F1/F11: a validated-but-unpublished result is re-validated for freshness before acceptance."""
        env = self.env
        env.reviewer.script = [{"decision": "checkpoint_passed"}]
        ctl = env.controller()
        ctl.accept_report(report(env, "phase-1"))
        ctl.transition("review", "t")
        real_post, calls = env.gh.post_comment, {"n": 0}

        def post(number, body_file):
            calls["n"] += 1
            if calls["n"] >= 2:
                raise ar.NotDelivered("simulated outage (no connection; nothing stored)")
            return real_post(number, body_file)
        env.gh.post_comment = post
        with self.assertRaises(ar.Stop):
            ctl.review_round()
        env.gh.post_comment = real_post
        env.commit("feature.txt", "moved\n", "push while paused")
        env.push()
        restarted = env.controller()
        self.assertEqual("validated", restarted.active()["status"])
        with self.assertRaises(ar.Stop) as stop:
            restarted.review_round()
        self.assertIn("historical", stop.exception.reason)
        self.assertEqual({}, restarted.state["rounds_completed"])
        self.assertEqual(1, len(env.reviewer.calls))

    def test_material_commit_after_ready_invalidates_the_ready_result(self):
        """WF04/WF09/F2: a ready verdict does not cover a later material change."""
        env = self.env
        ctl = env.controller()
        self.to_finalize(ctl)
        env.commit("feature.txt", "late change\n", "material change after review")
        env.push()
        with self.assertRaises(ar.Stop) as stop:
            ctl.finalize()
        self.assertEqual("PAUSED", stop.exception.status)
        self.assertIn("material change", stop.exception.reason)
        self.assertEqual("develop", ctl.state["phase"])
        self.assertIsNone(ctl.state["ready_review"])
        self.assertEqual(1, len(ctl.state["superseded_ready"]))

    def test_moved_merge_base_invalidates_the_ready_result(self):
        """F1: a changed comparison input (merge base) cannot keep a ready verdict."""
        env = Env("foreground", extra_files={"second.txt": "2\n"})
        self.addCleanup(env.cleanup)
        ctl = env.controller()
        env.reviewer.script = [{"decision": "checkpoint_passed"}, {"decision": "ready_for_owner_review"}]
        ctl.accept_report(report(env, "phase-1"))
        ctl.transition("review", "t")
        ctl.review_round()
        ctl.accept_report(report(env, "final"))
        ctl.transition("review", "t")
        ctl.review_round()
        git(env.work, "push", "--quiet", "--force", "origin", f"{env.base_root}:refs/heads/master")
        with self.assertRaises(ar.Stop) as stop:
            ctl.finalize()
        self.assertIn("merge base moved", stop.exception.reason)
        self.assertEqual("develop", ctl.state["phase"])

    def test_report_for_unpushed_candidate_is_refused(self):
        env = self.env
        ctl = env.controller()
        env.commit("feature.txt", "local only\n", "unpushed")
        self.assertIsNone(ctl.accept_report(report(env, "phase-1")))
        ctl.transition("review", "test")
        with self.assertRaises(ar.Stop) as stop:
            ctl.review_round()
        self.assertIn("not the pushed branch head", stop.exception.reason)


class InvalidReviewTests(unittest.TestCase):
    """WF05: no failure shape produces a decision or readiness."""

    CASES = {
        "wrong model (fatal, no retry)": ([{"decision": "checkpoint_passed", "model": "gpt-6.1-sol"}], "not affirmatively gpt-6.2-astra", 1),
        "wrong effort (fatal)": ([{"decision": "checkpoint_passed", "effort": "low"}], "effort", 1),
        "contradictory turn effort (fatal)": ([{"decision": "checkpoint_passed", "turn_efforts": ["high", "low"]}], "effort", 1),
        "usage limit (fatal)": ([{"decision": "checkpoint_passed", "stderr": "You've hit your usage limit", "exit_code": 1}], "usage limit", 1),
        "malformed JSON": ([{"raw": "{not json"}] * 3, "malformed JSON", 3),
        "JSON null": ([{"raw": "null"}] * 3, "expected ['object']", 3),
        "truncated output": ([{"raw": '{"schema_version": "agent-review.review.v1", "decision": "check'}] * 3, "malformed", 3),
        "empty output": ([{"raw": ""}] * 3, "no final structured message", 3),
        "missing required field": ([{"decision": "checkpoint_passed", "drop": ["evidence_assessment"]}] * 3, "missing required", 3),
        "failed process": ([{"decision": "checkpoint_passed", "exit_code": 1}] * 3, "exited 1", 3),
        "mismatched request id": ([{"decision": "checkpoint_passed", "override": {"request_id": "forged"}}] * 3, "does not match", 3),
        "final decision on intermediate": ([{"decision": "ready_for_owner_review"}] * 3, "not valid for a intermediate", 3),
        "pass with blocking finding": ([{"decision": "checkpoint_passed", "findings": [finding("R1-F1")]}] * 3, "passing decision", 3),
        "blank inspected entry": ([{"decision": "checkpoint_passed", "override": {"evidence_assessment": {
            "inspected": ["  "], "executed_verification": [], "source_inspection_only": [], "required_gaps": [],
            "limitations": []}}}] * 3, "blank entry", 3),
        "duplicate JSON keys": ([{"raw": '{"decision": "checkpoint_passed", "decision": "blocked"}'}] * 3, "duplicate JSON keys", 3),
        "blank rationale": ([{"decision": "checkpoint_passed", "override": {"decision_rationale": "  "}}] * 3, "is blank", 3),
        "pass without inspected evidence": ([{"decision": "checkpoint_passed", "override": {"evidence_assessment": {
            "inspected": [], "executed_verification": [], "source_inspection_only": [], "required_gaps": [],
            "limitations": []}}}] * 3, "no inspected evidence", 3),
        "malformed new finding id": ([{"decision": "changes_required", "findings": [finding("X-1")]}] * 3, "does not use the form", 3),
        "pass with required evidence gap": ([{"decision": "checkpoint_passed", "override": {"evidence_assessment": {
            "inspected": [], "executed_verification": [], "source_inspection_only": [],
            "required_gaps": ["native observation missing"], "limitations": []}}}] * 3, "required evidence gaps", 3),
    }

    def test_invalid_reviews_block_without_counting_a_round(self):
        for label, (script, needle, attempts) in self.CASES.items():
            with self.subTest(label):
                def check(env):
                    env.reviewer.script = [dict(item) for item in script]
                    ctl = env.controller()
                    ctl.accept_report(report(env, "phase-1"))
                    ctl.transition("review", "test")
                    with self.assertRaises(ar.Stop) as stop:
                        ctl.review_round()
                    self.assertEqual("BLOCKED", stop.exception.status)
                    self.assertIn(needle, stop.exception.reason)
                    rnd = ctl.state["rounds"][-1]
                    self.assertEqual(attempts, len(rnd["attempts"]))
                    self.assertEqual({}, ctl.state["rounds_completed"])
                    self.assertNotIn("decision", rnd)
                    self.assertFalse(any("Codex GPT-6.2 Astra — review" in h for h in env.gh.headings()))
                run_env("foreground", check)

    def test_transient_failure_then_valid_review_counts_once_with_monotonic_attempts(self):
        env = Env("foreground")
        self.addCleanup(env.cleanup)
        env.reviewer.script = [{"raw": "{oops"}, {"decision": "checkpoint_passed"}]
        ctl = env.controller()
        ctl.accept_report(report(env, "phase-1"))
        ctl.transition("review", "test")
        self.assertEqual("checkpoint_passed", ctl.review_round())
        rnd = ctl.state["rounds"][-1]
        self.assertEqual([1, 2], [a["n"] for a in rnd["attempts"]])
        self.assertEqual({"phase-1": 1}, ctl.state["rounds_completed"])
        self.assertTrue((ctl.dir / "rounds" / "r01" / "envelope-1.json").exists())


class AssessmentValidationTests(unittest.TestCase):
    """F4: prior-finding assessments must be unique, pending, compatible and consistent."""

    CASES = {
        "duplicate": ([("R1-F1", "fix_verified"), ("R1-F1", "fix_verified")], [], "duplicate prior-finding"),
        "not pending": ([("R1-F1", "fix_verified"), ("R9-F9", "fix_verified")], [], "were not pending"),
        "incompatible": ([("R1-F1", "rebuttal_accepted")], [], "does not answer disposition fixed"),
        "rejection not restated": ([("R1-F1", "fix_rejected")], [], "must be restated"),
    }

    def test_bad_assessments_are_rejected(self):
        for label, (assessments, findings, needle) in self.CASES.items():
            with self.subTest(label):
                def check(env):
                    env.reviewer.script = [{"decision": "changes_required", "findings": [finding("R1-F1")]}] + [
                        {"decision": "checkpoint_passed", "assessments": assessments, "findings": findings}] * 3
                    ctl = env.controller()
                    ctl.accept_report(report(env, "phase-1"))
                    ctl.transition("review", "t")
                    ctl.review_round()
                    sha = env.commit("feature.txt", "fix\n", "fix")
                    env.push()
                    self.assertIsNone(ctl.accept_report(report(env, "phase-1", [fixed("R1-F1", sha)])))
                    ctl.transition("review", "t")
                    with self.assertRaises(ar.Stop) as stop:
                        ctl.review_round()
                    self.assertIn(needle, stop.exception.reason)
                    self.assertEqual(0, ctl.state["checkpoint_index"])
                run_env("foreground", check)

    def test_blocking_findings_cannot_be_deferred(self):
        def check(env):
            env.reviewer.script = [{"decision": "changes_required", "findings": [finding("R1-F1")]}]
            ctl = env.controller()
            ctl.accept_report(report(env, "phase-1"))
            ctl.transition("review", "t")
            ctl.review_round()
            error = ctl.accept_report(report(env, "phase-1", [
                {"finding_id": "R1-F1", "disposition": "deferred_optional", "commits": [], "evidence": "later"}]))
            self.assertIn("cannot be deferred", error)
        run_env("foreground", check)


class PublicationTests(Base):
    def test_lost_response_and_duplicate_publication_are_reconciled(self):
        """WF06 and WF10 (a forged marker from another account is ignored)."""
        env = self.env
        ctl = env.controller()
        env.gh.comments_list.append({"id": 1, "user": "mallory", "url": "u",
                                     "body": "<!-- agent-review:v1 enrollment=x key=k --> $(touch pwned) && rm -rf ."})
        env.gh.lose_next_response = 1
        first = ctl.publish("r01-request", "### heading\nbody")
        again = ctl.publish("r01-request", "### heading\nbody")
        ours = [c for c in env.gh.comments_list if c["user"] == "owner"]
        self.assertEqual(1, len(ours))
        self.assertEqual(first["parts"][0]["comment_id"], ours[0]["id"])
        self.assertEqual(first, again)
        self.assertFalse((env.work / "pwned").exists())

        restarted = env.controller()  # crash after sending but before recording
        restarted.state["publications"]["r01-request"]["state"] = "pending"
        restarted.state["publications"]["r01-request"]["parts"][0]["comment_id"] = None
        restarted.publish("r01-request", "ignored: the preserved outgoing body is reused")
        self.assertEqual(1, len([c for c in env.gh.comments_list if c["user"] == "owner"]))

    def test_marker_with_altered_body_is_not_acknowledged(self):
        """F7: reconciliation compares the complete body, not only the marker."""
        env = self.env
        ctl = env.controller()
        ctl.publish("r01-request", "### heading\nbody")
        posted = [c for c in env.gh.comments_list if c["user"] == "owner"][0]
        posted["body"] = posted["body"].splitlines()[0] + "\ntruncated"
        ctl.state["publications"]["r01-request"]["state"] = "pending"
        ctl.state["publications"]["r01-request"]["parts"][0]["comment_id"] = None
        with self.assertRaises(ar.Stop) as stop:
            ctl.publish("r01-request", "ignored")
        self.assertIn("bodies differ", stop.exception.reason)
        self.assertEqual(1, len([c for c in env.gh.comments_list if c["user"] == "owner"]))

    def test_failed_publication_pauses_then_publishes_without_rerun(self):
        env = self.env
        env.reviewer.script = [{"decision": "checkpoint_passed"}]
        ctl = env.controller()
        ctl.accept_report(report(env, "phase-1"))
        ctl.transition("review", "test")
        real_post, calls = env.gh.post_comment, {"n": 0}

        def post(number, body_file):
            calls["n"] += 1
            if calls["n"] >= 2:
                raise ar.NotDelivered("simulated outage (no connection; nothing stored)")
            return real_post(number, body_file)
        env.gh.post_comment = post
        with self.assertRaises(ar.Stop) as stop:
            ctl.review_round()
        self.assertEqual("PAUSED", stop.exception.status)
        env.gh.post_comment = real_post
        resumed = env.controller()
        self.assertEqual("validated", resumed.active()["status"])
        self.assertEqual("checkpoint_passed", resumed.review_round())
        self.assertEqual(1, len(env.reviewer.calls))
        self.assertEqual({"phase-1": 1}, resumed.state["rounds_completed"])
        self.assertEqual("accepted", resumed.state["rounds"][0]["status"])

    def test_long_bodies_are_split_with_markers(self):
        ctl = self.env.controller()
        record = ctl.publish("big", "x" * (ar.COMMENT_LIMIT + 10))
        self.assertEqual(2, len(record["parts"]))
        self.assertTrue(all(c["body"].startswith("<!-- agent-review:v1") for c in self.env.gh.comments_list))


class StopResumeLockTests(Base):
    mode = "headless"

    def test_stop_then_resume_preserves_session_rounds_and_publications(self):
        """WF07."""
        env = self.env

        def phase1(e):
            e.commit("phase1.txt", "p1\n", "phase 1")
            e.push()
            (e.dir / "STOP").write_text("owner request\n", encoding="utf-8")  # owner runs `stop` mid-invocation
            return report(e, "phase-1")

        def final_work(e):
            e.commit("final.txt", "f\n", "final")
            e.push()
            return report(e, "final")
        env.developer.script = [phase1, final_work]
        env.reviewer.script = [{"decision": "checkpoint_passed"}, {"decision": "ready_for_owner_review"}]
        ctl = env.controller()
        with self.assertRaises(ar.Stop) as stop:
            ctl.run_loop()
        self.assertEqual("PAUSED", stop.exception.status)
        self.assertEqual("review", ctl.state["phase"])
        posted_before = len(env.gh.comments_list)

        restarted = env.controller()  # new process
        self.assertEqual("AWAITING_OWNER_REVIEW", restarted.resume("owner resumed"))
        self.assertEqual([False, True], [c["resume"] for c in env.developer.calls])
        self.assertEqual(1, len({c["session_id"] for c in env.developer.calls}))
        self.assertEqual({"phase-1": 1, "final": 1}, restarted.state["rounds_completed"])
        self.assertGreater(len(env.gh.comments_list), posted_before)

    def test_os_lock_is_exclusive_and_survives_dead_holders(self):
        """F8: one writer per branch; a dead holder's record never blocks."""
        ctl = self.env.controller()
        with ctl.lock("run") as held:
            with self.assertRaises(ar.UsageError):
                with self.env.controller().lock("review"):
                    pass
            self.assertEqual(os.getpid(), json.loads(held.holder.read_text(encoding="utf-8"))["pid"])
        lock = ctl.lock("run")
        lock.holder.write_text(json.dumps({"pid": 999999, "host": socket.gethostname(), "command": "run"}),
                               encoding="utf-8")
        with lock:
            self.assertEqual(os.getpid(), json.loads(lock.holder.read_text(encoding="utf-8"))["pid"])
        self.assertFalse(lock.holder.exists())

    def test_running_developer_session_is_never_resumed_concurrently(self):
        ctl = self.env.controller()
        ctl.state["developer"]["active_pid"] = os.getpid()
        with self.assertRaises(ar.Stop) as stop:
            ctl.develop_step()
        self.assertIn("still running", stop.exception.reason)
        with self.assertRaises(ar.Stop):
            ctl.archive("manual")
        self.assertEqual([], self.env.developer.calls)

    def test_operational_failure_is_persisted_as_a_visible_stop(self):
        """F18."""
        ctl = self.env.controller()

        def boom():
            raise ar.CommandError(["gh", "api"], subprocess.CompletedProcess([], 1, "", "simulated network failure"))
        self.assertEqual(ar.EXIT_PAUSED, ar.guarded(ctl, "run", boom))
        persisted = ar.read_json(self.env.dir / "state.json")
        self.assertEqual("PAUSED", persisted["status"])
        self.assertIn("operational failure", persisted["status_reason"])
        self.assertIn("Workflow — paused", self.env.gh.headings()[-1])


class LimitTests(Base):
    def test_round_cap_blocks_visibly(self):
        """WF08: exhausted limits yield a visible blocked status."""
        env = Env("foreground", max_rounds=1)
        self.addCleanup(env.cleanup)
        env.reviewer.script = [{"decision": "changes_required", "findings": [finding("R1-F1")]}]
        ctl = env.controller()
        ctl.accept_report(report(env, "phase-1"))
        ctl.transition("review", "t")
        with self.assertRaises(ar.Stop) as stop:  # R1-F15: the cap stops with the last allowed review itself
            ctl.review_round()
        self.assertIn("review-round cap", stop.exception.reason)
        on_disk = ar.read_json(env.dir / "state.json")
        self.assertEqual(("BLOCKED", "accepted"), (on_disk["status"], on_disk["rounds"][-1]["status"]))
        self.assertEqual(["R1-F1"], on_disk["pending_findings"])  # preserved for an owner-authorized extension
        ctl.verify_inputs()
        ctl.publish_status(stop.exception.status, stop.exception.reason)
        self.assertIn("Workflow — blocked", env.gh.headings()[-1])

    def test_missing_dispositions_bad_citations_and_failing_required_validation_are_refused(self):
        env = self.env
        env.reviewer.script = [{"decision": "changes_required", "findings": [finding("R1-F1")]}]
        ctl = env.controller()
        self.submit(ctl, "phase-1")
        self.assertIn("missing dispositions", ctl.accept_report(report(env, "phase-1")))
        self.assertIn("without a commit", ctl.accept_report(report(env, "phase-1", [
            {"finding_id": "R1-F1", "disposition": "fixed", "commits": [], "evidence": "x"}])))
        self.assertIn("not in the candidate history", ctl.accept_report(report(env, "phase-1", [fixed("R1-F1", "0" * 40)])))
        self.assertIn("unknown findings", ctl.accept_report(report(env, "phase-1", [
            {"finding_id": "R1-F1", "disposition": "rebutted", "commits": [], "evidence": "x"},
            {"finding_id": "NOPE", "disposition": "rebutted", "commits": [], "evidence": "x"}])))
        failing = [{"command": "focused gate", "required": True, "result": "fail", "duration": "1s", "scope_and_limits": "x"}]
        self.assertIn("required validation", ctl.accept_report(report(env, "phase-1", validation=failing)))

    def test_no_progress_on_unchanged_candidate_blocks(self):
        env = self.env
        env.reviewer.script = [{"decision": "changes_required", "findings": [finding("R1-F1")]},
                               {"decision": "changes_required", "findings": [finding("R1-F1")],
                                "assessments": [("R1-F1", "rebuttal_rejected")]}]
        ctl = env.controller()
        self.submit(ctl, "phase-1")
        with self.assertRaises(ar.Stop) as stop:
            self.submit(ctl, "phase-1", [{"finding_id": "R1-F1", "disposition": "rebutted", "commits": [],
                                          "evidence": "simulated rebuttal"}])
        self.assertIn("no progress", stop.exception.reason)
        self.assertEqual("accepted", ctl.state["rounds"][-1]["status"])

    def test_pending_restoration_unresolved_findings_and_required_checks_prevent_readiness(self):
        env = self.env
        ctl = env.controller()
        with self.assertRaises(ar.Stop) as stop:
            ctl.accept_report(report(env, "phase-1", restoration="pending"))
        self.assertIn("restoration", stop.exception.reason)
        head = git(env.work, "rev-parse", "HEAD")
        base = git(env.work, "merge-base", head, "origin/master")
        env.gh.required = ["ci/test"]
        ctl.state.update(checkpoint_index=1, ready_review={"round": 1, "H": head, "B": base, "M": base, "summary": {}},
                         findings={"R1-F1": {"blocks_readiness": True, "status": "open"}})
        reasons, _ = ctl.readiness(head)
        self.assertTrue(any("R1-F1" in r for r in reasons))
        self.assertTrue(any("restoration" in r for r in reasons))
        self.assertTrue(any("ci/test" in r for r in reasons))
        env.gh.check_results[head] = [{"name": "ci/test", "status": "completed", "conclusion": "success"}]
        self.assertFalse(any("ci/test" in r for r in ctl.readiness(head)[0]))


class TargetValidationTests(Base):
    def test_wrong_repository_branch_actor_or_pr_cannot_enroll_or_dispatch(self):
        """WF10, F15."""
        env = self.env
        args = env.args(state_root=str(env.root / "state2"))
        git(env.work, "remote", "set-url", "origin", "https://github.com/someone/else.git")
        with self.assertRaises(ar.UsageError):
            ar.enroll(args, github=env.gh, root=env.wf, developer=env.developer)
        git(env.work, "remote", "set-url", "origin", str(env.origin))
        git(env.work, "checkout", "--quiet", "-b", "feature/not-allowed")
        with self.assertRaises(ar.UsageError):
            ar.enroll(args, github=env.gh, root=env.wf, developer=env.developer)
        git(env.work, "checkout", "--quiet", env.branch)
        env.gh.pr_overrides = {"viewer": "mallory"}
        with self.assertRaises(ar.UsageError):
            ar.enroll(args, github=env.gh, root=env.wf, developer=env.developer)
        env.gh.pr_overrides = {}
        good = env.gh.pr(7)
        self.assertEqual([], ar.pr_identity_problems(good, "owner/repo", 7, env.branch, "master"))
        for override in ({"headRefName": "codex/other"}, {"baseRefName": "release"}, {"isCrossRepository": True},
                         {"headRepositoryOwner": {"login": "fork-owner"}}, {"number": 8},
                         {"url": "https://github.com/evil/repo/pull/7"}):
            with self.subTest(override):
                # The same checker gates enrollment and every mutation (verify_inputs).
                self.assertTrue(ar.pr_identity_problems({**good, **override}, "owner/repo", 7, env.branch, "master"))
                env.gh.pr_overrides = override
                with self.assertRaises(ar.UsageError):
                    env.controller().verify_inputs()

    def test_writer_exclusion_does_not_depend_on_the_selected_home(self):
        """R1-F8: a controller using another AGENT_REVIEW_HOME cannot enroll or lock the same worktree."""
        env = self.env
        ctl = env.controller()
        original = os.environ["AGENT_REVIEW_HOME"]
        with ctl.lock("run"):  # held under the original home
            os.environ["AGENT_REVIEW_HOME"] = str(env.root / "other-home")
            with self.assertRaises(ar.UsageError):  # the other home's lock is free; the worktree's lock is not
                with ar.writer_lock("owner/repo", env.branch, str(env.work), "review"):
                    pass
            os.environ["AGENT_REVIEW_HOME"] = original
        os.environ["AGENT_REVIEW_HOME"] = str(env.root / "other-home")
        with self.assertRaises(ar.UsageError) as refused:
            ar.enroll(env.args(), github=env.gh, root=env.wf, developer=env.developer)
        self.assertIn("active enrollment", str(refused.exception))

    def test_second_enrollment_for_active_branch_is_refused_across_state_roots(self):
        env = self.env
        with self.assertRaises(ar.UsageError) as refused:
            ar.enroll(env.args(state_root=str(env.root / "elsewhere")), github=env.gh, root=env.wf, developer=env.developer)
        self.assertIn("active enrollment", str(refused.exception))

    def test_configuration_comes_from_the_installed_root_and_owner_policy(self):
        """F14."""
        env = self.env
        outside = env.root / "evil.json"
        shutil.copy2(env.wf / "projects" / "test.json", outside)
        with self.assertRaises(ar.UsageError):
            ar.load_project(str(outside), env.wf)
        bad = ar.read_json(env.wf / "projects" / "test.json")
        bad["reviewer"]["model"] = "gpt-6.1-sol"
        ar.atomic_write_json(env.wf / "projects" / "bad.json", bad)
        with self.assertRaises(ar.UsageError) as refused:
            ar.load_project("bad", env.wf)
        self.assertIn("owner policy", str(refused.exception))
        with self.assertRaises(ar.UsageError):
            ar.find_enrollment(str(env.dir))

    def test_foreground_reports_are_bound_to_the_enrolled_session(self):
        """F16."""
        env = self.env
        ctl = env.controller()
        os.environ["CLAUDE_CODE_SESSION_ID"] = "someone-else"
        with self.assertRaises(ar.UsageError):
            ctl.accept_report(report(env, "phase-1"))
        os.environ["CLAUDE_CODE_SESSION_ID"] = FOREGROUND_SESSION
        env.developer.foreground = {"models": [OPUS, "claude-sonnet-5-5"], "efforts": ["high"]}
        with self.assertRaises(ar.Stop) as stop:
            ctl.accept_report(report(env, "phase-1"))
        self.assertIn("sonnet", stop.exception.reason)
        env.developer.foreground = {"models": [OPUS], "efforts": ["high", "low"]}
        with self.assertRaises(ar.Stop):
            ctl.accept_report(report(env, "phase-1"))
        env.developer.foreground = {"models": [OPUS], "efforts": ["high"], "permission_modes": ["default"]}
        self.assertIsNone(ctl.accept_report(report(env, "phase-1")))
        self.assertEqual(FOREGROUND_SESSION, ctl.state["last_report_provenance"]["session_id"])

    def test_handoff_requires_draft_without_requested_reviewers(self):
        """WF11."""
        env = self.env
        ctl = env.controller()
        self.to_finalize(ctl)
        env.gh.pr_overrides = {"reviewRequests": [{"login": "someone"}]}
        with self.assertRaises(ar.Stop) as stop:
            ctl.finalize()
        self.assertIn("reviewers", stop.exception.reason)
        env.gh.pr_overrides = {"isDraft": False}
        with self.assertRaises(ar.Stop) as stop:
            ctl.finalize()
        self.assertIn("no longer a draft", stop.exception.reason)
        env.gh.pr_overrides = {}
        self.assertEqual("AWAITING_OWNER_REVIEW", ctl.finalize())

    def test_superseded_handoff_is_detected_and_reopened(self):
        """F22."""
        env = self.env
        ctl = env.controller()
        self.to_finalize(ctl)
        self.assertEqual("AWAITING_OWNER_REVIEW", ctl.finalize())
        self.assertTrue(ctl.status(remote=True)["handoff_current"])
        env.commit("feature.txt", "after handoff\n", "material push after handoff")
        env.push()
        self.assertFalse(ctl.status(remote=True)["handoff_current"])
        ctl.verify_inputs()
        self.assertIn("ACTIVE", ctl.resume("owner pushed a change"))
        self.assertEqual("develop", ctl.state["phase"])
        self.assertEqual(1, len(ctl.state["superseded_handoffs"]))
        self.assertIn("superseded", env.gh.body)
        self.assertIn("Workflow — reopened", env.gh.headings()[-1])

    def test_changed_mission_snapshot_or_workflow_version_stops(self):
        """F21 and workflow activation."""
        env = self.env
        ctl = env.controller()
        ctl.verify_inputs()
        (env.wf / "prompts" / "reviewer.md").write_text("changed rules\n", encoding="utf-8")
        with self.assertRaises(ar.Stop) as stop:
            env.controller().verify_inputs()
        self.assertIn("activate", stop.exception.reason)
        ar.atomic_write_json(env.wf / "plans" / "another.json", {"x": 1})  # plans don't change the fingerprint
        fresh = env.controller()
        fresh.state["workflow"]["fingerprint"] = ar.workflow_fingerprint(env.wf)
        fresh.verify_inputs()
        Path(fresh.state["mission"]["snapshot"]).write_text("# Tampered snapshot\n", encoding="utf-8")
        with self.assertRaises(ar.Stop) as stop:
            fresh.verify_inputs()
        self.assertEqual("BLOCKED", stop.exception.status)
        self.assertIn("snapshot", stop.exception.reason)


class GeneralRepositoryTests(unittest.TestCase):
    """Any repository under C:\\Dev: built-in push, composed permissions, onboarding, generic plan."""

    def setUp(self):
        self.env = Env("foreground", cfg_overrides={"push_command": None})
        self.addCleanup(self.env.cleanup)

    def test_builtin_guarded_push_refuses_unsafe_pushes(self):
        env = self.env
        ctl = env.controller()
        head = env.commit("feature.txt", "v2\n", "v2")
        self.assertEqual(head, ar.guarded_push(ctl.state, ctl.cfg))
        self.assertEqual(head, git(env.origin, "rev-parse", f"refs/heads/{env.branch}"))
        (env.work / "feature.txt").write_text("dirty\n", encoding="utf-8")
        with self.assertRaises(ar.UsageError):
            ar.guarded_push(ctl.state, ctl.cfg)
        git(env.work, "checkout", "--", "feature.txt")
        git(env.work, "reset", "--quiet", "--hard", "HEAD~1")
        env.commit("feature.txt", "diverged\n", "diverged")
        with self.assertRaises(ar.UsageError) as refused:
            ar.guarded_push(ctl.state, ctl.cfg)
        self.assertIn("not an ancestor", str(refused.exception))
        git(env.work, "reset", "--quiet", "--hard", head)
        env.commit("config.txt", f"token=ghp_{'b' * 36}\n", "oops")
        with self.assertRaises(ar.UsageError) as refused:
            ar.guarded_push(ctl.state, ctl.cfg)
        self.assertIn("credential", str(refused.exception))
        self.assertEqual(head, git(env.origin, "rev-parse", f"refs/heads/{env.branch}"))
        git(env.work, "reset", "--quiet", "--hard", head)
        env.commit("feature.txt", "v3\n", "v3")
        git(env.work, "config", "remote.origin.pushurl", str(env.root / "elsewhere.git"))  # R3-F5
        with self.assertRaises(ar.UsageError) as refused:
            ar.guarded_push(ctl.state, ctl.cfg)
        self.assertIn("push destination", str(refused.exception))
        self.assertEqual(head, git(env.origin, "rev-parse", f"refs/heads/{env.branch}"))

    def test_archive_uses_builtin_push_without_a_wrapper(self):
        env = self.env
        ctl = env.controller()
        env.reviewer.script = [{"decision": "checkpoint_passed"}, {"decision": "ready_for_owner_review"}]
        for checkpoint in ("phase-1", "final"):
            ctl.accept_report(report(env, checkpoint))
            ctl.transition("review", "t")
            ctl.review_round()
        self.assertEqual("AWAITING_OWNER_REVIEW", ctl.finalize())
        self.assertEqual(git(env.work, "rev-parse", "HEAD"), git(env.origin, "rev-parse", f"refs/heads/{env.branch}"))

    def test_developer_settings_are_composed_and_pinned(self):
        env = self.env
        ctl = env.controller()
        settings = ar.read_json(env.controller().settings_path)["permissions"]
        helper = f"{env.wf.resolve().as_posix()}/agent_review.py"
        self.assertIn(f"Bash(python {helper} push --enrollment {ctl.state['enrollment_id']})", settings["allow"])
        self.assertIn(f"Bash(python {helper} run*)", settings["deny"])
        self.assertIn("Edit(./docs/agent-reviews/**)", settings["deny"])
        self.assertIn("Bash(dotnet test *)", settings["allow"])  # project extra
        self.assertIn(helper, ctl.render("developer-start.md", {**ctl.common_fields(), "push_command":
                      " ".join(ar.push_argv(ctl.cfg, env.wf, ctl.state["enrollment_id"]))}))
        ctl.verify_inputs()
        env.controller().settings_path.write_text('{"permissions": {"allow": ["Bash(*)"]}}', encoding="utf-8")
        with self.assertRaises(ar.Stop) as stop:
            ctl.verify_inputs()
        self.assertIn("permission file", stop.exception.reason)

    def test_init_project_onboards_a_repository_into_the_machine_home(self):
        env = self.env

        class FakeRepoGitHub:
            def __init__(self, slug):
                self.slug = slug

            def viewer(self):
                return "owner"

            def _json(self, *args):
                return {"defaultBranchRef": {"name": "main"}}
        git(env.work, "remote", "set-url", "origin", "https://github.com/owner/another-repo.git")
        (env.work / "CLAUDE.md").write_text("# instructions\n", encoding="utf-8")
        args = argparse.Namespace(repo=str(env.work), name="another-repo", branch_prefix="claude/", allow=["npm test"],
                                  push_command=None, claude_config_dir=None, force=False)
        path, cfg = ar.init_project(args, root=env.wf, github_factory=FakeRepoGitHub)
        self.assertEqual(Path(os.environ["AGENT_REVIEW_HOME"]) / "projects" / "another-repo.json", path)
        self.assertEqual(("owner/another-repo", "main", "owner"),
                         (cfg["repository"], cfg["default_target_branch"], cfg["expected_actor"]))
        self.assertTrue(re.match(cfg["branch_pattern"], "claude/new-feature"))
        self.assertFalse(re.match(cfg["branch_pattern"], "main"))
        self.assertEqual(["CLAUDE.md"], cfg["instructions"])
        self.assertIn("Bash(npm test*)", cfg["developer"]["permissions"]["allow"])
        self.assertNotIn("push_command", cfg)
        self.assertEqual(cfg, ar.load_project("another-repo", env.wf))
        with self.assertRaises(ar.UsageError):
            ar.init_project(args, root=env.wf, github_factory=FakeRepoGitHub)  # no silent overwrite

    def test_generic_plan_takes_identity_from_the_mission_file(self):
        plan = ar.load_plan("single")
        named = ar.plan_for_mission(plan, Path("C:/Dev/x/ADD-SEARCH-MISSION.md"))
        self.assertEqual(("add-search-mission", "ADD-SEARCH-MISSION"), (named["mission_id"], named["title"]))
        self.assertEqual("black-tentacles", ar.plan_for_mission(ar.load_plan("black-tentacles"), Path("m.md"))["mission_id"])


class RoundTwoRegressionTests(Base):
    """Focused regressions for the round-2 review findings (publication, recovery, identity, permissions, readiness)."""

    def submit_with(self, ctl, checkpoint, dispositions=(), evidence=()):
        r = report(self.env, checkpoint, dispositions)
        r["evidence_refs"] = list(evidence)
        self.assertIsNone(ctl.accept_report(r))
        ctl.transition("review", "t")
        return ctl.review_round()

    def test_wrapper_projects_cannot_use_the_builtin_helper(self):
        """R1-F19."""
        ctl = self.env.controller()
        with self.assertRaises(ar.UsageError) as refused:
            ar.guarded_push(ctl.state, ctl.cfg)
        self.assertIn("own push wrapper", str(refused.exception))
        settings = ar.read_json(self.env.controller().settings_path)["permissions"]["allow"]
        self.assertFalse([rule for rule in settings if " push --enrollment " in rule])

    def test_config_names_cannot_escape_trusted_directories(self):
        """R1-F14."""
        for name in ("../projects/test", "..\\projects\\test", "Test", "a/b"):
            with self.subTest(name), self.assertRaises(ar.UsageError):
                ar.load_project(name, self.env.wf)

    def test_actor_is_refreshed_and_posting_identity_checked(self):
        """R1-F9."""
        env = self.env
        ctl = env.controller()
        ctl.verify_inputs()
        env.gh.pr_overrides = {"viewer": "someone-else"}
        with self.assertRaises(ar.UsageError):
            ctl.verify_inputs()
        env.gh.pr_overrides = {}
        env.gh.poster = "someone-else"
        with self.assertRaises(ar.Stop) as stop:
            ctl.publish("r01-request", "### heading\nbody")
        self.assertIn("gh login changed", stop.exception.reason)

    def test_developer_report_requires_an_explicit_successful_terminal_event(self):
        """R1-F17."""
        log = self.env.root / "stream.jsonl"
        log.write_text(json.dumps({"type": "result", "subtype": "success", "structured_output": {}}) + "\n", encoding="utf-8")
        self.assertTrue(ar.ClaudeDeveloper.parse(log)["is_error"])  # is_error missing: not success
        env = Env("headless")
        self.addCleanup(env.cleanup)

        def interrupted(e):
            return report(e, "phase-1")
        interrupted.subtype = "error_during_execution"
        env.developer.script = [interrupted]
        self.assertIn("error_during_execution", env.controller().develop_step())

    def test_decode_failures_are_persisted_stops(self):
        """R1-F18."""
        ctl = self.env.controller()
        self.assertEqual(ar.EXIT_PAUSED, ar.guarded(ctl, "run", lambda: json.loads("{not json")))
        self.assertEqual("PAUSED", ar.read_json(self.env.dir / "state.json")["status"])

    def test_rival_marker_and_tampered_outbox_are_refused(self):
        """R1-F7."""
        env = self.env
        ctl = env.controller()
        ctl.publish("r01-request", "### heading\nbody")
        ours = env.gh.comments_list[-1]
        env.gh.comments_list.append({**ours, "id": 5, "body": ours["body"].splitlines()[0] + "\nconflicting copy"})
        ctl.state["publications"]["r01-request"].update(state="pending")
        ctl.state["publications"]["r01-request"]["parts"][0]["comment_id"] = None
        with self.assertRaises(ar.Stop) as stop:
            ctl.publish("r01-request", "ignored")
        self.assertIn("differ or are duplicated", stop.exception.reason)
        env.gh.fail_next = 99
        with self.assertRaises(ar.Stop):
            ctl.publish("r02-request", "### heading\nsecond")
        path = Path(ctl.state["publications"]["r02-request"]["parts"][0]["body_file"])
        path.write_text(path.read_text(encoding="utf-8") + "tampered", encoding="utf-8")
        env.gh.fail_next = 0
        with self.assertRaises(ar.Stop) as stop:
            ctl.publish("r02-request", "ignored")
        self.assertIn("modified on disk", stop.exception.reason)

    def test_disposition_publication_is_idempotent_per_content(self):
        """R3-F3."""
        env = self.env
        env.reviewer.script = [{"decision": "changes_required", "findings": [finding("R1-F1")]}]
        ctl = env.controller()
        self.submit(ctl, "phase-1")
        sha = env.commit("feature.txt", "fix\n", "fix")
        env.push()
        r = report(env, "phase-1", [fixed("R1-F1", sha)])
        ctl.publish_dispositions(r)
        ctl.publish_dispositions(r)  # replay after a crash
        count = lambda: sum("finding dispositions" in h for h in env.gh.headings())
        self.assertEqual(1, count())
        r2 = report(env, "phase-1", [{"finding_id": "R1-F1", "disposition": "rebutted", "commits": [], "evidence": "x"}])
        ctl.publish_dispositions(r2)
        self.assertEqual(2, count())

    def test_stop_outcome_is_saved_with_the_round(self):
        """R1-F11."""
        env = self.env
        env.reviewer.script = [{"decision": "changes_required", "findings": [finding("R1-F1")]},
                               {"decision": "changes_required", "findings": [finding("R1-F1")],
                                "assessments": [("R1-F1", "rebuttal_rejected")]}]
        ctl = env.controller()
        self.submit(ctl, "phase-1")
        with self.assertRaises(ar.Stop):
            self.submit(ctl, "phase-1", [{"finding_id": "R1-F1", "disposition": "rebutted", "commits": [], "evidence": "x"}])
        on_disk = ar.read_json(env.dir / "state.json")
        self.assertEqual("BLOCKED", on_disk["status"])
        self.assertEqual("accepted", on_disk["rounds"][-1]["status"])

    def test_preserved_results_are_bound_to_content_and_workflow_version(self):
        """R3-F1."""
        env = self.env
        env.reviewer.script = [{"decision": "checkpoint_passed"}, {"decision": "checkpoint_passed"}]
        ctl = env.controller()
        ctl.accept_report(report(env, "phase-1"))
        ctl.transition("review", "t")
        real_post, calls = env.gh.post_comment, {"n": 0}

        def post(number, body_file):
            calls["n"] += 1
            if calls["n"] >= 2:
                raise ar.NotDelivered("simulated outage (no connection; nothing stored)")
            return real_post(number, body_file)
        env.gh.post_comment = post
        with self.assertRaises(ar.Stop):
            ctl.review_round()
        env.gh.post_comment = real_post
        envelope = Path(ctl.active()["envelope_path"])
        data = ar.read_json(envelope)
        data["result"]["decision_rationale"] = "edited on disk"
        ar.atomic_write_json(envelope, data)
        self.assertEqual("checkpoint_passed", env.controller().review_round())
        self.assertEqual(2, len(env.reviewer.calls))  # the altered result was not consumed; a fresh review ran

        env2 = Env("foreground")
        self.addCleanup(env2.cleanup)
        ctl2 = env2.controller()
        env2.reviewer.script += [{"decision": "checkpoint_passed"}, {"decision": "ready_for_owner_review"}]
        for checkpoint in ("phase-1", "final"):
            ctl2.accept_report(report(env2, checkpoint))
            ctl2.transition("review", "t")
            ctl2.review_round()
        (env2.wf / "prompts" / "reviewer.md").write_text("new rules\n", encoding="utf-8")
        result = ctl2.activate()
        self.assertEqual(["ready result"], result["invalidated"])
        self.assertIsNone(ctl2.state["ready_review"])
        self.assertEqual("review", ctl2.state["phase"])

    def test_freshness_is_rechecked_after_publication(self):
        """R1-F1."""
        env = self.env
        env.reviewer.script = [{"decision": "checkpoint_passed"}]
        ctl = env.controller()

        def push_during_review_publication(record):
            if "Codex GPT-6.2 Astra — review" in record["body"]:
                env.gh.on_post = None
                env.commit("feature.txt", "racing\n", "push while the review was being posted")
                env.push()
        env.gh.on_post = push_during_review_publication
        with self.assertRaises(ar.Stop) as stop:
            self.submit(ctl, "phase-1")
        self.assertIn("historical", stop.exception.reason)
        self.assertEqual({}, ctl.state["rounds_completed"])
        self.assertIn("Workflow — correction", env.gh.headings()[-1])

    def test_blocking_status_is_sticky_and_required_gaps_must_block(self):
        """R1-F3, R1-F4."""
        env = self.env
        downgrade = {"decision": "changes_required", "findings": [finding("R1-F1", blocks=False), finding("R2-F1")],
                     "assessments": [("R1-F1", "fix_rejected")]}
        env.reviewer.script = [{"decision": "changes_required", "findings": [finding("R1-F1")]}] + [downgrade] * 3
        ctl = env.controller()
        self.submit(ctl, "phase-1")
        sha = env.commit("feature.txt", "fix\n", "fix")
        env.push()
        with self.assertRaises(ar.Stop) as stop:
            self.submit(ctl, "phase-1", [fixed("R1-F1", sha)])
        self.assertIn("cannot be restated as non-blocking", stop.exception.reason)

        env2 = Env("foreground")
        self.addCleanup(env2.cleanup)
        env2.reviewer.script = [{"decision": "changes_required",
                                 "findings": [finding("R1-F1"), finding("R1-F2", blocks=False, category="required_gap")]}] * 3
        ctl2 = env2.controller()
        ctl2.accept_report(report(env2, "phase-1"))
        ctl2.transition("review", "t")
        with self.assertRaises(ar.Stop) as stop:
            ctl2.review_round()
        self.assertIn("required_gap must block", stop.exception.reason)

    def test_required_gates_need_controller_receipts_bound_to_the_candidate(self):
        """R4-F2, R3-F6: gates are identified by ID and proven by controller-run receipts, not report text."""
        plan = {"schema_version": "agent-review.plan.v1", "mission_id": "fixture", "checkpoints": [
            {"id": "final", "type": "final", "scope": "s", "exit_conditions": ["e"], "required_gates": ["unit"]}]}
        env = Env("foreground", plan=plan, cfg_overrides={"gates": {"unit": {"argv": [sys.executable, "-c", "print('Ran 2 tests'); print('OK')"], "timeout_minutes": 5},
         "dirty": {"argv": [sys.executable, "-c", "open('stray.txt', 'w').write('x')"], "timeout_minutes": 5},
         "filtered": {"argv": [sys.executable, "-c", "import sys; print(sys.argv[1:])"],
                      "extra_args_pattern": "-Filter [a-z-]+"}}})
        self.addCleanup(env.cleanup)
        ctl = env.controller()
        self.assertIn("unit", ctl.accept_report(report(env, "final")))  # a claimed pass in the report is not enough
        receipt = ctl.run_gate("unit")
        self.assertTrue(receipt["passed"])
        self.assertEqual(git(env.work, "rev-parse", "HEAD"), receipt["candidate"])
        self.assertIsNone(ctl.accept_report(report(env, "final")))
        env.commit("feature.txt", "v2\n", "new candidate")
        env.push()
        self.assertIn("unit", ctl.accept_report(report(env, "final")))  # receipts do not carry over to a new commit
        dirty = ctl.run_gate("dirty")
        self.assertFalse(dirty["passed"])  # a gate that changes the worktree does not pass
        self.assertFalse(dirty["worktree_unchanged"])
        (env.work / "stray.txt").unlink()
        self.assertTrue(ctl.run_gate("filtered", ["--", "-Filter", "black-tentacles"])["passed"])
        with self.assertRaises(ar.UsageError):
            ctl.run_gate("filtered", ["-Filter", "x; rm -rf ."])
        with self.assertRaises(ar.UsageError):
            ctl.run_gate("unknown")

    def test_readiness_checks_runtime_lock_records_and_check_providers(self):
        """R3-F4, R1-F7 (handoff), R1-F6."""
        env = self.env
        ctl = env.controller()
        self.to_finalize(ctl)
        lock = env.root / "runtime.lock"
        lock.write_text("run-id\n", encoding="utf-8")
        with self.assertRaises(ar.Stop) as stop:
            ctl.finalize()
        self.assertIn("runtime transaction lock", stop.exception.reason)
        lock.unlink()
        removed = env.gh.comments_list.pop(0)
        with self.assertRaises(ar.Stop) as stop:
            ctl.finalize()
        self.assertIn("missing or altered", stop.exception.reason)
        env.gh.comments_list.insert(0, removed)
        h = ctl.state["ready_review"]["H"]
        env.gh.required = [{"context": "ci/test", "app_id": 15368}]
        env.gh.check_results[h] = [{"name": "ci/test", "status": "completed", "conclusion": "success", "app_id": 999}]
        with self.assertRaises(ar.Stop) as stop:
            ctl.finalize()
        self.assertIn("ci/test", stop.exception.reason)
        env.gh.check_results[h][0]["app_id"] = 15368
        self.assertEqual("AWAITING_OWNER_REVIEW", ctl.finalize())
        env.gh.pr_overrides = {"reviewRequests": [{"login": "someone"}]}
        self.assertFalse(ctl.status(remote=True)["handoff_current"])  # R1-F22: same head, changed gate

    def test_reserved_inbox_path_and_foreign_transcript_changes_block(self):
        """R3-F2, R1-F13."""
        env = self.env
        env.commit(".agent-review-inputs/request.json", "{}\n", "collides with the reviewer inbox")
        env.push()
        ctl = env.controller()
        env.reviewer.script = [{"decision": "checkpoint_passed"}]
        ctl.accept_report(report(env, "phase-1"))
        ctl.transition("review", "t")
        with self.assertRaises(ar.Stop) as stop:
            ctl.review_round()
        self.assertIn("reserved path", stop.exception.reason)

        env2 = Env("foreground", extra_files={"docs/agent-reviews/pr-3/001-r01-review.md": "old record\n"})
        self.addCleanup(env2.cleanup)
        env2.commit("docs/agent-reviews/pr-3/001-r01-review.md", "rewritten history\n", "edit another PR's record")
        env2.push()
        ctl2 = env2.controller()
        ctl2.accept_report(report(env2, "phase-1"))
        ctl2.transition("review", "t")
        with self.assertRaises(ar.Stop) as stop:
            ctl2.review_round()
        self.assertIn("transcript tree change", stop.exception.reason)

    def test_foreground_reviewer_gets_candidate_receipts_not_the_whole_session_log(self):
        """R3-F6."""
        env = Env("foreground", cfg_overrides={"gates": {"unit": {"argv": [sys.executable, "-c", "print('Ran 2 tests'); print('OK')"], "timeout_minutes": 5},
         "dirty": {"argv": [sys.executable, "-c", "open('stray.txt', 'w').write('x')"], "timeout_minutes": 5},
         "filtered": {"argv": [sys.executable, "-c", "import sys; print(sys.argv[1:])"],
                      "extra_args_pattern": "-Filter [a-z-]+"}}})
        self.addCleanup(env.cleanup)
        ctl = env.controller()
        old = ctl.run_gate("unit")
        env.commit("feature.txt", "v2\n", "new candidate")
        env.push()
        current = ctl.run_gate("unit")
        other = ctl.run_gate("filtered", ["-Filter", "abc"])
        tampered = sorted((ctl.dir / "evidence").glob("gate-filtered-*.log"))[-1]
        tampered.write_text("altered after the run\n", encoding="utf-8")  # its receipt's log digest no longer matches
        env.reviewer.script = [{"decision": "checkpoint_passed"}]
        ctl.accept_report(report(env, "phase-1"))
        ctl.transition("review", "t")
        ctl.review_round()
        call = env.reviewer.calls[-1]
        names = [n for n in call["inbox"] if n.startswith("evidence/")]
        self.assertIn("evidence/" + current["log"], names)
        self.assertNotIn("evidence/" + old["log"], names)  # a receipt for another commit is not current evidence
        self.assertNotIn("evidence/" + other["log"], names)  # tampered evidence is never supplied
        self.assertIn("withheld", call["transcript"])

    def test_developer_helpers_check_enrollment_authority(self):
        """R4-F4."""
        env = self.env
        ctl = env.controller()
        self.assertEqual([], ctl.helper_authority_problems())
        env.gh.pr_overrides = {"isDraft": False}
        self.assertTrue(ctl.helper_authority_problems())
        env.gh.pr_overrides = {}
        ctl.state["status"] = "AWAITING_OWNER_REVIEW"
        self.assertTrue(ctl.helper_authority_problems())

    def test_unrecorded_launch_is_found_by_session_id(self):
        """R4-F3: a live child whose PID was never recorded still blocks a second launch."""
        sid = str(uuid.uuid4())
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", "--session-id", sid])
        self.addCleanup(child.kill)
        ctl = self.env.controller()
        ctl.state["developer"].update(session_id=sid, active_pid=None, launch={"n": 1, "returned": False})
        with self.assertRaises(ar.Stop) as stop:
            ctl.assert_no_active_developer()
        self.assertIn(str(child.pid), stop.exception.reason)
        child.kill()
        child.wait()
        ctl.assert_no_active_developer()  # gone: the interrupted launch can be reconciled

    def test_cli_resolves_enrollments_through_the_host_registry(self):
        """The CLI and developer helpers find an enrollment by ID exactly where enrollment registered it."""
        ctl = self.env.controller()
        self.assertEqual(self.env.dir.resolve(), ar.find_enrollment(ctl.state["enrollment_id"]).resolve())
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(ar.EXIT_OK, ar.main(["status", "--enrollment", ctl.state["enrollment_id"]]))
        self.assertEqual(ctl.state["enrollment_id"], json.loads(out.getvalue())["enrollment"])

    def test_cancel_releases_claims_and_preserves_history(self):
        env = self.env
        ctl = env.controller()
        ctl.verify_inputs()
        self.assertEqual("CANCELLED", ctl.cancel("owner decision"))
        self.assertIn("Workflow — cancelled", env.gh.headings()[-1])
        folder, state = ar.enroll(env.args(), github=env.gh, root=env.wf, developer=env.developer)  # the branch can be enrolled again
        self.assertNotEqual(state["enrollment_id"], ctl.state["enrollment_id"])
        self.assertTrue((ctl.dir / "state.json").exists())


class RoundFourRegressionTests(Base):
    """Focused regressions for round-4 residuals."""

    def test_handoff_rechecked_after_the_pr_body_edit(self):
        """R1-F1."""
        env = self.env
        ctl = env.controller()
        self.to_finalize(ctl)
        real_edit = env.gh.edit_body

        def edit_then_request_reviewer(number, body_file):
            real_edit(number, body_file)
            env.gh.pr_overrides = {"reviewRequests": [{"login": "someone"}]}
        env.gh.edit_body = edit_then_request_reviewer
        with self.assertRaises(ar.Stop):
            ctl.finalize()
        self.assertNotEqual("AWAITING_OWNER_REVIEW", ar.read_json(env.dir / "state.json")["status"])
        self.assertIn("superseded", env.gh.body)

    def test_required_checks_sharing_a_context_all_must_pass(self):
        """R1-F6."""
        env = self.env
        ctl = env.controller()
        self.to_finalize(ctl)
        h = ctl.state["ready_review"]["H"]
        env.gh.required = [{"context": "ci", "app_id": 1}, {"context": "ci", "app_id": 2}]
        env.gh.check_results[h] = [{"name": "ci", "status": "completed", "conclusion": "success", "app_id": 1},
                                   {"name": "ci", "status": "in_progress", "conclusion": None, "app_id": 2}]
        with self.assertRaises(ar.Stop) as stop:
            ctl.finalize()
        self.assertIn("app 2", stop.exception.reason)

    def test_archive_authenticates_bodies_and_envelopes_first(self):
        """R1-F7."""
        env = self.env
        ctl = env.controller()
        self.to_finalize(ctl)
        envelope = Path(ctl.state["rounds"][-1]["envelope_path"])
        envelope.write_text(envelope.read_text(encoding="utf-8").replace("simulated", "altered"), encoding="utf-8")
        with self.assertRaises(ar.Stop) as stop:
            ctl.finalize()
        self.assertIn("changed on disk", stop.exception.reason)
        self.assertFalse((env.work / "docs" / "agent-reviews").exists())  # nothing written or committed

    def test_publication_without_author_identity_is_verified_by_reading(self):
        """R1-F9."""
        env = self.env
        ctl = env.controller()
        real = env.gh.post_comment

        def anonymous(number, body_file):
            out = real(number, body_file)
            out.pop("user")
            return out
        env.gh.post_comment = anonymous
        record = ctl.publish("r01-request", "### heading\nbody")
        self.assertEqual("posted", record["state"])  # confirmed through the authenticated listing
        env.gh.poster = "someone-else"
        with self.assertRaises(ar.Stop):
            ctl.publish("r02-request", "### heading\nother")

    def test_missing_handoff_receipt_supersedes_the_handoff(self):
        """R1-F22."""
        env = self.env
        ctl = env.controller()
        self.to_finalize(ctl)
        self.assertEqual("AWAITING_OWNER_REVIEW", ctl.finalize())
        self.assertTrue(ctl.status(remote=True)["handoff_current"])
        env.gh.comments_list.pop()  # the owner-review receipt disappears
        self.assertFalse(ctl.status(remote=True)["handoff_current"])

    def test_disposition_key_covers_validation(self):
        """R3-F3."""
        env = self.env
        env.reviewer.script = [{"decision": "changes_required", "findings": [finding("R1-F1")]}]
        ctl = env.controller()
        self.submit(ctl, "phase-1")
        sha = env.commit("feature.txt", "fix\n", "fix")
        env.push()
        r = report(env, "phase-1", [fixed("R1-F1", sha)])
        ctl.publish_dispositions(r)
        r["validation"][0]["duration"] = "corrected duration"
        ctl.publish_dispositions(r)
        self.assertEqual(2, sum("finding dispositions" in h for h in env.gh.headings()))

    def test_unsent_historical_publication_is_settled_before_advancing(self):
        """R4-F1."""
        env = self.env
        env.reviewer.script = [{"decision": "checkpoint_passed"}]
        ctl = env.controller()

        def push_then_fail(record):
            if "Codex GPT-6.2 Astra — review" in record["body"]:
                env.gh.on_post = None
                env.commit("feature.txt", "racing\n", "racing push")
                env.push()
                env.gh.fail_next = 99
        env.gh.on_post = push_then_fail
        with self.assertRaises(ar.Stop):
            self.submit(ctl, "phase-1")  # correction cannot be sent: it stays a pending required operation
        self.assertTrue(any("not sent" in m for m in ctl.missing_publications()))
        env.gh.fail_next = 0
        restarted = env.controller()
        restarted.settle_publications()
        self.assertFalse(restarted.missing_publications())
        self.assertIn("Workflow — correction", env.gh.headings()[-1])

    def test_owner_resume_restarts_no_progress_counting(self):
        env = self.env
        ctl = env.controller()
        ctl.state.update(status="BLOCKED", status_reason="no progress: R1-F1 open for 3 consecutive reviews",
                         findings={"R1-F1": {"status": "open", "blocks_readiness": True, "rounds_open": 3}})
        ctl.save()
        ctl.resume("owner reviewed the disagreement")
        self.assertEqual(0, ctl.state["findings"]["R1-F1"]["rounds_open"])


CRASH_DRIVER = """
import os, sys
from pathlib import Path
wf, enrollment, pidfile = sys.argv[1:4]
sys.path.insert(0, wf)
import agent_review as ar
Path(pidfile).write_text(str(os.getpid()), encoding="utf-8")
ar.Controller(Path(enrollment), github=object(), workflow_root=Path(wf), sleep=lambda s: None).finalize()
"""

HOOK = """import os, signal, sys, time
from pathlib import Path
pid = int(Path(sys.argv[1]).read_text(encoding="utf-8"))
os.kill(pid, signal.SIGTERM)  # terminate the controller at this exact point
time.sleep(1)
sys.exit(1)
"""


class CrashFixture:
    """Kill a real controller subprocess at a deterministic git-hook point during finalize (F20)."""

    def crash_finalize_at(self, env, hook_name):
        """Run finalize in a real controller subprocess and kill it from a git hook (F20)."""
        hook_py = env.root / "kill_controller.py"
        hook_py.write_text(HOOK, encoding="utf-8")
        pidfile = env.root / "controller.pid"
        hook = env.work / ".git" / "hooks" / hook_name
        hook.write_text(f'#!/bin/sh\n"{Path(sys.executable).as_posix()}" "{hook_py.as_posix()}" "{pidfile.as_posix()}"\n',
                        encoding="utf-8")
        driver = env.root / "driver.py"
        driver.write_text(CRASH_DRIVER, encoding="utf-8")
        proc = subprocess.run([sys.executable, str(driver), str(env.wf), str(env.dir), str(pidfile)],
                              capture_output=True, text=True, timeout=300)
        hook.unlink()
        self.assertNotEqual(0, proc.returncode)  # the controller was killed mid-archive


class DevProcRoundOneTests(CrashFixture, Base):
    """Regressions for the development-process round-1 review findings."""

    def test_archive_crash_before_commit_recovers_from_intent(self):
        """F20 + F12 (pre-commit kill): records written, no commit; one record lost; restart completes exactly."""
        env = self.env
        ctl = env.controller()
        self.to_finalize(ctl)
        self.crash_finalize_at(env, "pre-commit")
        pending = ar.read_json(env.dir / "state.json")["archive_pending"]
        self.assertIsNone(pending["commit"])
        (env.work / pending["files"][-1]["rel"]).unlink()
        self.assertEqual("AWAITING_OWNER_REVIEW", env.controller().finalize())
        self.assertTrue(ar.Git(env.work).clean())

    def test_archive_crash_after_commit_adopts_only_the_exact_commit(self):
        """F20 + F9 (post-commit kill): the commit exists but was not recorded; restart adopts it."""
        env = self.env
        ctl = env.controller()
        self.to_finalize(ctl)
        self.crash_finalize_at(env, "post-commit")
        self.assertIsNone(ar.read_json(env.dir / "state.json")["archive_pending"]["commit"])
        restarted = env.controller()
        self.assertEqual("AWAITING_OWNER_REVIEW", restarted.finalize())
        self.assertEqual(1, len(restarted.state["archive_commits"]))

    def test_archive_commit_must_contain_exactly_the_intended_records(self):
        """F9: a commit missing an intended record fails the inventory check; readiness re-verifies records."""
        env = self.env
        ctl = env.controller()
        parent = git(env.work, "rev-parse", "HEAD")
        rel = "docs/agent-reviews/pr-7/001-r01-request.md"
        commit = env.commit(rel, "x\n", "one of two records")
        digest = ar.Git(env.work).blob_sha256(commit, rel)
        expected = {rel: digest, "docs/agent-reviews/pr-7/002-r01-review.md": ar.sha256_text("y\n")}
        self.assertTrue(ctl.archive_commit_problems(parent, commit, expected))
        self.assertFalse(ctl.archive_commit_problems(parent, commit, {rel: digest}))

    def test_archive_destinations_are_validated_before_writing(self):
        """F10."""
        env = self.env
        ctl = env.controller()
        with self.assertRaises(ar.Stop):
            ctl.record_path("docs/agent-reviews/pr-7/../../../outside.md")
        with self.assertRaises(ar.Stop):
            ctl.record_path("docs/agent-reviews/pr-8/001-r01-review.md")
        target = env.root / "elsewhere"
        target.mkdir()
        link = env.work / "docs" / "agent-reviews"
        link.parent.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            import _winapi
            _winapi.CreateJunction(str(target), str(link))
        else:
            os.symlink(target, link)
        with self.assertRaises(ar.Stop) as stop:
            ctl.record_path("docs/agent-reviews/pr-7/001-r01-request.md")
        self.assertIn("link or junction", stop.exception.reason)
        self.assertEqual([], list(target.iterdir()))

    def test_resumed_stale_verdict_is_never_published_as_current(self):
        """F1 (verdict queued, not sent) and F12: a historical review replaces it and is settled on resume."""
        env = self.env
        env.reviewer.script = [{"decision": "checkpoint_passed"}]
        ctl = env.controller()
        ctl.accept_report(report(env, "phase-1"))
        ctl.transition("review", "t")
        real_post, calls = env.gh.post_comment, {"n": 0}

        def post(number, body_file):
            calls["n"] += 1
            if calls["n"] >= 2:
                raise ar.NotDelivered("simulated outage (no connection; nothing stored)")
            return real_post(number, body_file)
        env.gh.post_comment = post
        with self.assertRaises(ar.Stop):
            ctl.review_round()
        env.gh.post_comment = real_post
        env.commit("feature.txt", "moved\n", "push while paused")
        env.push()
        with self.assertRaises(ar.Stop):
            env.controller().review_round()
        headings = env.gh.headings()
        self.assertFalse([h for h in headings if "Astra — review — round 1" in h and "HISTORICAL" not in h])
        self.assertTrue([h for h in headings if "HISTORICAL" in h])

    def test_already_visible_verdict_gets_a_correction_when_stale(self):
        """F1 (verdict posted, crash before acceptance)."""
        env = self.env
        env.reviewer.script = [{"decision": "checkpoint_passed"}]
        ctl = env.controller()

        def crash_after_verdict(record):
            if "Astra — review" in record["body"]:
                env.gh.on_post = None
                raise KeyboardInterrupt("simulated controller crash right after the verdict was stored")
        env.gh.on_post = crash_after_verdict
        ctl.accept_report(report(env, "phase-1"))
        ctl.transition("review", "t")
        with self.assertRaises(KeyboardInterrupt):
            ctl.review_round()
        env.commit("feature.txt", "moved\n", "push before restart")
        env.push()
        with self.assertRaises(ar.Stop):
            env.controller().review_round()
        self.assertIn("Workflow — correction", env.gh.headings()[-1])

    def test_newest_gate_run_supersedes_and_tampered_logs_fail(self):
        """F2."""
        flag = Path(tempfile.gettempdir()) / f"agent-review-flag-{uuid.uuid4().hex}"
        self.addCleanup(lambda: flag.unlink(missing_ok=True))
        gates = {"flaky": {"argv": [sys.executable, "-c", f"import os,sys; sys.exit(0 if os.path.exists({str(flag)!r}) else 1)"]}}
        plan = {"schema_version": "agent-review.plan.v1", "mission_id": "fixture", "checkpoints": [
            {"id": "final", "type": "final", "scope": "s", "exit_conditions": ["e"], "required_gates": ["flaky"]}]}
        env = Env("foreground", plan=plan, cfg_overrides={"gates": gates})
        self.addCleanup(env.cleanup)
        ctl = env.controller()
        head = git(env.work, "rev-parse", "HEAD")
        flag.write_text("1", encoding="utf-8")
        self.assertTrue(ctl.run_gate("flaky")["passed"])
        self.assertEqual([], ctl.missing_gates(head))
        flag.unlink()
        self.assertFalse(ctl.run_gate("flaky")["passed"])
        self.assertEqual(["flaky"], ctl.missing_gates(head))  # a later failure supersedes the earlier pass
        flag.write_text("1", encoding="utf-8")
        latest = ctl.run_gate("flaky")
        (ctl.dir / "evidence" / latest["log"]).write_text("edited\n", encoding="utf-8")
        self.assertEqual(["flaky"], ctl.missing_gates(head))  # the same rule rejects a tampered log

    def test_install_is_versioned_and_never_disturbs_running_versions(self):
        """F3: installs add immutable versions; the launcher runs the current one; nothing is swapped or deleted."""
        env = self.env
        dest = env.root / "installed"
        first = ar.install(dest, env.wf)
        ctl = env.controller()
        with ctl.lock("run"):  # a running controller does not obstruct, and is not disturbed by, an install
            (env.wf / "prompts" / "reviewer.md").write_text("# new rules\n", encoding="utf-8")
            second = ar.install(dest, env.wf)
        self.assertNotEqual(first, second)
        current = ar.read_json(dest / "current.json")
        self.assertEqual(second, current["fingerprint"])
        versions = [v for v in (dest / "versions").iterdir()]
        self.assertEqual(2, len(versions))  # the earlier version is intact beside the new one
        self.assertIn(first, {ar.workflow_fingerprint(v) for v in versions})
        (env.wf / "plans" / "single.json").write_text(
            (env.wf / "plans" / "single.json").read_text(encoding="utf-8") + "\n", encoding="utf-8")
        self.assertEqual(second, ar.install(dest, env.wf))  # same behavior, different shipped plan (R4-F2)
        self.assertNotEqual(current["package"], ar.read_json(dest / "current.json")["package"])
        self.assertEqual(3, len(list((dest / "versions").iterdir())))
        out = subprocess.run([sys.executable, str(dest / "agent_review.py"), "status", "--enrollment",
                              ctl.state["enrollment_id"]], capture_output=True, text=True, timeout=120)
        self.assertEqual(0, out.returncode, out.stderr)
        self.assertEqual(ctl.state["enrollment_id"], json.loads(out.stdout)["enrollment"])
        self.assertFalse(list((dest / "versions").glob(".staging-*")))

    def test_a_controller_uses_one_snapshot_of_its_workflow(self):
        """F3: prompts read after start come from the verified snapshot; disk changes pause the next check."""
        env = self.env
        ctl = env.controller()
        (env.wf / "prompts" / "reviewer.md").write_text("tampered prompt\n", encoding="utf-8")
        self.assertNotIn("tampered", ctl.render("reviewer.md", {}))
        with self.assertRaises(ar.Stop):
            ctl.verify_inputs()

    def test_cancel_is_refused_under_live_work_and_survives_publication_failure(self):
        """F4."""
        env = self.env
        ctl = env.controller()
        ctl.state["developer"]["active_pid"] = os.getpid()
        with self.assertRaises(ar.Stop):
            ctl.cancel("x")
        ctl.state["developer"]["active_pid"] = None
        (env.root / "runtime.lock").write_text("run\n", encoding="utf-8")
        with self.assertRaises(ar.Stop):
            ctl.cancel("x")
        (env.root / "runtime.lock").unlink()
        env.gh.fail_next = 99
        self.assertEqual("CANCELLED", ctl.cancel("owner decision"))
        on_disk = ar.read_json(env.dir / "state.json")
        self.assertEqual(("CANCELLED", "cancelled"), (on_disk["status"], on_disk["phase"]))
        env.gh.fail_next = 0
        with self.assertRaises(ar.UsageError):
            env.controller().run_loop()

    def test_helpers_require_active_development_identity_and_version(self):
        """F5."""
        env = self.env
        ctl = env.controller()
        self.assertEqual([], ctl.helper_authority_problems())
        for status, phase in (("PAUSED", "develop"), ("ACTIVE", "review")):
            ctl.state.update(status=status, phase=phase)
            self.assertTrue(ctl.helper_authority_problems())
        ctl.state.update(status="ACTIVE", phase="develop")
        git(env.work, "checkout", "--quiet", "-b", "codex/other")
        self.assertTrue(ctl.helper_authority_problems())
        git(env.work, "checkout", "--quiet", env.branch)
        (env.wf / "prompts" / "reviewer.md").write_text("changed\n", encoding="utf-8")
        self.assertTrue(any("not the version activated" in p for p in env.controller().helper_authority_problems()))

    def test_reviewer_provenance_must_be_affirmative(self):
        """F6."""
        req = {"model": "gpt-6.2-astra", "effort": "high"}
        good = {"rollout_found": True, "observed_model": "gpt-6.2-astra", "observed_effort": "high",
                "turn_models": ["gpt-6.2-astra"], "turn_efforts": ["high"], "sandbox": "read-only",
                "approval_policy": "never", "network": "restricted", "subagent_suspected": False}
        info = {"completed": True, "failed": False}
        self.assertEqual(([], False), ar.invocation_problems(info, good, req))
        for change in ({"turn_models": []}, {"turn_efforts": []}, {"sandbox": None}, {"approval_policy": None},
                       {"network": None}, {"network": "enabled"}, {"sandbox": "<conflicting:read-only,workspace-write>"}):
            with self.subTest(change):
                self.assertTrue(ar.invocation_problems(info, {**good, **change}, req)[0])
        self.assertTrue(ar.invocation_problems({"completed": False}, good, req)[0])

    def test_unconfirmed_post_is_not_acknowledged_after_a_read_failure(self):
        """F8."""
        env = self.env
        ctl = env.controller()
        real_post, real_comments = env.gh.post_comment, env.gh.comments
        state = {"fail_reads": 1}

        def anonymous(number, body_file):
            out = real_post(number, body_file)
            out.pop("user")
            return out

        def flaky_comments(number):
            listing = real_comments(number)
            if state["fail_reads"] and len(listing) and "simulated" not in str(state):
                pass
            if state["fail_reads"] > 0 and any(c["user"] == "owner" for c in listing):
                state["fail_reads"] -= 1
                raise RuntimeError("simulated transient listing failure")
            return listing
        env.gh.post_comment, env.gh.comments = anonymous, flaky_comments
        record = ctl.publish("r01-request", "### heading\nbody")
        self.assertEqual("posted", record["state"])
        self.assertEqual(1, len(env.gh.comments_list))  # verified by a later authenticated read, never re-posted

    def test_activation_recomposes_permissions_and_supersedes_handoff(self):
        """F11."""
        env = self.env
        ctl = env.controller()
        self.to_finalize(ctl)
        self.assertEqual("AWAITING_OWNER_REVIEW", ctl.finalize())
        base = env.wf / "settings" / "developer.base.json"
        data = ar.read_json(base)
        data["permissions"]["deny"].append("Bash(newly-denied *)")
        ar.atomic_write_json(base, data)
        result = ctl.activate()
        self.assertIn("owner-review handoff", result["invalidated"])
        settings = ar.read_json(env.controller().settings_path)
        self.assertIn("Bash(newly-denied *)", settings["permissions"]["deny"])
        self.assertEqual(ar.sha256_file(env.controller().settings_path), env.controller().state["developer_settings_sha256"])
        self.assertEqual(("ACTIVE", "review"), (ctl.state["status"], ctl.state["phase"]))

    def test_pr_status_section_is_handled_explicitly_and_verified(self):
        """F13."""
        env = self.env
        ctl = env.controller()
        self.to_finalize(ctl)
        self.assertEqual("AWAITING_OWNER_REVIEW", ctl.finalize())
        env.gh.body = "owner text only"  # someone removed the status section
        self.assertFalse(ctl.status(remote=True)["handoff_current"])
        env.gh.body = "intro\n" + ar.STATUS_START + "\nunterminated"
        with self.assertRaises(ar.Stop) as stop:
            ctl.update_pr_body("x")
        self.assertIn("malformed", stop.exception.reason)

    def test_published_request_tuple_stays_fixed_when_the_target_moves(self):
        """F14."""
        env = self.env
        env.reviewer.script = [{"decision": "checkpoint_passed", "stderr": "usage limit reached", "exit_code": 1},
                               {"decision": "checkpoint_passed"}]
        ctl = env.controller()
        ctl.accept_report(report(env, "phase-1"))
        ctl.transition("review", "t")
        with self.assertRaises(ar.Stop):
            ctl.review_round()
        original_b = ctl.active()["B"]
        git(env.work, "checkout", "--quiet", "master")
        env.commit("other.txt", "x\n", "target moves")
        git(env.work, "push", "--quiet", "origin", "master")
        git(env.work, "checkout", "--quiet", env.branch)
        self.assertEqual("checkpoint_passed", ctl.resume("usage restored"))
        rnd = ctl.state["rounds"][-1]
        self.assertEqual(original_b, rnd["B"])
        self.assertEqual(1, len(rnd["B_observed"]))
        self.assertEqual(original_b, ar.read_json(Path(rnd["envelope_path"]))["B"])

    def test_interrupted_reviewer_attempts_are_reconciled(self):
        """F16."""
        env = self.env
        env.reviewer.script = [{"decision": "checkpoint_passed"}]
        ctl = env.controller()
        ctl.accept_report(report(env, "phase-1"))
        ctl.transition("review", "t")
        candidate = ctl.capture_candidate()
        ctl.state["rounds"].append({"round": 1, "request_id": "x-r01-abc", "checkpoint_id": "phase-1",
                                    "checkpoint_type": "intermediate", **candidate, "pending_findings": [],
                                    "report": ctl.state["last_report"], "created_at": ar.now_iso(), "status": "reviewing",
                                    "attempts": [{"n": 1, "started": ar.now_iso(), "pid": os.getpid()}], "attempt_seq": 1})
        ctl.state["active_round"] = 1
        with self.assertRaises(ar.Stop) as stop:
            ctl.review_round()  # the recorded reviewer process is alive
        self.assertIn("still running", stop.exception.reason)
        ctl.state["rounds"][0]["attempts"][0]["pid"] = 999999
        ctl.state.update(status="ACTIVE")
        self.assertEqual("checkpoint_passed", ctl.review_round())
        attempts = ctl.state["rounds"][0]["attempts"]
        self.assertIn("interrupted", attempts[0]["reasons"][0])
        self.assertEqual([1, 2], [a["n"] for a in attempts])

    def test_push_scans_intermediate_versions(self):
        """F17."""
        env = Env("foreground", cfg_overrides={"push_command": None})
        self.addCleanup(env.cleanup)
        ctl = env.controller()
        env.commit("config.txt", f"token=ghp_{'c' * 36}\n", "oops")
        env.commit("config.txt", "token=redacted\n", "remove it again")
        with self.assertRaises(ar.UsageError) as refused:
            ar.guarded_push(ctl.state, ctl.cfg)
        self.assertIn("outgoing version", str(refused.exception))

    def test_delegation_detection_uses_tool_identity(self):
        """F18 (structured): delegation is a recorded dispatch or a child session whose metadata names this thread
        as its parent; text mentioning the thread or delegation tools is not."""
        with tempfile.TemporaryDirectory() as home:
            folder = Path(home) / "sessions" / "2026" / "11" / "20"
            folder.mkdir(parents=True)
            rollout = folder / f"rollout-a-{TID}.jsonl"
            meta = json.dumps({"type": "session_meta", "payload": {"id": TID}})

            def write(*items):
                rollout.write_text("\n".join([meta] + [json.dumps({"type": "response_item", "payload": i}) for i in items])
                                   + "\n", encoding="utf-8")
            rev = ar.CodexReviewer({"executable": sys.executable, "codex_home": home, "model": "m", "effort": "high"})
            write({"type": "custom_tool_call", "name": "exec",
                   "input": "// tools.collaboration.spawn_agent(...) is mentioned here\nawait tools.exec_command({cmd: 'rg spawn_agent'})"})
            self.assertFalse(rev.provenance(TID)["subagent_suspected"])
            write({"type": "function_call", "name": "spawn_agent", "arguments": "{}"})
            self.assertTrue(rev.provenance(TID)["subagent_suspected"])
            write({"type": "custom_tool_call", "name": "exec", "input": "x"})
            other = Path(home) / "sessions" / "2026" / "11" / "21"
            other.mkdir(parents=True)
            unrelated = other / f"rollout-b-{TID2}.jsonl"
            unrelated.write_text(json.dumps({"type": "session_meta", "payload": {"id": TID2, "instructions": f"see {TID}"}})
                                 + "\n", encoding="utf-8")
            self.assertFalse(rev.provenance(TID)["subagent_suspected"])  # mere text mention is not a parent link
            unrelated.write_text(json.dumps({"type": "session_meta", "payload": {"id": TID2, "source": {
                "subagent": {"parent_thread_id": TID}}}}) + "\n", encoding="utf-8")
            self.assertTrue(rev.provenance(TID)["subagent_suspected"])  # child in another day's folder

    def test_re_enrollment_recognizes_the_controllers_earlier_records(self):
        """F19."""
        env = self.env
        ctl = env.controller()
        self.to_finalize(ctl)
        self.assertEqual("AWAITING_OWNER_REVIEW", ctl.finalize())
        ctl.cancel("start over")
        folder, state = ar.enroll(env.args(), github=env.gh, root=env.wf, developer=env.developer)
        self.assertTrue(state["archived"])
        again = ar.Controller(folder, github=env.gh, reviewer=env.reviewer, developer=env.developer,
                              sleep=lambda s: None, workflow_root=env.wf)
        again.verify_transcripts(git(env.work, "rev-parse", "HEAD"))  # genuine records are not foreign


class DevProcRoundTwoTests(CrashFixture, Base):
    """Regressions for the development-process round-2 review findings (reuses the crash fixture)."""

    def test_partial_archive_commit_is_not_adopted(self):
        """F20 port: a commit holding only part of the intended records (made after a real crash) is refused."""
        env = self.env
        ctl = env.controller()
        self.to_finalize(ctl)
        self.crash_finalize_at(env, "pre-commit")
        pending = ar.read_json(env.dir / "state.json")["archive_pending"]
        git(env.work, "reset", "--quiet")  # the killed controller had staged every record; commit only one
        git(env.work, "add", pending["files"][0]["rel"])
        git(env.work, "commit", "--quiet", "-m", "only part of the intended records")
        with self.assertRaises(ar.Stop) as stop:
            env.controller().finalize()
        self.assertIn("branch moved", stop.exception.reason)

    def test_stale_handoff_receipt_is_corrected_when_abandoned(self):
        """F1: a visible 'awaiting owner review' receipt is corrected when its handoff is abandoned."""
        env = self.env
        ctl = env.controller()
        self.to_finalize(ctl)
        self.assertEqual("AWAITING_OWNER_REVIEW", ctl.finalize())
        ctl.state.update(phase="finalize", status="ACTIVE")  # e.g. a restarted finalize
        env.commit("feature.txt", "late\n", "material change")
        env.push()
        with self.assertRaises(ar.Stop):
            ctl.finalize()
        self.assertIn("the owner-review handoff above is not current", env.gh.comments_list[-1]["body"])
        self.assertTrue(ar.VERDICT_KEY_RE.match("r100-review"))

    def test_damaged_receipts_fail_closed_and_passes_recheck_gates(self):
        """F2."""
        gates = {"unit": {"argv": [sys.executable, "-c", "print('ok')"]}}
        plan = {"schema_version": "agent-review.plan.v1", "mission_id": "fixture", "checkpoints": [
            {"id": "phase-1", "type": "intermediate", "scope": "s", "exit_conditions": ["e"], "required_gates": ["unit"]},
            {"id": "final", "type": "final", "scope": "s", "exit_conditions": ["e"]}]}
        env = Env("foreground", plan=plan, cfg_overrides={"gates": gates})
        self.addCleanup(env.cleanup)
        ctl = env.controller()
        head = git(env.work, "rev-parse", "HEAD")
        first = ctl.run_gate("unit")
        self.assertEqual([], ctl.missing_gates(head))
        damaged = ctl.dir / "evidence" / f"gate-unit-{head[:12]}-99999999T999999999999Z.json"
        damaged.write_text("{truncated", encoding="utf-8")
        self.assertEqual(["unit"], ctl.missing_gates(head))  # an unreadable newer receipt cannot revive the old pass
        damaged.unlink()
        env.reviewer.script = [{"decision": "checkpoint_passed"}]
        self.assertIsNone(ctl.accept_report(report(env, "phase-1")))
        (ctl.dir / "evidence" / first["log"]).write_text("edited after acceptance\n", encoding="utf-8")
        ctl.transition("review", "t")
        with self.assertRaises(ar.Stop) as stop:
            ctl.review_round()
        self.assertIn("gate evidence", stop.exception.reason)
        self.assertEqual(0, ctl.state["checkpoint_index"])

    def test_install_owns_only_its_layout_and_never_touches_other_files(self):
        """R2-F3 / R1-F3: only an empty directory or an owned installation is modified; a flat legacy copy is left
        untouched (and running legacy processes undisturbed) with instructions to install fresh."""
        env = self.env
        cases = {"unrelated files": {"notes.txt": "keep me\n"},
                 "familiar names": {"agent_review.py": "print('my own script')\n", "current.json": "{}"},
                 "legacy flat copy": {"MANIFEST.json": "{}", "agent_review.py": "legacy\n"}}
        for label, files in cases.items():
            with self.subTest(label):
                folder = env.root / label.replace(" ", "-")
                folder.mkdir()
                for name, text in files.items():
                    (folder / name).write_text(text, encoding="utf-8")
                with self.assertRaises(ar.UsageError):
                    ar.install(folder, env.wf)
                self.assertEqual(files, {p.name: p.read_text(encoding="utf-8") for p in folder.iterdir()})
        owned = env.root / "owned"
        ar.install(owned, env.wf)
        (owned / "versions" / "__pycache__").mkdir()
        with self.assertRaises(ar.UsageError):  # an unowned entry inside versions/ is not adopted
            ar.install(owned, env.wf)
        self.assertTrue((owned / "versions" / "__pycache__").exists())

    def test_cancel_waits_for_running_helpers(self):
        """F4."""
        ctl = self.env.controller()
        with ctl.helper_lock("verify"):
            with self.assertRaises(ar.Stop) as stop:
                self.env.controller().cancel("x")
        self.assertIn("helper is running", stop.exception.reason)

    def test_helpers_are_bound_to_the_calling_developer(self):
        """F5."""
        env = self.env
        ctl = env.controller()
        self.assertEqual([], ctl.helper_authority_problems())
        os.environ["CLAUDE_CODE_SESSION_ID"] = "another-session"
        self.assertTrue(any("not the enrolled foreground" in p for p in ctl.helper_authority_problems()))
        os.environ["CLAUDE_CODE_SESSION_ID"] = FOREGROUND_SESSION
        ctl.state["mode"] = "headless"
        self.assertTrue(any("headless developer" in p for p in ctl.helper_authority_problems()))
        os.environ["AGENT_REVIEW_HELPER_TOKEN"] = ctl.state["developer"]["helper_token"]
        self.addCleanup(os.environ.pop, "AGENT_REVIEW_HELPER_TOKEN", None)
        self.assertEqual([], ctl.helper_authority_problems())
        self.assertEqual(ctl.state["developer"]["helper_token"], ar.ClaudeDeveloper(
            {"executable": sys.executable, "model": "opus", "effort": "high"}, Path("s"), Path("x")).env().get(
            "AGENT_REVIEW_HELPER_TOKEN", ctl.state["developer"]["helper_token"]))

    def test_event_sequence_outcome_is_the_last_turn(self):
        """F6."""
        path = self.env.root / "events.jsonl"
        cases = {"completed": (['{"type":"thread.started","thread_id":"%s"}' % TID, '{"type":"turn.completed"}'], True),
                 "completed then unfinished": (['{"type":"turn.completed"}', '{"type":"turn.started"}'], False),
                 "malformed": (['{"type":"turn.completed"}', '{oops'], False),
                 "failed": (['{"type":"turn.started"}', '{"type":"turn.failed"}'], False)}
        for label, (lines, completed) in cases.items():
            with self.subTest(label):
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                self.assertEqual(completed, ar.parse_codex_events(path)["completed"])

    def test_activation_retires_unsent_verdicts_and_public_handoff(self):
        """F11."""
        env = self.env
        env.reviewer.script = [{"decision": "checkpoint_passed"}]
        ctl = env.controller()
        ctl.accept_report(report(env, "phase-1"))
        ctl.transition("review", "t")
        real_post, calls = env.gh.post_comment, {"n": 0}

        def post(number, body_file):
            calls["n"] += 1
            if calls["n"] >= 2:
                raise ar.NotDelivered("simulated outage (no connection; nothing stored)")
            return real_post(number, body_file)
        env.gh.post_comment = post
        with self.assertRaises(ar.Stop):
            ctl.review_round()  # verdict validated and queued, not sent
        env.gh.post_comment = real_post
        (env.wf / "prompts" / "reviewer.md").write_text("new rules\n", encoding="utf-8")
        fresh = env.controller()
        fresh.activate()
        self.assertEqual("superseded", fresh.state["publications"]["r01-review"]["state"])
        self.assertFalse([k for k in fresh.missing_publications() if k.startswith("r01-review")])

    def test_ready_record_keeps_the_reviewed_target_tip(self):
        """F14."""
        env = self.env
        ctl = env.controller()
        self.to_finalize(ctl)
        rnd = ctl.state["rounds"][-1]
        self.assertEqual(rnd["B"], ctl.state["ready_review"]["B"])

    def test_resume_respects_an_exhausted_round_budget(self):
        """F15."""
        env = Env("foreground", max_rounds=1)
        self.addCleanup(env.cleanup)
        env.reviewer.script = [{"decision": "changes_required", "findings": [finding("R1-F1")]}]
        ctl = env.controller()
        ctl.accept_report(report(env, "phase-1"))
        ctl.transition("review", "t")
        with self.assertRaises(ar.Stop):
            ctl.review_round()
        with self.assertRaises(ar.UsageError):
            ctl.resume("try again")
        self.assertEqual("BLOCKED", ar.read_json(env.dir / "state.json")["status"])
        self.assertIn("ACTIVE", ctl.resume("owner extends the budget", max_rounds=2))

    def test_resume_reconciles_a_live_reviewer_before_resetting(self):
        """F16."""
        env = self.env
        ctl = env.controller()
        ctl.accept_report(report(env, "phase-1"))
        candidate = ctl.capture_candidate()
        ctl.state["rounds"].append({"round": 1, "request_id": "x-r01-abc", "checkpoint_id": "phase-1",
                                    "checkpoint_type": "intermediate", **candidate, "pending_findings": [],
                                    "report": ctl.state["last_report"], "created_at": ar.now_iso(), "status": "reviewing",
                                    "attempts": [{"n": 1, "started": ar.now_iso(), "pid": os.getpid()}], "attempt_seq": 1})
        ctl.state.update(active_round=1, phase="review", status="BLOCKED", status_reason="usage limit")
        with self.assertRaises(ar.Stop) as stop:
            ctl.resume("try again")
        self.assertIn("still running", stop.exception.reason)
        self.assertEqual(1, len(ctl.state["rounds"][0]["attempts"]))  # not reset away

    def test_push_scans_commit_messages_and_never_follows_tags(self):
        """F17, R2-F4."""
        env = Env("foreground", cfg_overrides={"push_command": None})
        self.addCleanup(env.cleanup)
        ctl = env.controller()
        path = env.work / "a.txt"
        path.write_text("a\n", encoding="utf-8")
        git(env.work, "add", "a.txt")
        git(env.work, "commit", "--quiet", "-m", f"add with token ghp_{'d' * 36}")
        with self.assertRaises(ar.UsageError):
            ar.guarded_push(ctl.state, ctl.cfg)
        git(env.work, "reset", "--quiet", "--hard", "HEAD~1")
        env.commit("b.txt", "b\n", "clean commit")
        git(env.work, "config", "push.followTags", "true")
        git(env.work, "tag", "-a", "v9.9.9", "-m", "annotated")
        ar.guarded_push(ctl.state, ctl.cfg)
        self.assertEqual("", git(env.origin, "tag", "--list"))

    def test_literal_delegation_text_is_not_a_call(self):
        """F18."""
        with tempfile.TemporaryDirectory() as home:
            rollout = Path(home) / "sessions" / "rollout-x-thread1.jsonl"
            rollout.parent.mkdir(parents=True)
            rev = ar.CodexReviewer({"executable": sys.executable, "codex_home": home, "model": "m", "effort": "high"})
            item = {"type": "custom_tool_call", "name": "exec",
                    "input": "await tools.exec_command({cmd: \"rg 'tools.collaboration.spawn_agent(' src\"})"}
            rollout.write_text(json.dumps({"type": "response_item", "payload": item}) + "\n", encoding="utf-8")
            self.assertFalse(rev.provenance("thread1")["subagent_suspected"])

    def test_missing_earlier_records_block_re_enrollment(self):
        """F19."""
        env = self.env
        ctl = env.controller()
        self.to_finalize(ctl)
        self.assertEqual("AWAITING_OWNER_REVIEW", ctl.finalize())
        ctl.cancel("start over")
        first = sorted(ctl.state["archived"])[0]
        git(env.work, "rm", "--quiet", first)
        git(env.work, "commit", "--quiet", "-m", "lose a record")
        with self.assertRaises(ar.UsageError) as refused:
            ar.enroll(env.args(), github=env.gh, root=env.wf, developer=env.developer)
        self.assertIn("integrity", str(refused.exception))

    def test_partially_visible_review_is_retired_not_marked_posted(self):
        """R2-F1."""
        env = self.env
        env.reviewer.script = [{"decision": "checkpoint_passed"}]
        ctl = env.controller()
        original = ar.COMMENT_LIMIT
        ar.COMMENT_LIMIT = 900  # force a multi-part review
        self.addCleanup(setattr, ar, "COMMENT_LIMIT", original)
        state = {"parts": 0}

        def crash_after_first_part(record):
            if "agent-review:v1" in record["body"] and "key=r01-review part=1/" in record["body"]:
                env.gh.on_post = None
                raise KeyboardInterrupt("simulated crash after one of several parts")
        env.gh.on_post = crash_after_first_part
        ctl.accept_report(report(env, "phase-1"))
        ctl.transition("review", "t")
        with self.assertRaises(KeyboardInterrupt):
            ctl.review_round()
        env.commit("feature.txt", "moved\n", "push")
        env.push()
        restarted = env.controller()
        with self.assertRaises(ar.Stop):
            restarted.review_round()
        pubs = restarted.state["publications"]
        self.assertEqual("superseded", pubs["r01-review"]["state"])
        self.assertFalse(restarted.missing_publications())
        self.assertEqual("posted", pubs["r01-review-superseded"]["state"])  # the visible part is corrected
        historical = pubs["r01-review-historical"]  # and the complete review is published as historical
        self.assertEqual("posted", historical["state"])
        self.assertGreater(len(historical["parts"]), 1)

    def test_reviewer_inbox_carries_complete_prior_findings(self):
        """R2-F2."""
        env = self.env
        env.reviewer.script = [{"decision": "changes_required", "findings": [finding("R1-F1")]},
                               {"decision": "checkpoint_passed", "assessments": [("R1-F1", "fix_verified")]}]
        ctl = env.controller()
        self.submit(ctl, "phase-1")
        sha = env.commit("feature.txt", "fix\n", "fix")
        env.push()
        self.submit(ctl, "phase-1", [fixed("R1-F1", sha)])
        prior = ar.read_json(ctl.dir / "rounds" / "r02" / "prior-findings.json")["ledger"]["R1-F1"]
        self.assertEqual("e", prior["finding"]["expected"])
        self.assertEqual("c", prior["finding"]["requested_correction"])
        self.assertEqual(1, prior["finding_round"])

    def test_resume_of_a_completed_enrollment_rechecks_the_handoff(self):
        """R2-F6."""
        env = self.env
        ctl = env.controller()
        self.to_finalize(ctl)
        self.assertEqual("AWAITING_OWNER_REVIEW", ctl.finalize())
        ctl.state.update(status="PAUSED", status_reason="operational failure during resume")  # transient error
        self.assertIn("AWAITING_OWNER_REVIEW", ctl.resume("retry"))
        self.assertEqual(("AWAITING_OWNER_REVIEW", "done"), (ctl.state["status"], ctl.state["phase"]))


class DevProcRoundThreeTests(CrashFixture, Base):
    """Regressions for the development-process round-3 review findings."""

    def handed_off(self):
        ctl = self.env.controller()
        self.to_finalize(ctl)
        self.assertEqual("AWAITING_OWNER_REVIEW", ctl.finalize())
        return ctl

    def test_receipt_retirement_survives_a_failed_correction(self):
        """R1-F1: the correction is persisted before the receipt is retired and is sent on a later settle."""
        env = self.env
        ctl = self.handed_off()
        env.gh.fail_next = 99
        with self.assertRaises(ar.Stop):
            ctl.retire_receipts("test retirement")
        receipt = next(k for k in ctl.state["publications"] if ar.VERDICT_KEY_RE.match(k) and k.startswith("final-"))
        self.assertEqual("superseded", ctl.state["publications"][receipt]["state"])
        self.assertEqual("pending", ctl.state["publications"][receipt + "-retired"]["state"])
        env.gh.fail_next = 0
        env.controller().settle_publications()
        self.assertIn("handoff above is not current", env.gh.comments_list[-1]["body"])
        self.assertTrue(ctl.missing_publications(include_receipt=receipt))  # a retired receipt is not a current one

    def test_remote_only_movement_retires_the_receipt(self):
        """R1-F1: an early stale-head exit in finalize still corrects the visible receipt."""
        env = self.env
        ctl = self.handed_off()
        ctl.state.update(phase="finalize", status="ACTIVE")
        other = env.root / "other"
        subprocess.run(["git", "clone", "--quiet", "-b", env.branch, str(env.origin), str(other)], check=True)
        (other / "x.txt").write_text("x", encoding="utf-8")
        git(other, "add", "x.txt")
        git(other, "-c", "user.name=T", "-c", "user.email=t@e.invalid", "commit", "--quiet", "-m", "remote only")
        git(other, "push", "--quiet", "origin", env.branch)
        with self.assertRaises(ar.Stop):
            ctl.finalize()
        self.assertIn("handoff above is not current", env.gh.comments_list[-1]["body"])

    def test_parseable_damaged_receipt_and_gate_check_before_publication(self):
        """R1-F2."""
        gates = {"unit": {"argv": [sys.executable, "-c", "print('ok')"]}}
        plan = {"schema_version": "agent-review.plan.v1", "mission_id": "fixture", "checkpoints": [
            {"id": "phase-1", "type": "intermediate", "scope": "s", "exit_conditions": ["e"], "required_gates": ["unit"]},
            {"id": "final", "type": "final", "scope": "s", "exit_conditions": ["e"]}]}
        env = Env("foreground", plan=plan, cfg_overrides={"gates": gates})
        self.addCleanup(env.cleanup)
        ctl = env.controller()
        head = git(env.work, "rev-parse", "HEAD")
        receipt = ctl.run_gate("unit")
        empty = ctl.dir / "evidence" / f"gate-unit-{head[:12]}-99999999T999999999999Z.json"
        empty.write_text("{}", encoding="utf-8")
        self.assertEqual(["unit"], ctl.missing_gates(head))  # parseable but identity-less: fails closed
        empty.unlink()
        env.reviewer.script = [{"decision": "checkpoint_passed"}]
        self.assertIsNone(ctl.accept_report(report(env, "phase-1")))
        (ctl.dir / "evidence" / receipt["log"]).write_text("edited after acceptance\n", encoding="utf-8")
        ctl.transition("review", "t")
        with self.assertRaises(ar.Stop):
            ctl.review_round()
        self.assertFalse([h for h in env.gh.headings() if "Astra — review" in h])  # the pass was never published
        self.assertEqual(({}, "develop"), (ctl.state["rounds_completed"], ctl.state["phase"]))  # not charged
        ctl.resume("re-run gates")
        self.assertEqual([], ctl.helper_authority_problems())  # verify is available again
        self.assertTrue(ctl.run_gate("unit")["passed"])

    def test_helpers_see_current_state_and_claims(self):
        """R1-F4: a helper that loaded state before cancellation is refused once it reloads under its lock."""
        env = self.env
        stale = env.controller()
        env.controller().cancel("owner decision")
        stale.reload()
        problems = stale.helper_authority_problems()
        self.assertTrue(any("no longer holds" in p for p in problems))

    def test_conflicting_threads_and_settings_fail(self):
        """R1-F6."""
        path = self.env.root / "events.jsonl"
        path.write_text('{"type":"thread.started","thread_id":"%s"}\n{"type":"thread.started","thread_id":"%s"}\n'
                        '{"type":"turn.completed"}\n' % (TID, TID2), encoding="utf-8")
        self.assertFalse(ar.parse_codex_events(path)["completed"])
        path.write_text('["not an object"]\n{"type":"turn.completed"}\n', encoding="utf-8")
        self.assertFalse(ar.parse_codex_events(path)["completed"])
        with tempfile.TemporaryDirectory() as home:
            rollout = Path(home) / "sessions" / f"rollout-x-{TID}.jsonl"
            rollout.parent.mkdir(parents=True)
            rows = [{"type": "session_meta", "payload": {"id": TID}}] + [{"type": "event_msg", "payload": {"type": "thread_settings_applied", "thread_settings": {
                        "model": "m", "reasoning_effort": "high", "approval_policy": a,
                        "permission_profile": {"network": "restricted"}}}} for a in ("on-request", "never")]
            rollout.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
            prov = ar.CodexReviewer({"executable": sys.executable, "codex_home": home, "model": "m",
                                     "effort": "high"}).provenance(TID)
            self.assertTrue(prov["approval_policy"].startswith("<conflicting"))

    def test_activation_public_updates_are_durable(self):
        """R1-F11."""
        env = self.env
        ctl = self.handed_off()
        (env.wf / "prompts" / "reviewer.md").write_text("new rules\n", encoding="utf-8")
        env.gh.fail_next = 99
        fresh = env.controller()
        fresh.activate()  # one transaction: the public updates are persisted with the activation
        with self.assertRaises(ar.Stop):
            fresh.settle_after_activation()
        on_disk = ar.read_json(env.dir / "state.json")
        self.assertTrue(on_disk.get("public_ops") or any(p["state"] == "pending" for p in on_disk["publications"].values()))
        env.gh.fail_next = 0
        retry = env.controller()
        retry.settle_publications()
        self.assertFalse(retry.state.get("public_ops"))
        self.assertIn("superseded", env.gh.body)

    def test_exhausted_budget_is_numeric_not_textual(self):
        """R1-F15."""
        env = Env("foreground", max_rounds=1)
        self.addCleanup(env.cleanup)
        env.reviewer.script = [{"decision": "changes_required", "findings": [finding("R1-F1")]}]
        ctl = env.controller()
        ctl.accept_report(report(env, "phase-1"))
        ctl.transition("review", "t")
        with self.assertRaises(ar.Stop):
            ctl.review_round()
        ctl.state["status_reason"] = "operational failure during resume"  # the reason text no longer mentions the cap
        with self.assertRaises(ar.UsageError):
            ctl.resume("retry")
        ctl.state.update(status="ACTIVE", mode="headless")
        with self.assertRaises(ar.Stop) as stop:
            ctl.develop_step()
        self.assertIn("budget", stop.exception.reason)

    def test_review_round_reconciles_before_superseding(self):
        """R1-F16."""
        env = self.env
        ctl = env.controller()
        ctl.accept_report(report(env, "phase-1"))
        candidate = ctl.capture_candidate()
        ctl.state["rounds"].append({"round": 1, "request_id": "x-r01-abc", "checkpoint_id": "phase-1",
                                    "checkpoint_type": "intermediate", **candidate, "pending_findings": [],
                                    "report": ctl.state["last_report"], "created_at": ar.now_iso(), "status": "reviewing",
                                    "attempts": [{"n": 1, "started": ar.now_iso(), "pid": os.getpid()}], "attempt_seq": 1})
        ctl.state.update(active_round=1, phase="review")
        env.commit("feature.txt", "moved\n", "new candidate while the reviewer runs")
        env.push()
        with self.assertRaises(ar.Stop) as stop:
            ctl.review_round()
        self.assertIn("still running", stop.exception.reason)
        self.assertEqual("reviewing", ctl.state["rounds"][0]["status"])  # not superseded underneath it

    def test_replacing_a_completed_pre_ledger_claim_imports_its_records(self):
        """R1-F19."""
        env = self.env
        ctl = self.handed_off()
        ledger = ar.records_ledger_path("owner/repo", 7)
        ledger.unlink()  # as for an enrollment completed before the ledger existed
        folder, state = ar.enroll(env.args(), github=env.gh, root=env.wf, developer=env.developer)
        self.assertEqual(ctl.state["archived"], state["archived"])

    def test_unauthenticated_legacy_findings_block_dispatch(self):
        """R2-F2."""
        env = self.env
        env.reviewer.script = [{"decision": "changes_required", "findings": [finding("R1-F1")]}]
        ctl = env.controller()
        self.submit(ctl, "phase-1")
        ctl.state["findings"]["R1-F1"].pop("finding")  # a legacy ledger entry
        envelope = Path(ctl.state["rounds"][0]["envelope_path"])
        envelope.write_text(envelope.read_text(encoding="utf-8").replace('"e"', '"tampered"'), encoding="utf-8")
        sha = env.commit("feature.txt", "fix\n", "fix")
        env.push()
        self.assertIsNone(ctl.accept_report(report(env, "phase-1", [fixed("R1-F1", sha)])))
        ctl.transition("review", "t")
        with self.assertRaises(ar.Stop) as stop:
            ctl.review_round()
        self.assertIn("authenticated text", stop.exception.reason)

    def test_archive_names_and_round_identity_scale(self):
        """R3-F1."""
        self.assertTrue(ar.re.fullmatch(ar.ARCHIVE_NAME_RE, "1000-r100-review.md"))
        self.assertEqual("100", ar.re.fullmatch(r"r(\d+)-review(-historical)?", "r100-review").group(1))

    def test_actor_is_checked_at_each_mutation(self):
        """R3-F2."""
        env = self.env
        ctl = env.controller()
        ctl.verify_inputs()
        env.gh.pr_overrides = {"viewer": "someone-else"}  # login changed after the entry check
        with self.assertRaises(ar.Stop):
            ctl.publish("r01-request", "### heading\nbody")
        self.assertEqual([], env.gh.comments_list)  # nothing was posted
        with self.assertRaises(ar.Stop):
            ctl.update_pr_body("x")

    def test_headless_permissions_are_isolated(self):
        """R3-F3."""
        env = self.env
        (env.work / ".claude").mkdir(exist_ok=True)
        (env.work / ".claude" / "settings.json").write_text(json.dumps({"includeCoAuthoredBy": False, "permissions": {
            "allow": ["Bash(*)"]}}), encoding="utf-8")
        composed = ar.compose_developer_settings(env.controller().cfg, env.wf, "e1", env.work)
        self.assertFalse(composed["includeCoAuthoredBy"])
        self.assertNotIn("Bash(*)", composed["permissions"]["allow"])  # project allowances are not inherited
        dev = ar.ClaudeDeveloper({"executable": sys.executable, "model": "opus", "effort": "high"},
                                 env.dir / "developer-settings.json", env.wf / ar.REPORT_SCHEMA_FILE)
        argv = dev.argv(str(uuid.uuid4()), False)
        self.assertEqual("", argv[argv.index("--setting-sources") + 1])

    def test_invalid_envelope_retires_a_visible_verdict(self):
        """R3-F4."""
        env = self.env
        env.reviewer.script = [{"decision": "checkpoint_passed"}, {"decision": "checkpoint_passed"}]
        ctl = env.controller()

        def crash_after_verdict(record):
            if "Astra — review" in record["body"]:
                env.gh.on_post = None
                raise KeyboardInterrupt("simulated crash after the verdict was stored")
        env.gh.on_post = crash_after_verdict
        ctl.accept_report(report(env, "phase-1"))
        ctl.transition("review", "t")
        with self.assertRaises(KeyboardInterrupt):
            ctl.review_round()
        restarted = env.controller()
        envelope = Path(restarted.active()["envelope_path"])
        envelope.write_text(envelope.read_text(encoding="utf-8") + " ", encoding="utf-8")
        self.assertEqual("checkpoint_passed", restarted.review_round())
        self.assertTrue(any("not a current verdict" in c["body"] for c in env.gh.comments_list))

    def test_pr_description_outside_the_section_is_preserved(self):
        """R3-F5."""
        env = self.env
        ctl = env.controller()
        owner_text = f"Notes from {Path.home()} — keep exactly"
        env.gh.body = owner_text
        ctl.update_pr_body("status text")
        self.assertTrue(env.gh.body.startswith(owner_text))


class DevProcRoundFourTests(CrashFixture, Base):
    """Regressions for the development-process round-4 review findings."""

    def gated_env(self):
        gates = {"unit": {"argv": [sys.executable, "-c", "print('ok')"]}}
        plan = {"schema_version": "agent-review.plan.v1", "mission_id": "fixture", "checkpoints": [
            {"id": "phase-1", "type": "intermediate", "scope": "s", "exit_conditions": ["e"], "required_gates": ["unit"]},
            {"id": "final", "type": "final", "scope": "s", "exit_conditions": ["e"]}]}
        env = Env("foreground", plan=plan, cfg_overrides={"gates": gates})
        self.addCleanup(env.cleanup)
        return env

    def test_absent_named_receipt_is_missing(self):
        """R1-F1."""
        ctl = self.env.controller()
        self.assertTrue(ctl.missing_publications(include_receipt="final-status-nonexistent"))

    def test_gate_order_comes_from_filenames_and_damage_is_recoverable(self):
        """R1-F2."""
        env = self.gated_env()
        ctl = env.controller()
        head = git(env.work, "rev-parse", "HEAD")
        evidence = ctl.dir / "evidence"
        evidence.mkdir(parents=True, exist_ok=True)
        damaged = receipt_path(ctl, head, "unit", stamp="20000101T000000000000Z")
        damaged.write_text("{trunc", encoding="utf-8")
        self.assertEqual(["unit"], ctl.missing_gates(head))
        receipt = ctl.run_gate("unit")  # a newer valid run replaces damaged evidence
        self.assertEqual([], ctl.missing_gates(head))
        undated = dict(receipt, passed=False, exit_code=1)
        undated.pop("recorded_at")  # a newer failing receipt without its date still counts, and fails closed
        ar.atomic_write_json(receipt_path(ctl, head, "unit", stamp="99999999T999999999999Z"), undated)
        self.assertEqual(["unit"], ctl.missing_gates(head))

    def test_gate_invalidated_during_publication_is_not_accepted(self):
        """R1-F2: gates are re-checked after the verdict is published, immediately before acceptance."""
        env = self.gated_env()
        ctl = env.controller()
        receipt = ctl.run_gate("unit")
        env.reviewer.script = [{"decision": "checkpoint_passed"}]

        def damage_log(record):
            if "Astra — review" in record["body"]:
                (ctl.dir / "evidence" / receipt["log"]).write_text("edited\n", encoding="utf-8")
        env.gh.on_post = damage_log
        self.assertIsNone(ctl.accept_report(report(env, "phase-1")))
        ctl.transition("review", "t")
        with self.assertRaises(ar.Stop) as stop:
            ctl.review_round()
        self.assertEqual("PAUSED", stop.exception.status)
        self.assertEqual(({}, "develop", 0), (ctl.state["rounds_completed"], ctl.state["phase"], ctl.state["checkpoint_index"]))
        self.assertIn("is not accepted", env.gh.comments_list[-1]["body"])

    def test_reviewer_outcome_and_rollout_identity_are_exact(self):
        """R1-F6."""
        path = self.env.root / "events.jsonl"
        path.write_text('{"type":"turn.completed"}\n{"type":"thread.started","thread_id":"%s"}\n' % TID, encoding="utf-8")
        self.assertFalse(ar.parse_codex_events(path)["completed"])  # completion before the thread started
        with tempfile.TemporaryDirectory() as home:
            rev = ar.CodexReviewer({"executable": sys.executable, "codex_home": home, "model": "m", "effort": "high"})
            root = Path(home) / "sessions"
            (root / "a").mkdir(parents=True)
            (root / "b").mkdir(parents=True)
            meta = json.dumps({"type": "session_meta", "payload": {"id": TID}}) + "\n"
            (root / "a" / f"rollout-1-{TID}.jsonl").write_text(meta, encoding="utf-8")
            self.assertTrue(rev.provenance(TID)["rollout_found"])
            (root / "b" / f"rollout-2-{TID}.jsonl").write_text(meta, encoding="utf-8")
            self.assertIn("2 rollouts", rev.provenance(TID)["provenance_problem"])  # ambiguous
            (root / "b" / f"rollout-2-{TID}.jsonl").write_text(
                json.dumps({"type": "session_meta", "payload": {"id": TID2}}) + "\n", encoding="utf-8")
            self.assertTrue(rev.provenance(TID)["rollout_found"])  # a name match with another identity is ignored
            (root / "a" / f"rollout-1-{TID}.jsonl").write_text(meta + "{broken\n", encoding="utf-8")
            prov = rev.provenance(TID)
            self.assertIn("malformed", prov["provenance_problem"])
            self.assertTrue(any("unreliable" in r for r in ar.invocation_problems(
                {"completed": True, "thread_id": TID}, prov, {"model": "m", "effort": "high"})[0]))

    def test_fully_visible_retired_verdict_stays_on_the_record(self):
        """R2-F1."""
        env = self.env
        ctl = env.controller()
        head = git(env.work, "rev-parse", "HEAD")
        ctl.publish("r05-review", "### Astra — review — round 5\n\nfull text of the retired verdict")
        ctl.retire_verdict({"round": 5, "H": head}, "test retirement")
        self.assertEqual("superseded", ctl.state["publications"]["r05-review"]["state"])
        ctl.archive("test")
        folder = Path(ctl.state["repo_root"]) / ctl.transcript_folder()
        record = next(folder.glob("*-r05-review.md")).read_text(encoding="utf-8")
        self.assertIn("full text of the retired verdict", record)
        self.assertIn("Superseded record", record)

    def test_recovery_uses_only_the_latest_statement(self):
        """R2-F2: an older authentic envelope is never substituted for a tampered latest one."""
        env = self.env
        ctl = env.controller()
        rounds_dir = ctl.dir / "rounds"
        rounds_dir.mkdir(exist_ok=True)
        for n, text in ((1, "first statement"), (2, "latest statement")):
            path = rounds_dir / f"env-{n}.json"
            ar.atomic_write_json(path, {"result": {"findings": [dict(finding("R1-F1"), actual=text)]}})
            ctl.state["rounds"].append({"round": n, "status": "accepted", "envelope_path": str(path),
                                        "envelope_sha256": ar.sha256_file(path)})
        ctl.state["findings"] = {"R1-F1": {"status": "open", "last_round": 2, "finding_round": 2}}
        self.assertEqual("latest statement", ctl.full_findings()["R1-F1"]["finding"]["actual"])
        (rounds_dir / "env-2.json").write_text((rounds_dir / "env-2.json").read_text(encoding="utf-8") + " ",
                                               encoding="utf-8")
        self.assertNotIn("finding", ctl.full_findings()["R1-F1"])

    def test_archive_production_path_scales_past_99_rounds_and_999_records(self):
        """R3-F1."""
        env = self.env
        ctl = env.controller()
        folder_rel = ctl.transcript_folder()
        env.commit(f"{folder_rel}/999-earlier.md", "an earlier record\n", "earlier record")
        env.push()
        ctl.state.setdefault("archived", {})[f"{folder_rel}/999-earlier.md"] = \
            ctl.git.blob_sha256("HEAD", f"{folder_rel}/999-earlier.md")
        rounds_dir = ctl.dir / "rounds"
        rounds_dir.mkdir(exist_ok=True)
        for n in (10, 100):
            path = rounds_dir / f"env-{n}.json"
            ar.atomic_write_json(path, {"result": {"summary": f"<result of round {n}>"}})
            ctl.state["rounds"].append({"round": n, "status": "accepted", "envelope_path": str(path),
                                        "envelope_sha256": ar.sha256_file(path), "published": []})
            ctl.publish(f"r{n:02d}-review", f"### Astra — review — round {n}\n\nround {n} text")
        ctl.archive("test")
        folder = Path(ctl.state["repo_root"]) / folder_rel
        for n in (10, 100):
            envelope = next(folder.glob(f"*-r{n}-review-envelope.json"))
            self.assertGreaterEqual(int(envelope.name.split("-")[0]), 1000)
            self.assertIn(f"<result of round {n}>", envelope.read_text(encoding="utf-8"))
            self.assertNotIn(f"<result of round {10 if n == 100 else 100}>", envelope.read_text(encoding="utf-8"))

    def test_comment_post_rechecks_the_target_pr(self):
        """R3-F2."""
        env = self.env
        ctl = env.controller()
        ctl.verify_inputs()
        env.gh.pr_overrides = {"state": "CLOSED"}
        with self.assertRaises(ar.Stop):
            ctl.publish("r01-request", "### heading\nbody")
        env.gh.pr_overrides = {"isDraft": False}
        with self.assertRaises(ar.Stop):
            ctl.publish("r01-request", "### heading\nbody")
        self.assertEqual([], env.gh.comments_list)

    def test_truncated_envelope_retires_the_visible_verdict(self):
        """R3-F4."""
        env = self.env
        env.reviewer.script = [{"decision": "checkpoint_passed"}, {"decision": "checkpoint_passed"}]
        ctl = env.controller()

        def crash_after_verdict(record):
            if "Astra — review" in record["body"]:
                env.gh.on_post = None
                raise KeyboardInterrupt("simulated crash after the verdict was stored")
        env.gh.on_post = crash_after_verdict
        ctl.accept_report(report(env, "phase-1"))
        ctl.transition("review", "t")
        with self.assertRaises(KeyboardInterrupt):
            ctl.review_round()
        restarted = env.controller()
        envelope = Path(restarted.active()["envelope_path"])
        envelope.write_bytes(envelope.read_bytes()[:40])  # truncated JSON
        self.assertEqual("checkpoint_passed", restarted.review_round())
        self.assertTrue(any("not a current verdict" in c["body"] for c in env.gh.comments_list))

    def test_first_status_insertion_keeps_trailing_owner_text(self):
        """R3-F5."""
        env = self.env
        owner_text = "Owner notes  \n\t\n\n"
        env.gh.body = owner_text
        env.controller().update_pr_body("status")
        self.assertTrue(env.gh.body.startswith(owner_text))

    def test_readiness_checks_the_live_branch_head(self):
        """R4-F1: a lagging PR view cannot certify a handoff after the branch moved."""
        env = self.env
        ctl = env.controller()
        self.to_finalize(ctl)
        self.assertEqual("AWAITING_OWNER_REVIEW", ctl.finalize())
        head = git(env.work, "rev-parse", "HEAD")
        self.assertEqual([], ctl.readiness(head)[0])
        other = env.root / "other"
        subprocess.run(["git", "clone", "--quiet", "-b", env.branch, str(env.origin), str(other)], check=True)
        (other / "y.txt").write_text("y", encoding="utf-8")
        git(other, "add", "y.txt")
        git(other, "-c", "user.name=T", "-c", "user.email=t@e.invalid", "commit", "--quiet", "-m", "moved")
        git(other, "push", "--quiet", "origin", env.branch)
        env.gh.pr_overrides = {"headRefOid": head}  # GitHub's PR view has not caught up
        reasons, _ = ctl.readiness(head)
        self.assertTrue(any("branch head" in r for r in reasons))

    def test_transcript_delta_needs_positive_inventory_membership(self):
        """R4-F3: a path Git would display quoted is not mistaken for an inventoried record."""
        env = self.env
        ctl = env.controller()
        base = git(env.work, "rev-parse", "HEAD")
        rel = f"{ctl.transcript_folder()}/001-r\u00e9sum\u00e9.md"  # git displays this path quoted
        env.commit(rel, "not a controller record\n", "unexpected transcript file")
        with self.assertRaises(ar.Stop):
            ctl.verify_transcript_delta(base, git(env.work, "rev-parse", "HEAD"))

    def test_lost_post_with_stale_listing_is_not_duplicated(self):
        """R4-F4."""
        env = self.env
        ctl = env.controller()
        ctl.limits["uncertain_send_window_seconds"] = 600
        real_comments, hide = env.gh.comments, {"n": 99}

        def stale_listing(number):
            listing = real_comments(number)
            return listing[:-1] if hide["n"] > 0 and listing else listing
        env.gh.comments = stale_listing
        env.gh.lose_next_response = 1
        with self.assertRaises(ar.Stop) as stop:
            ctl.publish("r01-request", "### heading\nbody")
        self.assertEqual("PAUSED", stop.exception.status)
        self.assertEqual(1, len(env.gh.comments_list))  # never posted twice while delivery was uncertain
        hide["n"] = 0  # the stored comment becomes visible
        env.controller().settle_publications()
        self.assertEqual(1, len(env.gh.comments_list))
        self.assertFalse(env.controller().missing_publications())

    def test_shell_rules_are_mirrored_for_powershell(self):
        """Live smoke run 13: the PowerShell tool lacked an allowance the Bash tool had."""
        composed = ar.compose_developer_settings(self.env.controller().cfg, self.env.wf, "e1")
        for kind in ("allow", "deny"):
            rules = composed["permissions"][kind]
            for rule in rules:
                if rule.startswith("Bash("):
                    self.assertIn("PowerShell(" + rule[5:], rules)
        self.assertIn("PowerShell(git ls-remote *)", composed["permissions"]["allow"])
        self.assertIn("PowerShell(git checkout*)", composed["permissions"]["deny"])

    def test_stale_command_is_refused_after_cancellation(self):
        """R4-F5."""
        env = self.env
        stale = env.controller()  # resolved and status-checked before the lock
        env.controller().cancel("owner decision")
        with self.assertRaises(ar.UsageError):
            ar.guarded(stale, "review", lambda: self.fail("must not run"))


class DevProcRoundFiveTests(CrashFixture, Base):
    """Regressions for the development-process round-5 review findings."""

    def handed_off(self):
        ctl = self.env.controller()
        self.to_finalize(ctl)
        self.assertEqual("AWAITING_OWNER_REVIEW", ctl.finalize())
        return ctl

    def test_receipt_part_inventory_is_validated(self):
        """R1-F1: a posted receipt with no parts, or with a part missing, does not certify a handoff."""
        ctl = self.handed_off()
        key = next(k for k in ctl.state["publications"] if ar.VERDICT_KEY_RE.match(k) and k.startswith("final-"))
        self.assertFalse(ctl.missing_publications(include_receipt=key))
        saved = ctl.state["publications"][key]["parts"]
        ctl.state["publications"][key]["parts"] = []
        self.assertTrue(ctl.missing_publications(include_receipt=key))
        ctl.state["publications"][key]["parts"] = saved
        long_body = "### Workflow — note\n\n" + ("x" * 50 + "\n") * 2000
        ctl.publish("multi", long_body)
        multi = ctl.state["publications"]["multi"]
        self.assertGreater(len(multi["parts"]), 1)
        multi["parts"] = multi["parts"][:-1]  # a part lost from the inventory
        self.assertTrue(any(m.startswith("multi") for m in ctl.missing_publications()))

    def test_damage_is_cleared_only_by_the_same_argument_list(self):
        """R1-F2."""
        gates = {"unit": {"argv": [sys.executable, "-c", "print('ok')"], "extra_args_pattern": "A|B"}}
        plan = {"schema_version": "agent-review.plan.v1", "mission_id": "fixture", "checkpoints": [
            {"id": "phase-1", "type": "intermediate", "scope": "s", "exit_conditions": ["e"], "required_gates": ["unit"]},
            {"id": "final", "type": "final", "scope": "s", "exit_conditions": ["e"]}]}
        env = Env("foreground", plan=plan, cfg_overrides={"gates": gates})
        self.addCleanup(env.cleanup)
        ctl = env.controller()
        head = git(env.work, "rev-parse", "HEAD")
        a = ctl.run_gate("unit", ["A"])
        self.assertEqual([], ctl.missing_gates(head))
        stamp = ar.dt.datetime.now(ar.dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        damaged = dict(a, passed=False, exit_code=1)
        damaged.pop("recorded_at")  # a later failing run of A whose date was lost
        ar.atomic_write_json(receipt_path(ctl, head, "unit", ["A"], stamp), damaged)
        time.sleep(0.01)
        ctl.run_gate("unit", ["B"])  # a newer pass of a DIFFERENT argument list
        self.assertEqual(["unit"], ctl.missing_gates(head))
        ctl.run_gate("unit", ["A"])  # only a newer valid run of A clears A's damage
        self.assertEqual([], ctl.missing_gates(head))

    def test_unreadable_first_run_keeps_its_identity(self):
        """R1-F2 (round 6): the only run of A is unreadable; a later pass of B does not clear it."""
        gates = {"unit": {"argv": [sys.executable, "-c", "print('ok')"], "extra_args_pattern": "A|B"}}
        plan = {"schema_version": "agent-review.plan.v1", "mission_id": "fixture", "checkpoints": [
            {"id": "phase-1", "type": "intermediate", "scope": "s", "exit_conditions": ["e"], "required_gates": ["unit"]},
            {"id": "final", "type": "final", "scope": "s", "exit_conditions": ["e"]}]}
        env = Env("foreground", plan=plan, cfg_overrides={"gates": gates})
        self.addCleanup(env.cleanup)
        ctl = env.controller()
        head = git(env.work, "rev-parse", "HEAD")
        path = receipt_path(ctl, head, "unit", ["A"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{unreadable", encoding="utf-8")
        time.sleep(0.01)
        ctl.run_gate("unit", ["B"])
        self.assertEqual(["unit"], ctl.missing_gates(head))
        ctl.run_gate("unit", ["A"])
        self.assertEqual([], ctl.missing_gates(head))
        legacy = ctl.dir / "evidence" / f"gate-unit-{head[:12]}-99999999T999999999999Z.json"
        legacy.write_text("{unreadable", encoding="utf-8")  # an earlier naming scheme: scope unknowable
        ctl.run_gate("unit", ["A"])
        ctl.run_gate("unit", ["B"])
        self.assertEqual(["unit"], ctl.missing_gates(head))  # stays unresolved for this commit

    def test_replaced_gate_definition_is_history(self):
        """R6-F3: after a refresh changes a gate's command, old receipts no longer decide the gate."""
        gates = {"unit": {"argv": [sys.executable, "-c", "import sys; sys.exit(1)"]}}
        plan = {"schema_version": "agent-review.plan.v1", "mission_id": "fixture", "checkpoints": [
            {"id": "phase-1", "type": "intermediate", "scope": "s", "exit_conditions": ["e"], "required_gates": ["unit"]},
            {"id": "final", "type": "final", "scope": "s", "exit_conditions": ["e"]}]}
        env = Env("foreground", plan=plan, cfg_overrides={"gates": gates})
        self.addCleanup(env.cleanup)
        ctl = env.controller()
        head = git(env.work, "rev-parse", "HEAD")
        ctl.run_gate("unit")
        self.assertEqual(["unit"], ctl.missing_gates(head))
        ctl.cfg["gates"]["unit"] = {"argv": [sys.executable, "-c", "print('fixed command')"]}
        ctl.run_gate("unit")
        self.assertEqual([], ctl.missing_gates(head))

    def test_structurally_malformed_rollout_records_are_problems(self):
        """R1-F6."""
        with tempfile.TemporaryDirectory() as home:
            rev = ar.CodexReviewer({"executable": sys.executable, "codex_home": home, "model": "m", "effort": "high"})
            folder = Path(home) / "sessions"
            folder.mkdir()
            rollout = folder / f"rollout-1-{TID}.jsonl"
            meta = json.dumps({"type": "session_meta", "payload": {"id": TID}})
            for label, extra in {"null": "null", "array": "[1, 2]", "untyped": '{"payload": {}}',
                                 "second identity": json.dumps({"type": "session_meta", "payload": {"id": TID2}})}.items():
                with self.subTest(label):
                    rollout.write_text(meta + "\n" + extra + "\n", encoding="utf-8")
                    prov = rev.provenance(TID)  # never raises outside validation
                    self.assertTrue(prov.get("provenance_problem"), label)

    def test_archived_envelopes_carry_their_own_publication_links(self):
        """R2-F1: a partially sent verdict and its complete historical rendering keep their own references."""
        env = self.env
        ctl = env.controller()
        rounds_dir = ctl.dir / "rounds"
        rounds_dir.mkdir(exist_ok=True)
        path = rounds_dir / "env-7.json"
        ar.atomic_write_json(path, {"result": {"summary": "<round 7>"}})
        ctl.state["rounds"].append({"round": 7, "status": "historical", "envelope_path": str(path),
                                    "envelope_sha256": ar.sha256_file(path), "published": None})
        long_body = "### Codex GPT-6.2 Astra — review — round 7\n\n" + ("y" * 50 + "\n") * 2000
        ctl.queue("r07-review", long_body)
        normal = ctl.state["publications"]["r07-review"]
        ctl.send("r07-review", normal)
        normal["parts"][-1].update(comment_id=None, url=None)  # the last part never reached GitHub
        normal["state"] = "superseded"
        ctl.publish("r07-review-historical", long_body)
        ctl.archive("test")
        folder = Path(ctl.state["repo_root"]) / ctl.transcript_folder()
        partial = json.loads(next(folder.glob("*-r07-review-envelope.json")).read_text(encoding="utf-8"))
        full = json.loads(next(folder.glob("*-r07-review-historical-envelope.json")).read_text(encoding="utf-8"))
        self.assertEqual(len(normal["parts"]) - 1, len(partial["published"]))
        self.assertTrue(all(r["comment_id"] for r in partial["published"]))
        self.assertEqual(len(ctl.state["publications"]["r07-review-historical"]["parts"]), len(full["published"]))
        self.assertNotEqual({r["comment_id"] for r in partial["published"]}, {r["comment_id"] for r in full["published"]})

    def test_invalidated_damaged_envelope_does_not_block_the_final_archive(self):
        """R3-F4: carried through the last affected transition (archive)."""
        env = self.env
        env.reviewer.script = [{"decision": "checkpoint_passed"}, {"decision": "checkpoint_passed"}]
        ctl = env.controller()

        def crash_after_verdict(record):
            if "Astra — review" in record["body"]:
                env.gh.on_post = None
                raise KeyboardInterrupt("simulated crash after the verdict was stored")
        env.gh.on_post = crash_after_verdict
        ctl.accept_report(report(env, "phase-1"))
        ctl.transition("review", "t")
        with self.assertRaises(KeyboardInterrupt):
            ctl.review_round()
        restarted = env.controller()
        envelope = Path(restarted.active()["envelope_path"])
        envelope.write_bytes(envelope.read_bytes()[:40])
        self.assertEqual("checkpoint_passed", restarted.review_round())
        restarted.archive("test")  # succeeds; the damaged result is recorded as unavailable, not as authenticated
        folder = Path(restarted.state["repo_root"]) / restarted.transcript_folder()
        notes = [json.loads(p.read_text(encoding="utf-8")) for p in folder.glob("*-r01-review-envelope.json")]
        self.assertTrue(notes and notes[0]["envelope"].startswith("unavailable"))
        accepted = Path(restarted.state["rounds"][-1]["envelope_path"])
        accepted.write_text(accepted.read_text(encoding="utf-8") + " ", encoding="utf-8")
        restarted.state["archived_keys"] = [k for k in restarted.state.get("archived_keys", []) if not k.startswith("r02")]
        with self.assertRaises(ar.Stop):  # accepted envelopes must still be intact
            restarted.archive("test")

    def test_ambiguous_delivery_pauses_for_positive_resolution(self):
        """R4-F4."""
        env = self.env
        ctl = env.controller()
        real_comments = env.gh.comments
        env.gh.comments = lambda number: [c for c in real_comments(number) if "r01-request" not in c["body"]]
        env.gh.lose_next_response = 1  # stored, response lost, and the listing keeps omitting it
        with self.assertRaises(ar.Stop) as stop:
            ctl.publish("r01-request", "### heading\nbody")
        self.assertIn("ambiguous", stop.exception.reason)
        with self.assertRaises(ar.Stop):  # window expiry never authorizes another POST by itself
            env.controller().settle_publications()
        self.assertEqual(1, len(env.gh.comments_list))
        env.gh.comments_list.clear()  # the owner checks the PR: the comment really is absent
        env.gh.comments = real_comments
        owner = env.controller()
        owner.state.update(status="PAUSED")
        owner.resume("checked the PR; the request comment is absent", resend_undelivered=True)
        owner.settle_publications()
        self.assertEqual(1, len(env.gh.comments_list))
        self.assertFalse(owner.missing_publications())

    def test_package_only_install_recomposes_helper_permissions(self):
        """R5-F1."""
        env = self.env
        ctl = env.controller()
        other = env.root / "package-2"
        shutil.copytree(env.wf, other)  # same behavioral fingerprint, different package path
        moved = ar.Controller(env.dir, github=env.gh, reviewer=env.reviewer, developer=env.developer,
                              sleep=lambda s: None, workflow_root=other)
        moved.verify_inputs()
        settings = ar.read_json(env.controller().settings_path)
        helper = f"{other.resolve().as_posix()}/agent_review.py"
        self.assertTrue(any(helper in rule for rule in settings["permissions"]["allow"]))
        self.assertEqual(str(other), moved.state["workflow"]["root"])  # prompts' helper commands use self.wf too
        self.assertEqual(ar.sha256_file(moved.settings_path), moved.state["developer_settings_sha256"])

    def test_reopen_at_the_round_cap_is_consistent_and_resumable(self):
        """R5-F2."""
        env = self.env
        ctl = self.handed_off()
        cp = ctl.checkpoint["id"]
        ctl.state["limits"]["max_review_rounds_per_checkpoint"] = ctl.state["rounds_completed"][cp]
        ctl.save()
        env.commit("late.txt", "late\n", "moved after handoff")
        env.push()
        self.assertNotEqual(ar.EXIT_OK, ar.guarded(ctl, "resume", lambda: ctl.resume("owner looked")))
        on_disk = ar.read_json(env.dir / "state.json")
        self.assertEqual(("develop", "BLOCKED", None), (on_disk["phase"], on_disk["status"], on_disk["handoff"]))
        self.assertTrue(env.controller().helper_authority_problems())  # helpers are not available while blocked
        self.assertIn("exhausted", env.gh.comments_list[-1]["body"])  # the stop is visible on the PR
        again = env.controller()
        self.assertTrue(again.resume("extend", max_rounds=ctl.state["rounds_completed"][cp] + 2).startswith("ACTIVE"))

    def test_new_receipt_retires_the_previous_one(self):
        """R5-F3."""
        env = self.env
        ctl = env.controller()
        self.to_finalize(ctl)
        real_edit, calls = env.gh.edit_body, {"n": 0}

        def edit_fails_once(number, body_file):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ar.CommandError(["gh", "pr", "edit"], subprocess.CompletedProcess(
                    ["gh"], 1, "", "simulated HTTP 502 editing the PR body"))
            return real_edit(number, body_file)
        env.gh.edit_body = edit_fails_once
        self.assertNotEqual(ar.EXIT_OK, ar.guarded(ctl, "finalize", ctl.finalize))
        first = [k for k in ctl.state["publications"] if ar.VERDICT_KEY_RE.match(k) and k.startswith("final-")]
        self.assertEqual(1, len(first))
        resumed = env.controller()
        self.assertEqual("AWAITING_OWNER_REVIEW", resumed.resume("retry after the edit failure"))
        receipts = {k: p["state"] for k, p in resumed.state["publications"].items()
                    if ar.VERDICT_KEY_RE.match(k) and k.startswith("final-")}
        current = [k for k, v in receipts.items() if v != "superseded"]
        self.assertEqual(1, len(current))
        self.assertNotIn(first[0], current)  # the PAUSED status was archived, so the handoff moved to a new A
        self.assertEqual("posted", resumed.state["publications"][first[0] + "-retired"]["state"])

    def test_headless_effort_must_be_observed(self):
        """R5-F4."""
        env = Env("headless")
        self.addCleanup(env.cleanup)

        def work(e):
            e.commit("a.txt", "a\n", "work")
            e.push()
            return report(e, "phase-1")
        work.efforts = []
        env.developer.script = [work]
        ctl = env.controller()
        with self.assertRaises(ar.Stop) as stop:
            ctl.develop_step()
        self.assertIn("effort not affirmatively", stop.exception.reason)

    def test_activation_can_refresh_the_pinned_project_config(self):
        """A reviewed project change (e.g. a new gate) reaches a running enrollment only through activate."""
        env = self.env
        ctl = env.controller()
        cfg = json.loads(json.dumps(ctl.cfg))
        cfg["gates"] = {"extra": {"argv": [sys.executable, "-c", "print(1)"]}}
        projects = env.wf / "projects"
        projects.mkdir(exist_ok=True)
        ar.atomic_write_json(projects / "fixture-refresh.json", cfg)
        ctl.activate(refresh_project="fixture-refresh")
        self.assertIn("extra", env.controller().cfg["gates"])
        self.assertEqual(1, len(env.controller().state["project_history"]))
        cfg["repository"] = "someone/else"
        ar.atomic_write_json(projects / "fixture-refresh.json", cfg)
        with self.assertRaises(ar.UsageError):
            env.controller().activate(refresh_project="fixture-refresh")

    def test_probe_outcomes_come_from_cli_records(self):
        """R3-F3: decisions are read from tool_use/tool_result records and permission_denials ids."""
        log = self.env.root / "probe.jsonl"
        rows = [{"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "u1", "name": "Bash",
                                                                "input": {"command": "ambient"}}]}},
                {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "u1", "is_error": True,
                                                          "content": "denied"}]}},
                {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "u2", "name": "Bash",
                                                                "input": {"command": "helper"}}]}},
                {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "u2", "is_error": True,
                                                          "content": "refused: not registered (permission ok)"}]}},
                {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "u3", "name": "Bash",
                                                                "input": {"command": "unfinished"}}]}}]
        log.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        self.assertEqual([("ambient", "denied"), ("helper", "error"), ("unfinished", "no_result")],
                         ar._tool_outcomes(log, {"u1"}))


class DevProcRoundSixTests(CrashFixture, Base):
    """Regressions for the development-process round-6 review findings."""

    def handed_off(self):
        ctl = self.env.controller()
        self.to_finalize(ctl)
        self.assertEqual("AWAITING_OWNER_REVIEW", ctl.finalize())
        return ctl

    def test_rollout_headers_and_payloads_are_validated(self):
        """R1-F6."""
        with tempfile.TemporaryDirectory() as home:
            rev = ar.CodexReviewer({"executable": sys.executable, "codex_home": home, "model": "m", "effort": "high"})
            folder = Path(home) / "sessions"
            folder.mkdir()
            rollout = folder / f"rollout-1-{TID}.jsonl"
            meta = json.dumps({"type": "session_meta", "payload": {"id": TID}})
            for header in ("null", "[1]", '{"type": "session_meta", "payload": null}'):
                rollout.write_text(header + "\n", encoding="utf-8")
                self.assertFalse(rev.provenance(TID)["rollout_found"])  # no exception, no identity
            sibling = folder / f"rollout-2-{TID2}.jsonl"
            sibling.write_text("[1, 2]\n", encoding="utf-8")  # malformed sibling header is skipped safely
            for label, extra in {"null response payload": {"type": "response_item", "payload": None},
                                 "settings not an object": {"type": "event_msg", "payload": {
                                     "type": "thread_settings_applied", "thread_settings": "high"}},
                                 "profile not an object": {"type": "event_msg", "payload": {
                                     "type": "thread_settings_applied", "thread_settings": {"permission_profile": []}}},
                                 "token info not an object": {"type": "event_msg", "payload": {
                                     "type": "token_count", "info": 5}}}.items():
                with self.subTest(label):
                    rollout.write_text(meta + "\n" + json.dumps(extra) + "\n", encoding="utf-8")
                    prov = rev.provenance(TID)
                    self.assertTrue(prov.get("provenance_problem"), label)

    def test_interrupted_permission_rebinding_stays_resumable(self):
        """R5-F1 / R7-F5: the durable interrupted state (a staged file for the new package, state still selecting the
        previous file) is built on disk; the normal entry point completes the rebinding with persistence intact.
        An altered staged copy is replaced by the intended composition, never adopted."""
        env = self.env
        first = env.controller()
        previous = first.state["developer_settings_file"]
        other = env.root / "package-3"
        shutil.copytree(env.wf, other)
        composed = ar.compose_developer_settings(first.cfg, other, first.state["enrollment_id"], first.state["repo_root"])
        text = json.dumps(composed, indent=2) + "\n"
        staged = env.dir / f"developer-settings-{ar.sha256_bytes(text.encode('utf-8'))[:16]}.json"
        staged.write_text('{"permissions": {"allow": ["Bash(*)"]}}', encoding="utf-8")  # staged, then altered
        self.assertEqual(previous, ar.read_json(env.dir / "state.json")["developer_settings_file"])
        moved = ar.Controller(env.dir, github=env.gh, reviewer=env.reviewer, developer=env.developer,
                              sleep=lambda s: None, workflow_root=other)
        moved.verify_inputs()
        on_disk = ar.read_json(env.dir / "state.json")
        self.assertEqual((staged.name, str(other)), (on_disk["developer_settings_file"], on_disk["workflow"]["root"]))
        self.assertEqual(composed, ar.read_json(staged))  # the intended bytes, not the altered copy
        self.assertEqual(ar.sha256_bytes(text.encode("utf-8")), on_disk["developer_settings_sha256"])
        staged.write_text('{"permissions": {"allow": ["Bash(*)"]}}', encoding="utf-8")
        with self.assertRaises(ar.Stop):  # an edit to the selected file is still rejected
            ar.Controller(env.dir, github=env.gh, reviewer=env.reviewer, developer=env.developer,
                          sleep=lambda s: None, workflow_root=other).verify_inputs()

    def test_effort_is_bound_to_the_current_invocation(self):
        """R5-F4."""
        with tempfile.TemporaryDirectory() as config:
            sid = str(uuid.uuid4())
            folder = Path(config) / "projects" / "p"
            folder.mkdir(parents=True)
            rows = [{"type": "assistant", "timestamp": "2026-11-20T10:00:00.000Z", "effort": "high",
                     "message": {"model": OPUS}},
                    {"type": "assistant", "timestamp": "2026-11-20T11:00:00.500Z", "message": {"model": OPUS}}]
            (folder / f"{sid}.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
            dev = ar.ClaudeDeveloper({"executable": sys.executable, "model": "opus", "effort": "high",
                                      "config_dir": config}, Path("s"), Path("x"))
            self.assertEqual(["high"], dev.session_provenance(sid)["efforts"])  # whole session
            self.assertEqual([], dev.session_provenance(sid, since="2026-11-20T10:59:59")["efforts"])  # this run

    def test_uncertain_delivery_is_corrected_on_retirement(self):
        """R6-F1."""
        env = self.env
        ctl = env.controller()
        head = git(env.work, "rev-parse", "HEAD")
        ctl.queue("r05-review", "### Codex GPT-6.2 Astra — review — round 5\n\nverdict")
        pub = ctl.state["publications"]["r05-review"]
        pub["parts"][0]["posting_since"] = ar.now_iso()  # a POST whose outcome is unknown; not yet listed
        ctl.retire_verdict({"round": 5, "H": head}, "test retirement")
        self.assertIn("r05-review-superseded", ctl.state["publications"])  # corrected in advance
        stored = {"id": 4242, "user": "owner", "url": "https://example.test/c/4242",
                  "body": ctl.outbox_body("r05-review", pub["parts"][0])}
        env.gh.comments_list.append(stored)  # the uncertain POST appears later
        ctl.settle_publications()
        ctl.archive("test")
        folder = Path(ctl.state["repo_root"]) / ctl.transcript_folder()
        self.assertTrue(list(folder.glob("*-r05-review.md")))  # its delivered text is on the record
        self.assertEqual(4242, pub["parts"][0]["comment_id"])

    def test_project_refresh_that_changes_review_inputs_reopens_review(self):
        """R6-F2."""
        env = self.env
        ctl = self.handed_off()
        cfg = json.loads(json.dumps(ctl.cfg))
        cfg["instructions"] = list(cfg.get("instructions") or []) + ["NEW-INSTRUCTIONS.md"]
        projects = env.wf / "projects"
        projects.mkdir(exist_ok=True)
        ar.atomic_write_json(projects / "fixture-refresh.json", cfg)
        result = ctl.activate(refresh_project="fixture-refresh")
        self.assertIn("owner-review handoff", result["invalidated"])
        self.assertIsNone(ctl.state["ready_review"])
        self.assertEqual("review", ctl.state["phase"])

    def test_receipt_corrections_are_substantive(self):
        """R6-F4."""
        env = self.env
        ctl = self.handed_off()
        receipt = next(k for k in ctl.state["publications"] if ar.VERDICT_KEY_RE.match(k) and k.startswith("final-"))
        ctl.retire_receipts("test")
        correction = ctl.state["publications"][receipt + "-retired"]
        self.assertEqual("posted", correction["state"])
        self.assertFalse(ctl.missing_publications())
        env.gh.comments_list = [c for c in env.gh.comments_list if c["id"] != correction["parts"][0]["comment_id"]]
        self.assertIn(receipt + "-retired", ctl.missing_publications())


class DevProcRoundSevenTests(CrashFixture, Base):
    """Regressions for the development-process round-7 review findings (no internal persistence is stubbed)."""

    def handed_off(self):
        ctl = self.env.controller()
        self.to_finalize(ctl)
        self.assertEqual("AWAITING_OWNER_REVIEW", ctl.finalize())
        return ctl

    def gated_env(self, gates):
        plan = {"schema_version": "agent-review.plan.v1", "mission_id": "fixture", "checkpoints": [
            {"id": "phase-1", "type": "intermediate", "scope": "s", "exit_conditions": ["e"], "required_gates": ["unit"]},
            {"id": "final", "type": "final", "scope": "s", "exit_conditions": ["e"]}]}
        env = Env("foreground", plan=plan, cfg_overrides={"gates": gates})
        self.addCleanup(env.cleanup)
        return env

    def test_failed_activation_persists_nothing(self):
        """R7-F1: a failure inside activation (here GitHub failing during verdict retirement) leaves the previous
        workflow and its permission binding together; a retry commits the new version and binding together."""
        env = self.env
        env.reviewer.script = [{"decision": "checkpoint_passed"}]
        ctl = env.controller()

        def crash_after_verdict(record):
            if "Astra — review" in record["body"]:
                env.gh.on_post = None
                raise KeyboardInterrupt("simulated crash after the verdict was stored")
        env.gh.on_post = crash_after_verdict
        ctl.accept_report(report(env, "phase-1"))
        ctl.transition("review", "t")
        with self.assertRaises(KeyboardInterrupt):
            ctl.review_round()
        before = ar.read_json(env.dir / "state.json")
        base_path = env.wf / "settings" / "developer.base.json"
        base = ar.read_json(base_path)
        base["permissions"]["deny"].append("Bash(newly-denied *)")  # the new version also changes the permission base
        ar.atomic_write_json(base_path, base)
        real_comments = env.gh.comments
        env.gh.comments = lambda number: (_ for _ in ()).throw(RuntimeError("simulated GitHub listing outage"))
        with self.assertRaises(RuntimeError):
            env.controller().activate()
        after = ar.read_json(env.dir / "state.json")
        self.assertEqual((before["workflow"]["fingerprint"], before["developer_settings_file"]),
                         (after["workflow"]["fingerprint"], after["developer_settings_file"]))
        env.gh.comments = real_comments
        retry = env.controller()
        result = retry.activate()
        on_disk = ar.read_json(env.dir / "state.json")
        self.assertEqual(result["activated"], on_disk["workflow"]["fingerprint"])
        self.assertNotEqual(before["developer_settings_file"], on_disk["developer_settings_file"])
        self.assertEqual("invalidated", on_disk["rounds"][0]["status"])

    def test_rollout_leaf_values_and_discriminators(self):
        """R1-F6."""
        with tempfile.TemporaryDirectory() as home:
            rev = ar.CodexReviewer({"executable": sys.executable, "codex_home": home, "model": "m", "effort": "high"})
            folder = Path(home) / "sessions"
            folder.mkdir()
            rollout = folder / f"rollout-1-{TID}.jsonl"
            meta = json.dumps({"type": "session_meta", "payload": {"id": TID}})
            cases = {"object model": {"type": "turn_context", "payload": {"model": {"x": 1}, "effort": "high"}},
                     "list approval": {"type": "event_msg", "payload": {"type": "thread_settings_applied",
                                                                         "thread_settings": {"approval_policy": ["never"]}}},
                     "no discriminator": {"type": "response_item", "payload": {}}}
            for label, extra in cases.items():
                with self.subTest(label):
                    rollout.write_text(meta + "\n" + json.dumps(extra) + "\n", encoding="utf-8")
                    prov = rev.provenance(TID)  # never raises
                    self.assertTrue(prov.get("provenance_problem"), label)
                    reasons, _ = ar.invocation_problems({"completed": True, "thread_id": TID}, prov,
                                                        {"model": "m", "effort": "high"})
                    self.assertTrue(any("unreliable" in r for r in reasons))

    def test_effort_comes_from_records_appended_by_this_invocation(self):
        """R5-F4: adjacent invocations; position, not time, separates them."""
        with tempfile.TemporaryDirectory() as config:
            sid = str(uuid.uuid4())
            folder = Path(config) / "projects" / "p"
            folder.mkdir(parents=True)
            transcript = folder / f"{sid}.jsonl"
            stamp = ar.dt.datetime.now(ar.dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            transcript.write_text(json.dumps({"type": "assistant", "timestamp": stamp, "effort": "high",
                                              "message": {"model": OPUS}}) + "\n", encoding="utf-8")
            dev = ar.ClaudeDeveloper({"executable": sys.executable, "model": "opus", "effort": "high",
                                      "config_dir": config}, Path("s"), Path("x"))
            positions = {str(transcript): len(transcript.read_bytes())}
            with open(transcript, "a", encoding="utf-8") as handle:  # the next invocation, same second
                handle.write(json.dumps({"type": "assistant", "timestamp": stamp, "message": {"model": OPUS}}) + "\n")
            self.assertEqual([], dev.session_provenance(sid, after=positions)["efforts"])
            self.assertEqual(["high"], dev.session_provenance(sid)["efforts"])

    def test_narrowed_argument_policy_retires_excluded_evidence(self):
        """R7-F2."""
        env = self.gated_env({"unit": {"argv": [sys.executable, "-c", "print('ok')"], "extra_args_pattern": "A|B"}})
        ctl = env.controller()
        head = git(env.work, "rev-parse", "HEAD")
        ctl.run_gate("unit", ["A"])
        self.assertEqual([], ctl.missing_gates(head))
        ctl.cfg["gates"]["unit"]["extra_args_pattern"] = "B"  # a refresh narrows the allowed filters
        self.assertEqual(["unit"], ctl.missing_gates(head))
        ctl.run_gate("unit", ["B"])
        self.assertEqual([], ctl.missing_gates(head))

    def test_intact_predecessor_receipts_are_attributed(self):
        """R6-F3."""
        env = self.gated_env({"unit": {"argv": [sys.executable, "-c", "import sys; sys.exit(1)"]}})
        ctl = env.controller()
        head = git(env.work, "rev-parse", "HEAD")
        receipt = ctl.run_gate("unit")
        evidence = ctl.dir / "evidence"
        for path in list(evidence.glob(f"gate-unit-{head[:12]}-*.json")):  # the earlier naming scheme
            legacy = evidence / f"gate-unit-{head[:12]}-{receipt['recorded_at']}.json"
            path.rename(legacy)
        self.assertEqual(["unit"], ctl.missing_gates(head))  # an intact failing run still decides the gate
        ctl.cfg["gates"]["unit"] = {"argv": [sys.executable, "-c", "print('fixed')"]}
        ctl.run_gate("unit")  # the replacement definition: the old intact receipt is history
        self.assertEqual([], ctl.missing_gates(head))

    def test_a_gate_in_progress_or_interrupted_is_visible(self):
        """R7-F3: the durable state of an interrupted helper (a pending run record) is built on disk."""
        env = self.gated_env({"unit": {"argv": [sys.executable, "-c", "print('ok')"]}})
        ctl = env.controller()
        head = git(env.work, "rev-parse", "HEAD")
        ctl.run_gate("unit")
        self.assertEqual([], ctl.missing_gates(head))
        receipt = sorted((ctl.dir / "evidence").glob("gate-unit-*.json"))[-1]
        stamp = ar.dt.datetime.now(ar.dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        pending = receipt.with_name(re.sub(r"-\d{8}T\d{12}Z\.json$", f"-{stamp}.pending", receipt.name))
        pending.write_text("{}", encoding="utf-8")  # a newer run started and never completed
        self.assertEqual(["unit"], ctl.missing_gates(head))
        ctl.run_gate("unit")  # recovery through a completed valid rerun
        self.assertEqual([], ctl.missing_gates(head))

    def test_reopen_at_the_cap_is_blocked_before_any_publication(self):
        """R5-F2: the BLOCKED status is persisted with the cleared handoff even if publication then fails."""
        env = self.env
        ctl = self.handed_off()
        cp = ctl.checkpoint["id"]
        ctl.state["limits"]["max_review_rounds_per_checkpoint"] = ctl.state["rounds_completed"][cp]
        ctl.save()
        env.commit("late.txt", "late\n", "moved after handoff")
        env.push()
        env.gh.fail_next = 99  # every publication fails (definitely not delivered)
        with self.assertRaises(ar.Stop):
            ctl.resume("owner looked")
        on_disk = ar.read_json(env.dir / "state.json")
        self.assertEqual(("develop", "BLOCKED", None), (on_disk["phase"], on_disk["status"], on_disk["handoff"]))
        self.assertTrue(any(k.endswith("-reopened") and p["state"] == "pending"
                            for k, p in on_disk["publications"].items()))  # queued, sent on a later settle
        env.gh.fail_next = 0
        env.controller().settle_publications()
        self.assertTrue(any("reopened" in c["body"] for c in env.gh.comments_list))

    def test_unresolved_part_is_not_archived_and_blocks_the_handoff(self):
        """R6-F1."""
        env = self.env
        ctl = env.controller()
        long_body = "### Codex GPT-6.2 Astra — review — round 6\n\n" + ("z" * 50 + "\n") * 2000
        ctl.queue("r06-review", long_body)
        pub = ctl.state["publications"]["r06-review"]
        ctl.send("r06-review", pub)
        lost = pub["parts"][-1]
        stored = next(c for c in env.gh.comments_list if c["id"] == lost["comment_id"])
        env.gh.comments_list.remove(stored)  # its delivery is uncertain and not yet listed
        lost.update(comment_id=None, url=None, posting_since=ar.now_iso())
        pub["state"] = "superseded"
        ctl.archive("test")
        folder = Path(ctl.state["repo_root"]) / ctl.transcript_folder()
        self.assertFalse(list(folder.glob("*-r06-review.md")))
        self.assertTrue(any("not yet resolved" in r for r in ctl.readiness(git(env.work, "rev-parse", "HEAD"))[0]
                            ) or ctl.state.get("ready_review") is None)
        env.gh.comments_list.append(stored)  # it becomes visible later
        ctl.archive("test")
        record = next(folder.glob("*-r06-review.md")).read_text(encoding="utf-8")
        self.assertIn(f"of {len(pub['parts'])} part(s) were published", record)
        self.assertTrue(all(p["comment_id"] for p in pub["parts"]))

    def test_a_retired_verdict_never_advances_after_restart(self):
        """R7-F4: the durable state after a retirement (verdict superseded, round still validated) is built on
        disk; the round is invalidated and reviewed again, never accepted."""
        env = self.env
        env.reviewer.script = [{"decision": "checkpoint_passed"}, {"decision": "checkpoint_passed"}]
        ctl = env.controller()

        def crash_after_verdict(record):
            if "Astra — review" in record["body"]:
                env.gh.on_post = None
                raise KeyboardInterrupt("simulated crash after the verdict was stored")
        env.gh.on_post = crash_after_verdict
        ctl.accept_report(report(env, "phase-1"))
        ctl.transition("review", "t")
        with self.assertRaises(KeyboardInterrupt):
            ctl.review_round()
        state = ar.read_json(env.dir / "state.json")
        state["publications"]["r01-review"]["state"] = "superseded"
        ar.atomic_write_json(env.dir / "state.json", state)
        restarted = env.controller()
        self.assertEqual("checkpoint_passed", restarted.review_round())
        self.assertEqual("invalidated", restarted.state["rounds"][0]["status"])
        self.assertEqual("accepted", restarted.state["rounds"][-1]["status"])
        self.assertEqual(2, len(env.reviewer.calls))


class DevProcRoundEightTests(CrashFixture, Base):
    """Regressions for the development-process round-8 review findings."""

    def handed_off(self):
        ctl = self.env.controller()
        self.to_finalize(ctl)
        self.assertEqual("AWAITING_OWNER_REVIEW", ctl.finalize())
        return ctl

    def gated_env(self, gates):
        plan = {"schema_version": "agent-review.plan.v1", "mission_id": "fixture", "checkpoints": [
            {"id": "phase-1", "type": "intermediate", "scope": "s", "exit_conditions": ["e"], "required_gates": ["unit"]},
            {"id": "final", "type": "final", "scope": "s", "exit_conditions": ["e"]}]}
        env = Env("foreground", plan=plan, cfg_overrides={"gates": gates})
        self.addCleanup(env.cleanup)
        return env

    def test_gate_completing_during_checks_never_exposes_the_older_pass(self):
        """R7-F3: a real gate run (failing this time) completes while readiness is checked continuously."""
        import threading
        flag = Path(tempfile.mkdtemp(prefix="agent-review-flag-")) / "exit-code"
        self.addCleanup(shutil.rmtree, flag.parent, True)
        flag.write_text("0", encoding="utf-8")
        code = f"import time, sys, pathlib; time.sleep(0.4); sys.exit(int(pathlib.Path({str(flag)!r}).read_text()))"
        env = self.gated_env({"unit": {"argv": [sys.executable, "-c", code]}})
        ctl = env.controller()
        head = git(env.work, "rev-parse", "HEAD")
        ctl.run_gate("unit")
        self.assertEqual([], ctl.missing_gates(head))  # the older pass
        flag.write_text("1", encoding="utf-8")
        runner = env.controller()
        thread = threading.Thread(target=runner.run_gate, args=("unit",))
        thread.start()
        evidence = ctl.dir / "evidence"
        while not list(evidence.glob("gate-unit-*.pending"))[1:]:  # the second run's marker exists
            time.sleep(0.005)
        observations = []
        while thread.is_alive():
            observations.append(ctl.missing_gates(head))
        thread.join()
        observations.append(ctl.missing_gates(head))
        self.assertTrue(observations)
        self.assertTrue(all(o == ["unit"] for o in observations), observations)  # never the older pass

    def test_conflicting_applied_settings_and_unnamed_tool_calls(self):
        """R1-F6."""
        with tempfile.TemporaryDirectory() as home:
            rev = ar.CodexReviewer({"executable": sys.executable, "codex_home": home, "model": "m", "effort": "high"})
            folder = Path(home) / "sessions"
            folder.mkdir()
            rollout = folder / f"rollout-1-{TID}.jsonl"
            meta = json.dumps({"type": "session_meta", "payload": {"id": TID}})

            def applied(model):
                return json.dumps({"type": "event_msg", "payload": {"type": "thread_settings_applied", "thread_settings": {
                    "model": model, "reasoning_effort": "high", "approval_policy": "never",
                    "permission_profile": {"network": "restricted"}}}})
            rollout.write_text("\n".join([meta, applied("other-model"), applied("m")]) + "\n", encoding="utf-8")
            prov = rev.provenance(TID)
            self.assertTrue(prov["observed_model"].startswith("<conflicting"))  # the earlier setting is kept
            reasons, _ = ar.invocation_problems({"completed": True, "thread_id": TID}, prov,
                                                {"model": "m", "effort": "high"})
            self.assertTrue(any("model" in r for r in reasons))
            unnamed = json.dumps({"type": "response_item", "payload": {"type": "function_call", "arguments": "{}"}})
            rollout.write_text("\n".join([meta, applied("m"), unnamed]) + "\n", encoding="utf-8")
            self.assertIn("tool name", rev.provenance(TID)["provenance_problem"])

    def test_verdict_removed_from_github_is_not_accepted(self):
        """R7-F4: the verdict is authenticated on the PR before acceptance."""
        env = self.env
        env.reviewer.script = [{"decision": "checkpoint_passed"}]
        ctl = env.controller()

        def delete_after_store(record):
            if "Astra — review" in record["body"]:
                env.gh.on_post = None
                env.gh.comments_list.remove(record)  # removed on GitHub right after it was stored
        env.gh.on_post = delete_after_store
        ctl.accept_report(report(env, "phase-1"))
        ctl.transition("review", "t")
        with self.assertRaises(ar.Stop) as stop:
            ctl.review_round()
        self.assertIn("not completely published", stop.exception.reason)
        self.assertEqual({}, ctl.state["rounds_completed"])
        resumed = env.controller()
        self.assertEqual("checkpoint_passed", resumed.review_round())  # re-sent, authenticated, then accepted
        self.assertEqual(1, len(env.reviewer.calls))
        self.assertFalse(resumed.publication_problems("r01-review", resumed.state["publications"]["r01-review"],
                                                      env.gh.comments(7)))

    def test_extension_is_persisted_with_the_reopen(self):
        """R5-F2."""
        env = self.env
        ctl = self.handed_off()
        cp = ctl.checkpoint["id"]
        cap = ctl.state["rounds_completed"][cp]
        ctl.state["limits"]["max_review_rounds_per_checkpoint"] = cap
        ctl.save()
        env.commit("late.txt", "late\n", "moved after handoff")
        env.push()
        env.gh.fail_next = 99  # settlement fails after the reopen transaction
        with self.assertRaises(ar.Stop):
            ctl.resume("extend", max_rounds=cap + 2)
        on_disk = ar.read_json(env.dir / "state.json")
        self.assertEqual(("ACTIVE", cap + 2), (on_disk["status"], on_disk["limits"]["max_review_rounds_per_checkpoint"]))

    def test_preceding_hashed_receipts_keep_their_failing_scope(self):
        """R6-F3: the preceding hashed format (definition id = argv only, and no run markers) with an unchanged
        declaration: its own failing receipt decides the gate."""
        flag = Path(tempfile.mkdtemp(prefix="agent-review-flag-")) / "code"
        self.addCleanup(shutil.rmtree, flag.parent, True)
        flag.write_text("1", encoding="utf-8")
        code = f"import sys, pathlib; sys.exit(int(pathlib.Path({str(flag)!r}).read_text()))"
        env = self.gated_env({"unit": {"argv": [sys.executable, "-c", code], "extra_args_pattern": "A|B"}})
        ctl = env.controller()
        head = git(env.work, "rev-parse", "HEAD")
        decl = ctl.cfg["gates"]["unit"]
        ctl.run_gate("unit", ["A"])  # fails
        flag.write_text("0", encoding="utf-8")
        ctl.run_gate("unit", ["B"])  # passes
        evidence = ctl.dir / "evidence"
        for marker in evidence.glob("gate-*.pending"):
            marker.unlink()  # that format had no run markers
        for path in evidence.glob("gate-unit-*.json"):
            path.rename(path.with_name(path.name.replace(f"-d{ar.gate_definition_id(decl)}-",
                                                         f"-d{ar.legacy_definition_id(decl)}-")))
        self.assertFalse(list(evidence.glob("gate-*.pending")))
        self.assertEqual(["unit"], ctl.missing_gates(head))  # decided by A's legacy failing receipt alone
        ctl.run_gate("unit", ["A"])
        self.assertEqual([], ctl.missing_gates(head))

    def test_earliest_format_with_a_narrowed_filter_is_history(self):
        """R6-F3: timestamp-only receipts (no run markers); the declaration later narrows its filters."""
        flag = Path(tempfile.mkdtemp(prefix="agent-review-flag-")) / "code"
        self.addCleanup(shutil.rmtree, flag.parent, True)
        flag.write_text("1", encoding="utf-8")
        code = f"import sys, pathlib; sys.exit(int(pathlib.Path({str(flag)!r}).read_text()))"
        env = self.gated_env({"unit": {"argv": [sys.executable, "-c", code], "extra_args_pattern": "A|B"}})
        ctl = env.controller()
        head = git(env.work, "rev-parse", "HEAD")
        ctl.run_gate("unit", ["A"])  # fails under the earliest format
        evidence = ctl.dir / "evidence"
        for marker in evidence.glob("gate-*.pending"):
            marker.unlink()
        for path in evidence.glob("gate-unit-*.json"):
            receipt = ar.read_json(path)
            path.rename(evidence / f"gate-unit-{head[:12]}-{receipt['recorded_at']}.json")
        self.assertEqual(["unit"], ctl.missing_gates(head))  # intact and in scope: it decides the gate
        ctl.cfg["gates"]["unit"]["extra_args_pattern"] = "B"  # A is now positively excluded
        flag.write_text("0", encoding="utf-8")
        ctl.run_gate("unit", ["B"])
        self.assertEqual([], ctl.missing_gates(head))  # the excluded legacy failure is history

    def test_late_confirmed_part_is_appended_and_required(self):
        """R6-F1: a key archived with part of its inventory gets an append-only supplement."""
        env = self.env
        ctl = env.controller()
        long_body = "### Codex GPT-6.2 Astra — review — round 6\n\n" + ("q" * 50 + "\n") * 2000
        ctl.queue("r06-review", long_body)
        pub = ctl.state["publications"]["r06-review"]
        ctl.send("r06-review", pub)
        late = pub["parts"][-1]
        saved = (late["comment_id"], late["url"])
        late.update(comment_id=None, url=None)  # as an earlier version recorded it: not yet confirmed
        pub["state"] = "superseded"
        ctl.archive("first")
        self.assertIn("r06-review", ctl.state["archived_keys"])
        folder = Path(ctl.state["repo_root"]) / ctl.transcript_folder()
        late["comment_id"], late["url"] = saved  # confirmed later
        self.assertEqual([late], ctl.unarchived_parts(pub))
        ctl.archive("second")
        self.assertEqual([], ctl.unarchived_parts(pub))
        names = [n for n in git(env.work, "ls-tree", "-r", "--name-only", "HEAD").splitlines()
                 if n.endswith("-r06-review-supplement.md")]
        committed = git(env.work, "show", f"HEAD:{names[0]}")
        total = len(pub["parts"])
        self.assertIn(f"part {total} of {total}: comment {saved[0]} ({saved[1]})", committed)

    def test_receipt_corrections_are_archived(self):
        """R8-F1."""
        env = self.env
        ctl = self.handed_off()
        receipt = next(k for k in ctl.state["publications"] if ar.VERDICT_KEY_RE.match(k) and k.startswith("final-"))
        ctl.retire_receipts("test")
        ctl.archive("after correction")
        folder = Path(ctl.state["repo_root"]) / ctl.transcript_folder()
        self.assertTrue(list(folder.glob(f"*-{receipt}-retired.md")))
        self.assertFalse(list(folder.glob(f"*-{receipt}.md")))  # the receipt itself describes the archive head

    def test_activation_supersedes_an_outstanding_request(self):
        """R8-F2."""
        env = self.env
        ctl = env.controller()
        ctl.accept_report(report(env, "phase-1"))
        candidate = ctl.capture_candidate()
        ctl.state["rounds"].append({"round": 1, "request_id": "x-r01-old", "checkpoint_id": "phase-1",
                                    "checkpoint_type": "intermediate", **candidate, "pending_findings": [],
                                    "report": ctl.state["last_report"], "created_at": ar.now_iso(),
                                    "status": "requested", "attempts": [], "attempt_seq": 0,
                                    "contract": {"workflow": ctl.state["workflow"]["fingerprint"],
                                                 "project": ar.project_digest(ctl.cfg)}})
        ctl.state.update(active_round=1, phase="review")
        ctl.save()
        (env.wf / "prompts" / "reviewer.md").write_text("new rules\n", encoding="utf-8")
        result = env.controller().activate()
        self.assertIn("round 1 request", result["invalidated"])
        env.reviewer.script = [{"decision": "checkpoint_passed"}]
        fresh = env.controller()
        self.assertEqual("checkpoint_passed", fresh.review_round())
        self.assertNotEqual("x-r01-old", fresh.state["rounds"][-1]["request_id"])

    def test_final_pass_with_an_open_correctness_finding_is_invalid(self):
        """R8-F3."""
        env = self.env
        ctl = env.controller()
        self.to_finalize(ctl)
        ctl.state["findings"]["R9-F1"] = {"status": "open", "category": "defect", "blocks_readiness": False,
                                          "title": "non-blocking defect"}
        reasons, _ = ctl.readiness(git(env.work, "rev-parse", "HEAD"))
        self.assertTrue(any("actionable correctness" in r for r in reasons))

    def test_quota_error_in_json_events_is_fatal(self):
        """R8-F4."""
        path = self.env.root / "events.jsonl"
        path.write_text('{"type":"thread.started","thread_id":"%s"}\n{"type":"turn.started"}\n'
                        '{"type":"error","message":"You have hit your usage limit. Try again later."}\n' % TID,
                        encoding="utf-8")
        info = {"exit_code": 1, **ar.parse_codex_events(path)}
        self.assertTrue(info["errors"])
        ctl = self.env.controller()
        rnd = {"round": 1, "pending_findings": [], "checkpoint_type": "intermediate", "checkpoint_id": "phase-1",
               "request_id": "x-r01-q", "H": "0" * 40, "B": "0" * 40, "M": "0" * 40}
        envelope = ctl.validate_review(rnd, self.env.root / "missing.json", info, {}, self.env.root / "missing.txt")
        self.assertTrue(envelope["fatal"])

    def test_documented_module_invocation_imports(self):
        """R8-F5."""
        root = Path(ar.__file__).resolve().parent.parent
        out = subprocess.run([sys.executable, "-m", "unittest", "agent_review/test_live_smoke.py"], cwd=root,
                             capture_output=True, text=True, timeout=300,
                             env={k: v for k, v in os.environ.items() if k != "AGENT_REVIEW_LIVE"})
        self.assertEqual(0, out.returncode, out.stderr[-2000:])


class DevProcRoundNineTests(CrashFixture, Base):
    """Regressions for the development-process round-9 review findings."""

    def test_lagging_listing_never_causes_a_duplicate_verdict(self):
        """R9-F1."""
        env = self.env
        env.reviewer.script = [{"decision": "checkpoint_passed"}]
        ctl = env.controller()
        real_comments = env.gh.comments
        env.gh.comments = lambda number: [c for c in real_comments(number) if "Astra — review" not in c["body"]]
        ctl.accept_report(report(env, "phase-1"))
        ctl.transition("review", "t")
        with self.assertRaises(ar.Stop) as stop:
            ctl.review_round()
        self.assertIn("may lag", stop.exception.reason)
        record = ar.read_json(env.dir / "state.json")["publications"]["r01-review"]
        self.assertTrue(all(p["comment_id"] for p in record["parts"]))  # acknowledged IDs are kept
        with self.assertRaises(ar.Stop):
            env.controller().review_round()  # still lagging: still no second POST
        env.gh.comments = real_comments
        self.assertEqual("checkpoint_passed", env.controller().review_round())
        self.assertEqual(1, sum("Astra — review" in c["body"] for c in env.gh.comments_list))

    def test_report_admission_waits_for_a_running_helper(self):
        """R7-F3: a push/verify helper holding the helper lock (between authority and its run marker) blocks the
        foreground report admission and the transition out of develop."""
        env = self.env
        ctl = env.controller()
        with ctl.helper_lock("verify"):  # held exactly as the verify helper holds it
            with self.assertRaises(ar.UsageError):
                env.controller().admit_report(report(env, "phase-1"), "t")
        self.assertEqual("develop", ar.read_json(env.dir / "state.json")["phase"])
        self.assertIsNone(env.controller().admit_report(report(env, "phase-1"), "t"))
        self.assertEqual("review", ar.read_json(env.dir / "state.json")["phase"])

    def test_restated_defect_keeps_its_correctness_obligation(self):
        """R8-F3: restating a rejected defect as optional polish cannot permit a final pass."""
        env = self.env
        env.reviewer.script = [{"decision": "checkpoint_passed"},
                               {"decision": "changes_required",
                                "findings": [finding("R2-F1", blocks=False), finding("R2-F2")]},
                               ] + [{"decision": "ready_for_owner_review",
                                     "assessments": [("R2-F1", "fix_rejected"), ("R2-F2", "fix_verified")],
                                     "findings": [finding("R2-F1", blocks=False, category="optional_polish")]}] * 3
        ctl = env.controller()
        self.submit(ctl, "phase-1")
        self.submit(ctl, "final")
        sha = env.commit("final.txt", "attempt\n", "attempt R2-F1 and R2-F2")
        env.push()
        with self.assertRaises(ar.Stop) as stop:
            self.submit(ctl, "final", [fixed("R2-F1", sha), fixed("R2-F2", sha)])
        self.assertIn("actionable correctness", stop.exception.reason)
        self.assertTrue(ctl.state["findings"]["R2-F1"]["correctness_obligation"])

    def test_duplicate_members_are_rejected(self):
        """R1-F6."""
        path = self.env.root / "events.jsonl"
        path.write_text('{"type":"thread.started","thread_id":"%s"}\n{"type":"turn.completed","type":"turn.started"}\n'
                        % TID, encoding="utf-8")
        self.assertFalse(ar.parse_codex_events(path)["completed"])
        with tempfile.TemporaryDirectory() as home:
            rev = ar.CodexReviewer({"executable": sys.executable, "codex_home": home, "model": "m", "effort": "high"})
            folder = Path(home) / "sessions"
            folder.mkdir()
            rollout = folder / f"rollout-1-{TID}.jsonl"
            meta = json.dumps({"type": "session_meta", "payload": {"id": TID}})
            dup = ('{"type":"event_msg","payload":{"type":"thread_settings_applied","thread_settings":'
                   '{"model":"other","model":"m","reasoning_effort":"high"}}}')
            rollout.write_text(meta + "\n" + dup + "\n", encoding="utf-8")
            self.assertIn("malformed", rev.provenance(TID)["provenance_problem"])
            rollout.write_text('{"type":"session_meta","payload":{"id":"x","id":"%s"}}\n' % TID, encoding="utf-8")
            self.assertFalse(rev.provenance(TID)["rollout_found"])  # a duplicate-member header is not an identity

    def test_recorded_fatal_attempt_is_never_retried_after_restart(self):
        """R9-F2: the durable state after a fatal attempt is built on disk."""
        env = self.env
        ctl = env.controller()
        ctl.accept_report(report(env, "phase-1"))
        candidate = ctl.capture_candidate()
        ctl.state["rounds"].append({"round": 1, "request_id": "x-r01-f", "checkpoint_id": "phase-1",
                                    "checkpoint_type": "intermediate", **candidate, "pending_findings": [],
                                    "report": ctl.state["last_report"], "created_at": ar.now_iso(),
                                    "status": "reviewing", "attempt_seq": 1,
                                    "attempts": [{"n": 1, "started": ar.now_iso(), "ended": ar.now_iso(), "ok": False,
                                                  "fatal": True, "reasons": ["reviewer reported a usage limit"]}],
                                    "contract": {"workflow": ctl.state["workflow"]["fingerprint"],
                                                 "project": ar.project_digest(ctl.cfg)}})
        ctl.state.update(active_round=1, phase="review", status="ACTIVE")
        ctl.save()
        with self.assertRaises(ar.Stop) as stop:
            env.controller().review_round()
        self.assertEqual("BLOCKED", stop.exception.status)
        self.assertEqual([], env.reviewer.calls)

    def test_commit_statuses_are_paginated_and_current(self):
        """R9-F3: the real GitHub client against a gh shim (the external boundary)."""
        shim_dir = Path(tempfile.mkdtemp(prefix="agent-review-gh-"))
        self.addCleanup(shutil.rmtree, shim_dir, True)
        script = shim_dir / "gh.py"
        script.write_text("\n".join([
            "import json, sys",
            "args = sys.argv[1:]",
            f"open({str(shim_dir / 'calls.jsonl')!r}, 'a').write(json.dumps(args) + chr(10))",
            "if any(a.endswith('/statuses') for a in args):",
            "    for row in [('ci', 'success'), ('ci', 'failure'), ('lint', 'success')]:  # newest first",
            "        print(json.dumps({'name': row[0], 'status': 'completed', 'conclusion': row[1], 'app_id': None}))",
            ""]), encoding="utf-8")
        shim = shim_dir / "gh.cmd"
        shim.write_text(f'@"{sys.executable}" "{script}" %*\n', encoding="utf-8")
        checks = ar.GitHub("owner/repo", gh=str(shim)).commit_checks("a" * 40)
        calls = [json.loads(line) for line in (shim_dir / "calls.jsonl").read_text().splitlines()]
        status_call = next(c for c in calls if any(a.endswith("/statuses") for a in c))
        self.assertIn("--paginate", status_call)
        self.assertEqual({"ci": "success", "lint": "success"}, {c["name"]: c["conclusion"] for c in checks})


class GitHubCommentTransportTests(unittest.TestCase):
    """Comment bodies are read over the REST API exactly as stored (gh 2.99.0 rewrites literal backslash-u0000 in the
    output it prints). GitHub is simulated by local HTTP servers (clearly labeled: canned REST responses); the gh shim
    supplies only the credential and, if asked for API output, prints what gh 2.99.0 printed (caret notation), so any
    read through gh's output fails the comparisons."""

    TOKEN = "test-token-6f1c"

    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"GH_HOST": "github.com"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def serve(self, routes):
        """A local server answering GET path -> (status, headers, payload[, reason, declared_length]); headers is a list of
        (name, value) pairs (repeated names allowed); every request is recorded."""
        import http.server
        requests = []
        token = self.TOKEN
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append((self.path, self.headers.get("Authorization")))
                route = routes.get(self.path)
                if route is None:
                    route = (404, [], {"message": "Not Found"})
                elif self.headers.get("Authorization") != "Bearer " + token:
                    route = (401, [], {"message": "Bad credentials"})
                elif callable(route):
                    route = route(self.server.server_port)
                status, headers, payload = route[0], route[1], route[2]
                reason = route[3] if len(route) > 3 else None
                data = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
                declared = route[4] if len(route) > 4 else len(data)
                self.send_response(status, reason)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(declared))
                for name, value in headers:
                    self.send_header(name, value)
                self.end_headers()
                self.wfile.write(data)
            def log_message(self, *args):
                pass
        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server.server_port, requests

    def shim(self, printed=None, auth_exit=0, auth_stdout=None, auth_stderr=""):
        """The gh shim: `auth token` answers as configured; any other call prints the record serialized once, as gh 2.99.0
        printed it (literal backslash-u0000 in caret notation)."""
        shim_dir = Path(tempfile.mkdtemp(prefix="agent-review-gh-"))
        self.addCleanup(shutil.rmtree, shim_dir, True)
        (shim_dir / "record.json").write_text(json.dumps(printed), encoding="utf-8")
        (shim_dir / "auth.json").write_text(json.dumps({"exit": auth_exit, "stdout": self.TOKEN if auth_stdout is None else auth_stdout,
                                                        "stderr": auth_stderr}), encoding="utf-8")
        script = shim_dir / "gh.py"
        script.write_text("\n".join([
            "import json, sys",
            "from pathlib import Path",
            "here = Path(__file__).parent",
            "args = sys.argv[1:]",
            "open(here / 'calls.txt', 'a').write(' '.join(args) + chr(10))",
            "if args[:2] == ['auth', 'token']:",
            "    auth = json.loads((here / 'auth.json').read_text(encoding='utf-8'))",
            "    sys.stdout.write(auth['stdout'] + chr(10)); sys.stderr.write(auth['stderr']); sys.exit(auth['exit'])",
            "B = chr(92)",
            "text = (here / 'record.json').read_text(encoding='utf-8')",
            "sys.stdout.write(text.replace(B + B + 'u0000', B + B + '^@') + chr(10))  # gh 2.99.0's printed output",
            ""]), encoding="utf-8")
        shim = shim_dir / "gh.cmd"
        shim.write_text(f'@"{sys.executable}" "{script}" %*\n', encoding="utf-8")
        self.calls = shim_dir / "calls.txt"
        return shim

    def github(self, port, printed=None, **auth):
        return ar.GitHub("owner/repo", gh=str(self.shim(printed, **auth)), api_base=f"http://127.0.0.1:{port}")

    def failure(self, call, secret=None):
        with self.assertRaises(ar.CommandError) as caught:
            call()
        for value in (self.TOKEN, secret):
            if value:
                self.assertNotIn(value, str(caught.exception))
                self.assertNotIn(value, caught.exception.stderr)
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)  # nothing chained: the displayed exception is the whole diagnostic
        if secret:
            import traceback
            self.assertNotIn(secret, "".join(traceback.format_exception(caught.exception)))
        return str(caught.exception)

    @staticmethod
    def record(cid, body, login="agent"):
        return {"id": cid, "html_url": f"https://example.test/c/{cid}", "user": {"login": login}, "body": body}

    def test_comment_bodies_are_read_exactly_despite_gh_output_sanitizing(self):
        """Literal escapes (backslash-u0000, backslash-n, backslash-backslash-u0041), actual control characters (U+0000, U+0001,
        ESC, tab, CR) and ordinary Unicode (accents, CJK, a non-BMP emoji, Hebrew) read back exactly from the single lookup and
        from a three-page listing (absolute and relative next links), in order; the shim's own printed record, serialized once,
        shows the caret form gh 2.99.0 produced for the same body."""
        B = chr(92)
        literal = 'the JSON string "stock-' + B + 'u0000created", ' + B + 'n and ' + B + B + 'u0041'
        control = 'actual "x' + chr(0) + 'y' + chr(1) + chr(27) + '[0m' + chr(9) + chr(13) + '"'
        unicode = 'caf' + chr(0xE9) + ' ' + chr(0x6F22) + chr(0x5B57) + ' ' + chr(0x1F40E) + ' ' + chr(0x5E9) + chr(0x5DC) + chr(0x5D5) + chr(0x5DD)
        body = '<!-- marker -->\n' + literal + '\n' + control + '\n' + unicode + '\n'
        record = self.record(7, body)
        first, second = self.record(5, unicode), self.record(6, literal, "other")
        listing = "/repos/owner/repo/issues/5/comments"
        port, requests = self.serve({
            "/repos/owner/repo/issues/comments/7": (200, [], record),
            listing + "?per_page=100": lambda p: (200, [("Link", f'<http://127.0.0.1:{p}{listing}?per_page=100&page=2>; rel="next", '
                                                                 f'<http://127.0.0.1:{p}{listing}?per_page=100&page=3>; rel="last"')], [first]),
            listing + "?per_page=100&page=2": (200, [("Link", f'<{listing}?per_page=100&page=3>; rel="next"')], [second]),
            listing + "?per_page=100&page=3": (200, [], [record]),
        })
        github = self.github(port, printed=record)
        found = github.comment(7)
        self.assertEqual(body, found["body"])
        self.assertEqual({"id": 7, "url": "https://example.test/c/7", "user": "agent"}, {k: found[k] for k in ("id", "url", "user")})
        self.assertEqual([(5, unicode, "agent"), (6, literal, "other"), (7, body, "agent")],
                         [(c["id"], c["body"], c["user"]) for c in github.comments(5)])
        self.assertEqual(3, sum(1 for path, _ in requests if path.startswith(listing)))
        self.assertTrue(all(auth == "Bearer " + self.TOKEN for _, auth in requests))
        calls = self.calls.read_text(encoding="utf-8").splitlines()
        self.assertTrue(calls and all(c == "auth token --hostname github.com" for c in calls), calls)
        # The shim's printed API output, parsed independently: the caret form, not the stored six characters.
        printed = json.loads(ar.run([str(self.shim(record)), "api", "repos/owner/repo/issues/comments/7"]).stdout)
        self.assertIn(B + "^@created", printed["body"])
        self.assertNotIn(B + "u0000", printed["body"])
        self.assertIn(B + "u0000created", found["body"])

    def test_a_missing_comment_is_distinguished_from_request_failures(self):
        """Only HTTP 404 on a single comment means deleted (None). Authentication, rate limiting, other statuses, a missing
        listing, a failure on a later page, an undecodable response and a refused connection all raise, never None or a
        partial listing, and no message carries the credential."""
        listing = "/repos/owner/repo/issues/9/comments"
        port, _ = self.serve({
            "/repos/owner/repo/issues/comments/20": (401, [], {"message": "Bad credentials"}),
            "/repos/owner/repo/issues/comments/21": (403, [("X-RateLimit-Remaining", "0"), ("X-RateLimit-Reset", "1798761600")], {"message": "rate"}),
            "/repos/owner/repo/issues/comments/22": (429, [("Retry-After", "60")], {"message": "secondary rate limit"}),
            "/repos/owner/repo/issues/comments/23": (403, [], {"message": "Resource not accessible"}),
            "/repos/owner/repo/issues/comments/24": (500, [], {"message": "Server Error"}),
            "/repos/owner/repo/issues/comments/25": (200, [], b"<html>not json</html>"),
            listing + "?per_page=100": lambda p: (200, [("Link", f'<http://127.0.0.1:{p}{listing}?per_page=100&page=2>; rel="next"')],
                                                  [self.record(1, "page one")]),
            listing + "?per_page=100&page=2": (502, [], {"message": "Bad Gateway"}),
        })
        github = self.github(port)
        self.assertIsNone(github.comment(19))
        self.assertIn("HTTP 401: authentication failed", self.failure(lambda: github.comment(20)))
        self.assertIn("HTTP 403: rate limited (retry after 1798761600)", self.failure(lambda: github.comment(21)))
        self.assertIn("HTTP 429: rate limited (retry after 60)", self.failure(lambda: github.comment(22)))
        self.assertIn("HTTP 403: Forbidden", self.failure(lambda: github.comment(23)))
        self.assertIn("HTTP 500: Internal Server Error", self.failure(lambda: github.comment(24)))
        self.assertIn("undecodable response", self.failure(lambda: github.comment(25)))
        self.assertIn("HTTP 404", self.failure(lambda: github.comments(8)))
        self.assertIn("HTTP 502", self.failure(lambda: github.comments(9)))
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            closed = probe.getsockname()[1]
        self.assertIn("request failed", self.failure(lambda: self.github(closed).comment(7)))

    def test_failure_diagnostics_never_carry_the_credential(self):
        """A synthetic credential in the failing helper's stdout and stderr, in an HTTP reason phrase and in rate-limit header values
        never reaches the exception message or its stderr; only validated numbers and standard status descriptions do."""
        secret = "ghp_SYNTHETIC0123456789secret"
        port, _ = self.serve({
            "/repos/owner/repo/issues/comments/40": (500, [], {"message": secret}, "Boom " + secret),
            "/repos/owner/repo/issues/comments/41": (429, [("Retry-After", secret), ("X-RateLimit-Reset", "12 " + secret)], {"message": secret}, secret),
            "/repos/owner/repo/issues/comments/42": (403, [("X-RateLimit-Remaining", "0"), ("X-RateLimit-Reset", "1798761600")], {"message": secret}, secret),
        })
        failing = self.github(port, auth_exit=1, auth_stdout=secret, auth_stderr="error: " + secret + "\n")
        self.assertIn("authentication failed: gh auth token exited 1", self.failure(lambda: failing.comment(40), secret))
        empty = self.github(port, auth_stdout="")
        self.assertIn("authentication failed: gh auth token exited 0", self.failure(lambda: empty.comment(40), secret))
        github = self.github(port)
        self.assertIn("HTTP 500: Internal Server Error", self.failure(lambda: github.comment(40), secret))
        self.assertIn("HTTP 429: rate limited (retry after unknown)", self.failure(lambda: github.comment(41), secret))
        self.assertIn("HTTP 403: rate limited (retry after 1798761600)", self.failure(lambda: github.comment(42), secret))

    def test_incomplete_or_malformed_pages_are_never_a_listing(self):
        """A later page cut short of its Content-Length, a later 206 with valid JSON, a 200 object where a listing array is required
        and a comment without a string body all raise CommandError; a genuine empty array is a valid empty listing."""
        base = "/repos/owner/repo/issues/{}/comments"
        def two(number, second):
            path = base.format(number)
            return {path + "?per_page=100": lambda p: (200, [("Link", f'<http://127.0.0.1:{p}{path}?per_page=100&page=2>; rel="next"')], [self.record(1, "one")]),
                    path + "?per_page=100&page=2": second}
        routes = {}
        routes.update(two(11, (200, [], [self.record(2, "two")], None, 500)))
        routes.update(two(12, (206, [], [self.record(2, "two")])))
        routes[base.format(13) + "?per_page=100"] = (200, [], {"id": 3, "body": "not a list"})
        routes[base.format(14) + "?per_page=100"] = (200, [], [{"id": 4, "html_url": "u", "user": {"login": "agent"}}])
        routes[base.format(15) + "?per_page=100"] = (200, [], [])
        routes["/repos/owner/repo/issues/comments/16"] = (200, [], [self.record(16, "a list, not an object")])
        port, _ = self.serve(routes)
        github = self.github(port)
        self.assertIn("request failed: IncompleteRead", self.failure(lambda: github.comments(11)))
        self.assertIn("HTTP 206: unexpected status for a GET", self.failure(lambda: github.comments(12)))
        self.assertIn("unexpected response shape", self.failure(lambda: github.comments(13)))
        self.assertIn("unexpected comment record", self.failure(lambda: github.comments(14)))
        self.assertEqual([], github.comments(15))
        self.assertIn("unexpected response shape", self.failure(lambda: github.comment(16)))

    def test_pagination_follows_every_link_field_exactly_once(self):
        """A redirected listing whose next target is query-relative, in a second Link field with an unquoted rel among other
        parameters, resolves against the effective (redirected) URL: every ID arrives once, in order. A repeated next target ends
        with CommandError."""
        moved = "/repositories/1/issues/5/comments"
        port, requests = self.serve({
            "/repos/owner/repo/issues/5/comments?per_page=100": (301, [("Location", moved + "?per_page=100")], {}),
            moved + "?per_page=100": (200, [("Link", '<https://example.test/doc>; rel="help"'), ("Link", '<?per_page=100&page=2>; title="p2"; rel=next')],
                                      [self.record(1, "one"), self.record(2, "two")]),
            moved + "?per_page=100&page=2": (200, [("Link", '<?per_page=100&page=1>; rel="prev first"')], [self.record(3, "three")]),
            "/repos/owner/repo/issues/6/comments?per_page=100": (200, [("Link", '<?per_page=100&page=2>; rel="next"')], [self.record(1, "one")]),
            "/repos/owner/repo/issues/6/comments?per_page=100&page=2": (200, [("Link", '<?per_page=100&page=2>; rel="next"')], [self.record(2, "two")]),
        })
        github = self.github(port)
        self.assertEqual([1, 2, 3], [c["id"] for c in github.comments(5)])
        self.assertEqual(1, sum(1 for path, _ in requests if path == moved + "?per_page=100&page=2"))
        self.assertIn("pagination link repeated", self.failure(lambda: github.comments(6)))

    def test_the_credential_is_sent_only_to_the_api_origin(self):
        """A pagination link or a redirect to another port (another origin) is refused without sending anything there; a
        same-origin redirect is followed with the credential."""
        other_port, other_requests = self.serve({"/stolen": (200, [], [])})
        listing = "/repos/owner/repo/issues/3/comments"
        port, requests = self.serve({
            listing + "?per_page=100": (200, [("Link", f'<http://127.0.0.1:{other_port}/stolen>; rel="next"')], []),
            "/repos/owner/repo/issues/comments/30": (302, [("Location", f"http://127.0.0.1:{other_port}/stolen")], {}),
            "/repos/owner/repo/issues/comments/31": (301, [("Location", "/repositories/1/issues/comments/31")], {}),
            "/repositories/1/issues/comments/31": (200, [], self.record(31, "moved")),
        })
        github = self.github(port)
        self.assertIn("pagination link to another origin refused", self.failure(lambda: github.comments(3)))
        self.assertIn("redirect to another origin refused", self.failure(lambda: github.comment(30)))
        self.assertEqual([], other_requests)
        self.assertEqual("moved", github.comment(31)["body"])
        self.assertIn(("/repositories/1/issues/comments/31", "Bearer " + self.TOKEN), requests)

    def test_equivalent_origins_compare_equal(self):
        """A case variant of github.com selects the public API; implicit and explicit default ports compare equal; a different
        port or scheme is a different origin; an enterprise host keeps its own API base."""
        github = ar.GitHub("owner/repo", gh=sys.executable)
        with mock.patch.dict(os.environ, {"GH_HOST": "GitHub.COM"}):
            self.assertEqual("https://api.github.com", github._api_base())
        with mock.patch.dict(os.environ, {"GH_HOST": "GHE.Example.Test"}):
            self.assertEqual("https://ghe.example.test/api/v3", github._api_base())
        origin = ar.GitHub._origin
        self.assertEqual(origin("https://api.github.com/x"), origin("https://API.GitHub.com:443/y?page=2"))
        self.assertEqual(origin("http://127.0.0.1/x"), origin("http://127.0.0.1:80/y"))
        self.assertNotEqual(origin("https://api.github.com/x"), origin("https://api.github.com:8443/x"))
        self.assertNotEqual(origin("https://api.github.com/x"), origin("http://api.github.com/x"))

    def test_quoted_link_delimiters_do_not_hide_the_next_page(self):
        """R1-F4: a comma, a semicolon and an escaped quote inside a quoted title before rel=next, and a comma inside another
        entry's quoted title and inside a target, do not hide page two: both IDs arrive exactly once. A Link field that cannot be
        parsed ends with CommandError, never a shortened listing."""
        listing = "/repos/owner/repo/issues/{}/comments"
        first, second = listing.format(5), listing.format(6)
        port, requests = self.serve({
            first + "?per_page=100": lambda p: (200, [("Link", f'<http://127.0.0.1:{p}{first}?per_page=100&page=2>; '
                                                               'title="page two, continued; really \\"two\\", ok"; rel="next"')],
                                                [self.record(1, "one")]),
            first + "?per_page=100&page=2": (200, [], [self.record(2, "two")]),
            second + "?per_page=100": (200, [("Link", '<https://example.test/doc?a=1,2>; title="help, see also"; rel="help", '
                                                      '<?per_page=100&page=2>; rel="next"')], [self.record(3, "three")]),
            second + "?per_page=100&page=2": (200, [], [self.record(4, "four")]),
            listing.format(7) + "?per_page=100": (200, [("Link", '<?per_page=100&page=2>; title="unterminated, rel="next"')],
                                                  [self.record(5, "five")]),
        })
        github = self.github(port)
        self.assertEqual([1, 2], [c["id"] for c in github.comments(5)])
        self.assertEqual([3, 4], [c["id"] for c in github.comments(6)])
        self.assertEqual(1, sum(1 for path, _ in requests if path == first + "?per_page=100&page=2"))
        self.assertEqual(1, sum(1 for path, _ in requests if path == second + "?per_page=100&page=2"))
        self.assertIn("undecodable response: ValueError", self.failure(lambda: github.comments(7)))
        entries = ar.GitHub._link_entries('<a,b>; title="x, \\"y\\"; z"; REL=next, <c>;rel="prev first"')
        self.assertEqual([("a,b", [("title", 'x, "y"; z'), ("rel", "next")]), ("c", [("rel", "prev first")])], entries)

    def test_a_link_parameter_without_a_value_is_refused(self):
        """R3-F1: page two of a three-page listing ends its Link field with an incomplete `rel=` (also `rel=""` and `rel= ;`):
        GitHub.comments raises CommandError instead of returning the first two pages as complete. Control: the same listing with
        rel=next returns all three IDs, each page fetched exactly once."""
        listing = "/repos/owner/repo/issues/{}/comments"
        routes = {}
        for number, tail in ((80, "rel=next"), (81, "rel="), (82, 'rel=""'), (83, "rel= ;"), (84, "rel==next"), (85, "rel=ne<xt"), (86, "r@l=next")):
            path = listing.format(number)
            routes[path + "?per_page=100"] = (lambda path: lambda p: (200, [("Link", f'<http://127.0.0.1:{p}{path}?per_page=100&page=2>; rel="next"')],
                                                                     [self.record(1, "one")]))(path)
            routes[path + "?per_page=100&page=2"] = (lambda path, tail: lambda p: (200, [("Link", f'<http://127.0.0.1:{p}{path}?per_page=100&page=3>; {tail}')],
                                                                                   [self.record(2, "two")]))(path, tail)
            routes[path + "?per_page=100&page=3"] = (200, [], [self.record(3, "three")])
        port, requests = self.serve(routes)
        github = self.github(port)
        self.assertEqual([1, 2, 3], [c["id"] for c in github.comments(80)])
        self.assertEqual(1, sum(1 for path, _ in requests if path == listing.format(80) + "?per_page=100&page=3"))
        for number in (81, 82, 83, 84, 85, 86):  # R4-F1: an unquoted value or a name that is not an HTTP token is malformed too
            self.assertIn("undecodable response: ValueError", self.failure(lambda: github.comments(number)))
        with self.assertRaises(ValueError):
            ar.GitHub._link_entries('<a>; rel=')
        self.assertEqual([("a", [("title", "")])], ar.GitHub._link_entries('<a>; title=""'))  # an explicit empty quoted title stays valid
        self.assertEqual([("a", [("title", "a=b; c"), ("rel", "next")])], ar.GitHub._link_entries('<a>; title="a=b; c"; rel=next'))  # quoted "=" stays valid

    def test_link_relations_follow_the_relation_type_syntax(self):
        """Owner instruction 2026-11-27b section 5 (the R4-F1 failure family) through the public paginated reader, on page two of a
        three-page listing. Positive controls: a quoted title containing "=" before rel="next", a relation list with an extension
        relation, and an upper-case NEXT return all three IDs once. A page whose only relation is a valid unknown one is a genuine
        last page. Refused with CommandError (no listing): a quoted malformed relation rel="=next", an entry with no rel parameter,
        and a quoted relation holding a control character."""
        listing = "/repos/owner/repo/issues/{}/comments"
        cases = {90: 'title="a=b; c=d"; rel="next"', 91: 'rel="prev https://example.test/rel/extra next"', 92: 'rel=NEXT',
                 93: 'rel="https://example.test/rel/other"', 94: 'rel="=next"', 95: 'title="next page"', 96: 'rel="ne\\u0001xt"'}
        routes = {}
        for number, tail in cases.items():
            path = listing.format(number)
            routes[path + "?per_page=100"] = (lambda path: lambda p: (200, [("Link", f'<http://127.0.0.1:{p}{path}?per_page=100&page=2>; rel="next"')],
                                                                     [self.record(1, "one")]))(path)
            routes[path + "?per_page=100&page=2"] = (lambda path, tail: lambda p: (200, [("Link", f'<http://127.0.0.1:{p}{path}?per_page=100&page=3>; {tail}')],
                                                                                   [self.record(2, "two")]))(path, tail.replace("\\u0001", chr(1)))
            routes[path + "?per_page=100&page=3"] = (200, [], [self.record(3, "three")])
        port, requests = self.serve(routes)
        github = self.github(port)
        for number in (90, 91, 92):
            self.assertEqual([1, 2, 3], [c["id"] for c in github.comments(number)])
            self.assertEqual(1, sum(1 for path, _ in requests if path == listing.format(number) + "?per_page=100&page=3"))
        self.assertEqual([1, 2], [c["id"] for c in github.comments(93)])
        self.assertEqual(0, sum(1 for path, _ in requests if path == listing.format(93) + "?per_page=100&page=3"))
        for number in (94, 95, 96):
            self.assertIn("undecodable response: ValueError", self.failure(lambda: github.comments(number)))

    def test_comment_records_require_the_author_key(self):
        """R1-F3: otherwise identical records with an omitted user and an explicitly null user: the omitted field fails the whole
        lookup and the whole listing (also on a later page); the explicit null remains readable."""
        def record(cid, user=...):
            data = {"id": cid, "html_url": f"https://example.test/c/{cid}", "body": "<!-- marker -->"}
            if user is not ...:
                data["user"] = user
            return data
        listing = "/repos/owner/repo/issues/{}/comments"
        port, _ = self.serve({
            "/repos/owner/repo/issues/comments/50": (200, [], record(50)),
            "/repos/owner/repo/issues/comments/51": (200, [], record(51, None)),
            listing.format(52) + "?per_page=100": lambda p: (200, [("Link", f'<http://127.0.0.1:{p}{listing.format(52)}?per_page=100&page=2>; rel="next"')],
                                                             [self.record(1, "one")]),
            listing.format(52) + "?per_page=100&page=2": (200, [], [record(2)]),
            listing.format(53) + "?per_page=100": (200, [], [self.record(1, "one"), record(2, None)]),
        })
        github = self.github(port)
        self.assertIn("unexpected comment record", self.failure(lambda: github.comment(50)))
        self.assertEqual({"id": 51, "url": "https://example.test/c/51", "user": None, "body": "<!-- marker -->"}, github.comment(51))
        self.assertIn("unexpected comment record", self.failure(lambda: github.comments(52)))
        self.assertEqual([("agent", 1), (None, 2)], [(c["user"], c["id"]) for c in github.comments(53)])

    def test_an_explicit_port_zero_is_not_the_default_port(self):
        """R2-F1: explicit port zero differs from an omitted HTTP or HTTPS port (omitted and explicit default ports still compare
        equal). Against an API on its default port, a pagination link and a redirect to port zero of the same host are refused
        before any request is made there with the credential (the opener is replaced by a recorder at the urllib boundary)."""
        origin = ar.GitHub._origin
        for scheme, default in (("https", 443), ("http", 80)):
            self.assertNotEqual(origin(f"{scheme}://api.github.com/x"), origin(f"{scheme}://api.github.com:0/x"))
            self.assertEqual((scheme, "api.github.com", 0), origin(f"{scheme}://api.github.com:0/x"))
            self.assertEqual(origin(f"{scheme}://api.github.com/x"), origin(f"{scheme}://api.github.com:{default}/x"))
        import email.message
        sent, handlers = [], []

        class Response:
            def __init__(self, url, link):
                self.status, self.url, self.headers = 200, url, email.message.Message()
                self.headers["Link"] = link
            def read(self):
                return json.dumps([GitHubCommentTransportTests.record(1, "one")]).encode("utf-8")
            def geturl(self):
                return self.url
            def __enter__(self):
                return self
            def __exit__(self, *exc):
                return False

        class Opener:
            def open(self, request, timeout=None):
                sent.append((request.full_url, request.get_header("Authorization")))
                if request.full_url.endswith("/issues/comments/9"):  # a server redirecting to port zero of the same host
                    handlers[-1].redirect_request(request, None, 302, "Found", {}, "http://api.test:0/stolen")
                return Response(request.full_url, '<http://api.test:0/repos/owner/repo/issues/4/comments?page=2>; rel="next"')

        def build_opener(*given):
            handlers.extend(given)
            return Opener()
        github = ar.GitHub("owner/repo", gh=str(self.shim()), api_base="http://api.test")
        with mock.patch.object(ar.urllib.request, "build_opener", build_opener):
            self.assertIn("pagination link to another origin refused", self.failure(lambda: github.comments(4)))
            self.assertIn("redirect to another origin refused", self.failure(lambda: github.comment(9)))
        self.assertEqual(["http://api.test/repos/owner/repo/issues/4/comments?per_page=100",
                          "http://api.test/repos/owner/repo/issues/comments/9"], [url for url, _ in sent])
        self.assertTrue(all(":0" not in url for url, _ in sent))

    def test_credential_helper_launch_failures_and_timeouts_are_safe(self):
        """R2-F2: a helper that cannot be started (an absent executable, the real process boundary) and a helper that times out
        with synthetic partial output (subprocess.TimeoutExpired carrying it, injected at the process call) both reach the caller as
        CommandError; neither the message, its stderr, an exception chain nor the formatted traceback carries the helper's output,
        and no request is sent."""
        secret = "ghp_SYNTHETIC_partial_0123456789"
        port, requests = self.serve({"/repos/owner/repo/issues/comments/60": (200, [], self.record(60, "x"))})
        absent = ar.GitHub("owner/repo", gh=str(Path(tempfile.gettempdir()) / "agent-review-absent" / "gh.exe"),
                           api_base=f"http://127.0.0.1:{port}")
        self.assertIn("authentication failed: gh auth token could not be started (FileNotFoundError)",
                      self.failure(lambda: absent.comment(60), secret))
        github = self.github(port)
        expired = subprocess.TimeoutExpired(["gh", "auth", "token"], 60, output=secret + "\n", stderr="partial " + secret)
        with mock.patch.object(ar, "run", side_effect=expired) as call:
            message = self.failure(lambda: github.comment(60), secret)
            self.assertIn("authentication failed: gh auth token timed out after 60 s", message)
            self.assertIn("timeout", call.call_args.kwargs)
            self.assertIn("timed out", self.failure(lambda: github.comments(5), secret))  # a listing too
        self.assertEqual([], requests)

    def test_a_json_nesting_failure_is_an_undecodable_response(self):
        """R2-F3: a later page (and a single comment) whose JSON exceeds the decoder's nesting limit raises CommandError; the pages
        already read are discarded, never returned as a partial listing."""
        deep = b"[" * 200000 + b"]" * 200000
        with self.assertRaises(RecursionError):  # the standard decoder's own failure for this body
            json.loads(deep.decode("utf-8"))
        listing = "/repos/owner/repo/issues/70/comments"
        port, requests = self.serve({
            listing + "?per_page=100": lambda p: (200, [("Link", f'<http://127.0.0.1:{p}{listing}?per_page=100&page=2>; rel="next"')],
                                                  [self.record(1, "one")]),
            listing + "?per_page=100&page=2": (200, [], deep),
            "/repos/owner/repo/issues/comments/71": (200, [], b'{"id": 71, "body": ' + deep + b'}'),
        })
        github = self.github(port)
        self.assertIn("undecodable response: RecursionError", self.failure(lambda: github.comments(70)))
        self.assertIn("undecodable response: RecursionError", self.failure(lambda: github.comment(71)))
        self.assertEqual(1, sum(1 for path, _ in requests if path == listing + "?per_page=100&page=2"))


class FirstReleaseTests(Base):
    """Material findings fixed under the first-release scope (owner addendum 3)."""

    def test_correctness_obligation_cannot_be_deferred(self):
        """R8-F3: neither the developer's deferral nor the reviewer's acceptance can close it."""
        env = self.env
        ctl = env.controller()
        ctl.state["findings"]["R2-F1"] = {"status": "open", "category": "optional_polish", "blocks_readiness": False,
                                          "correctness_obligation": True, "title": "restated defect",
                                          "dispositions": []}
        bad = report(env, "phase-1", [{"finding_id": "R2-F1", "disposition": "deferred_optional", "commits": [],
                                       "evidence": "defer"}])
        self.assertIn("cannot be deferred", ctl.accept_report(bad))

    def test_generic_plan_keeps_the_projects_required_gates(self):
        """R11-F1: a plan without required_gates (like `single`) cannot drop the project's required gate; a failed
        run of it blocks readiness, and the developer prompt names it."""
        gates = {"unit": {"argv": [sys.executable, "-c", "import sys; sys.exit(1)"]},
                 "extra": {"argv": [sys.executable, "-c", "print('supplemental')"]}}
        plan = {"schema_version": "agent-review.plan.v1", "mission_id": "single", "checkpoints": [
            {"id": "final", "type": "final", "scope": "s", "exit_conditions": ["e"]}]}
        env = Env("foreground", plan=plan, cfg_overrides={"gates": gates, "required_gates": ["unit"]})
        self.addCleanup(env.cleanup)
        ctl = env.controller()
        head = git(env.work, "rev-parse", "HEAD")
        self.assertEqual(["unit"], ctl.required_gates())
        ctl.run_gate("unit")  # fails
        self.assertEqual(["unit"], ctl.missing_gates(head))
        error = ctl.accept_report(report(env, "final"))  # report admission refuses the failed required gate
        self.assertIn("unit", error)
        del ctl.cfg["required_gates"]  # default: every declared gate is required
        self.assertEqual(["extra", "unit"], ctl.required_gates())

    def test_handoff_waits_for_a_lagging_pr_view(self):
        """Live task (PR #2): right after the archive push, GitHub's PR view still showed the previous head and
        finalize blocked on every attempt. When the branch itself is already at the archive head, readiness waits a
        bounded time for the PR view; a PR view that never catches up still blocks."""
        env = self.env
        ctl = env.controller()
        self.to_finalize(ctl)
        stale = git(env.work, "rev-parse", "HEAD")
        real_pr, calls = env.gh.pr, {"n": 0}

        def lagging_pr(number):
            data = real_pr(number)
            calls["n"] += 1
            if calls["n"] <= 3:
                data["headRefOid"] = stale  # the previous head, as GitHub reported it for a few seconds
            return data
        env.gh.pr = lagging_pr
        self.assertEqual("AWAITING_OWNER_REVIEW", ctl.finalize())
        self.assertGreater(calls["n"], 3)

    def test_preflight_uses_the_same_developer_model_check(self):
        """R11-F2."""
        cfg = {"developer": {"allowed_model_pattern": "^claude-opus-", "model": "opus"}}
        good = {"init_model": OPUS, "main_models": [OPUS], "transcript_models": [OPUS]}
        self.assertIsNone(ar.developer_model_problem(cfg, good))
        self.assertTrue(ar.developer_model_problem(cfg, dict(good, transcript_models=[OPUS, "claude-sonnet-x"])))
        self.assertTrue(ar.developer_model_problem(cfg, dict(good, init_model=None)))

    def test_conflicting_transcript_model_is_refused(self):
        """R10-F1."""
        env = Env("headless")
        self.addCleanup(env.cleanup)

        def work(e):
            e.commit("a.txt", "a\n", "work")
            e.push()
            return report(e, "phase-1")
        work.transcript_models = [OPUS, "claude-sonnet-other"]
        env.developer.script = [work]
        with self.assertRaises(ar.Stop) as stop:
            env.controller().develop_step()
        self.assertIn("not an allowed", stop.exception.reason)


def tree_snapshot(root):
    """Every file and directory under root with its size and modification time: any write shows up as a change."""
    return {str(p.relative_to(root)): (p.is_dir(), p.stat().st_size if p.is_file() else 0, p.stat().st_mtime_ns)
            for p in sorted(Path(root).rglob("*"))}


@contextlib.contextmanager
def forbid_processes_and_network(test, forbidden=()):
    """Tripwire, not a simulated response: fails the test if the code under test starts any process (git, gh),
    opens a network connection, or reads a JSON file on a UNC/device path or under any `forbidden` path (links the
    code must not follow). Nothing is answered on the code's behalf; every attempt is recorded and refused, and the
    record is checked after the block (so a catch-all in the code under test cannot hide a violation)."""
    from unittest import mock
    attempts = []
    real_read_json = ar.read_json
    blocked = [os.path.normcase(os.path.normpath(str(p))) for p in forbidden]

    def refuse(what):
        def _refuse(*args, **kwargs):
            attempts.append(what)
            raise AssertionError(f"read-only command attempted {what}")
        return _refuse

    def guarded_read_json(path):
        text = str(path).replace("/", "\\")
        if text.startswith("\\\\") and not re.match(r"\\\\[?.]\\[A-Za-z]:", text):  # \\?\C:\ is a local drive
            return refuse(f"to read network path {path}")()
        effective = os.path.normcase(os.path.normpath(str(path)))  # what the OS opens after collapsing '..'
        if any(effective.startswith(prefix) for prefix in blocked):
            return refuse(f"to read through a link: {path}")()
        return real_read_json(path)
    with mock.patch.object(subprocess, "Popen", side_effect=refuse("a process")), \
            mock.patch.object(socket.socket, "connect", refuse("a network connection")), \
            mock.patch.object(socket, "create_connection", side_effect=refuse("a network connection")), \
            mock.patch.object(ar, "read_json", guarded_read_json):
        yield
    test.assertEqual([], attempts)


def set_windows_privilege(name, enabled):
    """Enable or disable a privilege in this process's own token; returns whether it was enabled before, or None
    if the token does not hold it. Test setup only (real OS state, nothing simulated)."""
    import ctypes
    from ctypes import wintypes
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class LUID(ctypes.Structure):
        _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]

    class LUID_AND_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("Luid", LUID), ("Attributes", wintypes.DWORD)]

    class TOKEN_PRIVILEGES(ctypes.Structure):
        _fields_ = [("PrivilegeCount", wintypes.DWORD), ("Privileges", LUID_AND_ATTRIBUTES * 1)]
    enabled_flag = 0x2  # SE_PRIVILEGE_ENABLED
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi32.LookupPrivilegeValueW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.POINTER(LUID)]
    advapi32.AdjustTokenPrivileges.argtypes = [wintypes.HANDLE, wintypes.BOOL, ctypes.POINTER(TOKEN_PRIVILEGES),
                                               wintypes.DWORD, ctypes.POINTER(TOKEN_PRIVILEGES),
                                               ctypes.POINTER(wintypes.DWORD)]
    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), 0x20 | 0x8, ctypes.byref(token)):  # ADJUST|QUERY
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        luid = LUID()
        if not advapi32.LookupPrivilegeValueW(None, name, ctypes.byref(luid)):
            raise ctypes.WinError(ctypes.get_last_error())
        new = TOKEN_PRIVILEGES(1, (LUID_AND_ATTRIBUTES * 1)(LUID_AND_ATTRIBUTES(luid, enabled_flag if enabled else 0)))
        old, size = TOKEN_PRIVILEGES(), wintypes.DWORD(0)
        if not advapi32.AdjustTokenPrivileges(token, False, ctypes.byref(new), ctypes.sizeof(old), ctypes.byref(old),
                                              ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() == 1300:  # ERROR_NOT_ALL_ASSIGNED: the token does not hold this privilege
            return None
        if old.PrivilegeCount == 0:  # already in the requested state
            return enabled
        return bool(old.Privileges[0].Attributes & enabled_flag)
    finally:
        kernel32.CloseHandle(token)


class ListCommandTests(Base):
    """Mission: read-only `list` of every enrollment claim in the host registry."""

    def run_list(self, forbidden=()):
        with forbid_processes_and_network(self, forbidden), contextlib.redirect_stdout(io.StringIO()) as out:
            code = ar.main(["list"])
        self.assertEqual(ar.EXIT_OK, code)
        return out.getvalue()

    def test_lists_an_enrollment_with_its_fields_without_locks_or_writes(self):
        env = self.env
        ctl = env.controller()
        ctl.save()  # stamps updated_at, as every controller transition does
        self.assertTrue(ctl.state["updated_at"])
        claim = ar.registry_path("owner/repo", env.branch)
        self.assertTrue(claim.exists())
        with ctl.lock("run"):  # the owning controller holds its writer lock: list neither waits nor is refused
            before = tree_snapshot(env.root)
            rows = json.loads(self.run_list())
            self.assertEqual(before, tree_snapshot(env.root))  # nothing written, no lock or holder files
        self.assertEqual([{"enrollment": ctl.state["enrollment_id"], "repository": "owner/repo",
                           "branch": env.branch, "status": "ACTIVE", "phase": ctl.state["phase"], "pr": 7,
                           "updated_at": ctl.state["updated_at"]}], rows)
        self.assertEqual(ctl.state["status"], rows[0]["status"])

    def test_empty_registry_prints_an_empty_array(self):
        env = self.env
        ctl = env.controller()
        ctl.verify_inputs()
        self.assertEqual("CANCELLED", ctl.cancel("owner decision"))  # releases the only claim
        self.assertEqual([], list((ar.host_dir() / "registry").glob("*.json")))
        self.assertEqual("[]", self.run_list().strip())
        from unittest import mock
        absent = env.root / "fresh-host"  # a machine where nothing was ever enrolled
        with mock.patch.dict(os.environ, {"AGENT_REVIEW_HOST_DIR": str(absent)}):
            self.assertEqual("[]", self.run_list().strip())
        self.assertFalse(absent.exists())  # list does not even create the registry folder

    def test_damaged_enrollments_are_reported_unknown_without_failing(self):
        env = self.env
        ctl = env.controller()
        enrollment = ctl.state["enrollment_id"]
        (env.dir / "state.json").write_text("{ not json", encoding="utf-8")  # damaged state file
        registry = ar.host_dir() / "registry"
        ar.atomic_write_json(registry / "other.json", {"enrollment_id": "a-missing-state", "dir": str(env.root / "gone"),
                                                        "repository": "owner/other", "branch": "claude/x"})
        (registry / "zz-broken.json").write_text("garbage", encoding="utf-8")  # damaged claim itself
        rows = json.loads(self.run_list())
        self.assertEqual(["a-missing-state", enrollment, None], [r["enrollment"] for r in rows])  # sorted by ID
        missing, damaged, broken = rows
        self.assertEqual(("unknown", "owner/other", "claude/x", None, None),
                         (missing["status"], missing["repository"], missing["branch"], missing["pr"], missing["phase"]))
        self.assertIn("missing", missing["error"])
        self.assertIn(str(env.root / "gone"), missing["error"])
        self.assertEqual(("unknown", "owner/repo", env.branch), (damaged["status"], damaged["repository"], damaged["branch"]))
        self.assertIn("unreadable", damaged["error"])
        self.assertEqual("unknown", broken["status"])
        self.assertIn("zz-broken.json", broken["error"])

    # R1 regressions: each damaged entry is listed next to the real, healthy enrollment.

    def claim(self, enrollment, folder, **extra):
        ar.atomic_write_json(ar.host_dir() / "registry" / f"{enrollment}.json",
                             {"enrollment_id": enrollment, "dir": folder, "repository": "owner/other",
                              "branch": f"claude/{enrollment}", **extra})

    def state_dir(self, name, text):
        folder = self.env.root / "other-state" / name
        folder.mkdir(parents=True)
        (folder / "state.json").write_text(text, encoding="utf-8")
        return str(folder)

    def listed(self, forbidden=()):
        rows = {r["enrollment"]: r for r in json.loads(self.run_list(forbidden))}
        ctl = self.env.controller()
        healthy = rows.pop(ctl.state["enrollment_id"])
        self.assertEqual({"enrollment": ctl.state["enrollment_id"], "repository": "owner/repo",
                          "branch": self.env.branch, "status": "ACTIVE", "phase": ctl.state["phase"], "pr": 7,
                          "updated_at": ctl.state.get("updated_at")}, healthy)
        return rows

    def test_malformed_claims_never_hide_healthy_enrollments(self):
        """R1-F1: non-string dir values and pathologically nested JSON (RecursionError) stay per-entry."""
        deep = "[" * 200000
        self.claim("a-dir-number", 42)
        self.claim("b-dir-object", {"path": "x"})
        self.claim("c-dir-empty", "")
        self.claim("d-deep-state", self.state_dir("deep", deep))
        (ar.host_dir() / "registry" / "e-deep-claim.json").write_text(deep, encoding="utf-8")
        rows = self.listed()
        for enrollment, needle in (("a-dir-number", "dir is int"), ("b-dir-object", "dir is dict"),
                                   ("c-dir-empty", "dir is str"), ("d-deep-state", "RecursionError")):
            self.assertEqual("unknown", rows[enrollment]["status"], enrollment)
            self.assertEqual("owner/other", rows[enrollment]["repository"])
            self.assertIn(needle, rows[enrollment]["error"])
        self.assertIn("e-deep-claim.json", rows[None]["error"])
        self.assertIn("RecursionError", rows[None]["error"])

    def test_invalid_state_values_keep_the_output_types(self):
        """R1-F2: pr is a positive integer or null; status is a string (else unknown with an error)."""
        base = {"phase": "develop", "updated_at": "2026-11-21T00:00:00Z"}
        for name, pr in (("p-string", {"number": "7"}), ("p-bool", {"number": True}), ("p-object", {"number": {}}),
                         ("p-float", {"number": 7.5}), ("p-scalar", 7)):
            self.claim(name, self.state_dir(name, json.dumps({**base, "enrollment_id": name, "status": "ACTIVE",
                                                              "pr": pr})))
        self.claim("s-number", self.state_dir("s-number", json.dumps({**base, "enrollment_id": "s-number", "status": 5,
                                                                       "pr": {"number": 3}, "phase": ["x"]})))
        rows = self.listed()
        for name in ("p-string", "p-bool", "p-object", "p-float", "p-scalar"):
            self.assertEqual(("ACTIVE", None, "develop"), (rows[name]["status"], rows[name]["pr"], rows[name]["phase"]))
        bad = rows["s-number"]
        self.assertEqual(("unknown", 3, None), (bad["status"], bad["pr"], bad["phase"]))
        self.assertIn("no valid status", bad["error"])

    def test_enrollment_with_a_relative_state_root_is_listed_from_any_directory(self):
        """R1-F3 (round 2): a real enrollment made with a relative --state-root records an absolute state_dir in
        its claim (and, since R13-F1, an absolute dir as well), so list reads that enrollment's own state from any
        working directory, never a decoy that a relative path would resolve to there."""
        env = self.env
        ctl = env.controller()
        ctl.verify_inputs()
        self.assertEqual("CANCELLED", ctl.cancel("re-enroll with a relative state root"))
        saved = os.getcwd()
        self.addCleanup(os.chdir, saved)
        os.chdir(env.root)
        folder, state = ar.enroll(env.args(state_root="rel-root"), github=env.gh, root=env.wf, developer=env.developer)
        enrollment = state["enrollment_id"]
        claim = ar.read_json(ar.registry_path("owner/repo", env.branch))
        self.assertEqual(str(env.root / "rel-root" / enrollment), claim["dir"])  # resolved at enrollment (R13-F1)
        self.assertEqual(str(env.root / "rel-root" / enrollment), claim["state_dir"])
        on_disk = ar.read_json(env.root / "rel-root" / enrollment / "state.json")
        decoy = env.work / "rel-root" / enrollment  # what the relative dir would mean from the work tree
        decoy.mkdir(parents=True)
        (decoy / "state.json").write_text(json.dumps({"enrollment_id": enrollment, "status": "AWAITING_OWNER_REVIEW",
                                                      "phase": "done", "pr": {"number": 99}}), encoding="utf-8")
        expected = [{"enrollment": enrollment, "repository": "owner/repo", "branch": env.branch,
                     "status": on_disk["status"], "phase": on_disk["phase"], "pr": 7,
                     "updated_at": on_disk.get("updated_at")}]
        self.assertEqual("ACTIVE", on_disk["status"])
        for cwd in (env.work, env.root, env.origin):
            os.chdir(cwd)
            self.assertEqual(expected, json.loads(self.run_list()))

    def test_relative_state_directory_is_not_resolved_against_the_callers_directory(self):
        """R1-F3: an older claim (no state_dir) with a relative dir would read whatever state happens to sit under
        the current directory. It is reported (unknown, with the reason) and never read, from any directory."""
        decoy = self.env.root / "rel-state" / "x"
        decoy.mkdir(parents=True)
        (decoy / "state.json").write_text(json.dumps({"status": "AWAITING_OWNER_REVIEW", "pr": {"number": 99}}),
                                          encoding="utf-8")
        self.claim("relative", os.path.join("rel-state", "x"))
        saved = os.getcwd()
        self.addCleanup(os.chdir, saved)
        for cwd in (self.env.root, self.env.work):  # the decoy resolves from the first; nothing from the second
            os.chdir(cwd)
            row = self.listed()["relative"]
            self.assertEqual(("unknown", None), (row["status"], row["pr"]))
            self.assertIn("relative state directory", row["error"])

    @unittest.skipUnless(os.name == "nt", "UNC paths and mapped network drives are Windows path forms")
    def test_network_state_directories_are_reported_without_access(self):
        """R1-F4: UNC/device paths are refused from the string alone (the tripwire fails on any read of them);
        the healthy enrollment on a local drive is still read through the drive-type check."""
        paths = {"n-unc": r"\\agent-review-unreachable.invalid\share\state\x",
                 "n-forward": "//agent-review-unreachable.invalid/share/state/x",
                 "n-long-unc": r"\\?\UNC\agent-review-unreachable.invalid\share\x"}
        for name, folder in paths.items():
            self.claim(name, folder)
        own = self.state_dir("long", json.dumps({"enrollment_id": "n-local-long", "status": "PAUSED",
                                                 "pr": {"number": 11}}))
        self.claim("n-local-long", "\\\\?\\" + str(Path(own).resolve()))  # long-path form of a local drive
        rows = self.listed()
        for name, folder in paths.items():
            self.assertEqual("unknown", rows[name]["status"])
            self.assertIn("UNC or device path", rows[name]["error"])
            self.assertIn("did not access it", rows[name]["error"])
        self.assertEqual(("PAUSED", 11), (rows["n-local-long"]["status"], rows["n-local-long"]["pr"]))
        self.assertIsNone(ar.remote_path_reason(str(self.env.root)))  # local fixed drive: not network storage

    def test_claim_pointing_at_another_enrollments_state_shows_none_of_its_fields(self):
        """R2-F1: identity is checked before any summary field is copied."""
        env = self.env
        self.claim("m-mismatch", str(env.dir))  # the healthy enrollment's own state directory
        ar.atomic_write_json(ar.host_dir() / "registry" / "m-anonymous.json",
                             {"dir": str(env.dir), "repository": "owner/other", "branch": "claude/anon"})
        rows = self.listed()  # the healthy enrollment keeps its own values
        mismatch = rows["m-mismatch"]
        self.assertEqual(("unknown", None, None, None),
                         (mismatch["status"], mismatch["pr"], mismatch["phase"], mismatch["updated_at"]))
        self.assertIn("belongs to enrollment", mismatch["error"])
        anonymous = rows[None]
        self.assertEqual(("unknown", None, "claude/anon"), (anonymous["status"], anonymous["pr"], anonymous["branch"]))
        self.assertIn("not to this claim's None", anonymous["error"])

    @unittest.skipUnless(os.name == "nt", "junctions and reparse points are Windows filesystem links")
    def test_links_are_refused_before_they_are_followed(self):
        """R1-F4 (round 2): a junction as the state directory or as a parent component of it, and a junctioned
        registry, are refused from lstat alone; the tripwire fails on any read through them. Link targets are
        local, so conservative refusal is exercised without contacting a share."""
        import _winapi
        env = self.env
        target = Path(self.state_dir("target", json.dumps({"enrollment_id": "l-direct", "status": "ACTIVE",
                                                           "pr": {"number": 5}})))
        (target / "sub").mkdir()
        (target / "sub" / "state.json").write_text(json.dumps({"enrollment_id": "l-component", "status": "ACTIVE"}),
                                                   encoding="utf-8")
        junction = env.root / "junction"
        _winapi.CreateJunction(str(target), str(junction))
        self.addCleanup(os.rmdir, junction)  # removes the junction itself, never its target
        self.claim("l-direct", str(target))  # the same content, read directly, is fine
        self.claim("l-junction", str(junction))
        self.claim("l-component", str(junction / "sub"))
        rows = self.listed([junction])
        self.assertEqual(("ACTIVE", 5), (rows["l-direct"]["status"], rows["l-direct"]["pr"]))
        for name in ("l-junction", "l-component"):
            self.assertEqual(("unknown", None), (rows[name]["status"], rows[name]["pr"]), name)
            self.assertIn("reparse point", rows[name]["error"])
            self.assertIn("did not access it", rows[name]["error"])
        host_link = env.root / "host-link"
        _winapi.CreateJunction(str(ar.host_dir()), str(host_link))
        self.addCleanup(os.rmdir, host_link)
        from unittest import mock
        with mock.patch.dict(os.environ, {"AGENT_REVIEW_HOST_DIR": str(host_link)}), \
                forbid_processes_and_network(self, [host_link]), \
                contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(ar.EXIT_USAGE, ar.main(["list"]))
        self.assertEqual("", out.getvalue())
        self.assertIn("reparse point", err.getvalue())

    @unittest.skipUnless(os.name == "nt", "junctions are Windows filesystem links")
    def test_noncanonical_or_missing_paths_are_never_opened(self):
        """R1-F4 (round 3): Windows collapses `missing\\..` lexically, so `<root>\\missing\\..\\junction` would
        open through a junction the component walk never reached. '..' segments are refused, and a missing component
        stops the walk without opening the path (reported as missing). The tripwire compares normalized paths."""
        import _winapi
        env = self.env
        target = Path(self.state_dir("target", json.dumps({"enrollment_id": "c-dotdot", "status": "ACTIVE",
                                                           "pr": {"number": 5}})))
        junction = env.root / "junction"
        _winapi.CreateJunction(str(target), str(junction))
        self.addCleanup(os.rmdir, junction)
        self.claim("c-dotdot", str(env.root) + r"\missing\..\junction")
        self.claim("c-dotdot-local", str(env.root) + r"\missing\..\other-state\target")  # refused, though local
        self.claim("c-missing", str(env.root / "nope" / "x"))
        rows = self.listed([junction, env.root / "nope", env.root / "missing"])
        for name in ("c-dotdot", "c-dotdot-local"):
            self.assertEqual(("unknown", None), (rows[name]["status"], rows[name]["pr"]), name)
            self.assertIn("'..' segment", rows[name]["error"])
        self.assertEqual(("unknown", None), (rows["c-missing"]["status"], rows["c-missing"]["pr"]))
        self.assertIn("state file is missing", rows["c-missing"]["error"])

    def test_unreadable_registry_is_refused_not_reported_empty(self):
        """R3-F1: when the registry's attributes are readable but listing its contents is denied, list refuses
        with a registry diagnostic and a nonzero exit instead of printing []. Absent and readable-empty registries
        still print [] (test_empty_registry_prints_an_empty_array)."""
        registry = ar.host_dir() / "registry"
        self.assertTrue(list(registry.glob("*.json")))  # populated: the fixture's real enrollment claim
        if os.name == "nt":
            # An elevated token may hold SeBackupPrivilege enabled, which bypasses the DACL for directory opens;
            # disable it in this test process for the duration (restored in cleanup) so the deny ACE applies.
            previous = set_windows_privilege("SeBackupPrivilege", False)
            if previous:
                self.addCleanup(set_windows_privilege, "SeBackupPrivilege", True)
            user = subprocess.run(["whoami"], check=True, capture_output=True, text=True).stdout.strip()
            subprocess.run(["icacls", str(registry), "/deny", f"{user}:(RD)"], check=True, capture_output=True)
            self.addCleanup(subprocess.run, ["icacls", str(registry), "/remove:d", user], check=True,
                            capture_output=True)
        else:
            if os.geteuid() == 0:
                self.skipTest("root bypasses directory permissions")
            os.chmod(registry, 0o300)  # search and write, no read: entries cannot be listed
            self.addCleanup(os.chmod, registry, 0o755)
        with self.assertRaises(PermissionError):
            os.listdir(registry)  # the condition under test really holds
        self.assertTrue(registry.is_dir())  # while its metadata stays readable
        with forbid_processes_and_network(self), contextlib.redirect_stdout(io.StringIO()) as out, \
                contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(ar.EXIT_USAGE, ar.main(["list"]))
        self.assertEqual("", out.getvalue())
        self.assertIn("cannot be enumerated", err.getvalue())
        self.assertIn("registry", err.getvalue())

    def test_registry_that_is_not_a_directory_is_refused(self):
        """R3-F1: any scan error is a refusal, not an empty listing."""
        from unittest import mock
        host = self.env.root / "file-host"
        host.mkdir()
        (host / "registry").write_text("not a directory", encoding="utf-8")
        with mock.patch.dict(os.environ, {"AGENT_REVIEW_HOST_DIR": str(host)}), forbid_processes_and_network(self), \
                contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(ar.EXIT_USAGE, ar.main(["list"]))
        self.assertEqual("", out.getvalue())
        self.assertIn("cannot be enumerated", err.getvalue())

    def test_symbolic_links_to_state_or_claim_files_are_refused(self):
        """R1-F4 (round 2): a symbolic link as state.json or as a registry claim file is refused from lstat alone
        (also on POSIX); the tripwire fails on any read through either link."""
        env = self.env
        target = Path(self.state_dir("target", json.dumps({"enrollment_id": "l-file", "status": "ACTIVE",
                                                           "pr": {"number": 5}})))
        registry = ar.host_dir() / "registry"
        plain = env.root / "plain"
        plain.mkdir()
        self.claim("l-real", str(target))
        try:
            os.symlink(target / "state.json", plain / "state.json")
            os.symlink(registry / "l-real.json", registry / "l-claimlink.json")
        except OSError as exc:  # Windows needs Developer Mode or SeCreateSymbolicLinkPrivilege; junctions do not
            self.skipTest(f"symbolic links cannot be created here: {exc}")
        self.claim("l-file", str(plain))
        rows = self.listed([plain / "state.json", registry / "l-claimlink.json"])
        self.assertIn("belongs to enrollment", rows["l-real"]["error"])  # control: the target itself is readable
        self.assertEqual(("unknown", None), (rows["l-file"]["status"], rows["l-file"]["pr"]))
        self.assertIn("reparse point", rows["l-file"]["error"])
        self.assertIn("did not access it", rows["l-file"]["error"])
        self.assertIn("l-claimlink.json was not read", rows[None]["error"])
        self.assertIn("reparse point", rows[None]["error"])


class EnrollmentOwnershipTests(Base):
    """R13-F1: enrollment ownership must not depend on the caller's directory, and a claim whose prior state cannot
    be established is never replaced."""

    def claims(self):
        env = self.env
        reg = ar.registry_path("owner/repo", env.branch)
        marker = Path(git(env.work, "rev-parse", "--absolute-git-dir")) / "agent-review-enrollment.json"
        return {path: path.read_bytes() for path in (reg, marker)}

    def test_relative_state_root_is_resolved_and_a_second_enrollment_elsewhere_is_refused(self):
        env = self.env
        state = ar.read_json(env.dir / "state.json")
        state["status"] = "CANCELLED"  # release the fixture's own enrollment
        ar.atomic_write_json(env.dir / "state.json", state)
        first, second = env.root / "first-cwd", env.root / "second-cwd"
        first.mkdir()
        second.mkdir()
        saved = os.getcwd()
        self.addCleanup(os.chdir, saved)
        os.chdir(first)
        folder, state = ar.enroll(env.args(state_root="relative-state"), github=env.gh, root=env.wf, developer=env.developer)
        self.assertTrue(folder.is_absolute())
        self.assertEqual((first / "relative-state").resolve(), folder.parent)
        before = self.claims()
        for data in before.values():
            self.assertTrue(Path(json.loads(data)["dir"]).is_absolute())
        os.chdir(second)  # e.g. status run from the developer worktree
        self.assertEqual(folder, ar.find_enrollment(state["enrollment_id"]))
        self.assertTrue((ar.find_enrollment(state["enrollment_id"]) / "state.json").is_file())
        with self.assertRaises(ar.UsageError) as refused:
            ar.enroll(env.args(state_root="relative-state"), github=env.gh, root=env.wf, developer=env.developer)
        self.assertIn("active enrollment", str(refused.exception))
        self.assertEqual(before, self.claims())  # both original claims intact
        self.assertFalse((second / "relative-state").exists() and any((second / "relative-state").iterdir()))

    def test_claim_whose_prior_state_cannot_be_established_is_not_replaced(self):
        env = self.env
        before = self.claims()
        state_file = env.dir / "state.json"
        hidden = env.root / "hidden-state.json"
        state_file.rename(hidden)  # absolute claim, prior state unavailable (the developer may still be running)
        with self.assertRaises(ar.UsageError) as refused:
            ar.enroll(env.args(state_root=str(env.root / "elsewhere")), github=env.gh, root=env.wf, developer=env.developer)
        self.assertIn("cannot be verified", str(refused.exception))
        self.assertIn("missing", str(refused.exception))
        self.assertEqual(before, self.claims())
        self.assertFalse((env.root / "elsewhere").exists() and any((env.root / "elsewhere").iterdir()))
        reg = next(iter(before))
        for label, text in (("unreadable state", "{not json"), ("foreign state", '{"enrollment_id": "other"}')):
            with self.subTest(label):
                state_file.write_text(text, encoding="utf-8")
                with self.assertRaises(ar.UsageError) as refused:
                    ar.enroll(env.args(state_root=str(env.root / "elsewhere")), github=env.gh, root=env.wf, developer=env.developer)
                self.assertIn("cannot be verified", str(refused.exception))
                self.assertEqual(before, self.claims())
        hidden.replace(state_file)
        for label, claim in (("relative claim", dict(json.loads(before[reg]), dir="relative-state/x")),
                             ("malformed claim", ["not", "a", "claim"])):
            with self.subTest(label):
                ar.atomic_write_json(reg, claim)
                with self.assertRaises(ar.UsageError) as refused:
                    ar.enroll(env.args(state_root=str(env.root / "elsewhere")), github=env.gh, root=env.wf, developer=env.developer)
                self.assertIn("cannot be verified", str(refused.exception))
        reg.write_bytes(before[reg])
        self.assertEqual(before, self.claims())


def rebutted(fid):
    return {"finding_id": fid, "disposition": "rebutted", "commits": [], "evidence": "simulated rebuttal"}


class ResumeGuidanceTests(Base):
    """`resume --guidance` (headless only): one owner document captured in private state by digest, given inline to
    every later developer invocation, copied byte-exact to the reviewer and rendered (sanitized) in the review request.
    Real Git repositories, controller state, locks, transactions and archive; the Claude, Codex and GitHub boundaries
    are the labeled simulations above."""
    mode = "headless"
    GUIDANCE = "# Owner guidance (simulated)\n\nChange the repair approach for R1-F1: rewrite feature.txt from scratch.\n"
    NEW_NOTICE = "This revision is new"
    NO_PROGRESS = {"decision": "changes_required", "findings": [finding("R1-F1")],
                   "assessments": [("R1-F1", "rebuttal_rejected")]}

    def doc(self, env, name, data):
        path = env.root / name
        path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        return path

    @staticmethod
    def snapshot(env, text):
        return env.dir / "guidance" / f"{ar.sha256_bytes(text.encode('utf-8'))}.md"

    @staticmethod
    def paused(e):
        return report(e, "phase-1", status="paused")

    @staticmethod
    def fix(e):
        sha = e.commit("feature.txt", "rewritten\n", "rewrite feature.txt per owner guidance")
        e.push()
        return report(e, "phase-1", [fixed("R1-F1", sha)])

    def blocked(self, env):
        """Drive the real loop to a no-progress BLOCKED stop in the develop phase: a finding, a rejected rebuttal on
        the unchanged candidate. Returns a fresh controller (a new process sees only persisted state)."""
        env.reviewer.script += [{"decision": "changes_required", "findings": [finding("R1-F1")]}, self.NO_PROGRESS]

        def phase1(e):
            e.commit("phase1.txt", "p1\n", "phase 1")
            e.push()
            return report(e, "phase-1")
        env.developer.script += [phase1, lambda e: report(e, "phase-1", [rebutted("R1-F1")])]
        with self.assertRaises(ar.Stop) as stop:
            env.controller().run_loop()
        self.assertIn("no progress", stop.exception.reason)
        disk = ar.read_json(env.dir / "state.json")
        self.assertEqual(("BLOCKED", "develop"), (disk["status"], disk["phase"]))
        return env.controller()

    def resume(self, ctl, reason="owner decision", guidance=None, **kw):
        """The owner's `resume` command path (lock, claims, precheck, guard); returns (exit code, printed JSON)."""
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = ar.resume_command(ctl, reason, guidance_file=None if guidance is None else str(guidance), **kw)
        return code, json.loads(out.getvalue())

    def state_bytes(self, env):
        return (env.dir / "state.json").read_bytes()

    def test_blocked_enrollment_resumed_with_guidance_reaches_both_roles_the_pr_and_the_archive(self):
        env = self.env
        ctl = self.blocked(env)
        token = "ghp_" + "A" * 36  # simulated credential: the public rendering goes through the standard sanitizer
        text = self.GUIDANCE + f"Do not publish tokens such as {token}.\n"
        digest = ar.sha256_bytes(text.encode("utf-8"))
        path = self.doc(env, "guidance.md", text)
        devs, reviews = len(env.developer.calls), len(env.reviewer.calls)
        fix = {}

        def wrong_checkpoint(e):  # rejected by the controller: the correction is another continuation prompt
            return report(e, "final")

        def correct(e):
            fix["sha"] = e.commit("feature.txt", "rewritten\n", "rewrite feature.txt per owner guidance")
            e.push()
            return report(e, "phase-1", [fixed("R1-F1", fix["sha"])])

        def final_work(e):
            e.commit("final.txt", "f\n", "final")
            e.push()
            return report(e, "final")
        env.developer.script += [wrong_checkpoint, correct, final_work]
        env.reviewer.script += [{"decision": "checkpoint_passed", "assessments": [("R1-F1", "fix_verified")]},
                                {"decision": "ready_for_owner_review"}]
        code, out = self.resume(ctl, "owner changes the repair approach", guidance=path)
        self.assertEqual((ar.EXIT_OK, "AWAITING_OWNER_REVIEW"), (code, out["result"]))  # a matching result finishes
        g = out["guidance"]  # status: the selection, then what the latest invocation and round recorded
        self.assertEqual((1, digest, "intact"), tuple(g["selected"][k] for k in ("revision", "sha256", "integrity")))
        self.assertEqual((True, 1, True), tuple(g["latest_developer_invocation"][k]
                                                for k in ("returned", "guidance_revision", "matches_selected")))
        self.assertEqual(("accepted", digest, True), tuple(g["latest_review_round"][k]
                                                           for k in ("status", "guidance_sha256", "matches_selected")))

        after = env.developer.calls[devs:]
        self.assertEqual(3, len(after))  # the start, the report-correction continuation and the final checkpoint
        self.assertIn("rejected your last report", after[1]["prompt"])
        for call in after:  # every developer invocation after capture carries the text, its revision, digest, scope
            self.assertIn(f"## Owner guidance — revision 1 (sha256 `{digest}`)", call["prompt"])
            self.assertIn(f"----- BEGIN OWNER GUIDANCE (sha256 {digest}) -----", call["prompt"])
            self.assertIn(self.GUIDANCE.strip(), call["prompt"])
            self.assertIn(ar.GUIDANCE_SCOPE, call["prompt"])
        self.assertIn(self.NEW_NOTICE, after[0]["prompt"])
        self.assertNotIn(self.NEW_NOTICE, after[1]["prompt"])  # an invocation that included it has returned
        self.assertTrue(all("OWNER GUIDANCE" not in c["prompt"] for c in env.developer.calls[:devs]))

        for call in env.reviewer.calls[reviews:]:  # the reviewer's own snapshot holds the captured bytes
            self.assertEqual(text.encode("utf-8"), call["guidance"])
            self.assertIn("owner-guidance.md", call["inbox"])
            self.assertEqual((1, digest), (call["request"]["guidance_revision"], call["request"]["guidance_sha256"]))
            self.assertIn(digest, call["prompt"])
            self.assertIn(".agent-review-inputs/owner-guidance.md", call["prompt"])
            self.assertIn(ar.GUIDANCE_SCOPE, call["prompt"])
            self.assertNotIn(str(env.dir / "guidance"), call["prompt"])  # no path outside its workspace
        for call in env.reviewer.calls[:reviews]:
            self.assertIsNone(call["guidance"])
            self.assertEqual("none", call["request"]["guidance_sha256"])
            self.assertIn("Owner guidance: none", call["prompt"])
        self.assertEqual(2, len(env.reviewer.calls) - reviews)

        state = ar.read_json(env.dir / "state.json")
        for rnd in state["rounds"]:  # historical rounds keep their original binding
            want = digest if rnd["round"] > 2 else None
            self.assertEqual(want, rnd["guidance_sha256"])
            self.assertEqual(want or "none", ar.read_json(rnd["envelope_path"])["guidance_sha256"])
        self.assertEqual(text.encode("utf-8"), self.snapshot(env, text).read_bytes())

        rendering = f"**Owner guidance — revision 1, captured-source sha256 `{digest}`.**"
        for n in (3, 4):  # the published request carries the sanitized public rendering and its binding
            body = next(c["body"] for c in env.gh.comments_list if f"review request — round {n} —" in c["body"])
            self.assertIn(rendering, body)
            self.assertIn("rewrite feature.txt from scratch", body)
            self.assertIn("[REDACTED-CREDENTIAL]", body)
            self.assertNotIn(token, body)
            self.assertNotIn(str(path), body)  # no private input or state path is published
            self.assertNotIn(str(env.dir), body)
        early = next(c["body"] for c in env.gh.comments_list if "review request — round 1 —" in c["body"])
        self.assertIn("| Owner guidance | none |", early)
        self.assertNotIn("Owner guidance — revision", early)

        records = env.work / "docs" / "agent-reviews" / "pr-7"  # archived request, review and envelope records
        archived = next(records.glob("*-r03-request.md")).read_text(encoding="utf-8")
        self.assertIn(f"| Owner guidance | revision 1, sha256 `{digest}` |", archived)
        self.assertIn(rendering, archived)
        self.assertNotIn(token, archived)
        self.assertIn(f"Owner guidance bound to this review: revision 1, sha256 `{digest}`.",
                      next(records.glob("*-r04-review.md")).read_text(encoding="utf-8"))
        self.assertEqual(digest, json.loads(next(records.glob("*-r04-review-envelope.json")).read_text(
            encoding="utf-8"))["guidance_sha256"])
        self.assertIn("| Owner guidance | none |", next(records.glob("*-r01-request.md")).read_text(encoding="utf-8"))
        self.assertEqual("none", json.loads(next(records.glob("*-r01-review-envelope.json")).read_text(
            encoding="utf-8"))["guidance_sha256"])

    def test_captured_guidance_survives_restarts_and_changes_to_the_original(self):
        env = self.env
        ctl = self.blocked(env)
        digest = ar.sha256_bytes(self.GUIDANCE.encode("utf-8"))
        path = self.doc(env, "guidance.md", self.GUIDANCE)
        env.developer.script += [lambda e: report(e, "phase-1", status="paused")]
        env.developer.sessions.clear()  # no saved Claude session: the first invocation after capture is a start
        self.assertEqual(ar.EXIT_PAUSED, self.resume(ctl, guidance=path)[0])
        first = env.developer.calls[-1]
        self.assertFalse(first["resume"])
        self.assertIn("Agent-review mission start", first["prompt"])
        self.assertIn(self.GUIDANCE.strip(), first["prompt"])
        self.assertIn(self.NEW_NOTICE, first["prompt"])  # the fresh-report notice also reaches a start prompt
        path.write_text("# edited after capture\n", encoding="utf-8")
        restarted = env.controller()  # a new controller process
        self.assertEqual(digest, restarted.status()["guidance"]["selected"]["sha256"])
        path.unlink()
        env.developer.sessions.clear()  # the Claude session is gone as well: the next invocation is a start prompt
        env.developer.script += [self.fix]
        env.reviewer.script += [{"decision": "blocked", "assessments": [("R1-F1", "fix_verified")]}]
        code, out = self.resume(env.controller(), "ordinary resume after a restart")  # no --guidance
        self.assertEqual(ar.EXIT_BLOCKED, code)
        self.assertIn("reviewer blocked", out["reason"])
        start = env.developer.calls[-1]
        self.assertFalse(start["resume"])
        self.assertIn("Agent-review mission start", start["prompt"])
        for text in (start["prompt"], env.reviewer.calls[-1]["prompt"]):
            self.assertIn(digest, text)
            self.assertNotIn("edited after capture", text)
        self.assertIn(self.GUIDANCE.strip(), start["prompt"])
        self.assertNotIn(self.NEW_NOTICE, start["prompt"])  # an invocation that included it already returned
        self.assertEqual(self.GUIDANCE.encode("utf-8"), env.reviewer.calls[-1]["guidance"])
        self.assertEqual(digest, env.reviewer.calls[-1]["request"]["guidance_sha256"])
        self.assertEqual(1, len(ar.read_json(env.dir / "state.json")["guidance"]["revisions"]))

    def assert_needs_report(self, env):
        ctl = env.controller()
        reviews = len(env.reviewer.calls)
        ctl.transition("review", "simulated: review requested without a fresh report")
        self.assertEqual("needs_report", ctl.review_round())
        self.assertEqual((reviews, "develop"), (len(env.reviewer.calls), ctl.state["phase"]))

    def restore_report_binding(self, env, head):
        """Simulated (labeled): put back the commit binding that a new revision clears, so that the guidance binding
        is the only thing that can make the report stale."""
        state = ar.read_json(env.dir / "state.json")
        state["last_report_for"] = head
        ar.atomic_write_json(env.dir / "state.json", state)

    def test_new_revision_needs_a_fresh_report_and_stale_bindings_are_refused(self):
        env = self.env
        ctl = self.blocked(env)
        head = git(env.work, "rev-parse", "HEAD")
        a, b = "first approach\n", "second approach\n"
        da, db = ar.sha256_bytes(a.encode()), ar.sha256_bytes(b.encode())
        self.assertEqual(head, ar.read_json(env.dir / "state.json")["last_report_for"])  # reported for this commit

        def rebut_again(e):  # a fresh report on the unchanged commit
            return report(e, "phase-1", [rebutted("R1-F1")])
        # revision 1: the earlier report does not count; a fresh one on the same commit is reviewed under revision 1
        env.developer.script += [rebut_again]
        env.reviewer.script += [self.NO_PROGRESS]
        code, out = self.resume(ctl, guidance=self.doc(env, "a.md", a))
        self.assertEqual(ar.EXIT_BLOCKED, code)
        self.assertIn("no progress", out["reason"])
        self.assertEqual((1, da, head), tuple(env.reviewer.calls[-1]["request"][k]
                                              for k in ("guidance_revision", "guidance_sha256", "H")))

        # revision 2 on the same commit: the report and ready bindings are cleared; no review without a fresh report
        env.developer.script += [self.paused]
        self.assertEqual(ar.EXIT_PAUSED, self.resume(env.controller(), guidance=self.doc(env, "b.md", b))[0])
        state = ar.read_json(env.dir / "state.json")
        self.assertEqual((None, None, {"guidance_revision": 1, "guidance_sha256": da}),
                         (state["last_report_for"], state.get("ready_review"), state["last_report_guidance"]))
        self.assert_needs_report(env)
        self.restore_report_binding(env, head)
        self.assert_needs_report(env)  # a report for this very commit, bound to revision 1, is stale under 2

        # A again: revision 3 reuses A's immutable content file; revision 1's binding (same digest) is still stale
        env.developer.script += [self.paused]
        self.assertEqual(ar.EXIT_PAUSED, self.resume(env.controller(), guidance=self.doc(env, "a-again.md", a))[0])
        state = ar.read_json(env.dir / "state.json")
        revs = state["guidance"]["revisions"]
        self.assertEqual([(1, da, None), (2, db, 1), (3, da, 2)], [(r["revision"], r["sha256"], r["supersedes"])
                                                                    for r in revs])
        self.assertEqual(3, state["guidance"]["current"])
        self.assertEqual(sorted([f"{da}.md", f"{db}.md"]), sorted(p.name for p in (env.dir / "guidance").iterdir()))
        self.assertEqual((a.encode(), b.encode()), (self.snapshot(env, a).read_bytes(),
                                                    self.snapshot(env, b).read_bytes()))
        self.restore_report_binding(env, head)
        self.assertEqual({"guidance_revision": 1, "guidance_sha256": da},
                         ar.read_json(env.dir / "state.json")["last_report_guidance"])
        self.assert_needs_report(env)  # the revision number alone makes it stale

        env.developer.script += [rebut_again]  # a fresh revision-3 report on that same commit is reviewed
        env.reviewer.script += [self.NO_PROGRESS]
        code, out = self.resume(env.controller(), "continue under revision 3")
        self.assertEqual(ar.EXIT_BLOCKED, code)
        self.assertEqual((3, da, head), tuple(env.reviewer.calls[-1]["request"][k]
                                              for k in ("guidance_revision", "guidance_sha256", "H")))

        seen = {}

        def observe(e):  # what was persisted when this invocation launched
            seen.update(ar.read_json(e.dir / "state.json"))
            return self.paused(e)
        env.developer.script += [observe]
        self.assertEqual(ar.EXIT_PAUSED, self.resume(env.controller(), guidance=self.doc(env, "a-copy.md", a))[0])
        self.assertEqual((3, 3), (len(seen["guidance"]["revisions"]), seen["guidance"]["current"]))  # identical
        self.assertEqual((head, {"guidance_revision": 3, "guidance_sha256": da}),  # bindings kept: nothing changed
                         (seen["last_report_for"], seen["last_report_guidance"]))
        self.assertEqual((3, da), (seen["developer"]["launch"]["guidance_revision"],
                                   seen["developer"]["launch"]["guidance_sha256"]))
        rounds = ar.read_json(env.dir / "state.json")["rounds"]  # historical rounds keep their original binding
        self.assertEqual([(None, None), (None, None), (1, da), (3, da)],
                         [(r["guidance_revision"], r["guidance_sha256"]) for r in rounds])
        self.assertEqual([1, 3], [ar.read_json(r["envelope_path"])["guidance_revision"] for r in rounds[2:]])

    def test_invalid_guidance_input_is_refused_without_any_change(self):
        env = self.env
        self.blocked(env)
        (env.dir / "STOP").write_text("owner stop\n", encoding="utf-8")
        before = self.state_bytes(env)
        cases = {"missing": env.root / "absent.md", "directory": env.root,
                 "empty": self.doc(env, "empty.md", b""), "whitespace": self.doc(env, "blank.md", b" \r\n\t\n"),
                 "bom-only": self.doc(env, "bom.md", b"\xef\xbb\xbf\n"),
                 "non-utf8": self.doc(env, "latin1.md", "Änderung\n".encode("latin-1")),
                 "oversized": self.doc(env, "big.md", b"x" * (ar.GUIDANCE_MAX_BYTES + 1))}
        for label, path in cases.items():
            with self.subTest(label):
                with self.assertRaises(ar.UsageError):
                    self.resume(env.controller(), guidance=path)
                self.assertEqual(before, self.state_bytes(env))  # no status change, no counter reset
                self.assertTrue((env.dir / "STOP").exists())
                self.assertFalse((env.dir / "guidance").exists())
        with contextlib.redirect_stderr(io.StringIO()) as err:  # the CLI refuses with the refusal exit code
            code = ar.main(["resume", "--enrollment", ar.read_json(env.dir / "state.json")["enrollment_id"],
                            "--reason", "x", "--guidance", str(cases["empty"])])
        self.assertEqual(ar.EXIT_USAGE, code)
        self.assertIn("empty or whitespace only", err.getvalue())
        self.assertEqual(before, self.state_bytes(env))
        self.assertEqual(2, len(env.developer.calls))  # no agent was launched

    def test_damaged_or_invalid_selection_blocks_before_any_launch_and_refuses_guidance(self):
        env = self.env
        self.blocked(env)
        path = self.doc(env, "guidance.md", self.GUIDANCE)
        env.developer.script += [self.paused]
        self.assertEqual(ar.EXIT_PAUSED, self.resume(env.controller(), guidance=path)[0])
        state_path, snapshot = env.dir / "state.json", self.snapshot(env, self.GUIDANCE)
        original = ar.read_json(state_path)

        def edit(**guidance):  # simulated damage to the selection in state.json (labeled)
            ar.atomic_write_json(state_path, {**original, "guidance": guidance.get("value", {
                **original["guidance"], **{k: v for k, v in guidance.items() if k != "value"}})})
        damages = {"altered snapshot": lambda: snapshot.write_bytes(b"simulated tampering\n"),
                   "missing snapshot": lambda: snapshot.unlink(),
                   "null guidance member": lambda: edit(value=None),
                   "null selection": lambda: edit(current=None),
                   "dangling selection": lambda: edit(current=7),
                   "malformed revision": lambda: edit(revisions=[None]),
                   "boolean recorded revision": lambda: edit(revisions=[{**original["guidance"]["revisions"][0],
                                                                         "revision": True}]),
                   "float recorded revision": lambda: edit(revisions=[{**original["guidance"]["revisions"][0],
                                                                       "revision": 1.0}]),
                   "nonpositive revision": lambda: edit(current=0, revisions=[{**original["guidance"]["revisions"][0],
                                                                               "revision": 0}])}
        for label, damage in damages.items():
            with self.subTest(label):
                ar.atomic_write_json(state_path, original)
                snapshot.write_bytes(self.GUIDANCE.encode("utf-8"))
                damage()
                before, calls = self.state_bytes(env), len(env.developer.calls)
                for document in (self.doc(env, "other.md", "different\n"), path):  # no repair bypass, either document
                    with self.assertRaises(ar.UsageError) as refusal:
                        self.resume(env.controller(), guidance=document)
                    self.assertIn("owner guidance", str(refusal.exception))
                    self.assertEqual(before, self.state_bytes(env))
                selected = env.controller().status()["guidance"]["selected"]
                self.assertEqual("problem", selected["integrity"])  # shown as a problem, never as "none"
                self.assertTrue(selected["problem"])
                # integrity at use: an ordinary resume stops BLOCKED before any launch or invocation charge
                code, out = self.resume(env.controller(), "ordinary resume")
                self.assertEqual(ar.EXIT_BLOCKED, code)
                self.assertIn("owner guidance", out["reason"])
                state = ar.read_json(state_path)
                self.assertEqual((calls, original["developer"]["invocations"]),
                                 (len(env.developer.calls), state["developer"]["invocations"]))
                self.assertEqual(original["developer"]["launch"], state["developer"]["launch"])
                # the stop reason is published: it names the revision/digest, never private paths or state content
                for body in [out["reason"]] + [c["body"] for c in env.gh.comments_list]:
                    self.assertNotIn(env.root.name, body)
                    self.assertNotIn('"revisions"', body)
                self.assertTrue("snapshot" in selected or "recorded" in selected)  # local detail for recovery
        self.assertTrue(any("Workflow — blocked" in c["body"] and "owner guidance" in c["body"]
                            for c in env.gh.comments_list))  # a blocked notice was actually published
        ar.atomic_write_json(state_path, original)
        snapshot.write_bytes(self.GUIDANCE.encode("utf-8"))

        def fix_then_damage(e):  # the snapshot is altered between the developer's report and the reviewer launch
            report_ = self.fix(e)
            snapshot.write_bytes(b"simulated alteration before the review launch\n")
            return report_
        env.developer.script += [fix_then_damage]
        rounds_before, reviews = len(original["rounds"]), len(env.reviewer.calls)
        code, out = self.resume(env.controller(), "ordinary resume")
        self.assertEqual(ar.EXIT_BLOCKED, code)
        self.assertIn("missing or altered", out["reason"])
        self.assertEqual(reviews, len(env.reviewer.calls))  # the reviewer was never launched
        state = ar.read_json(state_path)
        self.assertEqual(("BLOCKED", "review"), (state["status"], state["phase"]))
        self.assertEqual(rounds_before, len(state["rounds"]))  # detected before any request was recorded
        self.assertFalse([k for k in state["publications"] if k.startswith(f"r{rounds_before + 1:02d}-")])
        before = self.state_bytes(env)
        with self.assertRaises(ar.UsageError) as refusal:  # guidance stays develop-only
            self.resume(env.controller(), guidance=path)
        self.assertIn("develop phase", str(refusal.exception))
        self.assertEqual(before, self.state_bytes(env))
        # supervised recovery: restore the identical captured bytes (never repaired automatically), then resume
        selected = env.controller().status()["guidance"]["selected"]
        Path(selected["snapshot"]).write_bytes(path.read_bytes())
        self.assertEqual("intact", env.controller().status()["guidance"]["selected"]["integrity"])
        env.reviewer.script += [{"decision": "blocked", "assessments": [("R1-F1", "fix_verified")]}]
        code, out = self.resume(env.controller(), "guidance snapshot restored")
        self.assertEqual(ar.EXIT_BLOCKED, code)
        self.assertIn("reviewer blocked", out["reason"])
        state = ar.read_json(state_path)
        self.assertEqual((1, rounds_before + 1), (len(state["guidance"]["revisions"]), len(state["rounds"])))
        digest = ar.sha256_bytes(self.GUIDANCE.encode("utf-8"))
        self.assertEqual(self.GUIDANCE.encode("utf-8"), env.reviewer.calls[-1]["guidance"])
        self.assertEqual((1, digest), (state["rounds"][-1]["guidance_revision"], state["rounds"][-1]["guidance_sha256"]))

    def test_null_guidance_member_never_launches_unguided_while_a_missing_key_is_legacy(self):
        """Direct regression: an explicit `guidance: null` used to launch an unguided developer."""
        env = self.env
        self.blocked(env)
        state = ar.read_json(env.dir / "state.json")
        ar.atomic_write_json(env.dir / "state.json", {**state, "guidance": None})  # simulated damage (labeled)
        calls = len(env.developer.calls)
        env.developer.script += [self.paused]
        code, out = self.resume(env.controller(), "ordinary resume")
        self.assertEqual(ar.EXIT_BLOCKED, code)
        self.assertIn("owner guidance selection in the enrollment state is invalid", out["reason"])
        self.assertEqual(calls, len(env.developer.calls))
        state.pop("guidance", None)
        ar.atomic_write_json(env.dir / "state.json", state)  # no key at all: an unguided enrollment, as before
        code, out = self.resume(env.controller(), "ordinary resume")
        self.assertEqual(ar.EXIT_PAUSED, code)
        self.assertEqual(calls + 1, len(env.developer.calls))
        self.assertNotIn("OWNER GUIDANCE", env.developer.calls[-1]["prompt"])
        self.assertIsNone(out["guidance"]["selected"])

    def test_guidance_reads_are_bounded_and_a_document_at_the_limit_is_accepted(self):
        env = self.env
        self.blocked(env)
        huge = env.root / "huge.md"
        with open(huge, "wb") as handle:  # a large regular file: refused after reading at most limit + 1 bytes
            handle.truncate(64 * 1024 * 1024)
        before = self.state_bytes(env)
        with self.assertRaises(ar.UsageError) as refusal:
            self.resume(env.controller(), guidance=huge)
        self.assertIn("larger than", str(refusal.exception))
        self.assertEqual(before, self.state_bytes(env))
        at_limit = b"#" * ar.GUIDANCE_MAX_BYTES
        env.developer.script += [self.paused]
        self.assertEqual(ar.EXIT_PAUSED, self.resume(env.controller(), guidance=self.doc(env, "limit.md", at_limit))[0])
        rec = ar.read_json(env.dir / "state.json")["guidance"]["revisions"][0]
        self.assertEqual((ar.GUIDANCE_MAX_BYTES, ar.sha256_bytes(at_limit)), (rec["bytes"], rec["sha256"]))
        snapshot = env.dir / "guidance" / f"{rec['sha256']}.md"
        with open(snapshot, "r+b") as handle:  # a snapshot grown past the bound is damaged, never read whole
            handle.truncate(32 * 1024 * 1024)
        with self.assertRaises(ar.Stop) as stop:
            env.controller().develop_step()
        self.assertIn("missing or altered", stop.exception.reason)

    def test_ordinary_resume_is_unchanged_for_state_written_before_guidance(self):
        env = self.env
        self.blocked(env)
        state = ar.read_json(env.dir / "state.json")  # simulate a state file written before this change
        state.pop("last_report_guidance")
        state.pop("last_report_instructions", None)  # report-history bindings did not exist either
        state.pop("last_report_amendments", None)
        for entry in state.get("reports", []):
            for key in ("guidance_revision", "guidance_sha256", "amendment_revision", "amendment_sha256"):
                entry.pop(key, None)
        for rnd in state["rounds"]:
            for key in ("guidance_revision", "guidance_sha256"):
                rnd.pop(key)
            envelope = ar.read_json(rnd["envelope_path"])
            for key in ("guidance_revision", "guidance_sha256"):
                envelope.pop(key)
            ar.atomic_write_json(rnd["envelope_path"], envelope)
            rnd["envelope_sha256"] = ar.sha256_file(rnd["envelope_path"])
        self.assertFalse([k for k in json.dumps(state).split('"') if k.startswith("guidance")])
        ar.atomic_write_json(env.dir / "state.json", state)

        def fix(e):
            sha = e.commit("feature.txt", "rewritten\n", "rewrite")
            e.push()
            return report(e, "phase-1", [fixed("R1-F1", sha)])

        def final_work(e):
            e.commit("final.txt", "f\n", "final")
            e.push()
            return report(e, "final")
        env.developer.script += [fix, final_work]
        env.reviewer.script += [{"decision": "checkpoint_passed", "assessments": [("R1-F1", "fix_verified")]},
                                {"decision": "ready_for_owner_review"}]
        code, out = self.resume(env.controller(), "owner reviewed the disagreement")
        self.assertEqual((ar.EXIT_OK, "AWAITING_OWNER_REVIEW"), (code, out["result"]))
        self.assertEqual(None, out["guidance"]["selected"])  # an unguided enrollment, not a problem
        self.assertEqual("none", out["guidance"]["latest_review_round"]["guidance_sha256"])
        self.assertTrue(all("OWNER GUIDANCE" not in c["prompt"] for c in env.developer.calls))
        self.assertTrue(all(c["guidance"] is None and "owner-guidance.md" not in c["inbox"] for c in env.reviewer.calls))
        final = ar.read_json(env.dir / "state.json")
        self.assertNotIn("guidance", final)
        self.assertFalse((env.dir / "guidance").exists())
        records = env.work / "docs" / "agent-reviews" / "pr-7"
        self.assertNotIn("guidance_sha256", json.loads(next(records.glob("*-r01-review-envelope.json")).read_text(
            encoding="utf-8")))  # legacy envelopes archive unchanged
        self.assertEqual("none", json.loads(next(records.glob("*-r04-review-envelope.json")).read_text(
            encoding="utf-8"))["guidance_sha256"])

    def test_guidance_is_refused_unless_idle_headless_blocked_or_paused_in_develop_with_budget(self):
        env = self.env
        self.blocked(env)
        path = self.doc(env, "guidance.md", self.GUIDANCE)
        state_path = env.dir / "state.json"
        original = ar.read_json(state_path)
        (env.dir / "STOP").write_text("owner stop\n", encoding="utf-8")

        def refused(changes=None, expect=None, **kw):
            ar.atomic_write_json(state_path, {**original, **(changes or {})})
            before, posted = self.state_bytes(env), len(env.gh.comments_list)
            with self.assertRaises(ar.UsageError) as refusal:
                self.resume(env.controller(), guidance=path, **kw)
            self.assertEqual(before, self.state_bytes(env))  # not even a refusal note
            self.assertEqual(posted, len(env.gh.comments_list))
            self.assertTrue((env.dir / "STOP").exists())
            self.assertFalse((env.dir / "guidance").exists())
            if expect:
                self.assertIn(expect, str(refusal.exception))
            ar.atomic_write_json(state_path, original)

        copy = lambda value: json.loads(json.dumps(value))  # noqa: E731
        live_round, requested_round = copy(original["rounds"]), copy(original["rounds"])
        live_round[-1].update(status="reviewing", attempts=[{"n": 1, "started": ar.now_iso()}])  # simulated attempt
        requested_round[-1].update(status="requested", attempts=[])  # simulated: a round opened, no attempt yet
        unreturned = copy(original["developer"])
        unreturned["launch"]["returned"] = False  # simulated: launch intent recorded, no recorded return
        pending, uncertain = copy(original["publications"]), copy(original["publications"])
        key = sorted(pending)[-1]
        pending[key]["state"] = "pending"
        uncertain[key]["parts"][0].update(comment_id=None, posting_since=ar.now_iso())
        for label, changes, expect in (  # every simulated state below is labeled; the command path is real
                ("ACTIVE", {"status": "ACTIVE"}, "develop phase"),
                ("review phase", {"status": "PAUSED", "phase": "review"}, "develop phase"),
                ("finalize phase", {"status": "BLOCKED", "phase": "finalize"}, "develop phase"),
                ("awaiting owner review", {"status": "AWAITING_OWNER_REVIEW", "phase": "done"}, "develop phase"),
                ("cancelled", {"status": "CANCELLED", "phase": "cancelled"}, "not permitted"),
                ("foreground mode", {"mode": "foreground", "foreground_session": FOREGROUND_SESSION}, "headless"),
                ("active developer", {"developer": {**original["developer"], "active_pid": os.getpid()}}, "still running"),
                ("unreturned developer launch", {"developer": unreturned}, "no recorded return"),
                ("reviewer attempt", {"rounds": live_round, "active_round": len(live_round)}, "still active"),
                ("open review round", {"rounds": requested_round, "active_round": len(requested_round)}, "still active"),
                ("pending publication", {"publications": pending}, key),
                ("uncertain publication", {"publications": uncertain}, "uncertain delivery"),
                ("queued public operation", {"public_ops": [{"op": "pr_body", "at": ar.now_iso(), "text": "x"}]},
                 "pr_body"),
                ("archive commit in progress", {"archive_pending": {"parent": "x", "reason": "simulated",
                                                                    "commit": None, "files": []}}, "archive commit"),
                ("invalid selection", {"guidance": None}, "owner guidance selection in the enrollment state is invalid"),
                ("round budget", {"limits": {**original["limits"], "max_review_rounds_per_checkpoint": 2}}, "budget"),
                ("developer budget", {"limits": {**original["limits"], "max_developer_invocations": 0}}, "budget")):
            with self.subTest(label):
                refused(changes, expect)
        with self.subTest("malformed worktree claim JSON (CLI)"):
            claim = Path(git(env.work, "rev-parse", "--absolute-git-dir")) / "agent-review-enrollment.json"
            saved = claim.read_bytes()
            claim.write_text("{simulated damage", encoding="utf-8")
            before = self.state_bytes(env)
            with contextlib.redirect_stderr(io.StringIO()) as err:
                code = ar.main(["resume", "--enrollment", original["enrollment_id"], "--reason", "x",
                                "--guidance", str(path)], root=env.wf)
            self.assertEqual((ar.EXIT_USAGE, before), (code, self.state_bytes(env)))
            self.assertIn("--guidance refused", err.getvalue())
            self.assertTrue((env.dir / "STOP").exists())
            claim.write_bytes(saved)
        with self.subTest("budget extension in the same call"):  # 2 of 2 completed: --max-rounds cannot lift it
            refused({"limits": {**original["limits"], "max_review_rounds_per_checkpoint": 2}}, "budget", max_rounds=6)
        for proposed in (6, 3):  # 2 of 5 completed: neither a higher nor a lower limit accompanies guidance
            with self.subTest("budget change below the cap", proposed=proposed):
                refused(expect="budget change", max_rounds=proposed)
        with self.subTest("installed workflow fails its manifest (CLI)"):
            manifest = env.wf / "MANIFEST.json"
            ar.atomic_write_json(manifest, {"files": {}, "fingerprint": "simulated damaged installation"})
            before = self.state_bytes(env)
            with contextlib.redirect_stderr(io.StringIO()) as err:
                code = ar.main(["resume", "--enrollment", original["enrollment_id"], "--reason", "x",
                                "--guidance", str(path)], root=env.wf)
            self.assertEqual((ar.EXIT_USAGE, before), (code, self.state_bytes(env)))
            self.assertIn("differs from its MANIFEST", err.getvalue())
            self.assertTrue((env.dir / "STOP").exists())
            manifest.unlink()
        with self.subTest("resend combined"):
            refused(expect="--resend-undelivered", resend_undelivered=True)
        with self.subTest("misdirected enrollment ID"):
            refused(expect="not the requested", enrollment_id="t-misdirected-0001")
            entry = ar.host_dir() / "registry" / "misdirected.json"  # a registry entry naming another state dir
            ar.atomic_write_json(entry, {"enrollment_id": "t-misdirected-0001", "dir": str(env.dir)})
            before = self.state_bytes(env)
            with contextlib.redirect_stderr(io.StringIO()) as err:
                code = ar.main(["resume", "--enrollment", "t-misdirected-0001", "--reason", "x", "--guidance", str(path)])
            self.assertEqual((ar.EXIT_USAGE, before), (code, self.state_bytes(env)))
            self.assertIn("not the requested t-misdirected-0001", err.getvalue())
            entry.unlink()
        with self.subTest("wrong GitHub actor"):
            env.gh.pr_overrides = {"viewer": "someone-else"}
            refused(expect="refused before any change")
            env.gh.pr_overrides = {}
        for label, target, text in (("changed workflow", env.wf / "prompts" / "reviewer.md", "changed rules\n"),
                                    ("changed mission", env.mission, "# a different mission\n")):
            with self.subTest(label):
                saved = target.read_bytes()
                target.write_text(text, encoding="utf-8")
                refused(expect="refused before any change")
                target.write_bytes(saved)
        with self.subTest("runtime lock"):
            (env.root / "runtime.lock").write_text("simulated runtime transaction\n", encoding="utf-8")
            refused(expect="runtime transaction")
            (env.root / "runtime.lock").unlink()
        with self.subTest("runtime transaction starts during the remote admission checks"):
            calls = len(env.developer.calls)

            def viewer():  # simulated: another project's enrollment takes the shared runtime lock meanwhile
                (env.root / "runtime.lock").write_text("simulated shared runtime transaction\n", encoding="utf-8")
                return "owner"
            env.gh.viewer = viewer
            try:
                refused(expect="runtime transaction")
            finally:
                del env.gh.viewer
                (env.root / "runtime.lock").unlink(missing_ok=True)
            self.assertEqual(calls, len(env.developer.calls))
        with self.subTest("a regular file occupies the guidance folder"):
            occupant = env.dir / "guidance"
            occupant.write_text("simulated stray file\n", encoding="utf-8")
            before, posted = self.state_bytes(env), len(env.gh.comments_list)
            with self.assertRaises(ar.UsageError) as refusal:
                self.resume(env.controller(), guidance=path)
            self.assertIn("not a folder", str(refusal.exception))
            self.assertEqual((before, posted), (self.state_bytes(env), len(env.gh.comments_list)))
            self.assertTrue((env.dir / "STOP").exists())
            occupant.unlink()

        def cli(argv, **kw):
            before = self.state_bytes(env)
            with contextlib.redirect_stderr(io.StringIO()) as err:
                code = ar.main(argv, **kw)
            self.assertEqual((ar.EXIT_USAGE, before), (code, self.state_bytes(env)))
            self.assertTrue((env.dir / "STOP").exists())
            return err.getvalue()
        guided = ["--reason", "x", "--guidance", str(path)]
        with self.subTest("non-object manifest (CLI)"):
            manifest = env.wf / "MANIFEST.json"
            manifest.write_text("[]\n", encoding="utf-8")
            try:
                self.assertIn("differs from its MANIFEST",
                              cli(["resume", "--enrollment", original["enrollment_id"], *guided], root=env.wf))
            finally:
                manifest.unlink()
        with self.subTest("malformed registry claims (CLI)"):
            registry = ar.host_dir() / "registry"
            (registry / "zz-not-an-object.json").write_text("[1, 2]\n", encoding="utf-8")
            ar.atomic_write_json(registry / "zz-no-dir.json", {"enrollment_id": "t-claim-without-dir-0002"})
            try:
                self.assertIn("records no state folder",
                              cli(["resume", "--enrollment", "t-claim-without-dir-0002", *guided]))
                self.assertIn("zz-not-an-object.json", cli(["resume", "--enrollment", "t-absent-0003", *guided]))
            finally:
                (registry / "zz-not-an-object.json").unlink()
                (registry / "zz-no-dir.json").unlink()
        with self.subTest("unavailable worktree (CLI)"):
            away = env.work.with_name("work-unavailable")
            env.work.rename(away)
            try:
                self.assertIn("cannot be used", cli(["resume", "--enrollment", original["enrollment_id"], *guided],
                                                    root=env.wf))
            finally:
                away.rename(env.work)
        with self.subTest("writer lock held"):
            with env.controller().lock("run"):
                refused(expect="locked by")
        with self.subTest("helper lock held"):
            with env.controller().helper_lock("verify"):
                refused(expect="helper")
        with self.subTest("another enrollment's state"):
            ctl = env.controller()
            ctl.verify_inputs()
            ctl.cancel("owner re-enrolls the branch")
            ar.enroll(env.args(), github=env.gh, root=env.wf, developer=env.developer)  # a new enrollment now owns the branch
            original = {**ar.read_json(state_path), "status": "BLOCKED", "phase": "develop"}  # simulated stale state
            refused(expect="does not name enrollment")

    def test_owner_resume_restarts_the_streak_and_keeps_counters_and_budgets(self):
        for with_guidance in (False, True):
            with self.subTest(guidance=with_guidance):
                env = self.env if not with_guidance else Env("headless")
                if with_guidance:
                    self.addCleanup(env.cleanup)
                ctl = self.blocked(env)
                before = ar.read_json(env.dir / "state.json")
                self.assertEqual(2, before["findings"]["R1-F1"]["rounds_open"])
                seen = {}

                def observe(e):
                    seen.update(ar.read_json(e.dir / "state.json"))  # persisted at the moment of this launch
                    return report(e, "phase-1", status="paused")
                env.developer.script += [observe]
                kw = {"guidance": self.doc(env, "guidance.md", self.GUIDANCE)} if with_guidance else {}
                self.assertEqual(ar.EXIT_PAUSED, self.resume(ctl, "owner reviewed the disagreement", **kw)[0])
                self.assertEqual(0, seen["findings"]["R1-F1"]["rounds_open"])  # the streak restarts
                self.assertEqual(before["rounds_completed"], seen["rounds_completed"])
                self.assertEqual(before["developer"]["invocations"] + 1, seen["developer"]["invocations"])
                self.assertEqual((before["pending_findings"], "open"),
                                 (seen["pending_findings"], seen["findings"]["R1-F1"]["status"]))
                self.assertEqual((before["limits"], len(before["rounds"])), (seen["limits"], len(seen["rounds"])))
                self.assertEqual(with_guidance, "guidance" in seen)

    def test_admission_holds_the_helper_lock_until_capture(self):
        env = self.env
        self.blocked(env)
        path = self.doc(env, "guidance.md", self.GUIDANCE)
        ctl = env.controller()
        ctl.admit_guidance(ar.read_guidance(path))
        with self.assertRaises(ar.UsageError):  # a push/verify helper cannot start between admission and capture
            with env.controller().helper_lock("verify"):
                pass
        ctl.release_guidance_admission()
        with env.controller().helper_lock("verify"):
            pass

    def test_failed_state_save_keeps_the_committed_selection(self):
        env = self.env
        self.blocked(env)
        a, b = "approach A\n", "approach B\n"
        env.developer.script += [self.paused]
        self.assertEqual(ar.EXIT_PAUSED, self.resume(env.controller(), guidance=self.doc(env, "a.md", a))[0])
        committed = ar.read_json(env.dir / "state.json")
        calls, posted = len(env.developer.calls), len(env.gh.comments_list)
        # a real filesystem fault at the state save: the writer's temporary file name is occupied by a directory
        obstruction = env.dir / f"state.json.{os.getpid()}.tmp"
        obstruction.mkdir()
        try:
            with self.assertRaises(OSError):  # the save and the guard's own attempt to record the failure both fail
                self.resume(env.controller(), guidance=self.doc(env, "b.md", b))
        finally:
            obstruction.rmdir()
        state = ar.read_json(env.dir / "state.json")  # after releasing it: the last committed state is authoritative
        self.assertEqual((1, [1]), (state["guidance"]["current"], [r["revision"] for r in state["guidance"]["revisions"]]))
        self.assertEqual((committed["status"], committed["developer"]), (state["status"], state["developer"]))
        self.assertEqual(a.encode(), self.snapshot(env, a).read_bytes())  # the selected bytes are intact
        self.assertEqual(b.encode(), self.snapshot(env, b).read_bytes())  # B's file exists but is unreferenced
        self.assertEqual((calls, posted), (len(env.developer.calls), len(env.gh.comments_list)))
        env.developer.script += [self.paused]  # a later guided resume verifies B's existing file before reusing it
        self.assertEqual(ar.EXIT_PAUSED, self.resume(env.controller(), guidance=self.doc(env, "b2.md", b))[0])
        state = ar.read_json(env.dir / "state.json")
        self.assertEqual((2, ar.sha256_bytes(b.encode())), (state["guidance"]["current"],
                                                            state["guidance"]["revisions"][-1]["sha256"]))
        self.assertIn("approach B", env.developer.calls[-1]["prompt"])
        snapshot = self.snapshot(env, self.GUIDANCE)
        path = self.doc(env, "guidance.md", self.GUIDANCE)
        snapshot.write_bytes(b"simulated damage to an existing, unreferenced content file\n")
        state = ar.read_json(env.dir / "state.json")
        ar.atomic_write_json(env.dir / "state.json", {k: v for k, v in state.items() if k != "guidance"})  # labeled
        before = self.state_bytes(env)
        with self.assertRaises(ar.UsageError) as refusal:  # an existing file that does not match is never adopted
            self.resume(env.controller(), guidance=path)
        self.assertIn("never overwritten", str(refusal.exception))
        self.assertEqual(before, self.state_bytes(env))

    def test_reviewer_input_write_failure_leaves_no_unfinished_attempt(self):
        env = self.env
        self.blocked(env)
        path = self.doc(env, "guidance.md", self.GUIDANCE)
        digest = ar.sha256_bytes(self.GUIDANCE.encode("utf-8"))
        n = len(ar.read_json(env.dir / "state.json")["rounds"]) + 1
        rnd_dir = env.dir / "rounds" / f"r{n:02d}"
        obstacle = rnd_dir / "owner-guidance.md"
        obstacle.mkdir(parents=True)  # simulated environment fault: the reviewer copy's destination is a directory
        env.developer.script += [self.fix]
        reviews = len(env.reviewer.calls)
        code, out = self.resume(env.controller(), guidance=path)  # the real copy/write raises an OSError
        self.assertEqual(ar.EXIT_BLOCKED, code)
        self.assertIn(f"reviewer input preparation for round {n} failed", out["reason"])
        self.assertEqual(False, out["guidance"]["latest_review_round"]["latest_attempt"]["process_start_recorded"])
        state = ar.read_json(env.dir / "state.json")  # restart: no reviewer ran and the attempt says so
        attempt = state["rounds"][-1]["attempts"][-1]
        self.assertEqual((False, False, False), (attempt["ok"], attempt["fatal"], attempt["launched"]))
        self.assertIn("ended", attempt)
        self.assertIn("owner-guidance.md", attempt["reasons"][0])  # the full diagnostic stays in private state ...
        for body in [out["reason"]] + [c["body"] for c in env.gh.comments_list]:  # ... never in public notices
            self.assertNotIn(env.root.name, body)
            self.assertNotIn("owner-guidance.md", body)
        self.assertEqual(reviews, len(env.reviewer.calls))
        self.assertFalse(list(rnd_dir.glob("snapshot-*")))  # the reviewer snapshot was removed
        obstacle.rmdir()  # the owner clears the fault; an ordinary resume reviews exactly once
        env.reviewer.script += [{"decision": "blocked", "assessments": [("R1-F1", "fix_verified")]}]
        code, out = self.resume(env.controller(), "reviewer input fault cleared")
        self.assertIn("reviewer blocked", out["reason"])
        self.assertEqual(reviews + 1, len(env.reviewer.calls))
        self.assertEqual((1, digest), (env.reviewer.calls[-1]["request"]["guidance_revision"],
                                       env.reviewer.calls[-1]["request"]["guidance_sha256"]))
        self.assertEqual(self.GUIDANCE.encode("utf-8"), env.reviewer.calls[-1]["guidance"])

    def test_crlf_guidance_publishes_retries_archives_and_reaches_the_reviewer_byte_exact(self):
        env = self.env
        self.blocked(env)
        data = b"# Owner guidance (simulated, Windows line endings)\r\n\r\nRewrite feature.txt from scratch.\r\nKeep tests.\r\n"
        digest = ar.sha256_bytes(data)
        path = self.doc(env, "crlf.md", data)
        env.developer.script += [self.fix]
        # simulated outage after the dispositions comment: the request is queued, then retried on resume
        env.gh.on_post = lambda rec: setattr(env.gh, "fail_next", 99) if "finding dispositions" in rec["body"] else None
        self.assertEqual(ar.EXIT_PAUSED, self.resume(env.controller(), guidance=path)[0])
        env.gh.on_post, env.gh.fail_next = None, 0
        n = ar.read_json(env.dir / "state.json")["rounds"][-1]["round"]

        def final_work(e):
            e.commit("final.txt", "f\n", "final")
            e.push()
            return report(e, "final")
        env.developer.script += [final_work]
        env.reviewer.script += [{"decision": "checkpoint_passed", "assessments": [("R1-F1", "fix_verified")]},
                                {"decision": "ready_for_owner_review"}]
        code, out = self.resume(env.controller(), "publication outage over")
        self.assertEqual((ar.EXIT_OK, "AWAITING_OWNER_REVIEW"), (code, out["result"]))
        self.assertEqual(digest, ar.read_json(env.dir / "state.json")["guidance"]["revisions"][0]["sha256"])
        self.assertEqual(data, (env.dir / "guidance" / f"{digest}.md").read_bytes())  # captured bytes unchanged
        for call in env.reviewer.calls[-2:]:  # byte-exact, CRLF included
            self.assertEqual(data, call["guidance"])
            self.assertEqual(digest, call["request"]["guidance_sha256"])
        posted = [c["body"] for c in env.gh.comments_list if f"review request — round {n} —" in c["body"]]
        self.assertEqual(1, len(posted))
        self.assertIn("Rewrite feature.txt from scratch.\nKeep tests.", posted[0])  # LF public rendering
        self.assertNotIn("\r", posted[0])
        records = env.work / "docs" / "agent-reviews" / "pr-7"
        archived = next(records.glob(f"*-r{n:02d}-request.md")).read_text(encoding="utf-8")
        self.assertIn(f"captured-source sha256 `{digest}`", archived)
        self.assertIn("Rewrite feature.txt from scratch.", archived)

    def test_reselecting_earlier_guidance_never_recreates_its_missing_file(self):
        env = self.env
        self.blocked(env)
        a, b = "approach A\n", "approach B\n"
        for name, text in (("a.md", a), ("b.md", b)):
            env.developer.script += [self.paused]
            self.assertEqual(ar.EXIT_PAUSED, self.resume(env.controller(), guidance=self.doc(env, name, text))[0])
        self.snapshot(env, a).unlink()  # simulated loss of revision 1's private content file
        before, calls = self.state_bytes(env), len(env.developer.calls)
        with self.assertRaises(ar.UsageError) as refusal:
            self.resume(env.controller(), guidance=self.doc(env, "a-again.md", a))
        self.assertIn("never recreated", str(refusal.exception))
        self.assertEqual((before, calls), (self.state_bytes(env), len(env.developer.calls)))
        self.assertFalse(self.snapshot(env, a).exists())
        self.snapshot(env, a).write_bytes(a.encode())  # supervised restoration of the identical captured bytes
        env.developer.script += [self.paused]
        self.assertEqual(ar.EXIT_PAUSED, self.resume(env.controller(), guidance=self.doc(env, "a-again.md", a))[0])
        g = ar.read_json(env.dir / "state.json")["guidance"]
        self.assertEqual((3, [1, 2, 3]), (g["current"], [r["revision"] for r in g["revisions"]]))

    def test_reviewer_stream_setup_failure_closes_the_attempt_as_unlaunched(self):
        env = self.env
        self.blocked(env)
        path = self.doc(env, "guidance.md", self.GUIDANCE)
        n = len(ar.read_json(env.dir / "state.json")["rounds"]) + 1
        rnd_dir = env.dir / "rounds" / f"r{n:02d}"
        (rnd_dir / "events-1.jsonl").mkdir(parents=True)  # simulated fault: the events stream cannot be opened
        ctl = env.controller()
        # the real Codex boundary: it opens its streams before process creation, so no executable is ever started
        ctl._reviewer = ar.CodexReviewer({**ctl.cfg["reviewer"], "executable": str(env.root / "never-started.exe")})
        env.developer.script += [self.fix]
        code, out = self.resume(ctl, guidance=path)
        self.assertEqual(ar.EXIT_BLOCKED, code)
        self.assertIn(f"reviewer launch setup for round {n} failed", out["reason"])
        self.assertNotIn(env.root.name, out["reason"])
        state = ar.read_json(env.dir / "state.json")  # restart: the attempt is closed as never launched
        attempt = state["rounds"][-1]["attempts"][-1]
        self.assertEqual((1, False, False), (attempt["n"], attempt["ok"], attempt["launched"]))
        self.assertIn("ended", attempt)
        self.assertNotIn("pid", attempt)
        self.assertEqual(False, env.controller().status()["guidance"]["latest_review_round"]["latest_attempt"]
                         ["process_start_recorded"])
        (rnd_dir / "events-1.jsonl").rmdir()
        reviews = len(env.reviewer.calls)
        env.reviewer.script += [{"decision": "blocked", "assessments": [("R1-F1", "fix_verified")]}]
        code, out = self.resume(env.controller(), "stream fault cleared")  # nothing to reconcile; one dispatch
        self.assertIn("reviewer blocked", out["reason"])
        self.assertEqual(reviews + 1, len(env.reviewer.calls))

    def test_status_distinguishes_intent_process_start_and_return(self):
        env = self.env
        self.blocked(env)
        path = self.doc(env, "guidance.md", self.GUIDANCE)
        seen = {}

        def first(e):  # runs inside the simulated developer, before any start record
            seen["developer_before_start"] = env.controller().status()["guidance"]["latest_developer_invocation"]
            return self.paused(e)

        def started(e):  # this simulated invocation reports a process start through the controller's callback
            seen["developer_after_start"] = env.controller().status()["guidance"]["latest_developer_invocation"]
            return self.fix(e)
        started.start_pid = os.getpid()
        env.developer.script += [first]
        self.assertEqual(ar.EXIT_PAUSED, self.resume(env.controller(), guidance=path)[0])
        self.assertEqual((None, False, 1, True), tuple(seen["developer_before_start"][k] for k in (
            "process_start_recorded", "returned", "guidance_revision", "matches_selected")))
        self.assertTrue(seen["developer_before_start"]["intent_recorded_at"])
        returned = env.controller().status()["guidance"]["latest_developer_invocation"]
        self.assertEqual((seen["developer_before_start"]["invocation"], True, True),
                         (returned["invocation"], returned["process_start_recorded"], returned["returned"]))

        class Observed(ar.Controller):  # in-process observation of the real attempt, before its start callback
            def write_review_inputs(self, rnd, rnd_dir, snapshot, guidance_rec=None):
                seen["attempt_preparing"] = self.guidance_status()["latest_review_round"]
                return super().write_review_inputs(rnd, rnd_dir, snapshot, guidance_rec)
        env.reviewer.during_run = lambda: seen.update(
            attempt_running=env.controller().status()["guidance"]["latest_review_round"])
        env.developer.script += [started]
        env.reviewer.script += [{"decision": "blocked", "assessments": [("R1-F1", "fix_verified")]}]
        self.resume(env.controller(Observed), "continue")
        env.reviewer.during_run = None
        self.assertEqual((True, False, 1), tuple(seen["developer_after_start"][k] for k in (
            "process_start_recorded", "returned", "guidance_revision")))
        ended = env.controller().status()["guidance"]["latest_review_round"]
        for key, (start, done) in (("attempt_preparing", (None, None)), ("attempt_running", (True, None))):
            attempt = seen[key]["latest_attempt"]
            self.assertEqual((ended["round"], ended["latest_attempt"]["n"], start, done),
                             (seen[key]["round"], attempt["n"], attempt["process_start_recorded"], attempt["ended_at"]))
            self.assertEqual((1, True), (seen[key]["guidance_revision"], seen[key]["matches_selected"]))
        self.assertEqual(True, ended["latest_attempt"]["process_start_recorded"])
        self.assertTrue(ended["latest_attempt"]["ended_at"])

    def test_queued_request_is_retried_with_its_frozen_rendering_and_review_waits_for_intact_guidance(self):
        env = self.env
        self.blocked(env)
        path = self.doc(env, "guidance.md", self.GUIDANCE)
        digest = ar.sha256_bytes(self.GUIDANCE.encode("utf-8"))
        env.developer.script += [self.fix]
        # simulated outage: GitHub rejects every post after the dispositions comment, so the request stays queued
        env.gh.on_post = lambda rec: setattr(env.gh, "fail_next", 99) if "finding dispositions" in rec["body"] else None
        code, out = self.resume(env.controller(), guidance=path)
        self.assertEqual(ar.EXIT_PAUSED, code)
        env.gh.on_post, env.gh.fail_next = None, 0
        state = ar.read_json(env.dir / "state.json")
        n = state["rounds"][-1]["round"]
        pub = state["publications"][f"r{n:02d}-request"]
        self.assertEqual("pending", pub["state"])
        frozen = Path(pub["parts"][0]["body_file"]).read_text(encoding="utf-8")
        self.assertIn(f"captured-source sha256 `{digest}`", frozen)
        self.assertIn("rewrite feature.txt from scratch", frozen)
        before = self.state_bytes(env)
        with self.assertRaises(ar.UsageError) as refusal:  # stopped in review with a request queued: refused
            self.resume(env.controller(), guidance=self.doc(env, "other.md", "different\n"))
        self.assertIn("develop phase", str(refusal.exception))
        self.assertEqual(before, self.state_bytes(env))
        # the private snapshot is damaged after the body was frozen: the retry sends the frozen body unchanged (no
        # guidance check inside publication), and integrity-at-use stops the reviewer launch
        self.snapshot(env, self.GUIDANCE).write_bytes(b"simulated damage\n")
        reviews = len(env.reviewer.calls)
        code, out = self.resume(env.controller(), "publication outage over")
        self.assertEqual(ar.EXIT_BLOCKED, code)
        self.assertIn("missing or altered", out["reason"])
        posted = [c["body"] for c in env.gh.comments_list if f"review request — round {n} —" in c["body"]]
        self.assertEqual(1, len(posted))
        self.assertEqual(ar.normalize_body(frozen), ar.normalize_body(posted[0]))
        self.assertEqual(reviews, len(env.reviewer.calls))
        self.snapshot(env, self.GUIDANCE).write_bytes(path.read_bytes())  # supervised restore of the same bytes
        env.reviewer.script += [{"decision": "blocked", "assessments": [("R1-F1", "fix_verified")]}]
        code, out = self.resume(env.controller(), "guidance snapshot restored")
        self.assertIn("reviewer blocked", out["reason"])
        self.assertEqual(reviews + 1, len(env.reviewer.calls))
        self.assertEqual(1, sum(f"review request — round {n} —" in c["body"] for c in env.gh.comments_list))


    # -- round-2 corrections of enrollment 57a2 (R1-F2, R1-F4, R1-F6, R1-F7, R1-F8, R2-F1) -------------------------
    def outward(self, env):
        """Everything published or committed for the PR: simulated comments and archived records."""
        records = env.work / "docs" / "agent-reviews"
        files = [p.read_text(encoding="utf-8") for p in records.rglob("*") if p.is_file()] if records.exists() else []
        return [c["body"] for c in env.gh.comments_list] + files

    def test_guided_setup_failures_on_the_real_command_path_refuse_with_exit_4(self):
        env = self.env
        self.blocked(env)
        ar.write_text(env.dir / "STOP", "owner stop (simulated)\n")
        path = self.doc(env, "guidance.md", self.GUIDANCE)
        enrollment = ar.read_json(env.dir / "state.json")["enrollment_id"]
        calls, posted = len(env.developer.calls), len(env.gh.comments_list)

        def cli():
            before = self.state_bytes(env)
            with contextlib.redirect_stderr(io.StringIO()) as err:
                code = ar.main(["resume", "--enrollment", enrollment, "--reason", "x", "--guidance", str(path)],
                               root=env.wf)
            self.assertEqual((ar.EXIT_USAGE, before), (code, self.state_bytes(env)))
            self.assertTrue((env.dir / "STOP").exists())
            self.assertEqual((calls, posted), (len(env.developer.calls), len(env.gh.comments_list)))
            return err.getvalue()
        with self.subTest("a directory occupies the helper lock file"):
            lock = env.dir / "helper.lock"
            lock.unlink(missing_ok=True)
            lock.mkdir()  # simulated environment fault: the lock file cannot be opened at all
            try:
                self.assertIn("cannot be opened", cli())
            finally:
                lock.rmdir()
        with self.subTest("the enrollment state decodes to a non-object"):
            saved = self.state_bytes(env)
            (env.dir / "state.json").write_bytes(b"[]\n")  # simulated damage to the private state file
            try:
                self.assertIn("not a JSON object", cli())
            finally:
                (env.dir / "state.json").write_bytes(saved)
        env.developer.script += [self.paused]  # once the faults are cleared the same command is admitted
        self.assertEqual(ar.EXIT_PAUSED, self.resume(env.controller(), guidance=path)[0])

    def test_reselecting_a_digest_with_damaged_history_is_refused_unchanged(self):
        env = self.env
        self.blocked(env)
        a, b = "approach A\n", "approach B\n"
        for name, text in (("a.md", a), ("b.md", b)):
            env.developer.script += [self.paused]
            self.assertEqual(ar.EXIT_PAUSED, self.resume(env.controller(), guidance=self.doc(env, name, text))[0])
        state = ar.read_json(env.dir / "state.json")
        del state["guidance"]["revisions"][0]["revision"]  # labeled: damage only A's historical record
        ar.atomic_write_json(env.dir / "state.json", state)
        before, stop = self.state_bytes(env), (env.dir / "STOP").exists()
        calls, posted = len(env.developer.calls), len(env.gh.comments_list)
        with self.assertRaises(ar.UsageError) as refusal:
            self.resume(env.controller(), guidance=self.doc(env, "a-again.md", a))
        self.assertIn("malformed", str(refusal.exception))
        self.assertEqual((before, stop, calls, posted), (self.state_bytes(env), (env.dir / "STOP").exists(),
                                                         len(env.developer.calls), len(env.gh.comments_list)))
        self.assertEqual(2, ar.read_json(env.dir / "state.json")["guidance"]["current"])

    def test_a_recorded_snapshot_lost_during_admission_is_not_recreated(self):
        env = self.env
        self.blocked(env)
        a, b = "approach A\n", "approach B\n"
        for name, text in (("a.md", a), ("b.md", b)):
            env.developer.script += [self.paused]
            self.assertEqual(ar.EXIT_PAUSED, self.resume(env.controller(), guidance=self.doc(env, name, text))[0])
        snapshot = self.snapshot(env, a)
        self.assertTrue(snapshot.is_file())  # intact when the reselection starts

        def viewer():  # simulated: A's content file disappears while admission waits for the remote identity reads
            snapshot.unlink(missing_ok=True)
            return "owner"
        env.gh.viewer = viewer
        before, stop = self.state_bytes(env), (env.dir / "STOP").exists()
        calls, posted = len(env.developer.calls), len(env.gh.comments_list)
        try:
            with self.assertRaises(ar.UsageError) as refusal:
                self.resume(env.controller(), guidance=self.doc(env, "a-again.md", a))
        finally:
            del env.gh.viewer
        self.assertIn("never recreated", str(refusal.exception))
        self.assertFalse(snapshot.exists())
        self.assertEqual((before, stop, calls, posted), (self.state_bytes(env), (env.dir / "STOP").exists(),
                                                         len(env.developer.calls), len(env.gh.comments_list)))
        self.assertEqual(2, ar.read_json(env.dir / "state.json")["guidance"]["current"])  # B is still selected
        snapshot.write_bytes(a.encode())  # supervised restoration of the identical captured bytes
        env.developer.script += [self.paused]
        self.assertEqual(ar.EXIT_PAUSED, self.resume(env.controller(), guidance=self.doc(env, "a-again.md", a))[0])
        self.assertEqual(3, ar.read_json(env.dir / "state.json")["guidance"]["current"])

    def test_capture_write_failure_is_a_local_refusal(self):
        env = self.env
        self.blocked(env)
        path = self.doc(env, "guidance.md", self.GUIDANCE)
        target = self.snapshot(env, self.GUIDANCE)
        obstacle = target.with_name(target.name + f".{os.getpid()}.tmp")
        obstacle.mkdir(parents=True)  # simulated fault: the capture's temporary file cannot be created
        before, stop = self.state_bytes(env), (env.dir / "STOP").exists()
        calls, posted = len(env.developer.calls), len(env.gh.comments_list)
        with self.assertRaises(ar.UsageError) as refusal:
            self.resume(env.controller(), guidance=path)
        self.assertIn("could not be captured", str(refusal.exception))
        self.assertIn(str(target.parent), str(refusal.exception))  # the local diagnostic names the path
        self.assertEqual((before, stop, calls, posted), (self.state_bytes(env), (env.dir / "STOP").exists(),
                                                         len(env.developer.calls), len(env.gh.comments_list)))
        self.assertFalse(target.exists())
        obstacle.rmdir()
        env.developer.script += [self.paused]
        self.assertEqual(ar.EXIT_PAUSED, self.resume(env.controller(), guidance=path)[0])

    def test_round_directory_failure_publishes_no_private_path(self):
        env = self.env
        self.blocked(env)
        path = self.doc(env, "guidance.md", self.GUIDANCE)
        n = len(ar.read_json(env.dir / "state.json")["rounds"]) + 1
        obstacle = env.dir / "rounds" / f"r{n:02d}"
        obstacle.write_text("simulated fault: a file where the round directory belongs\n", encoding="utf-8")
        env.developer.script += [self.fix]
        code, out = self.resume(env.controller(), guidance=path)
        self.assertEqual(ar.EXIT_PAUSED, code)
        state = ar.read_json(env.dir / "state.json")
        self.assertIn(env.dir.name, state["status_reason"])  # the local diagnostic keeps the path ...
        public = [c["body"] for c in env.gh.comments_list if "operational failure during resume" in c["body"]]
        self.assertEqual(1, len(public))
        self.assertIn("FileExistsError", public[0])
        obstacle.unlink()  # the owner clears the fault; the run continues to the owner handoff

        def final_work(e):
            e.commit("final.txt", "f\n", "final")
            e.push()
            return report(e, "final")
        env.developer.script += [final_work]
        env.reviewer.script += [{"decision": "checkpoint_passed", "assessments": [("R1-F1", "fix_verified")]},
                                {"decision": "ready_for_owner_review"}]
        code, out = self.resume(env.controller(), "round directory fault cleared")
        self.assertEqual((ar.EXIT_OK, "AWAITING_OWNER_REVIEW"), (code, out["result"]))
        notices = [t for t in self.outward(env) if "operational failure during resume" in t]
        self.assertGreaterEqual(len(notices), 2)  # the PR comment and its archived record
        for text in notices:  # ... never in the published notice or its archived record
            self.assertNotIn(env.root.name, text)

    def test_missing_reviewer_executable_opens_no_attempt(self):
        env = self.env
        self.blocked(env)
        path = self.doc(env, "guidance.md", self.GUIDANCE)
        ctl = env.controller()
        ctl._reviewer = None  # normal lazy construction of the real Codex boundary
        name = ar.expand(ctl.cfg["reviewer"].get("executable", "codex"))
        self.assertFalse(os.path.isabs(name))  # the shipped configuration needs a PATH lookup
        which = shutil.which
        env.developer.script += [self.fix]
        reviews = len(env.reviewer.calls)
        with mock.patch.object(ar.shutil, "which", lambda cmd, *a, **k: None if cmd == name else which(cmd, *a, **k)):
            code, out = self.resume(ctl, guidance=path)  # simulated: the reviewer executable is absent from PATH
        self.assertEqual(ar.EXIT_BLOCKED, code)
        self.assertIn("could not be prepared", out["reason"])
        state = ar.read_json(env.dir / "state.json")  # restart: nothing to reconcile
        self.assertEqual([], state["rounds"][-1]["attempts"])
        self.assertIsNone(env.controller().status()["guidance"]["latest_review_round"]["latest_attempt"])
        env.reviewer.script += [{"decision": "blocked", "assessments": [("R1-F1", "fix_verified")]}]
        code, out = self.resume(env.controller(), "reviewer executable restored")
        self.assertIn("reviewer blocked", out["reason"])
        self.assertEqual(reviews + 1, len(env.reviewer.calls))

    def test_a_dead_developers_pid_is_not_the_next_invocations_start(self):
        env = self.env
        self.blocked(env)
        env.developer.script += [self.paused]
        self.assertEqual(ar.EXIT_PAUSED, self.resume(env.controller(), guidance=self.doc(env, "g.md", self.GUIDANCE))[0])
        dead = subprocess.Popen([sys.executable, "-c", "pass"])
        dead.wait()
        state = ar.read_json(env.dir / "state.json")  # labeled: invocation n started, then died before returning
        n = state["developer"]["invocations"]
        state["developer"]["launch"].update(returned=False, pid=dead.pid)
        state["developer"]["active_pid"] = dead.pid
        ar.atomic_write_json(env.dir / "state.json", state)
        seen = {}

        def fails_before_start(e):  # simulated launch failure before the process-start callback
            seen["before_start"] = env.controller().status()["guidance"]["latest_developer_invocation"]
            raise OSError("simulated launch failure before process creation")
        env.developer.script += [fails_before_start]
        code, _ = self.resume(env.controller(), "retry after the interrupted invocation")
        self.assertEqual(ar.EXIT_PAUSED, code)
        self.assertEqual((n + 1, None, False), tuple(seen["before_start"][k] for k in (
            "invocation", "process_start_recorded", "returned")))
        after = env.controller().status()["guidance"]["latest_developer_invocation"]  # restart
        self.assertEqual((n + 1, None, False), (after["invocation"], after["process_start_recorded"], after["returned"]))
        self.assertIsNone(ar.read_json(env.dir / "state.json")["developer"]["active_pid"])

        def started(e):
            return self.paused(e)
        started.start_pid = os.getpid()
        env.developer.script += [started]
        self.resume(env.controller(), "retry")
        after = env.controller().status()["guidance"]["latest_developer_invocation"]
        self.assertEqual((n + 2, True, True), (after["invocation"], after["process_start_recorded"], after["returned"]))


class StaleGuidanceResultTests(Base):
    """A genuine validated or ready review bound to other owner guidance (or to none) is never accepted, while the
    same review flow under matching guidance reaches the owner handoff. Headless; simulated models and GitHub. The
    change of selection between review and acceptance is applied directly to controller state (labeled), because no
    owner command can change guidance while a validated or ready result exists."""
    mode = "headless"

    def guided(self, env, text):
        """Capture and select guidance as the owner's resume would (simulated: directly, outside a stop)."""
        ctl = env.controller()
        document = {"source": "simulated", "data": text.encode(), "text": text, "sha256": ar.sha256_bytes(text.encode())}
        ctl.stage_guidance(document)
        with ctl.txn():
            rec, _ = ctl.select_guidance(document, "simulated selection change")
        return rec["revision"], rec["sha256"]

    def develop_and_review(self, ctl, checkpoint, note):
        """One developer invocation, launched under the current selection, then the review of its report."""
        def act(e):
            r = report(e, checkpoint)
            r["summary"] = f"simulated developer report {note}"
            return r
        self.env.developer.script.append(act)
        self.assertIsNone(ctl.develop_step())
        return ctl.review_round()

    def test_preserved_and_ready_results_bound_to_other_guidance_are_not_accepted(self):
        env = self.env
        self.guided(env, "approach A\n")
        ctl = env.controller()
        env.reviewer.script += [{"decision": "checkpoint_passed"}, {"decision": "ready_for_owner_review"}]
        self.assertEqual("checkpoint_passed", self.develop_and_review(ctl, "phase-1", "p1"))
        # the final review validates, then its publication fails (GitHub rejects posts from the reviewer run on):
        # a preserved, validated result
        env.reviewer.during_run = lambda: setattr(env.gh, "fail_next", 99)
        with self.assertRaises(ar.Stop):
            self.develop_and_review(ctl, "final", "final-a")
        env.reviewer.during_run = None
        rnd = ar.read_json(env.dir / "state.json")["rounds"][-1]
        self.assertEqual(("validated", 1), (rnd["status"], rnd["guidance_revision"]))
        env.gh.fail_next = 0
        self.guided(env, "approach B\n")  # simulated: the selection changes before acceptance
        ctl = env.controller()
        self.assertEqual("needs_report", ctl.review_round())  # retired, not accepted; a fresh report is required
        state = ar.read_json(env.dir / "state.json")
        self.assertEqual(("invalidated", None, {"phase-1": 1}),
                         (state["rounds"][-1]["status"], state.get("ready_review"), state["rounds_completed"]))
        self.assertFalse(any("Codex GPT-6.2 Astra — review — round 2" in h for h in env.gh.headings()))

        env.reviewer.script += [{"decision": "ready_for_owner_review"}]  # a genuine ready result under B
        self.assertEqual("ready_for_owner_review", self.develop_and_review(ctl, "final", "final-b"))
        self.assertEqual(2, ar.read_json(env.dir / "state.json")["ready_review"]["guidance_revision"])
        self.guided(env, "approach C\n")  # simulated: the selection changes before the handoff
        with self.assertRaises(ar.Stop) as stop:
            env.controller().finalize()
        self.assertIn("owner guidance changed", stop.exception.reason)
        state = ar.read_json(env.dir / "state.json")
        self.assertEqual((None, "develop"), (state["ready_review"], state["phase"]))
        self.assertFalse(any("awaiting owner review" in h for h in env.gh.headings()))

        env.reviewer.script += [{"decision": "ready_for_owner_review"}]  # the matching control reaches the handoff
        ctl = env.controller()
        self.assertEqual("ready_for_owner_review", self.develop_and_review(ctl, "final", "final-c"))
        self.assertEqual(3, ar.read_json(env.dir / "state.json")["ready_review"]["guidance_revision"])
        self.assertEqual("AWAITING_OWNER_REVIEW", ctl.finalize())
        self.assertTrue(env.controller().status(remote=True)["handoff_current"])

    def test_an_unguided_ready_result_does_not_satisfy_readiness_under_guidance(self):
        env = self.env
        ctl = env.controller()
        env.reviewer.script += [{"decision": "checkpoint_passed"}, {"decision": "ready_for_owner_review"}]
        self.assertEqual("checkpoint_passed", self.develop_and_review(ctl, "phase-1", "p1"))
        self.assertEqual("ready_for_owner_review", self.develop_and_review(ctl, "final", "final"))
        self.assertIsNone(ar.read_json(env.dir / "state.json")["ready_review"]["guidance_sha256"])
        self.guided(env, "approach A\n")  # simulated: guidance selected after the unguided ready review
        with self.assertRaises(ar.Stop) as stop:
            env.controller().finalize()
        self.assertIn("owner guidance changed", stop.exception.reason)
        self.assertIn("none", stop.exception.reason)
        self.assertFalse(any("awaiting owner review" in h for h in env.gh.headings()))
        self.assertIsNone(ar.read_json(env.dir / "state.json")["ready_review"])


class OwnerFlowFixture:
    """Shared helpers for the continuation and owner-amendment behavior tests: the owner's real `run`/`resume`
    command paths (writer lock, claims, admission, guard, transactions) over the real Git fixtures. The Claude, Codex
    and GitHub boundaries are the labeled simulations at the top of this file."""
    mode = "headless"
    CONTINUATION = ("Verdict: changes required; R1-F1 is still present at this candidate.\n\n"
                    "Continuation for Claude\n\n"
                    "1. What remains wrong: feature.txt still holds v1 (DISTINCTIVE-CONTINUATION-5c1e).\n"
                    "2. Correction approach: rewrite feature.txt in one commit; leave phase1.txt unchanged.\n"
                    "3. Scope boundaries: do not touch README.md or expand into other files.\n"
                    "4. Evidence for the next review: the focused unit run at the new candidate.\n")

    def doc(self, env, name, data):
        """The supervisor saves the owner's exact text durably, outside the enrolled developer worktree."""
        folder = env.root / "owner-updates"
        folder.mkdir(exist_ok=True)
        path = folder / name
        path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        return path

    def resume(self, ctl, reason="owner decision", amendment=None, guidance=None, **kw):
        """The owner's `resume` command path; returns (exit code, printed JSON)."""
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = ar.resume_command(ctl, reason, guidance_file=None if guidance is None else str(guidance),
                                     amendment_file=None if amendment is None else str(amendment), **kw)
        return code, json.loads(out.getvalue())

    def run_command(self, ctl):
        """The owner's `run` command path (it holds the writer lock for the whole loop)."""
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = ar.guarded(ctl, "run", ctl.run_loop)
        return code, json.loads(out.getvalue())

    @staticmethod
    def state(env):
        return ar.read_json(env.dir / "state.json")

    @staticmethod
    def state_bytes(env):
        return (env.dir / "state.json").read_bytes()

    @staticmethod
    def paused(checkpoint="phase-1"):
        return lambda e: report(e, checkpoint, status="paused")

    @staticmethod
    def work(name, checkpoint, dispositions=()):
        def act(e):
            e.commit(name, f"{name} content\n", f"work: {name}")
            e.push()
            return report(e, checkpoint, dispositions)
        return act

    @staticmethod
    def rereport(checkpoint, dispositions=()):
        """A fresh report on the unchanged candidate."""
        return lambda e: report(e, checkpoint, dispositions)

    def to_handoff(self, env):
        env.developer.script += [self.work("phase1.txt", "phase-1"), self.work("final.txt", "final")]
        env.reviewer.script += [{"decision": "checkpoint_passed"}, {"decision": "ready_for_owner_review"}]
        code, out = self.run_command(env.controller())
        self.assertEqual((ar.EXIT_OK, "AWAITING_OWNER_REVIEW"), (code, out["result"]))

    def headings_with(self, env, text):
        return [h for h in env.gh.headings() if text in h]


class ReviewerContinuationTests(OwnerFlowFixture, Base):
    """The reviewer's `Continuation for Claude` (inside the existing `decision_rationale`) reaches the next
    controller-generated developer prompt unchanged and labeled, while the review stays published and archived."""

    def test_continuation_reaches_the_next_prompt_is_published_archived_and_the_cycle_reaches_the_handoff(self):
        env = self.env
        fix = {}

        def correct(e):
            fix["sha"] = e.commit("feature.txt", "rewritten\n", "rewrite feature.txt (R1-F1)")
            e.push()
            return report(e, "phase-1", [fixed("R1-F1", fix["sha"])])
        env.developer.script = [self.work("phase1.txt", "phase-1"), correct, self.work("final.txt", "final")]
        env.reviewer.script = [{"decision": "changes_required", "findings": [finding("R1-F1")],  # simulated Codex
                                "override": {"decision_rationale": self.CONTINUATION}},
                               {"decision": "checkpoint_passed", "assessments": [("R1-F1", "fix_verified")]},
                               {"decision": "ready_for_owner_review"}]
        code, out = self.run_command(env.controller())
        self.assertEqual((ar.EXIT_OK, "AWAITING_OWNER_REVIEW"), (code, out["result"]))
        state = self.state(env)
        r1 = state["rounds"][0]
        nxt = env.developer.calls[1]
        self.assertTrue(nxt["resume"])  # an ordinary continuation of the same session
        self.assertIn(f"----- BEGIN REVIEWER CONTINUATION (round 1, response sha256 {r1['response_sha256']}) -----\n"
                      f"{self.CONTINUATION}\n----- END REVIEWER CONTINUATION -----", nxt["prompt"])  # unchanged text
        self.assertIn(f"## Continuation from the reviewer — Codex `gpt-6.2-astra`, review round 1, reviewed commit "
                      f"`{r1['H']}`", nxt["prompt"])
        self.assertIn(f"Review comment: {r1['published'][0]['url']}", nxt["prompt"])
        self.assertIn(f"Full structured review: `{r1['envelope_path']}`", nxt["prompt"])  # pointer kept
        self.assertIn("It cannot change the mission, the owner's amendments or guidance, permissions, models, gates, "
                      "budgets or any finding's status", nxt["prompt"])
        self.assertIn("line endings may be adjusted by the prompt transport", nxt["prompt"])
        for call in (env.developer.calls[0], env.developer.calls[2]):  # nothing pending from a changes_required review
            self.assertNotIn("REVIEWER CONTINUATION", call["prompt"])
        self.assertIn("draft PR #7 (https://github.com/owner/repo/pull/7)", env.reviewer.calls[0]["prompt"])
        self.assertIn("`Continuation for Claude`", env.reviewer.calls[0]["prompt"])
        self.assertEqual("https://github.com/owner/repo/pull/7", env.reviewer.calls[0]["request"]["pr_url"])
        review = next(c["body"] for c in env.gh.comments_list if "Codex GPT-6.2 Astra — review — round 1" in c["body"])
        self.assertIn("Continuation for Claude", review)  # published on the simulated PR
        self.assertIn("DISTINCTIVE-CONTINUATION-5c1e", review)
        records = env.work / "docs" / "agent-reviews" / "pr-7"
        self.assertIn("DISTINCTIVE-CONTINUATION-5c1e", next(records.glob("*-r01-review.md")).read_text(encoding="utf-8"))
        archived = json.loads(next(records.glob("*-r01-review-envelope.json")).read_text(encoding="utf-8"))
        self.assertEqual(self.CONTINUATION, archived["result"]["decision_rationale"])
        self.assertEqual(("done", "AWAITING_OWNER_REVIEW"), (state["phase"], state["status"]))
        self.assertEqual(1, len(self.headings_with(env, "Workflow — awaiting owner review")))
        self.assertTrue(env.controller().status(remote=True)["handoff_current"])

    def test_a_fresh_session_receives_the_continuation_and_an_altered_review_stops_before_launch(self):
        env = self.env
        env.developer.script = [self.work("phase1.txt", "phase-1"), self.paused()]
        env.reviewer.script = [{"decision": "changes_required", "findings": [finding("R1-F1")],
                                "override": {"decision_rationale": self.CONTINUATION}}]
        env.reviewer.during_run = lambda: env.developer.sessions.clear()  # simulated: the saved Claude session is gone
        code, out = self.run_command(env.controller())
        env.reviewer.during_run = None
        self.assertEqual(ar.EXIT_PAUSED, code)
        start = env.developer.calls[1]
        self.assertFalse(start["resume"])
        self.assertIn("Agent-review mission start", start["prompt"])
        self.assertIn(self.CONTINUATION, start["prompt"])
        self.assertIn("Review round 1 returned findings", start["prompt"])  # the situation and its pointer
        state = self.state(env)
        envelope = Path(state["rounds"][0]["envelope_path"])
        saved = envelope.read_bytes()
        envelope.write_bytes(saved.replace(b"DISTINCTIVE", b"ALTERED-TEXT"))  # simulated tampering (labeled)
        calls, invocations = len(env.developer.calls), state["developer"]["invocations"]
        code, out = self.resume(env.controller(), "ordinary resume")
        self.assertEqual(ar.EXIT_BLOCKED, code)
        self.assertIn("missing or altered", out["reason"])
        self.assertEqual((calls, invocations), (len(env.developer.calls), self.state(env)["developer"]["invocations"]))
        envelope.write_bytes(saved)  # supervised restoration of the preserved result
        env.developer.script += [self.paused()]
        self.assertEqual(ar.EXIT_PAUSED, self.resume(env.controller(), "review result restored")[0])
        self.assertIn(self.CONTINUATION, env.developer.calls[-1]["prompt"])
        self.assertNotIn("ALTERED-TEXT", env.developer.calls[-1]["prompt"])


class OwnerAmendmentTests(OwnerFlowFixture, Base):
    """`resume --amend-mission FILE`: an owner's updated instruction, applied at a safe boundary to the same
    enrollment, captured verbatim into a cumulative owner-amendments document with the existing revision/digest
    mechanism, delivered to both roles and bound into report, round, envelope and readiness freshness."""
    A1 = "Owner amendment (simulated): also add a CHANGELOG entry for the feature.\n"
    A2 = "Owner amendment (simulated): the CHANGELOG entry is no longer required; add docs/usage.md instead.\n"
    G = "Owner guidance (simulated): write docs/usage.md before anything else.\n"
    WITHDRAW = ("Owner amendment (simulated): requirement X is withdrawn; do not implement it. "
                "Everything else in the mission still applies.\n")

    def pause_in_develop(self, env):
        env.developer.script += [self.paused()]
        code, out = self.run_command(env.controller())
        self.assertEqual(ar.EXIT_PAUSED, code)
        self.assertEqual(("PAUSED", "develop"), (self.state(env)["status"], self.state(env)["phase"]))

    def document(self, env, revision=None):
        state = self.state(env)
        rec = next(r for r in state["amendments"]["revisions"]
                   if r["revision"] == (revision or state["amendments"]["current"]))
        return (env.dir / "amendments" / f"{rec['sha256']}.md").read_bytes(), rec

    def test_an_update_during_an_invocation_is_refused_and_applied_at_the_stop_boundary(self):
        env = self.env
        enrollment = self.state(env)["enrollment_id"]
        pending = self.doc(env, "pending-1.md", self.A1)  # the supervisor saved it as pending
        seen = {}

        def working(e):  # runs while the controller's `run` holds the writer lock
            e.commit("phase1.txt", "p1\n", "phase 1")
            e.push()
            with contextlib.redirect_stdout(io.StringIO()):  # the supervisor requests the cooperative stop
                ar.main(["stop", "--enrollment", enrollment, "--reason", "owner update pending"], root=env.wf)
            before = self.state_bytes(env)
            with contextlib.redirect_stderr(io.StringIO()) as err:
                seen["code"] = ar.main(["resume", "--enrollment", enrollment, "--reason", "apply owner update",
                                        "--amend-mission", str(pending)], root=env.wf)
            seen.update(err=err.getvalue(), unchanged=before == self.state_bytes(env), calls=len(env.developer.calls),
                        folder=(env.dir / "amendments").exists())
            return report(e, "phase-1", status="paused")  # the developer honours the stop file
        env.developer.script = [working]
        code, out = self.run_command(env.controller())
        self.assertEqual(ar.EXIT_PAUSED, code)
        self.assertIn("developer paused", out["reason"])
        self.assertEqual((ar.EXIT_USAGE, True, 1, False), (seen["code"], seen["unchanged"], seen["calls"],
                                                           seen["folder"]))
        self.assertIn("locked by", seen["err"])  # the active run's writer lock refuses it: no second agent
        state = self.state(env)
        self.assertNotIn("amendments", state)
        self.assertEqual((1, 1), (len(env.developer.calls), state["developer"]["invocations"]))
        self.assertTrue((env.dir / "STOP").exists())
        # at the safe boundary the same instruction is applied to the same enrollment, which continues
        env.developer.script += [self.rereport("phase-1")]  # unchanged source: a fresh report under the amended task
        env.reviewer.script += [{"decision": "blocked"}]
        code, out = self.resume(env.controller(), "apply the owner's update", amendment=pending)
        self.assertEqual(ar.EXIT_BLOCKED, code)
        self.assertIn("reviewer blocked", out["reason"])
        self.assertFalse((env.dir / "STOP").exists())  # the stop request was consumed by the resume
        state = self.state(env)
        self.assertEqual((enrollment, 7, 2, 2, 1), (state["enrollment_id"], state["pr"]["number"],
                                                    len(env.developer.calls), state["developer"]["invocations"],
                                                    len(env.reviewer.calls)))
        data, rec = self.document(env)
        self.assertIn(self.A1.encode(), data)
        self.assertEqual(ar.sha256_bytes(self.A1.encode()), rec["message_sha256"])
        prompt = env.developer.calls[1]["prompt"]
        self.assertIn(f"## Owner amendments to the mission — revision 1 (sha256 `{rec['sha256']}`)", prompt)
        self.assertIn(self.A1, prompt)
        self.assertIn("This amendment revision is new", prompt)
        self.assertIn(ar.AMENDMENT_PRECEDENCE, prompt)
        self.assertIn("The owner amended the task", prompt)
        review = env.reviewer.calls[0]
        self.assertEqual(data, review["amendments"])  # byte-exact copy for the reviewer
        self.assertEqual(env.mission.read_bytes(), review["mission"])  # the original mission, unchanged
        self.assertEqual((1, rec["sha256"]), (review["request"]["amendment_revision"],
                                              review["request"]["amendment_sha256"]))
        self.assertIn(".agent-review-inputs/owner-amendments.md", review["prompt"])
        a = out["amendments"]  # applied, and included in a returned invocation and a recorded review round
        self.assertEqual((1, "intact", 2), tuple(a["selected"][k] for k in ("revision", "integrity",
                                                                            "first_returned_invocation")))
        self.assertEqual((True, True), (a["latest_developer_invocation"]["returned"],
                                        a["latest_developer_invocation"]["matches_selected"]))
        self.assertTrue(a["latest_review_round"]["matches_selected"])
        body = next(c["body"] for c in env.gh.comments_list if "review request — round 1 —" in c["body"])
        self.assertIn(f"| Owner amendments | revision 1, sha256 `{rec['sha256']}` |", body)
        self.assertIn("**Owner amendments to the mission — revision 1", body)
        self.assertIn("also add a CHANGELOG entry", body)
        self.assertNotIn(str(env.root), body)

    def assert_needs_report(self, env):
        ctl = env.controller()
        reviews = len(env.reviewer.calls)
        ctl.transition("review", "simulated: review requested without a fresh report")
        self.assertEqual("needs_report", ctl.review_round())
        self.assertEqual((reviews, "develop"), (len(env.reviewer.calls), ctl.state["phase"]))

    def test_an_amendment_supersedes_a_handoff_needs_a_fresh_report_and_stale_results_never_satisfy_readiness(self):
        env = self.env
        self.to_handoff(env)
        before = self.state(env)
        head, old_ready = before["handoff"]["A"], before["ready_review"]
        reviews, calls = len(env.reviewer.calls), len(env.developer.calls)
        env.developer.script += [self.paused("final")]
        code, out = self.resume(env.controller(), "owner amends the task",
                                amendment=self.doc(env, "a1.md", self.A1))
        self.assertEqual(ar.EXIT_PAUSED, code)
        state = self.state(env)
        self.assertEqual((None, None, "develop"), (state["ready_review"], state["handoff"], state["phase"]))
        self.assertEqual(old_ready["H"], state["superseded_ready"][-1]["H"])
        self.assertIn("owner amendment 1", state["superseded_handoffs"][-1]["why"])
        self.assertEqual(reviews, len(env.reviewer.calls))  # no obsolete review was launched
        self.assertEqual(calls + 1, len(env.developer.calls))  # the next launch carries the amended task
        self.assertIn(self.A1, env.developer.calls[-1]["prompt"])
        self.assertEqual(1, len(self.headings_with(env, "the owner-review handoff above is not current")))
        self.assertEqual(1, len(self.headings_with(env, "Workflow — reopened")))
        self.assertIn("owner amendment 1", env.gh.body)
        self.assertEqual(head, git(env.origin, "rev-parse", f"refs/heads/{env.branch}"))  # unchanged source
        self.assert_needs_report(env)
        state = self.state(env)  # labeled: bind the earlier report to the current head (the application cleared the
        state["last_report_for"] = head  # commit binding), so that only the amendment binding can make it stale
        ar.atomic_write_json(env.dir / "state.json", state)
        self.assertEqual(state["last_report_guidance"], {"guidance_revision": None, "guidance_sha256": None})
        self.assert_needs_report(env)
        self.assertIn("no accepted developer report under the current owner amendments",
                      self.state(env)["transitions"][-1]["why"])
        state = self.state(env)  # labeled: put the superseded ready result back; it cannot satisfy readiness
        state.update(ready_review=old_ready, phase="finalize", last_report_for=old_ready["H"], status="ACTIVE")
        ar.atomic_write_json(env.dir / "state.json", state)
        with self.assertRaises(ar.Stop) as stop:
            env.controller().finalize()
        self.assertIn("owner amendments changed", stop.exception.reason)
        self.assertEqual(1, len(self.headings_with(env, "Workflow — awaiting owner review")))  # still only the old one
        state = self.state(env)
        self.assertEqual((None, "develop"), (state["ready_review"], state["phase"]))
        state["status"] = "PAUSED"  # labeled: the stop above was raised directly, not through a command
        ar.atomic_write_json(env.dir / "state.json", state)
        # a fresh report on the unchanged source, reviewed under the amended task, reaches a new handoff
        env.developer.script += [self.rereport("final")]
        env.reviewer.script += [{"decision": "ready_for_owner_review"}]
        code, out = self.resume(env.controller(), "continue under the amended task")
        self.assertEqual((ar.EXIT_OK, "AWAITING_OWNER_REVIEW"), (code, out["result"]))
        state = self.state(env)
        data, rec = self.document(env)
        self.assertEqual((1, rec["sha256"]), (state["ready_review"]["amendment_revision"],
                                              state["ready_review"]["amendment_sha256"]))
        self.assertEqual(data, env.reviewer.calls[-1]["amendments"])
        self.assertEqual(2, len(self.headings_with(env, "Workflow — awaiting owner review")))
        self.assertTrue(env.controller().status(remote=True)["handoff_current"])
        records = env.work / "docs" / "agent-reviews" / "pr-7"
        last = sorted(records.glob("*-review.md"))[-1].read_text(encoding="utf-8")
        self.assertIn(f"Owner amendments bound to this review: revision 1, sha256 `{rec['sha256']}`.", last)

    def test_stopped_review_and_finalize_boundaries_use_the_shared_path_without_an_obsolete_launch(self):
        def check(env, label):
            state = self.state(env)
            reviews, calls = len(env.reviewer.calls), len(env.developer.calls)
            completed = dict(state["rounds_completed"])
            env.developer.script += [self.paused("final")]
            code, out = self.resume(env.controller(), f"amend at the {label} boundary",
                                    amendment=self.doc(env, f"{label}.md", self.A1))
            self.assertEqual(ar.EXIT_PAUSED, code, out)
            after = self.state(env)
            self.assertEqual((reviews, calls + 1), (len(env.reviewer.calls), len(env.developer.calls)))
            self.assertEqual((completed, None, None, "develop", "amended"),
                             (after["rounds_completed"], after["ready_review"], after["active_round"], after["phase"],
                              after["develop_context"]))
            self.assertIn(self.A1, env.developer.calls[-1]["prompt"])
            return after

        with self.subTest("finalize: a ready result stopped before the handoff"):
            env = Env("headless")
            self.addCleanup(env.cleanup)
            env.developer.script += [self.work("phase1.txt", "phase-1"), self.work("final.txt", "final")]
            env.reviewer.script += [{"decision": "checkpoint_passed"}, {"decision": "ready_for_owner_review"}]
            calls = []
            env.reviewer.during_run = lambda: calls.append(1) or (
                len(calls) == 2 and ar.write_text(env.dir / "STOP", "owner update pending (simulated)\n"))
            code, out = self.run_command(env.controller())
            env.reviewer.during_run = None
            self.assertEqual(ar.EXIT_PAUSED, code)
            self.assertEqual(("finalize", True), (self.state(env)["phase"], bool(self.state(env)["ready_review"])))
            after = check(env, "finalize")
            self.assertEqual("amended", after["develop_context"])
            self.assertIn("owner amendment 1", after["superseded_ready"][-1]["why"])
            self.assertFalse(self.headings_with(env, "awaiting owner review"))
            # the accepted ready verdict was already public: it gets a visible supersession before any handoff exists
            self.assertTrue(self.headings_with(env, "Codex GPT-6.2 Astra — review — round 2"))
            self.assertEqual(1, len(self.headings_with(env, "round 2 ready verdict is not current")))

        with self.subTest("review: a validated result whose publication failed"):
            env = Env("headless")
            self.addCleanup(env.cleanup)
            env.developer.script += [self.work("phase1.txt", "phase-1"), self.work("final.txt", "final")]
            env.reviewer.script += [{"decision": "checkpoint_passed"}, {"decision": "ready_for_owner_review"}]
            calls = []
            env.reviewer.during_run = lambda: calls.append(1) or (len(calls) == 2 and setattr(env.gh, "fail_next", 99))
            code, out = self.run_command(env.controller())
            env.reviewer.during_run, env.gh.fail_next = None, 0
            self.assertEqual(ar.EXIT_PAUSED, code)
            state = self.state(env)
            self.assertEqual(("review", "validated"), (state["phase"], state["rounds"][-1]["status"]))
            after = check(env, "review-validated")
            self.assertEqual(("invalidated", "superseded"), (after["rounds"][-1]["status"],
                                                             after["publications"]["r02-review"]["state"]))
            self.assertFalse(self.headings_with(env, "Codex GPT-6.2 Astra — review — round 2"))  # never accepted

        with self.subTest("review: a requested round whose request was never delivered"):
            env = Env("headless")
            self.addCleanup(env.cleanup)
            env.developer.script += [self.work("phase1.txt", "phase-1")]
            env.gh.fail_next = 99  # simulated outage: the request is preserved, unsent
            code, out = self.run_command(env.controller())
            env.gh.fail_next = 0
            self.assertEqual(ar.EXIT_PAUSED, code)
            state = self.state(env)
            self.assertEqual(("review", "requested", "pending"), (state["phase"], state["rounds"][-1]["status"],
                                                                  state["publications"]["r01-request"]["state"]))
            env.developer.script += [self.paused()]
            code, out = self.resume(env.controller(), "amend at the review boundary",
                                    amendment=self.doc(env, "review.md", self.A1))
            self.assertEqual(ar.EXIT_PAUSED, code)
            after = self.state(env)
            self.assertEqual(("superseded", "withdrawn"), (after["rounds"][-1]["status"],
                                                           after["publications"]["r01-request"]["state"]))
            self.assertNotIn("r01-request", out["pending_publications"])  # withdrawn, never sent: settled
            self.assertEqual([], env.reviewer.calls)
            self.assertFalse(self.headings_with(env, "review request — round 1"))  # withdrawn, never posted
            self.assertIn(self.A1, env.developer.calls[-1]["prompt"])

    def test_successive_amendments_and_later_guidance_keep_the_effective_task_across_restarts(self):
        env = self.env
        original_mission = self.state(env)["mission"]
        self.pause_in_develop(env)
        a1, a2 = self.doc(env, "pending-a1.md", self.A1), self.doc(env, "pending-a2.md", self.A2)
        env.developer.script += [self.paused()]
        self.assertEqual(ar.EXIT_PAUSED, self.resume(env.controller(), "first update", amendment=a1)[0])
        first, rec1 = self.document(env, 1)
        env.developer.script += [self.paused()]
        self.assertEqual(ar.EXIT_PAUSED, self.resume(env.controller(), "second update", amendment=a2)[0])
        second, rec2 = self.document(env, 2)
        self.assertTrue(second.startswith(first))  # the second capture keeps the first message verbatim
        self.assertLess(second.index(self.A1.encode()), second.index(self.A2.encode()))
        self.assertIn(b"----- BEGIN OWNER AMENDMENT 1 (", second)
        self.assertIn(b"----- BEGIN OWNER AMENDMENT 2 (", second)
        self.assertEqual((first, 1), (self.document(env, 1)[0], rec2["supersedes"]))  # earlier snapshot unchanged
        for text in (self.A1, self.A2):
            self.assertIn(text, env.developer.calls[-1]["prompt"])
        g = self.doc(env, "guidance.md", self.G)  # later approach-only guidance keeps the amended task
        env.developer.script += [self.paused()]
        self.assertEqual(ar.EXIT_PAUSED, self.resume(env.controller(), "approach change", guidance=g)[0])
        state = self.state(env)
        self.assertEqual((2, 1), (state["amendments"]["current"], state["guidance"]["current"]))
        for text in (self.A1, self.A2, self.G):
            self.assertIn(text, env.developer.calls[-1]["prompt"])
        self.assertEqual(original_mission, state["mission"])  # the original mission and its hash are unchanged
        self.assertEqual(original_mission["sha256"], ar.sha256_file(env.mission))
        # damaged selected amendments block before any launch; neither option repairs them
        snapshot = env.dir / "amendments" / f"{rec2['sha256']}.md"
        snapshot.write_bytes(b"simulated damage\n")
        calls, invocations = len(env.developer.calls), state["developer"]["invocations"]
        code, out = self.resume(env.controller(), "ordinary resume")
        self.assertEqual(ar.EXIT_BLOCKED, code)
        self.assertIn("owner amendments", out["reason"])
        self.assertIn("missing or altered", out["reason"])
        self.assertEqual((calls, invocations), (len(env.developer.calls), self.state(env)["developer"]["invocations"]))
        for kw in ({"amendment": self.doc(env, "a3.md", "another update\n")}, {"guidance": self.doc(env, "g2.md", "x\n")}):
            before = self.state_bytes(env)
            with self.assertRaises(ar.UsageError) as refusal:
                self.resume(env.controller(), "no repair bypass", **kw)
            self.assertIn("owner amendments", str(refusal.exception))
            self.assertEqual(before, self.state_bytes(env))
        state = self.state(env)  # labeled: a null selection is a problem, never "no amendments"
        ar.atomic_write_json(env.dir / "state.json", {**state, "amendments": {**state["amendments"], "current": None}})
        code, out = self.resume(env.controller(), "ordinary resume")
        self.assertEqual(ar.EXIT_BLOCKED, code)
        self.assertIn("owner amendments selection in the enrollment state is invalid", out["reason"])
        self.assertEqual(calls, len(env.developer.calls))
        state = self.state(env)
        state["amendments"]["current"] = 2
        ar.atomic_write_json(env.dir / "state.json", state)
        snapshot.write_bytes(second)  # supervised restoration of the identical captured bytes
        # the original input files are edited, then deleted; a new controller process still has the captured task
        a2.write_text("edited after capture\n", encoding="utf-8")
        for path in (a1, a2, g):
            path.unlink()
        env.developer.sessions.clear()  # and the Claude session is gone: the next invocation is a start prompt
        env.developer.script += [self.rereport("phase-1")]
        env.reviewer.script += [{"decision": "blocked"}]
        code, out = self.resume(env.controller(), "ordinary resume after a restart")
        self.assertEqual(ar.EXIT_BLOCKED, code)
        self.assertIn("reviewer blocked", out["reason"])
        start = env.developer.calls[-1]
        self.assertFalse(start["resume"])
        for text in (self.A1, self.A2, self.G):
            self.assertIn(text, start["prompt"])
        self.assertNotIn("edited after capture", start["prompt"])
        self.assertNotIn("This amendment revision is new", start["prompt"])  # an invocation with it returned before
        self.assertEqual(second, env.reviewer.calls[-1]["amendments"])
        self.assertEqual(self.G.encode(), env.reviewer.calls[-1]["guidance"])
        self.assertEqual((2, rec2["sha256"]), (env.reviewer.calls[-1]["request"]["amendment_revision"],
                                               env.reviewer.calls[-1]["request"]["amendment_sha256"]))

    GATE = {"gates": {"check": {"argv": [sys.executable, "-c", "print('Ran 1 test'); print('OK')"],
                                "timeout_minutes": 5}}, "required_gates": ["check"]}
    ASSESSMENT = ("OWNER AMENDMENT 1 withdrew requirement X, which is exactly what R1-F1 required; the remaining "
                  "phase-1 behavior is sound under the effective task (simulated assessment)")

    @staticmethod
    def gated(checkpoint, edit=None, dispositions=lambda sha: ()):
        """A developer invocation that commits, pushes and runs the project's required gate through the controller
        (the developer's `verify`) before reporting; edit=None reports the unchanged candidate."""
        def act(e):
            sha = e.commit(*edit) if edit else None
            if edit:
                e.push()
            e.controller().run_gate("check")
            return report(e, checkpoint, dispositions(sha))
        return act

    def test_a_withdrawn_requirement_needs_a_cited_rebuttal_and_reviewer_assessment_while_an_unrelated_defect_blocks(self):
        env = Env("headless", cfg_overrides=self.GATE)  # a real, non-empty required project gate
        self.addCleanup(env.cleanup)
        self.assertEqual(["check"], self.state(env)["project"]["required_gates"])
        withdrawn, unrelated = finding("R1-F1"), finding("R1-F2")
        withdrawn["title"], unrelated["title"] = "requirement X is not implemented", "feature.txt has a defect"
        env.developer.script += [self.gated("phase-1", ("phase1.txt", "p1\n", "phase 1")), self.paused()]
        env.reviewer.script += [{"decision": "changes_required", "findings": [withdrawn, unrelated],
                                 "override": {"decision_rationale": self.CONTINUATION}}]
        code, out = self.run_command(env.controller())
        self.assertEqual(ar.EXIT_PAUSED, code)  # the supervisor's stop: the developer paused
        before = self.state(env)
        settings = (before["developer_settings_file"], before["developer_settings_sha256"])
        cfg = before["project"]
        devs = len(env.developer.calls)
        seen, reviews_at_rejection = {}, {}
        cite = {"finding_id": "R1-F1", "disposition": "rebutted", "commits": [],
                "evidence": "OWNER AMENDMENT 1 withdrew requirement X; the finding was valid under the original "
                            "mission and no longer applies (simulated)"}

        def dispose_without_gate(e):  # a new candidate reported before its required receipt exists
            seen.update(self.state(e))  # what the application persisted when this invocation launched
            sha = e.commit("feature.txt", "partial attempt\n", "attempt R1-F2")
            e.push()
            reviews_at_rejection["n"] = len(e.reviewer.calls)
            return report(e, "phase-1", [cite, fixed("R1-F2", sha)])

        def dispose_after_gate(e):  # the report-correction invocation: same candidate, now with its receipt
            e.controller().run_gate("check")
            sha = git(e.work, "rev-parse", "HEAD")
            return report(e, "phase-1", [cite, fixed("R1-F2", sha)])
        env.developer.script += [dispose_without_gate, dispose_after_gate,
                                 self.gated("phase-1", ("feature.txt", "corrected\n", "fix R1-F2"),
                                            lambda sha: [fixed("R1-F2", sha)]),
                                 self.gated("final", ("final.txt", "f\n", "final"))]
        restated = dict(unrelated, actual="still defective (simulated)")
        env.reviewer.script += [
            # attempt 1 (simulated): a pass while the unrelated blocker is still open is rejected by validation
            {"decision": "checkpoint_passed", "findings": [restated],
             "assessments": [("R1-F1", "rebuttal_accepted", self.ASSESSMENT), ("R1-F2", "fix_rejected")]},
            {"decision": "changes_required", "findings": [restated],
             "assessments": [("R1-F1", "rebuttal_accepted", self.ASSESSMENT), ("R1-F2", "fix_rejected")]},
            {"decision": "checkpoint_passed", "assessments": [("R1-F2", "fix_verified")]},
            {"decision": "ready_for_owner_review"}]
        code, out = self.resume(env.controller(), "owner withdraws requirement X",
                                amendment=self.doc(env, "withdraw.md", self.WITHDRAW))
        self.assertEqual((ar.EXIT_OK, "AWAITING_OWNER_REVIEW"), (code, out["result"]))
        # the required gate was enforced on the amended candidate: rejected before any reviewer dispatch, then the
        # report-correction invocation carried the selected amendment and proceeded with the real receipt
        correction = env.developer.calls[devs + 1]
        self.assertIn("rejected your last report", correction["prompt"])
        self.assertIn("passing controller-run gates on this candidate: check", correction["prompt"])
        self.assertIn(self.WITHDRAW, correction["prompt"])
        self.assertEqual(1, reviews_at_rejection["n"])  # only round 1 had been reviewed when the report was rejected
        r2 = self.state(env)["rounds"][1]  # round 2 reviewed the amended candidate with its passing receipt
        self.assertEqual([], env.controller().missing_gates(r2["H"]))
        receipt = ar.read_json(sorted((env.dir / "evidence").glob(f"gate-check-{r2['H'][:12]}-*.json"))[-1])
        self.assertEqual(("check", r2["H"], True), (receipt["gate"], receipt["candidate"], receipt["passed"]))
        stored = [r for r in self.state(env)["reports"] if r["report"]["candidate_commit"] == r2["H"]]
        self.assertEqual([1, 1], [r["amendment_revision"] for r in stored])  # the rejected and the corrected report
        # the application kept the spent counters, limits and configuration
        self.assertEqual((before["rounds_completed"], before["developer"]["invocations"] + 1, before["limits"]),
                         (seen["rounds_completed"], seen["developer"]["invocations"], seen["limits"]))
        self.assertEqual((before["findings"]["R1-F1"]["finding"], before["pending_findings"]),
                         (seen["findings"]["R1-F1"]["finding"], seen["pending_findings"]))
        self.assertEqual((settings, cfg), ((seen["developer_settings_file"], seen["developer_settings_sha256"]),
                                           seen["project"]))
        prompt = env.developer.calls[devs]["prompt"]
        self.assertIn(self.WITHDRAW, prompt)
        self.assertIn(ar.AMENDMENT_FINDINGS, prompt)
        self.assertIn(self.CONTINUATION, prompt)  # the older continuation stays, marked as historical context
        self.assertIn("**Written under earlier owner instructions**", prompt)
        self.assertIn("Pending findings still need dispositions: R1-F1, R1-F2", prompt)
        round2 = env.reviewer.calls[1]
        self.assertIn(ar.AMENDMENT_REVIEW, round2["prompt"])
        self.assertIn(self.WITHDRAW.encode(), round2["amendments"])
        dispositions = round2["prior"]["ledger"]["R1-F1"]["dispositions"]
        self.assertIn("OWNER AMENDMENT 1", dispositions[-1]["evidence"])
        self.assertEqual(5, len(env.reviewer.calls))  # round 1, two attempts of round 2, round 3, round 4
        state = self.state(env)
        attempts = state["rounds"][1]["attempts"]
        self.assertEqual((2, False, True), (len(attempts), attempts[0]["ok"], attempts[1]["ok"]))
        self.assertIn("a passing decision lists findings that block readiness", "; ".join(attempts[0]["reasons"]))
        f1, f2 = state["findings"]["R1-F1"], state["findings"]["R1-F2"]
        self.assertEqual(("resolved", "rebuttal_accepted", "requirement X is not implemented", 1),
                         (f1["status"], f1["assessments"][-1]["assessment"], f1["finding"]["title"], f1["first_round"]))
        self.assertEqual(["rebutted"], [d["disposition"] for d in f1["dispositions"]])  # never recorded as fixed
        self.assertEqual(self.ASSESSMENT, f1["assessments"][-1]["rationale"])  # retained: names the amendment
        review2 = next(c["body"] for c in env.gh.comments_list if "Codex GPT-6.2 Astra — review — round 2" in c["body"])
        self.assertIn(f"- **R1-F1** — `rebuttal_accepted` — {self.ASSESSMENT}", review2)  # published and archived
        records = env.work / "docs" / "agent-reviews" / "pr-7"
        self.assertIn(self.ASSESSMENT, next(records.glob("*-r02-review.md")).read_text(encoding="utf-8"))
        self.assertEqual(["fix_rejected", "fix_verified"], [a["assessment"] for a in f2["assessments"]])
        self.assertEqual(("accepted", "changes_required", ["R1-F2"]),
                         (state["rounds"][1]["status"], state["rounds"][1]["decision"], state["rounds"][1]["open_findings"]))
        self.assertEqual(({"phase-1": 3, "final": 1}, before["limits"], settings, cfg),
                         (state["rounds_completed"], state["limits"],
                          (state["developer_settings_file"], state["developer_settings_sha256"]), state["project"]))
        posted = next(c["body"] for c in env.gh.comments_list if "finding dispositions — round 1" in c["body"])
        self.assertIn("OWNER AMENDMENT 1 withdrew requirement X", posted)

    def test_an_exhausted_budget_records_the_amendment_but_launches_nothing(self):
        env = Env("headless", max_rounds=1)
        self.addCleanup(env.cleanup)
        env.developer.script += [self.work("phase1.txt", "phase-1")]
        env.reviewer.script += [{"decision": "changes_required", "findings": [finding("R1-F1")]}]
        code, out = self.run_command(env.controller())
        self.assertEqual(ar.EXIT_BLOCKED, code)
        self.assertIn("review-round cap reached", out["reason"])
        before = self.state(env)
        calls = len(env.developer.calls)
        code, out = self.resume(env.controller(), "owner amends the task", amendment=self.doc(env, "a1.md", self.A1))
        self.assertEqual(ar.EXIT_BLOCKED, code)
        self.assertIn("budget", out["reason"])
        state = self.state(env)
        self.assertEqual((calls, before["developer"]["invocations"], before["rounds_completed"], before["limits"]),
                         (len(env.developer.calls), state["developer"]["invocations"], state["rounds_completed"],
                          state["limits"]))
        a = out["amendments"]  # applied to the enrollment, not included in any agent input
        self.assertEqual((1, None), (a["selected"]["revision"], a["selected"]["first_returned_invocation"]))
        self.assertEqual(False, a["latest_developer_invocation"]["matches_selected"])
        env.developer.script += [self.paused()]  # the owner's separate, explicit budget decision
        self.assertEqual(ar.EXIT_PAUSED, self.resume(env.controller(), "owner extends the budget", max_rounds=2)[0])
        self.assertIn(self.A1, env.developer.calls[-1]["prompt"])
        self.assertEqual(1, self.state(env)["amendments"]["current"])

    def test_an_amendment_is_refused_unchanged_outside_a_safe_boundary(self):
        env = self.env
        self.pause_in_develop(env)
        path = self.doc(env, "update.md", self.A1)
        state_path = env.dir / "state.json"
        original = self.state(env)
        ar.write_text(env.dir / "STOP", "owner stop (simulated)\n")

        def refused(changes=None, expect=None, **kw):
            ar.atomic_write_json(state_path, {**original, **(changes or {})})
            before, posted, calls = self.state_bytes(env), len(env.gh.comments_list), len(env.developer.calls)
            with self.assertRaises(ar.UsageError) as refusal:
                self.resume(env.controller(), amendment=path, **kw)
            self.assertEqual((before, posted, calls), (self.state_bytes(env), len(env.gh.comments_list),
                                                       len(env.developer.calls)))
            self.assertTrue((env.dir / "STOP").exists())
            self.assertFalse((env.dir / "amendments").exists())
            if expect:
                self.assertIn(expect, str(refusal.exception))
            ar.atomic_write_json(state_path, original)

        copy = lambda value: json.loads(json.dumps(value))  # noqa: E731
        unreturned = copy(original["developer"])
        unreturned["launch"]["returned"] = False  # simulated: launch intent recorded, no recorded return
        reviewing = [{"round": 1, "status": "reviewing", "attempts": [{"n": 1, "started": ar.now_iso()}],
                      "H": "0" * 40, "checkpoint_id": "phase-1"}]  # simulated attempt without an end record
        publications = copy(original.get("publications", {}))
        chunk = "simulated body whose POST outcome is unknown\n"  # simulated outbox record (labeled), absent on the PR
        marker = f"<!-- agent-review:v1 enrollment={original['enrollment_id']} key=r09-request part=1/1 " \
                 f"sha256={ar.sha256_text(chunk)} -->"
        body_file = env.dir / "outbox" / "r09-request-part1.md"
        ar.write_text(body_file, f"{marker}\n{chunk}")
        publications["r09-request"] = {"key": "r09-request", "state": "pending", "seq": 99, "redactions": [],
                                       "parts": [{"marker": marker, "body_file": str(body_file),
                                                  "sha256": ar.sha256_text(chunk), "comment_id": None, "url": None,
                                                  "posting_since": ar.now_iso()}]}
        for label, changes, expect in (  # every simulated state is labeled; the command path is real
                ("ACTIVE (a run that has not stopped)", {"status": "ACTIVE"}, "safe stopping boundary"),
                ("cancelled", {"status": "CANCELLED", "phase": "cancelled"}, "not permitted"),
                # foreground amendments are supported between the session's commands (ForegroundDevelopmentTests);
                # a foreground enrollment outside every supported boundary is still refused
                ("foreground mode outside a safe boundary", {"mode": "foreground", "foreground_session": FOREGROUND_SESSION,
                                                             "status": "ACTIVE", "phase": "done"},
                 "safe stopping boundary"),
                ("live developer", {"developer": {**original["developer"], "active_pid": os.getpid()}}, "still running"),
                ("unreturned developer launch", {"developer": unreturned}, "no recorded return"),
                ("reviewer attempt without an end", {"phase": "review", "rounds": reviewing, "active_round": 1},
                 "no recorded end"),
                ("uncertain publication", {"publications": publications}, "uncertain"),
                ("archive commit in progress", {"archive_pending": {"parent": "x", "reason": "simulated",
                                                                    "commit": None, "files": []}}, "archive commit"),
                ("invalid guidance selection", {"guidance": None}, "owner guidance selection")):
            with self.subTest(label):
                refused(changes, expect)
        with self.subTest("budget change in the same call"):
            refused(expect="budget change", max_rounds=9)
        with self.subTest("resend combined"):
            refused(expect="--resend-undelivered", resend_undelivered=True)
        with self.subTest("closed PR"):
            env.gh.pr_overrides = {"state": "CLOSED"}
            refused(expect="refused before any change")
            env.gh.pr_overrides = {}
        with self.subTest("runtime lock"):
            (env.root / "runtime.lock").write_text("simulated runtime transaction\n", encoding="utf-8")
            refused(expect="runtime transaction")
            (env.root / "runtime.lock").unlink()
        with self.subTest("helper lock held"):
            with env.controller().helper_lock("verify"):
                refused(expect="helper")
        with self.subTest("both options in one call (CLI)"):
            before = self.state_bytes(env)
            with contextlib.redirect_stderr(io.StringIO()) as err:
                code = ar.main(["resume", "--enrollment", original["enrollment_id"], "--reason", "x",
                                "--guidance", str(path), "--amend-mission", str(path)], root=env.wf)
            self.assertEqual((ar.EXIT_USAGE, before), (code, self.state_bytes(env)))
            self.assertIn("one at a time", err.getvalue())
        with self.subTest("a declared pending restoration without any lock file"):
            last = {**original["last_report"], "runtime_restoration": "pending"}  # simulated stopped report (labeled)
            refused({"last_report": last}, "restoration still pending")
        with self.subTest("unpublishable text (a lone private-key opening delimiter)"):
            # assembled at run time so that no source version carries the delimiter (the guarded push scans them)
            unsafe = self.doc(env, "unsafe.md", "Quote this line verbatim: -----BEGIN RSA " + "PRIVATE KEY-----\n")
            before = self.state_bytes(env)
            with self.assertRaises(ar.UsageError) as refusal:
                self.resume(env.controller(), amendment=unsafe)
            self.assertIn("could not be published", str(refusal.exception))
            self.assertEqual(before, self.state_bytes(env))
            self.assertFalse((env.dir / "amendments").exists())
            with self.assertRaises(ar.UsageError) as refusal:  # the same policy guards guidance (neighbor path)
                self.resume(env.controller(), guidance=unsafe)
            self.assertIn("could not be published", str(refusal.exception))
            self.assertEqual(before, self.state_bytes(env))
            # the PR-safe replacement, in this same enrollment, is applied and published in the next review request
            safe_text = "Owner amendment (simulated, PR-safe): quote no key material; describe the format instead.\n"
            safe = self.doc(env, "safe.md", safe_text)
            env.developer.script += [self.rereport("phase-1")]
            env.reviewer.script += [{"decision": "blocked"}]
            code, out = self.resume(env.controller(), "apply the PR-safe update", amendment=safe)
            self.assertEqual(ar.EXIT_BLOCKED, code)
            self.assertIn("reviewer blocked", out["reason"])
            rec = self.state(env)["amendments"]["revisions"][-1]
            self.assertEqual((1, ar.sha256_bytes(safe_text.encode())), (rec["revision"], rec["message_sha256"]))
            request = next(c["body"] for c in env.gh.comments_list if "review request — round 1 —" in c["body"])
            self.assertIn(f"| Owner amendments | revision 1, sha256 `{rec['sha256']}` |", request)
            self.assertIn(f"**Owner amendments to the mission — revision 1, captured-source sha256 `{rec['sha256']}`.**",
                          request)
            self.assertIn(safe_text.strip(), request)
            self.assertEqual(1, env.reviewer.calls[-1]["request"]["amendment_revision"])
        with self.subTest("a replay of the same saved submission"):
            env.developer.script += [self.paused()]
            self.assertEqual(ar.EXIT_PAUSED, self.resume(env.controller(), "apply", amendment=path)[0])
            ar.write_text(env.dir / "STOP", "owner stop (simulated)\n")
            before = self.state_bytes(env)
            with self.assertRaises(ar.UsageError) as refusal:
                self.resume(env.controller(), "apply again", amendment=path)
            self.assertIn("already applied as owner amendment 2", str(refusal.exception))
            self.assertEqual(before, self.state_bytes(env))


class ContinuationCrlfTests(OwnerFlowFixture, Base):
    def test_a_crlf_continuation_is_published_delivered_unchanged_archived_and_reaches_the_handoff(self):
        env = self.env
        crlf = self.CONTINUATION.replace("5c1e", "CRLF-77").replace("\n", "\r\n")  # simulated Codex output (labeled)

        def correct(e):
            sha = e.commit("feature.txt", "rewritten\n", "rewrite feature.txt (R1-F1)")
            e.push()
            return report(e, "phase-1", [fixed("R1-F1", sha)])
        env.developer.script = [self.work("phase1.txt", "phase-1"), correct, self.work("final.txt", "final")]
        env.reviewer.script = [{"decision": "changes_required", "findings": [finding("R1-F1")],
                                "override": {"decision_rationale": crlf}},
                               {"decision": "checkpoint_passed", "assessments": [("R1-F1", "fix_verified")]},
                               {"decision": "ready_for_owner_review"}]
        code, out = self.run_command(env.controller())
        self.assertEqual((ar.EXIT_OK, "AWAITING_OWNER_REVIEW"), (code, out["result"]))
        state = self.state(env)
        private = json.loads(Path(state["rounds"][0]["envelope_path"]).read_bytes())
        self.assertEqual(crlf, private["result"]["decision_rationale"])  # the private rationale is exact
        self.assertIn(crlf, env.developer.calls[1]["prompt"])  # given unchanged to the developer
        review = next(c["body"] for c in env.gh.comments_list if "Codex GPT-6.2 Astra — review — round 1" in c["body"])
        self.assertNotIn("\r", review)  # the public rendering uses LF and passed its integrity check
        self.assertIn(crlf.replace("\r\n", "\n").strip(), review)
        records = env.work / "docs" / "agent-reviews" / "pr-7"
        self.assertIn("DISTINCTIVE-CONTINUATION-CRLF-77", next(records.glob("*-r01-review.md")).read_text(encoding="utf-8"))
        archived = json.loads(next(records.glob("*-r01-review-envelope.json")).read_text(encoding="utf-8"))
        self.assertEqual(crlf, archived["result"]["decision_rationale"])  # JSON keeps the escaped CR LF
        self.assertTrue(env.controller().status(remote=True)["handoff_current"])


class AmendmentBoundaryTests(OwnerFlowFixture, Base):
    """Round-1 corrections: restoration and runtime boundaries, delivery reconciliation, public retirement of
    superseded work, distinct owner messages, stopped handoffs, report history, status evidence and activation."""
    A1 = "Owner amendment (simulated): add one more acceptance example.\n"

    def validated_review_stop(self, env):
        """Stopped in review with a validated phase-1 result whose verdict could not be posted (definitively)."""
        env.developer.script += [self.work("phase1.txt", "phase-1")]
        env.reviewer.script += [{"decision": "checkpoint_passed"}]
        env.reviewer.during_run = lambda: setattr(env.gh, "fail_next", 99)
        code, out = self.run_command(env.controller())
        env.reviewer.during_run, env.gh.fail_next = None, 0
        self.assertEqual(ar.EXIT_PAUSED, code)
        self.assertEqual("validated", self.state(env)["rounds"][-1]["status"])

    def test_a_pending_restoration_and_a_late_runtime_lock_keep_the_update_pending(self):
        env = self.env
        env.developer.script += [lambda e: report(e, "phase-1", status="paused", restoration="pending")]
        code, out = self.run_command(env.controller())
        self.assertEqual(ar.EXIT_PAUSED, code)
        self.assertIn("runtime restoration still pending", out["reason"])
        self.assertFalse((env.root / "runtime.lock").exists())  # no lock file: only the report says so
        path = self.doc(env, "a1.md", self.A1)
        before, calls = self.state_bytes(env), len(env.developer.calls)
        with self.assertRaises(ar.UsageError) as refusal:
            self.resume(env.controller(), amendment=path)
        self.assertIn("restoration still pending", str(refusal.exception))
        self.assertEqual((before, calls), (self.state_bytes(env), len(env.developer.calls)))

        env2 = Env("headless")  # a shared runtime lock appears during the application's last publication lookup
        self.addCleanup(env2.cleanup)
        self.validated_review_stop(env2)
        ar.write_text(env2.dir / "STOP", "owner update pending (simulated)\n")
        lock = env2.root / "runtime.lock"

        def comments(number):  # simulated: another project's enrollment takes the shared lock meanwhile
            lock.write_text("simulated shared runtime transaction\n", encoding="utf-8")
            return FakeGitHub.comments(env2.gh, number)
        env2.gh.comments = comments
        path2 = self.doc(env2, "a1.md", self.A1)
        before, calls, posted = self.state_bytes(env2), len(env2.developer.calls), len(env2.gh.comments_list)
        try:
            with self.assertRaises(ar.UsageError) as refusal:
                self.resume(env2.controller(), amendment=path2)
        finally:
            del env2.gh.comments
        self.assertIn("runtime transaction lock appeared", str(refusal.exception))
        self.assertEqual((before, calls, posted), (self.state_bytes(env2), len(env2.developer.calls),
                                                   len(env2.gh.comments_list)))
        self.assertTrue((env2.dir / "STOP").exists())
        lock.unlink()
        env2.developer.script += [self.paused()]
        self.assertEqual(ar.EXIT_PAUSED, self.resume(env2.controller(), amendment=path2)[0])
        self.assertEqual(1, self.state(env2)["amendments"]["current"])

    def test_a_lost_post_response_is_reconciled_before_application_and_the_obsolete_request_is_withdrawn(self):
        env = self.env
        hidden = {"on": True}

        def comments(number):  # simulated listing lag: the stored request is not yet visible
            return [c for c in FakeGitHub.comments(env.gh, number)
                    if not (hidden["on"] and "review request — round 1" in c["body"])]
        env.gh.comments = comments
        env.gh.lose_next_response = 1  # simulated: the request POST is stored but its response is lost
        env.developer.script += [self.work("phase1.txt", "phase-1")]
        code, out = self.run_command(env.controller())
        self.assertEqual(ar.EXIT_PAUSED, code)
        self.assertIn("ambiguous", out["reason"])
        part = self.state(env)["publications"]["r01-request"]["parts"][0]
        self.assertTrue(part["posting_since"] and not part["comment_id"])
        path = self.doc(env, "a1.md", self.A1)
        before = self.state_bytes(env)
        with self.assertRaises(ar.UsageError) as refusal:  # still not visible: ambiguous, refused unchanged
            self.resume(env.controller(), amendment=path)
        self.assertIn("uncertain", str(refusal.exception))
        self.assertEqual(before, self.state_bytes(env))
        hidden["on"] = False  # the stored comment becomes visible
        env.developer.script += [self.paused()]
        try:
            code, out = self.resume(env.controller(), amendment=path)
        finally:
            del env.gh.comments
        self.assertEqual(ar.EXIT_PAUSED, code)
        state = self.state(env)
        request = state["publications"]["r01-request"]
        self.assertEqual("posted", request["state"])  # reconciled as completely delivered: settled and still verified
        self.assertTrue(request["parts"][0]["comment_id"])
        self.assertEqual(1, len(self.headings_with(env, "review request — round 1")))  # never re-posted
        self.assertEqual(1, len(self.headings_with(env, "round 1 review request is withdrawn")))
        self.assertEqual([], env.reviewer.calls)  # no obsolete review
        self.assertIn(self.A1, env.developer.calls[-1]["prompt"])

    def test_a_partly_delivered_request_keeps_its_delivered_part_and_never_sends_the_rest(self):
        env = self.env

        def big(e):  # a report long enough to split its review request into two parts
            e.commit("phase1.txt", "p1\n", "phase 1")
            e.push()
            r = report(e, "phase-1")
            r["summary"] = "simulated long summary " + "x" * (ar.COMMENT_LIMIT + 100)
            return r
        env.developer.script += [big]
        # simulated outage after the first part: the second part is definitively rejected on every attempt
        env.gh.on_post = lambda rec: setattr(env.gh, "fail_next", 99) if "part=1/2" in rec["body"] else None
        code, out = self.run_command(env.controller())
        env.gh.on_post, env.gh.fail_next = None, 0
        self.assertEqual(ar.EXIT_PAUSED, code)
        parts = self.state(env)["publications"]["r01-request"]["parts"]
        self.assertEqual((2, True, None), (len(parts), bool(parts[0]["comment_id"]), parts[1]["comment_id"]))
        env.developer.script += [self.paused()]
        code, out = self.resume(env.controller(), amendment=self.doc(env, "a1.md", self.A1))
        self.assertEqual(ar.EXIT_PAUSED, code)
        self.assertEqual("withdrawn", self.state(env)["publications"]["r01-request"]["state"])
        self.assertNotIn("r01-request", out["pending_publications"])  # settled, not awaiting delivery
        posted = [c["body"] for c in env.gh.comments_list if "key=r01-request " in c["body"]]
        self.assertEqual(1, len(posted))  # part two was never sent after supersession
        self.assertIn("part=1/2", posted[0])
        self.assertEqual(1, len(self.headings_with(env, "round 1 review request is withdrawn")))
        self.assertEqual([], env.reviewer.calls)
        # the run continues under the amended task to a verified handoff
        env.developer.script += [self.rereport("phase-1"), self.work("final.txt", "final")]
        env.reviewer.script += [{"decision": "checkpoint_passed"}, {"decision": "ready_for_owner_review"}]
        code, out = self.resume(env.controller(), "continue under the amended task")
        self.assertEqual((ar.EXIT_OK, "AWAITING_OWNER_REVIEW"), (code, out["result"]))
        self.assertNotIn("r01-request", out["pending_publications"])
        self.assertEqual(1, sum("key=r01-request " in c["body"] for c in env.gh.comments_list))
        record = next((env.work / "docs" / "agent-reviews" / "pr-7").glob("*-r01-request.md")).read_text(encoding="utf-8")
        self.assertIn("Withdrawn record: 1 of 2 part(s) were published", record)  # the delivered part is the record
        self.assertTrue(env.controller().status(remote=True)["handoff_current"])
        delivered = next(c for c in env.gh.comments_list if "key=r01-request part=1/2" in c["body"])
        delivered["body"] = delivered["body"].replace("simulated long summary", "edited on GitHub (simulated)")
        status = env.controller().status(remote=True)  # the delivered part is still verified remotely
        self.assertFalse(status["handoff_current"])
        self.assertIn("r01-request", status["handoff_superseded_by"])
        env.gh.comments_list.remove(delivered)  # removed entirely: also detected
        self.assertIn("r01-request", env.controller().status(remote=True)["handoff_superseded_by"])

    def test_identical_words_received_again_become_a_new_entry_while_a_replay_is_refused(self):
        env = self.env
        first = self.doc(env, "20261122T100000Z.md", self.A1)
        env.developer.script += [self.paused()]
        self.pause_in_develop_quick(env)
        env.developer.script += [self.work("example.txt", "phase-1")]  # the requested work is completed and reviewed
        env.reviewer.script += [{"decision": "blocked"}]
        code, out = self.resume(env.controller(), "first decision", amendment=first)
        self.assertEqual(ar.EXIT_BLOCKED, code)
        with self.assertRaises(ar.UsageError):  # the same saved submission again: a replay
            self.resume(env.controller(), "replay", amendment=first)
        second = self.doc(env, "20261122T120000Z.md", self.A1)  # a newly received decision, same words
        env.developer.script += [self.paused()]
        self.assertEqual(ar.EXIT_PAUSED, self.resume(env.controller(), "second decision", amendment=second)[0])
        state = self.state(env)
        rec = state["amendments"]["revisions"][-1]
        data = (env.dir / "amendments" / f"{rec['sha256']}.md").read_bytes()
        self.assertEqual(2, data.count(self.A1.encode()))
        self.assertLess(data.index(b"BEGIN OWNER AMENDMENT 1 ("), data.index(b"BEGIN OWNER AMENDMENT 2 ("))
        self.assertEqual(2, env.developer.calls[-1]["prompt"].count(self.A1))

    def test_a_failed_verdict_post_closes_the_posted_request(self):
        env = self.env
        self.validated_review_stop(env)  # the request is on the PR; its verdict POST was definitively rejected
        state = self.state(env)
        h = state["rounds"][-1]["H"]
        self.assertEqual(("posted", "pending"), (state["publications"]["r01-request"]["state"],
                                                 state["publications"]["r01-review"]["state"]))
        reviews = len(env.reviewer.calls)
        env.developer.script += [self.paused()]
        code, out = self.resume(env.controller(), amendment=self.doc(env, "a1.md", self.A1))
        self.assertEqual(ar.EXIT_PAUSED, code)
        self.assertEqual([], out["pending_publications"])  # the retired verdict is settled once its correction posts
        correction = [c["body"] for c in env.gh.comments_list if "round 1 review request is withdrawn" in c["body"]]
        self.assertEqual(1, len(correction))
        self.assertIn(f"`{ar.short(h)}` will not receive a current verdict", correction[0])
        self.assertIn("owner amendment 1", correction[0])
        state = self.state(env)
        self.assertEqual(("invalidated", "superseded", "posted"),
                         (state["rounds"][-1]["status"], state["publications"]["r01-review"]["state"],
                          state["publications"]["r01-request"]["state"]))  # complete, so still verified as posted
        self.assertFalse(self.headings_with(env, "Codex GPT-6.2 Astra — review — round 1"))
        self.assertEqual(reviews, len(env.reviewer.calls))  # no obsolete reviewer launch

    def test_a_failed_first_receipt_post_corrects_the_ready_verdict_and_claims_no_handoff(self):
        env = self.env
        env.developer.script += [self.work("phase1.txt", "phase-1"), self.work("final.txt", "final")]
        env.reviewer.script += [{"decision": "checkpoint_passed"}, {"decision": "ready_for_owner_review"}]
        # simulated outage right after the ready verdict is posted: the handoff receipt is definitively rejected
        env.gh.on_post = lambda rec: setattr(env.gh, "fail_next", 99) \
            if "Codex GPT-6.2 Astra — review — round 2" in rec["body"] else None
        code, out = self.run_command(env.controller())
        env.gh.on_post, env.gh.fail_next = None, 0
        self.assertEqual(ar.EXIT_PAUSED, code)
        state = self.state(env)
        h = state["ready_review"]["H"]
        receipts = [k for k in state["publications"] if ar.VERDICT_KEY_RE.match(k) and k.startswith("final-status-")]
        self.assertEqual(("finalize", 1), (state["phase"], len(receipts)))
        self.assertFalse(any(p.get("comment_id") for p in state["publications"][receipts[0]]["parts"]))
        reviews = len(env.reviewer.calls)
        env.developer.script += [self.paused("final")]
        code, out = self.resume(env.controller(), amendment=self.doc(env, "a1.md", self.A1))
        self.assertEqual(ar.EXIT_PAUSED, code)
        self.assertEqual([], out["pending_publications"])  # the retired receipt is settled once the correction posts
        state = self.state(env)  # labeled: a retired record whose POST outcome is unknown stays listed
        state["publications"][receipts[0]]["parts"][0]["posting_since"] = ar.now_iso()
        ar.atomic_write_json(env.dir / "state.json", state)
        self.assertEqual([receipts[0]], env.controller().status()["pending_publications"])
        state["publications"][receipts[0]]["parts"][0].pop("posting_since")
        ar.atomic_write_json(env.dir / "state.json", state)
        correction = [c["body"] for c in env.gh.comments_list if "round 2 ready verdict is not current" in c["body"]]
        self.assertEqual(1, len(correction))
        self.assertIn(f"decision above for `{ar.short(h)}` no longer applies", correction[0])
        self.assertFalse(self.headings_with(env, "Workflow — reopened"))  # no handoff ever reached the PR
        self.assertFalse(self.headings_with(env, "handoff above is not current"))
        self.assertFalse(self.headings_with(env, "awaiting owner review"))
        self.assertEqual("superseded", self.state(env)["publications"][receipts[0]]["state"])  # never sent later
        self.assertEqual(reviews, len(env.reviewer.calls))

    def test_retrying_an_older_saved_file_never_reinstates_it_over_a_later_amendment(self):
        env = self.env
        env.developer.script += [self.paused()]
        self.pause_in_develop_quick(env)
        a = self.doc(env, "20261122T100000Z.md", "Owner amendment (simulated): require feature X.\n")
        b = self.doc(env, "20261122T110000Z.md", "Owner amendment (simulated): feature X is withdrawn.\n")
        for path in (a, b):
            env.developer.script += [self.paused()]
            self.assertEqual(ar.EXIT_PAUSED, self.resume(env.controller(), "owner update", amendment=path)[0])
        ar.write_text(env.dir / "STOP", "owner stop (simulated)\n")
        before, calls = self.state_bytes(env), len(env.developer.calls)
        with self.assertRaises(ar.UsageError) as refusal:  # a retry of A's original saved file
            self.resume(env.controller(), "retry", amendment=a)
        self.assertIn("already applied as owner amendment 1", str(refusal.exception))
        self.assertEqual((before, calls), (self.state_bytes(env), len(env.developer.calls)))
        self.assertEqual(2, self.state(env)["amendments"]["current"])  # B stays selected
        again = self.doc(env, "20261122T120000Z.md", a.read_bytes())  # a newly received decision with A's words
        env.developer.script += [self.paused()]
        self.assertEqual(ar.EXIT_PAUSED, self.resume(env.controller(), "new decision", amendment=again)[0])
        state = self.state(env)
        self.assertEqual(3, state["amendments"]["current"])
        self.assertEqual(state["amendments"]["revisions"][0]["message_sha256"],
                         state["amendments"]["revisions"][2]["message_sha256"])

    def pause_in_develop_quick(self, env):
        code, out = self.run_command(env.controller())
        self.assertEqual(ar.EXIT_PAUSED, code)

    def test_a_handoff_paused_by_an_operational_failure_and_an_ended_attempt_with_a_reused_pid_are_eligible(self):
        env = self.env
        self.to_handoff(env)

        def failing_pr(number):
            raise OSError("simulated temporary PR read failure")
        env.gh.pr = failing_pr
        try:
            code, out = self.resume(env.controller(), "ordinary resume")
        finally:
            del env.gh.pr
        self.assertEqual(ar.EXIT_PAUSED, code)
        state = self.state(env)
        self.assertEqual(("PAUSED", "done", True), (state["status"], state["phase"], bool(state["handoff"])))
        reviews = len(env.reviewer.calls)
        env.developer.script += [self.paused("final")]
        self.assertEqual(ar.EXIT_PAUSED, self.resume(env.controller(), amendment=self.doc(env, "a1.md", self.A1))[0])
        state = self.state(env)
        self.assertEqual((None, "develop", reviews), (state["handoff"], state["phase"], len(env.reviewer.calls)))
        self.assertEqual(1, len(self.headings_with(env, "the owner-review handoff above is not current")))

        env2 = Env("headless")  # three invalid reviewer outputs: stopped in review with ended attempts
        self.addCleanup(env2.cleanup)
        env2.developer.script += [self.work("phase1.txt", "phase-1")]
        env2.reviewer.script += [{"raw": "not json (simulated)"}] * 3
        code, out = self.run_command(env2.controller())
        self.assertEqual(ar.EXIT_BLOCKED, code)
        state = self.state(env2)
        self.assertEqual(("review", "reviewing", 3), (state["phase"], state["rounds"][-1]["status"],
                                                      len(state["rounds"][-1]["attempts"])))
        state["rounds"][-1]["attempts"][-1]["pid"] = os.getpid()  # labeled: a live, unrelated process reuses the PID
        ar.atomic_write_json(env2.dir / "state.json", state)
        env2.developer.script += [self.paused()]
        self.assertEqual(ar.EXIT_PAUSED, self.resume(env2.controller(), amendment=self.doc(env2, "a1.md", self.A1))[0])
        state = self.state(env2)
        self.assertEqual(("superseded", 3), (state["rounds"][-1]["status"], len(env2.reviewer.calls)))
        self.assertEqual(1, len(self.headings_with(env2, "round 1 review request is withdrawn")))

    def test_report_history_keeps_bindings_and_status_distinguishes_reviewer_delivery(self):
        env = self.env
        a1, a2 = self.doc(env, "a1.md", self.A1), self.doc(env, "a2.md", "Owner amendment (simulated): also X.\n")
        env.developer.script += [self.paused()]
        self.pause_in_develop_quick(env)

        def ready_then_stop(e):  # a ready report under revision 1, then the supervisor's stop before any request
            ar.write_text(e.dir / "STOP", "owner update pending (simulated)\n")
            return report(e, "phase-1")
        env.developer.script += [ready_then_stop]
        code, out = self.resume(env.controller(), "first update", amendment=a1)
        self.assertEqual(ar.EXIT_PAUSED, code)
        state = self.state(env)
        self.assertEqual(("review", []), (state["phase"], state["rounds"]))
        env.developer.script += [self.paused()]
        self.assertEqual(ar.EXIT_PAUSED, self.resume(env.controller(), "second update", amendment=a2)[0])
        state = ar.read_json(env.dir / "state.json")  # restart: what persisted
        revs = {r["revision"]: r["sha256"] for r in state["amendments"]["revisions"]}
        self.assertEqual([("paused", None, "none"), ("checkpoint_ready", 1, revs[1]), ("paused", 2, revs[2])],
                         [(r["report"]["status"], r["amendment_revision"], r["amendment_sha256"] or "none")
                          for r in state["reports"]])
        self.assertEqual((2, revs[2]), (state["last_report_instructions"]["amendment_revision"],
                                        state["last_report_instructions"]["amendment_sha256"]))
        self.assertEqual("paused", state["last_report"]["status"])
        self.assertIsNone(state["last_report_for"])  # the freshness guard: the stopped report is not reviewable
        ctl = env.controller()
        ctl.transition("review", "simulated: review requested without a fresh report")
        self.assertEqual("needs_report", ctl.review_round())

        def ready_publication_fails(e):  # a fresh revision-2 report; then GitHub rejects the review request
            setattr(e.gh, "fail_next", 99)
            return report(e, "phase-1")
        env.developer.script += [ready_publication_fails]
        code, out = self.resume(env.controller(), "continue under revision 2")
        env.gh.fail_next = 0
        self.assertEqual(ar.EXIT_PAUSED, code)
        a = out["amendments"]
        self.assertEqual((True, True), (a["latest_developer_invocation"]["returned"],
                                        a["latest_developer_invocation"]["matches_selected"]))
        self.assertEqual((True, None), (a["latest_review_round"]["matches_selected"],
                                        a["latest_review_round"]["latest_attempt"]))  # allocated; no reviewer input
        env.reviewer.script += [{"decision": "blocked"}]
        code, out = self.resume(env.controller(), "publication outage over")
        self.assertEqual(ar.EXIT_BLOCKED, code)
        attempt = out["amendments"]["latest_review_round"]["latest_attempt"]
        self.assertEqual((True, True), (attempt["process_start_recorded"], attempt["ok"]))
        self.assertTrue(attempt["ended_at"])
        self.assertIn("Owner amendment (simulated): also X.", env.reviewer.calls[-1]["amendments"].decode())

    def test_activation_at_a_handoff_reaches_a_stopped_boundary_without_dispatching_the_old_review(self):
        env = self.env
        self.to_handoff(env)
        ar.write_text(env.dir / "STOP", "activate the amendment-capable controller (simulated)\n")  # `stop`
        prompt = env.wf / "prompts" / "reviewer.md"  # a reviewed new version (simulated: changed workflow bytes)
        prompt.write_text(prompt.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        ctl = env.controller()
        with ctl.lock("activate"):  # the `activate` command path
            ctl.reload()
            ctl.assert_claims()
            ctl.activate()
            ctl.settle_after_activation()
        state = self.state(env)
        self.assertEqual(("ACTIVE", "review", None), (state["status"], state["phase"], state["ready_review"]))
        path = self.doc(env, "a1.md", self.A1)
        with self.assertRaises(ar.UsageError) as refusal:  # ACTIVE: not yet a stopped boundary
            self.resume(env.controller(), amendment=path)
        self.assertIn("safe stopping boundary", str(refusal.exception))
        reviews = len(env.reviewer.calls)
        code, out = self.run_command(env.controller())  # documented branch (b): `run` pauses at once on the stop file
        self.assertEqual(ar.EXIT_PAUSED, code)
        self.assertIn("stop requested", out["reason"])
        self.assertEqual(reviews, len(env.reviewer.calls))
        env.developer.script += [self.paused("final")]
        self.assertEqual(ar.EXIT_PAUSED, self.resume(env.controller(), amendment=path)[0])
        self.assertEqual(reviews, len(env.reviewer.calls))  # the old review was never dispatched
        self.assertIn(self.A1, env.developer.calls[-1]["prompt"])

    def test_an_exhausted_invocation_budget_is_not_lifted_by_max_rounds(self):
        env = self.env
        env.developer.script += [self.paused()]
        self.pause_in_develop_quick(env)
        state = self.state(env)  # labeled: the developer-invocation cap is reached at this stop
        state["limits"]["max_developer_invocations"] = state["developer"]["invocations"]
        ar.atomic_write_json(env.dir / "state.json", state)
        calls = len(env.developer.calls)
        code, out = self.resume(env.controller(), "owner update", amendment=self.doc(env, "a1.md", self.A1))
        self.assertEqual(ar.EXIT_BLOCKED, code)
        self.assertIn("developer invocation budget exhausted", out["reason"])
        self.assertEqual(1, out["amendments"]["selected"]["revision"])  # applied, not delivered
        code, out = self.resume(env.controller(), "owner extends review rounds", max_rounds=9)
        self.assertEqual(ar.EXIT_BLOCKED, code)  # the review-round remedy does not lift the invocation cap
        self.assertIn("developer invocation budget exhausted", out["reason"])
        self.assertEqual(calls, len(env.developer.calls))


class ToolTranscriptTests(unittest.TestCase):
    def test_extracts_recorded_commands_and_outputs_since_a_time(self):
        """Executed-validation evidence for the read-only reviewer, from the CLI-recorded session log."""
        with tempfile.TemporaryDirectory() as folder:
            sid = "abc-session"
            log = Path(folder) / "projects" / "C--repo" / f"{sid}.jsonl"
            log.parent.mkdir(parents=True)

            def use(stamp, uid, cmd, side=False):
                return {"type": "assistant", "timestamp": stamp, "isSidechain": side, "message": {"content": [
                    {"type": "tool_use", "id": uid, "name": "Bash", "input": {"command": cmd}}]}}

            def result(stamp, uid, text, err=False):
                return {"type": "user", "timestamp": stamp, "message": {"content": [
                    {"type": "tool_result", "tool_use_id": uid, "content": text, "is_error": err}]}}
            rows = [use("2026-11-20T10:00:00.000Z", "u0", "old command"), result("2026-11-20T10:00:01.000Z", "u0", "old"),
                    use("2026-11-20T12:00:00.000Z", "u1", "python -m unittest test_calc"),
                    result("2026-11-20T12:00:01.000Z", "u1", "Ran 2 tests\n\nOK"),
                    use("2026-11-20T12:01:00.000Z", "u2", "git push", side=True),
                    use("2026-11-20T12:02:00.000Z", "u3", "false"), result("2026-11-20T12:02:01.000Z", "u3", "exit 1", True)]
            log.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
            dev = ar.ClaudeDeveloper({"executable": sys.executable, "config_dir": folder, "model": "opus", "effort": "high"},
                                     Path(folder) / "s.json", HERE / ar.REPORT_SCHEMA_FILE)
            text = dev.tool_transcript(sid, "2026-11-20T11:00:00Z")
            self.assertIn("$ python -m unittest test_calc\nRan 2 tests\n\nOK", text)
            self.assertIn("· error", text)
            self.assertNotIn("old command", text)
            self.assertNotIn("git push", text)  # sidechain (sub-agent) entries are not the developer's own record
            self.assertIn("commands since 2026-11-20T11:00:00Z: 2", text)
            # R1-F16: effort comes from main-thread assistant metadata only, not from text that mentions it.
            noise = [{"type": "assistant", "timestamp": "2026-11-20T12:03:00.000Z", "effort": "high",
                      "message": {"model": "claude-opus-5-5", "content": []}},
                     {"type": "user", "timestamp": "2026-11-20T12:04:00.000Z",
                      "message": {"content": [{"type": "text", "text": '{"effort":"low"}'}]}},
                     {"type": "assistant", "isSidechain": True, "effort": "low", "message": {"model": "claude-haiku-5-5"}}]
            with log.open("a", encoding="utf-8") as handle:
                handle.write("\n".join(json.dumps(r) for r in noise) + "\n")
            prov = dev.session_provenance(sid)
            self.assertEqual(["high"], prov["efforts"])
            self.assertEqual(["claude-opus-5-5"], prov["models"])


class UnitTests(unittest.TestCase):
    def test_sanitize_redacts_whole_credentials_and_home(self):
        """F20."""
        # Markers are assembled at runtime so this source file never contains a literal key header
        # (the repository's guarded push correctly refuses files that do).
        dashes, label = "-" * 5, "PRIVATE " + "KEY"
        key = f"{dashes}BEGIN RSA {label}{dashes}\nMIIEsecretbody\nmoresecret\n{dashes}END RSA {label}{dashes}"
        text, count = ar.sanitize(f"ghp_{'a' * 36} at {Path.home()}\\x\n{key}\n" + json.dumps({"k": key}))
        self.assertEqual(3, count)
        for secret in ("ghp_", "secretbody", "moresecret", label, str(Path.home())):
            self.assertNotIn(secret, text)
        with self.assertRaises(ar.Stop):
            ar.sanitize(f"{dashes}BEGIN {label}{dashes}\ntruncated body without an end marker")
        # Local model inputs (developer tool transcript): redact the lone marker and key-like lines instead.
        local, n = ar.sanitize(f"$ grep BEGIN file\n{dashes}BEGIN {label}{dashes}\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASC\nok\n",
                               strict=False)
        self.assertEqual(1, n)
        self.assertNotIn("BEGIN " + label, local)
        self.assertNotIn("MIIEvQIBADANBgkq", local)
        self.assertIn("ok", local)

    def test_shipped_schemas_validate_examples(self):
        req = {"request_id": "r", "round": 1, "checkpoint_id": "c", "checkpoint_type": "final", "H": "h"}
        schema = ar.read_json(HERE / ar.REVIEW_SCHEMA_FILE)
        self.assertEqual([], ar.validate_schema(review_result(req, "ready_for_owner_review"), schema))
        bad = review_result(req, "ready_for_owner_review")
        bad["round"] = True
        self.assertTrue(ar.validate_schema(bad, schema))

    def test_project_and_plans_load_under_owner_policy(self):
        cfg = ar.load_project("kingmaker-gunslinger")
        self.assertEqual(("gpt-6.2-astra", "max"), (cfg["reviewer"]["model"], cfg["reviewer"]["effort"]))
        self.assertEqual(("opus", "high"), (cfg["developer"]["model"], cfg["developer"]["effort"]))
        for path in sorted((ar.HERE / "projects").glob("*.json")):  # every shipped profile meets the policy
            shipped = ar.load_project(path.stem)
            self.assertEqual(("max", "high"), (shipped["reviewer"]["effort"], shipped["developer"]["effort"]), path.name)
        stale = json.loads(json.dumps(cfg))
        stale["reviewer"]["effort"] = "high"  # a snapshot pinned before the policy change is refused, not run
        with self.assertRaisesRegex(ar.UsageError, "reviewer.effort"):
            ar.check_policy(stale)
        for name in ("black-tentacles", "agent-review-setup"):
            self.assertEqual("final", ar.load_plan(name)["checkpoints"][-1]["type"])


GATE_LIVE_SCRIPT = """import pathlib, sys, time
marker = 'GATE-LIVE-' + 'MARKER-7f3'
print(marker, flush=True)
logs = pathlib.Path(sys.argv[1]).parent / 'state'
deadline, seen = time.time() + 20, False
while time.time() < deadline and not seen:
    seen = any(('| ' + marker) in p.read_text(encoding='utf-8') for p in logs.glob('*/live.log'))
    time.sleep(0.05)
print('seen' if seen else 'not-seen', flush=True)
print('stderr-line', file=sys.stderr, flush=True)
sys.exit(0 if seen else 3)
"""


class LiveReviewer(FakeReviewer):
    """Simulated Codex that streams one command event into its events file, then waits (bounded) until that
    activity is visible in the enrollment's live log before it exits. Records whether it was seen while running."""

    def __init__(self, live_path):
        super().__init__()
        self.live_path, self.seen_while_running = Path(live_path), []

    def run(self, prompt, workdir, schema, result_path, events_path, *args, **kwargs):
        with open(events_path, "a", encoding="utf-8") as out:  # SIMULATED `codex exec --json` event
            out.write(json.dumps({"type": "item.started", "item": {"type": "command_execution",
                                                                   "command": "rg -n REVIEW-LIVE-MARKER feature.txt"}})
                      + "\n")
            out.write(json.dumps({"type": "item.reasoning", "item": {"type": "reasoning", "text": "PRIVATE-THOUGHT"}})
                      + "\n")
        deadline, seen = time.time() + 10, False
        while time.time() < deadline and not seen:
            seen = self.live_path.is_file() and \
                "Codex ▸ $ rg -n REVIEW-LIVE-MARKER feature.txt" in self.live_path.read_text(encoding="utf-8")
            time.sleep(0.05)
        self.seen_while_running.append(seen)
        return super().run(prompt, workdir, schema, result_path, events_path, *args, **kwargs)


class ForegroundFixture(OwnerFlowFixture):
    """Shared helpers for the foreground tests: the real foreground command paths over the Git fixtures."""
    mode = "foreground"
    A1 = "Owner amendment (simulated): also add docs/usage.md describing the feature.\n"

    def fg_env(self, **cfg):
        plan = {"schema_version": "agent-review.plan.v1", "mission_id": "fixture", "title": "Fixture mission",
                "checkpoints": [{"id": "final", "type": "final", "scope": "s", "exit_conditions": ["e"]}]}
        env = Env("foreground", plan=plan, cfg_overrides=cfg or None)
        self.addCleanup(env.cleanup)
        return env

    def review_cmd(self, env, checkpoint="final", dispositions=(), ctl=None, cite=None, path=None):
        """The foreground `review --report FILE` command path; returns (exit code, stdout JSON, stderr text). cite: the
        amendment citation the report carries in evidence_refs; path: resubmit an existing report file unchanged."""
        if path is None:
            path = env.root / f"report-{uuid.uuid4().hex[:6]}.json"
            data = report(env, checkpoint, dispositions)
            if cite:
                data["evidence_refs"] = [cite]
            path.write_text(json.dumps(data), encoding="utf-8")
        self.last_report_path = path
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
            code = ar.review_command(ctl or env.controller(), str(path))
        return code, json.loads(out.getvalue()), err.getvalue()  # stdout is the result alone: it parses as JSON

    def finalize_cmd(self, env):
        ctl = env.controller()
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
            code = ar.guarded(ctl, "finalize", ctl.finalize, honor_stop=True)
        return code, json.loads(out.getvalue())

    def resume(self, ctl, *args, **kw):
        with contextlib.redirect_stderr(io.StringIO()):
            return super().resume(ctl, *args, **kw)

    def live_text(self, env):
        return (env.dir / "live.log").read_text(encoding="utf-8")

    def real_reader(self, env):
        config = env.root / "claude-config"
        (config / "projects" / "C--fixture").mkdir(parents=True, exist_ok=True)
        return (ar.ClaudeDeveloper({"executable": sys.executable, "config_dir": str(config), "model": "opus",
                                    "effort": "high", "allowed_model_pattern": "^claude-opus-"}, None, None),
                config / "projects" / "C--fixture" / f"{FOREGROUND_SESSION}.jsonl")


class ForegroundDevelopmentTests(ForegroundFixture, Base):
    """Foreground (main-conversation) development: the enrolled interactive session develops, `review --report`
    returns the accepted review for it to continue from, reviewer activity and gate output are readable while they
    run, owner amendments are applied from the session and reach both roles, and the session's recorded model,
    effort and permission mode are verified. Claude, Codex and GitHub are the labeled simulations above."""

    def test_the_session_develops_reviews_and_continues_from_the_returned_review_to_the_handoff(self):
        env = self.fg_env()
        head = env.commit("feature.txt", "v2\n", "feature v2")
        env.push()
        env.reviewer.script = [{"decision": "changes_required", "findings": [finding("R1-F1")],  # simulated Codex
                                "override": {"decision_rationale": self.CONTINUATION}},
                               {"decision": "ready_for_owner_review", "assessments": [("R1-F1", "fix_verified")]}]
        code, out, err = self.review_cmd(env)
        self.assertEqual((ar.EXIT_OK, "changes_required"), (code, out["result"]))
        state = self.state(env)
        r1, review = state["rounds"][0], out["review"]
        self.assertEqual((1, "changes_required", head), (review["round"], review["decision"], review["candidate"]))
        self.assertEqual(self.CONTINUATION, review["continuation"])  # the reviewer's text, unchanged
        self.assertEqual([p["url"] for p in r1["published"]], review["review_reference"])
        self.assertTrue(review["review_reference"])
        self.assertEqual(r1["envelope_path"], review["structured_review"])
        self.assertEqual((["R1-F1"], ["R1-F1"]), ([f["id"] for f in review["findings"]], review["pending_findings"]))
        self.assertIn("dispose of every pending finding", review["next"])
        self.assertEqual(str(env.dir / "live.log"), out["live_log"])
        self.assertNotIn("review round 1 attempt 1", json.dumps(out))  # progress never mixes into the result
        live = self.live_text(env)
        self.assertIn(f"review round 1 accepted on {head[:10]}: changes_required; pending findings: R1-F1", live)
        self.assertIn("DISTINCTIVE-CONTINUATION-5c1e", live)  # the final review text is readable too
        # the same session corrects the candidate and submits it again; no owner relay is involved
        fix = env.commit("feature.txt", "rewritten\n", "rewrite feature.txt (R1-F1)")
        env.push()
        code, out, _ = self.review_cmd(env, dispositions=[fixed("R1-F1", fix)])
        self.assertEqual((ar.EXIT_OK, "ready_for_owner_review"), (code, out["result"]))
        self.assertEqual((2, fix, []), (out["review"]["round"], out["review"]["candidate"],
                                        out["review"]["pending_findings"]))
        self.assertIn("Run `finalize`", out["review"]["next"])
        code, out = self.finalize_cmd(env)
        self.assertEqual((ar.EXIT_OK, "AWAITING_OWNER_REVIEW"), (code, out["status"]))
        self.assertEqual({"final": 2}, self.state(env)["rounds_completed"])
        expected = ["Claude Opus — review request — round 1", "Codex GPT-6.2 Astra — review — round 1",
                    "Claude Opus — finding dispositions — round 1", "Claude Opus — review request — round 2",
                    "Codex GPT-6.2 Astra — review — round 2", "Workflow — awaiting owner review"]
        headings = env.gh.headings()
        self.assertEqual(len(expected), len(headings), headings)
        for want, got in zip(expected, headings):
            self.assertIn(want, got)
        self.assertTrue(env.controller().status(remote=True)["handoff_current"])

    def test_reviewer_activity_is_readable_in_the_live_log_before_the_reviewer_exits(self):
        env = self.fg_env()
        env.reviewer = LiveReviewer(env.dir / "live.log")
        env.reviewer.script = [{"decision": "ready_for_owner_review"}]
        env.commit("feature.txt", "v2\n", "feature v2")
        env.push()
        code, out, _ = self.review_cmd(env)
        self.assertEqual((ar.EXIT_OK, "ready_for_owner_review"), (code, out["result"]))
        self.assertEqual([True], env.reviewer.seen_while_running)  # visible while the simulated reviewer ran
        live = self.live_text(env)
        self.assertNotIn("PRIVATE-THOUGHT", live)  # reasoning items are never shown
        self.assertIn("review round 1 attempt 1 ended: valid result, decision ready_for_owner_review", live)
        events = (env.dir / "rounds" / "r01" / "events-1.jsonl").read_text(encoding="utf-8")
        self.assertIn("thread.started", events)  # the event file stays the private record

    def test_gate_output_is_readable_before_the_gate_finishes_and_the_receipt_is_unchanged(self):
        env = self.fg_env(gates={"unit": {"argv": [sys.executable, "-u", "{repo_root}/../gate_live.py", "{repo_root}"],
                                          "timeout_minutes": 2}}, required_gates=["unit"])
        (env.root / "gate_live.py").write_text(GATE_LIVE_SCRIPT, encoding="utf-8")
        ctl = env.controller()
        with contextlib.redirect_stderr(io.StringIO()):
            receipt = ctl.run_gate("unit")
        # the gate exits 0 only if it saw its own first line in the live log while it was still running
        self.assertEqual((0, True), (receipt["exit_code"], receipt["passed"]), receipt.get("output_tail"))
        log = ctl.dir / "evidence" / receipt["log"]
        self.assertEqual("GATE-LIVE-MARKER-7f3\nseen\nstderr-line\n", log.read_text(encoding="utf-8"))  # stdout, then stderr
        self.assertEqual(ar.sha256_file(log), receipt["log_sha256"])
        live = self.live_text(env)
        for line in ("gate unit | GATE-LIVE-MARKER-7f3", "gate unit | seen", "gate unit | stderr-line",
                     f"gate unit finished on {receipt['candidate'][:10]}: exit 0"):
            self.assertIn(line, live)
        self.assertEqual([], ctl.missing_gates(receipt["candidate"]))  # still a valid receipt for readiness

    def test_an_owner_amendment_from_the_session_reaches_both_roles_and_stale_results_never_satisfy_readiness(self):
        env = self.fg_env()
        mission = env.mission.read_bytes()
        enrollment = self.state(env)["enrollment_id"]
        head = env.commit("feature.txt", "v2\n", "feature v2")
        env.push()
        pending = self.doc(env, "owner-update-1.md", self.A1)  # saved as pending, outside the worktree
        with self.subTest("refused while a review command holds the writer lock"):
            before = self.state_bytes(env)
            with env.controller().lock("review"):
                with self.assertRaises(ar.UsageError):
                    self.resume(env.controller(), "apply owner update", amendment=pending)
            self.assertEqual(before, self.state_bytes(env))
            self.assertFalse((env.dir / "amendments").exists())
        with self.subTest("refused while a push/verify helper holds the helper lock"):
            before = self.state_bytes(env)
            with env.controller().helper_lock("verify"):
                with self.assertRaises(ar.UsageError):
                    self.resume(env.controller(), "apply owner update", amendment=pending)
            self.assertEqual(before, self.state_bytes(env))
        env.reviewer.script = [{"decision": "ready_for_owner_review"}]
        self.assertEqual("ready_for_owner_review", self.review_cmd(env)[1]["result"])
        self.assertEqual("AWAITING_OWNER_REVIEW", self.finalize_cmd(env)[1]["status"])
        before = self.state(env)
        old_ready, reviews = before["ready_review"], len(env.reviewer.calls)
        head = before["handoff"]["A"]  # the branch head at the handoff: source plus its archive commit
        # applied at the existing owner-review handoff of the same enrollment
        code, out = self.resume(env.controller(), "owner amends the task", amendment=pending)
        self.assertEqual(ar.EXIT_OK, code)
        self.assertEqual("ACTIVE (foreground: continue with `review --report`)", out["result"])
        task = out["effective_task"]
        data, rec = (env.dir / "amendments" / f"{task['amendments']['sha256']}.md").read_bytes(), \
            self.state(env)["amendments"]["revisions"][-1]
        self.assertEqual((1, rec["sha256"]), (task["amendments"]["revision"], task["amendments"]["sha256"]))
        self.assertEqual(data.decode("utf-8"), task["amendments"]["text"])
        self.assertEqual(head, git(env.origin, "rev-parse", f"refs/heads/{env.branch}"))  # unchanged source
        self.assertIn(self.A1, task["amendments"]["text"])
        self.assertEqual(before["mission"]["sha256"], task["mission_sha256"])  # the original mission is unchanged
        state = self.state(env)
        self.assertEqual((None, None, "develop", "ACTIVE"), (state["ready_review"], state["handoff"], state["phase"],
                                                             state["status"]))
        self.assertEqual(before["rounds_completed"], state["rounds_completed"])  # nothing refunded or charged
        self.assertEqual(reviews, len(env.reviewer.calls))  # no obsolete review was launched
        self.assertEqual(1, len(self.headings_with(env, "Workflow — reopened")))
        self.assertIsNone(env.controller().status()["amendments"]["selected"]["shown_in_foreground_session_at"])
        with self.subTest("an earlier ready result cannot satisfy the amended task"):
            stale = self.state(env)
            stale.update(ready_review=old_ready, phase="finalize", last_report_for=old_ready["H"])  # labeled tamper
            ar.atomic_write_json(env.dir / "state.json", stale)
            with self.assertRaises(ar.Stop) as stop:
                env.controller().finalize()
            self.assertIn("owner amendments changed", stop.exception.reason)
            restored = self.state(env)
            restored.update(status="ACTIVE", phase="develop")  # labeled: the stop above bypassed the command path
            ar.atomic_write_json(env.dir / "state.json", restored)
        with self.subTest("a report before the amended task was shown to the session is refused"):
            with self.assertRaises(ar.UsageError) as refused:
                self.review_cmd(env)
            self.assertIn("has not been verifiably displayed in this session", str(refused.exception))
            self.assertEqual(reviews, len(env.reviewer.calls))
        with contextlib.redirect_stdout(io.StringIO()) as shown:  # the read-only re-display path
            self.assertEqual(ar.EXIT_OK, ar.main(["status", "--enrollment", enrollment, "--instructions"], root=env.wf))
        self.assertEqual(task, json.loads(shown.getvalue())["effective_task"])
        env.developer.show(json.dumps(out))  # SIMULATED: the resume output reached the session's transcript
        self.assertTrue(env.controller().status()["amendments"]["selected"]["shown_in_foreground_session_at"])
        # a fresh report on the unchanged source is reviewed under the amended task
        env.reviewer.script += [{"decision": "ready_for_owner_review"}]
        code, out, _ = self.review_cmd(env, cite=task["amendments"]["report_citation"])
        self.assertEqual((ar.EXIT_OK, "ready_for_owner_review"), (code, out["result"]))
        changed = git(env.work, "diff", "--name-only", head, out["review"]["candidate"]).splitlines()
        self.assertTrue(all(p.startswith("docs/agent-reviews/pr-7/") for p in changed), changed)  # source unchanged
        self.assertEqual(1, out["review"]["amendment_revision"])
        call = env.reviewer.calls[-1]
        self.assertEqual((data, mission), (call["amendments"], call["mission"]))  # Codex got both, byte-exact
        state = self.state(env)
        self.assertEqual({"amendment_revision": 1, "amendment_sha256": rec["sha256"]}, state["last_report_amendments"])
        self.assertEqual("AWAITING_OWNER_REVIEW", self.finalize_cmd(env)[1]["status"])
        state = self.state(env)
        self.assertEqual((1, rec["sha256"]), (state["ready_review"]["amendment_revision"],
                                              state["ready_review"]["amendment_sha256"]))
        self.assertEqual({"final": 2}, state["rounds_completed"])
        self.assertEqual(2, len(self.headings_with(env, "Workflow — awaiting owner review")))
        self.assertTrue(env.controller().status(remote=True)["handoff_current"])

    def test_the_sessions_recorded_model_effort_and_permission_mode_are_verified(self):
        env = self.fg_env()
        states = sorted(p.name for p in (env.root / "state").iterdir())
        comments = len(env.gh.comments_list)
        good = dict(env.developer.foreground)
        for label, prov, expect in (
                ("permissions skipped", {**good, "permission_modes": ["default", "bypassPermissions"]},
                 "skip permission checks"),
                ("permission mode not recorded", {**good, "permission_modes": []}, "permission mode is not recorded"),
                ("another model", {**good, "models": [OPUS, "claude-sonnet-5-5"]}, "sonnet"),
                ("another effort", {**good, "efforts": ["high", "low"]}, "effort")):
            with self.subTest(label):
                env.developer.foreground = prov
                with self.assertRaises(ar.UsageError) as refused:  # before any claim, state or PR is touched
                    ar.enroll(env.args(), github=env.gh, root=env.wf, developer=env.developer)
                self.assertIn("foreground enrollment refused; nothing was created", str(refused.exception))
                self.assertIn(expect, str(refused.exception))
                self.assertEqual(states, sorted(p.name for p in (env.root / "state").iterdir()))
                self.assertEqual(comments, len(env.gh.comments_list))
                status = env.controller().status()["foreground_session"]
                self.assertTrue(any(expect in p for p in status["problems"]), status)
        env.developer.foreground = good
        status = env.controller().status()["foreground_session"]
        self.assertEqual(([], ["default"]), (status["problems"], status["permission_modes"]))
        self.assertIn("headless permission profile is not applied", status["permissions"])
        env.commit("feature.txt", "v2\n", "feature v2")
        env.push()
        env.developer.foreground = {**good, "permission_modes": ["bypassPermissions"]}
        code, out = None, None
        with contextlib.redirect_stdout(io.StringIO()) as stdout, contextlib.redirect_stderr(io.StringIO()):
            path = env.root / "report.json"
            path.write_text(json.dumps(report(env, "final")), encoding="utf-8")
            code = ar.review_command(env.controller(), str(path))
        self.assertEqual(ar.EXIT_BLOCKED, code)
        self.assertIn("skip permission checks", json.loads(stdout.getvalue())["reason"])
        self.assertEqual([], env.reviewer.calls)  # no review of work from an unverified session


def cli_tool_result(text, is_error=False, stamp=None, as_list=False):
    """One CLI-shaped transcript record: a main-thread user turn carrying one tool result (SIMULATED content)."""
    content = [{"type": "text", "text": text}] if as_list else text
    return json.dumps({"type": "user", "isSidechain": False, "timestamp": stamp or ar.now_iso(),
                       "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_sim",
                                                                "is_error": is_error, "content": content}]}})


def cli_assistant(message_id, model="claude-opus-5-5", effort="high"):
    record = {"type": "assistant", "isSidechain": False, "timestamp": ar.now_iso(),
              "message": {"id": message_id, "model": model, "content": [{"type": "text", "text": "simulated"}]}}
    if effort is not None:
        record.update(effort=effort, perTurnEffort=effort)
    return json.dumps(record)


GATE_PIPE_SCRIPT = """import subprocess, sys
child = 'import sys, time; time.sleep(float(sys.argv[1])); print("CHILD-MARKER-" + "2b9", flush=True)'
subprocess.Popen([sys.executable, '-c', child, sys.argv[1]], stdout=sys.stdout, stderr=sys.stderr)
print('launcher exits', flush=True)
"""

GATE_RESTORE_SCRIPT = """import pathlib, sys, time
root = pathlib.Path(sys.argv[1]).parent
lock = root / 'runtime.lock'
lock.write_text('restoring', encoding='utf-8')
print('restoration started', flush=True)
time.sleep(5)
(root / 'restored.txt').write_text('done', encoding='utf-8')
lock.unlink()
print('restoration finished', flush=True)
time.sleep(60)
"""

GATE_KEY_SCRIPT = """import sys
begin, end = '-----' + 'BEGIN RSA ' + 'PRIVATE KEY-----', '-----' + 'END RSA ' + 'PRIVATE KEY-----'
body = ['QkxPQ0stQk9EWS1MSU5FLU9ORS1zaW11bGF0ZWQtbm90LWEta2V5LTAwMDAwMDAw',
        'QkxPQ0stQk9EWS1MSU5FLVRXTy1zaW11bGF0ZWQtbm90LWEta2V5LTExMTExMTEx']
print('ordinary progress before', flush=True)
for line in [begin] + body + [end]:
    print(line, flush=True)
print('ordinary progress after', flush=True)
print('stderr ordinary line', file=sys.stderr, flush=True)
for line in [begin] + body + [end]:
    print(line, file=sys.stderr, flush=True)
"""
KEY_BODY = ("QkxPQ0stQk9EWS1MSU5FLU9ORS1zaW11bGF0ZWQtbm90LWEta2V5LTAwMDAwMDAw",
            "QkxPQ0stQk9EWS1MSU5FLVRXTy1zaW11bGF0ZWQtbm90LWEta2V5LTExMTExMTEx")


class ForegroundCorrectionTests(ForegroundFixture, Base):
    """Round-1 corrections (PR #7): content-verified amendment delivery and report binding, enrolled-caller checks,
    the round cap after an amendment, per-turn session provenance, the accepted review on stopped and recovered paths,
    complete and protected gate capture, streamed credential redaction, the interactive enrollment default, the
    read-only watch command, project push routes and unreadable transcripts. Real Git/state/lock/archive fixtures;
    Claude, Codex and GitHub simulated unless a test uses the production transcript reader on CLI-shaped records."""

    def amended(self, env, name="u1.md"):
        """A foreground amendment applied by the enrolled session at ACTIVE develop; returns the resume output."""
        code, out = self.resume(env.controller(), "owner amends the task", amendment=self.doc(env, name, self.A1))
        self.assertEqual(ar.EXIT_OK, code, out)
        return out

    def test_delivery_requires_the_complete_amendment_in_one_successful_tool_result(self):
        env = self.fg_env()
        enrollment = self.state(env)["enrollment_id"]
        env.commit("feature.txt", "v2\n", "feature v2")
        env.push()
        out = self.amended(env)
        full = json.dumps(out, indent=2)  # exactly what the command printed on stdout
        rec = self.state(env)["amendments"]["revisions"][-1]
        with contextlib.redirect_stdout(io.StringIO()) as ordinary:
            ar.main(["status", "--enrollment", enrollment], root=env.wf)
        self.assertIn(rec["sha256"], ordinary.getvalue())  # status names the digest ...
        reader, transcript = self.real_reader(env)
        ctl = env.controller()
        ctl._developer = reader  # the production transcript reader, over CLI-shaped records
        refusal = ctl.foreground_amendments_binding(report(env, "final"))[1]
        self.assertIn(rec["sha256"], refusal)  # ... and so does the refusal
        cut = full[:full.index('"text"') + 200]
        transcript.write_text("\n".join([cli_tool_result(ordinary.getvalue()), cli_tool_result(refusal, is_error=True),
                                         cli_tool_result(cut), cli_tool_result(full, is_error=True)]) + "\n",
                              encoding="utf-8")
        self.assertEqual((None, None), ctl.foreground_delivery(ctl.guidance_record("amendments")))
        self.assertIsNone(ctl.status()["amendments"]["selected"]["shown_in_foreground_session_at"])
        self.assertIn("not been verifiably displayed", ctl.foreground_amendments_binding(report(env, "final"))[1])
        with open(transcript, "a", encoding="utf-8") as f:  # the complete, successful display (list-shaped content)
            f.write(cli_tool_result(full, as_list=True) + "\n")
        shown, problem = ctl.foreground_delivery(ctl.guidance_record("amendments"))
        self.assertTrue(shown)
        self.assertIsNone(problem)
        self.assertEqual(shown, ctl.status()["amendments"]["selected"]["shown_in_foreground_session_at"])
        cited = dict(report(env, "final"), evidence_refs=[out["effective_task"]["amendments"]["report_citation"]])
        self.assertEqual(((1, rec["sha256"]), None), ctl.foreground_amendments_binding(cited))

    def test_a_report_prepared_before_an_amendment_cannot_be_relabeled(self):
        env = self.fg_env()
        env.commit("feature.txt", "v2\n", "feature v2")
        env.push()
        env.reviewer.script = [{"decision": "ready_for_owner_review"}, {"decision": "ready_for_owner_review"}]
        self.assertEqual("ready_for_owner_review", self.review_cmd(env)[1]["result"])  # accepted on H
        old_report = self.last_report_path
        self.assertEqual("finalize", self.state(env)["phase"])
        out = self.amended(env)  # before finalization, by the enrolled session
        env.developer.show(json.dumps(out, indent=2))  # SIMULATED: the full update reached the session
        posted, reviews = len(env.gh.comments_list), len(env.reviewer.calls)
        with self.assertRaises(ar.UsageError) as refused:
            self.review_cmd(env, path=old_report)  # the same file, unchanged
        self.assertIn("cannot be reused", str(refused.exception))
        self.assertEqual((posted, reviews), (len(env.gh.comments_list), len(env.reviewer.calls)))
        code, result, _ = self.review_cmd(env, cite=out["effective_task"]["amendments"]["report_citation"])
        self.assertEqual((ar.EXIT_OK, "ready_for_owner_review"), (code, result["result"]))
        self.assertEqual(1, self.state(env)["last_report_amendments"]["amendment_revision"])

    def test_foreground_task_changes_and_new_review_attempts_need_the_enrolled_session(self):
        env = self.fg_env()
        env.commit("feature.txt", "v2\n", "feature v2")
        env.push()
        pending = self.doc(env, "u1.md", self.A1)
        for caller in ("another-session", None):
            with self.subTest(caller=caller):
                before = self.state_bytes(env)
                if caller:
                    os.environ["CLAUDE_CODE_SESSION_ID"] = caller
                else:
                    os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
                try:
                    with self.assertRaises(ar.UsageError) as refused:
                        self.resume(env.controller(), "from another terminal", amendment=pending)
                finally:
                    os.environ["CLAUDE_CODE_SESSION_ID"] = FOREGROUND_SESSION
                self.assertIn("only its enrolled Claude session", str(refused.exception))
                self.assertEqual(before, self.state_bytes(env))
                self.assertFalse((env.dir / "amendments").exists())
        ctl = env.controller()  # labeled setup: an accepted report, review phase, no attempt launched yet
        self.assertIsNone(ctl.accept_report(report(env, "final")))
        ctl.transition("review", "simulated: review requested, not yet launched")
        env.reviewer.script = [{"decision": "ready_for_owner_review"}]
        os.environ["CLAUDE_CODE_SESSION_ID"] = "another-session"
        try:
            with self.assertRaises(ar.UsageError) as refused:
                self.review_cmd(env)
        finally:
            os.environ["CLAUDE_CODE_SESSION_ID"] = FOREGROUND_SESSION
        self.assertIn("only the enrolled foreground session", str(refused.exception))
        self.assertEqual(([], []), (env.reviewer.calls, self.state(env)["rounds"]))
        code, out, _ = self.review_cmd(env)  # the enrolled session launches it
        self.assertEqual((ar.EXIT_OK, "ready_for_owner_review"), (code, out["result"]))
        self.amended(env)  # the enrolled session may also apply an amendment between its commands

    def test_an_amendment_after_the_last_round_stays_blocked_until_an_owner_extension(self):
        env = Env("foreground", max_rounds=1, plan={"schema_version": "agent-review.plan.v1", "mission_id": "f",
                                                    "title": "f", "checkpoints": [{"id": "final", "type": "final",
                                                                                   "scope": "s", "exit_conditions": ["e"]}]})
        self.addCleanup(env.cleanup)
        env.commit("feature.txt", "v2\n", "feature v2")
        env.push()
        env.reviewer.script = [{"decision": "changes_required", "findings": [finding("R1-F1")],
                                "override": {"decision_rationale": self.CONTINUATION}}]
        code, out, _ = self.review_cmd(env)
        self.assertEqual(ar.EXIT_BLOCKED, code)  # accepted and charged at the cap, then stopped
        self.assertIn("review-round cap reached", out["reason"])
        self.assertEqual((1, "changes_required", self.CONTINUATION, True),
                         (out["review"]["round"], out["review"]["decision"], out["review"]["continuation"],
                          out["review"]["accepted_in_this_command"]))
        self.assertIn("owner decision is needed", out["review"]["next"])
        self.assertEqual({"final": 1}, self.state(env)["rounds_completed"])
        code, out = self.resume(env.controller(), "owner amends at the cap", amendment=self.doc(env, "u1.md", self.A1))
        self.assertEqual(ar.EXIT_BLOCKED, code)
        self.assertIn("budget for final is exhausted (1/1); the owner amendment is applied", out["reason"])
        self.assertNotIn("effective_task", out)  # applied, not delivered
        state = self.state(env)
        self.assertEqual(("BLOCKED", "develop", {"final": 1}, 1, 1),
                         (state["status"], state["phase"], state["rounds_completed"],
                          state["limits"]["max_review_rounds_per_checkpoint"], state["amendments"]["current"]))
        self.assertTrue(any("helpers act only during development" in p
                            for p in env.controller().helper_authority_problems()))
        code, out = self.resume(env.controller(), "owner extends the budget", max_rounds=2)  # separate authorization
        self.assertEqual(ar.EXIT_OK, code)
        self.assertEqual(("ACTIVE", 2), (self.state(env)["status"],
                                         self.state(env)["limits"]["max_review_rounds_per_checkpoint"]))
        self.assertEqual([], env.controller().helper_authority_problems())

    def test_the_accepted_review_is_returned_on_a_reviewer_blocker_and_on_publication_recovery(self):
        with self.subTest("an accepted reviewer blocker"):
            env = self.fg_env()
            env.commit("feature.txt", "v2\n", "feature v2")
            env.push()
            env.reviewer.script = [{"decision": "blocked", "override": {"decision_rationale": "BLOCKER-CONTINUATION"}}]
            code, out, _ = self.review_cmd(env)
            self.assertEqual(ar.EXIT_BLOCKED, code, out)
            self.assertEqual(("blocked", "BLOCKER-CONTINUATION", {"final": 1}),
                             (out["review"]["decision"], out["review"]["continuation"],
                              self.state(env)["rounds_completed"]))
        with self.subTest("publication recovered by the owner's resume"):
            env = self.fg_env()
            env.commit("feature.txt", "v2\n", "feature v2")
            env.push()
            env.reviewer.script = [{"decision": "changes_required", "findings": [finding("R1-F1")],
                                    "override": {"decision_rationale": self.CONTINUATION}}]
            original = env.gh.post_comment
            calls = {"n": 0}

            def flaky(number, body_file):
                calls["n"] += 1
                if "Codex GPT-6.2 Astra — review" in Path(body_file).read_text(encoding="utf-8") and calls["n"] < 50:
                    raise ar.NotDelivered("simulated transient GitHub failure (request rejected; nothing stored)")
                return original(number, body_file)
            env.gh.post_comment = flaky
            code, out, _ = self.review_cmd(env)
            self.assertEqual(ar.EXIT_PAUSED, code, out)
            self.assertIsNone(out["review"])  # nothing was accepted: no earlier verdict is presented as current
            self.assertEqual("validated", self.state(env)["rounds"][-1]["status"])
            calls["n"] = 100  # the outage is over
            code, out = self.resume(env.controller(), "GitHub is back")
            self.assertEqual(ar.EXIT_OK, code, out)
            rnd = self.state(env)["rounds"][-1]
            envelope = json.loads(Path(rnd["envelope_path"]).read_text(encoding="utf-8"))
            self.assertEqual((1, envelope["result"]["decision_rationale"], [p["url"] for p in rnd["published"]]),
                             (out["review"]["round"], out["review"]["continuation"], out["review"]["review_reference"]))
            self.assertEqual({"final": 1}, self.state(env)["rounds_completed"])  # charged once
            self.assertEqual(1, len(env.reviewer.calls))  # never reviewed again

    def test_gate_capture_waits_for_descendants_within_the_deadline(self):
        for label, delay, minutes, passed in (("complete within the deadline", 1.5, 0.5, True),
                                              ("deadline expires first", 6, 0.05, False)):
            with self.subTest(label):
                env = self.fg_env(gates={"unit": {"argv": [sys.executable, "-u", "{repo_root}/../gate_pipe.py",
                                                           str(delay)], "timeout_minutes": minutes}},
                                  required_gates=["unit"])
                (env.root / "gate_pipe.py").write_text(GATE_PIPE_SCRIPT, encoding="utf-8")
                receipt = env.controller().run_gate("unit")
                log = (env.dir / "evidence" / receipt["log"]).read_text(encoding="utf-8")
                self.assertEqual(passed, receipt["passed"], receipt)
                if passed:
                    self.assertEqual((0, "launcher exits\nCHILD-MARKER-2b9\n"), (receipt["exit_code"], log))
                else:
                    self.assertEqual((None, f"timed out after {minutes * 60}s"), (receipt["exit_code"], log))
                if not passed:
                    time.sleep(delay)  # let the detached child finish before the fixture is removed

    def test_a_gate_timeout_never_interrupts_a_protected_restoration(self):
        env = self.fg_env(gates={"unit": {"argv": [sys.executable, "-u", "{repo_root}/../gate_restore.py", "{repo_root}"],
                                          "timeout_minutes": 0.03}}, required_gates=["unit"])
        (env.root / "gate_restore.py").write_text(GATE_RESTORE_SCRIPT, encoding="utf-8")
        started = time.monotonic()
        receipt = env.controller().run_gate("unit")
        self.assertEqual((None, False), (receipt["exit_code"], receipt["passed"]))  # nonpassing
        self.assertTrue((env.root / "restored.txt").is_file())  # the restoration reached its safe boundary
        self.assertFalse((env.root / "runtime.lock").exists())
        self.assertGreaterEqual(time.monotonic() - started, 5)
        self.assertLess(time.monotonic() - started, 50)  # then the gate itself was terminated

    def test_streamed_gate_output_never_shows_a_multiline_key_body(self):
        env = self.fg_env(gates={"unit": {"argv": [sys.executable, "-u", "{repo_root}/../gate_key.py"],
                                          "timeout_minutes": 1}}, required_gates=["unit"])
        (env.root / "gate_key.py").write_text(GATE_KEY_SCRIPT, encoding="utf-8")
        ctl = env.controller()
        ctl._live = ar.LiveLog(ctl.live_path, echo=True)  # as in an interactive terminal
        with contextlib.redirect_stderr(io.StringIO()) as echoed:
            receipt = ctl.run_gate("unit")
        live = self.live_text(env)
        log = (ctl.dir / "evidence" / receipt["log"]).read_text(encoding="utf-8")
        for text in (live, echoed.getvalue(), log):
            for body in KEY_BODY:
                self.assertNotIn(body, text)
        for line in ("ordinary progress before", "ordinary progress after", "stderr ordinary line"):
            self.assertIn(f"gate unit | {line}", live)
            self.assertIn(line, echoed.getvalue())
        self.assertEqual(2, live.count("gate unit | [REDACTED-CREDENTIAL]"))  # one placeholder per stream

    def test_the_sessions_turns_and_modes_are_checked_with_the_production_parser(self):
        env = self.fg_env()
        reader, transcript = self.real_reader(env)
        mode = lambda value: json.dumps({"type": "permission-mode", "permissionMode": value, "sessionId": "s"})  # noqa
        cases = (("valid multi-record turns", [cli_assistant("m1"), cli_assistant("m1"), cli_assistant("m2"),
                                               cli_assistant("s1", model="<synthetic>", effort=None), mode("auto")], None),
                 ("a turn without effort", [cli_assistant("m1"), cli_assistant("m2", effort=None), mode("default")],
                  "lack a recorded model or effort"),
                 ("a turn without model", [cli_assistant("m1"), cli_assistant("m2", model=None), mode("default")],
                  "lack a recorded model or effort"),
                 ("an empty mode", [cli_assistant("m1"), mode("")], "unidentifiable permission mode"),
                 ("bypass", [cli_assistant("m1"), mode("bypassPermissions")], "skip permission checks"))
        for label, records, expect in cases:
            with self.subTest(label):
                transcript.write_text("\n".join(records) + "\n", encoding="utf-8")
                problems = ar.foreground_session_problems(reader.session_provenance(FOREGROUND_SESSION),
                                                          env.controller().cfg["developer"])
                if expect is None:
                    self.assertEqual([], problems)
                    continue
                self.assertTrue(any(expect in p for p in problems), problems)
                with self.assertRaises(ar.UsageError) as refused:  # enrollment: refused before anything is created
                    ar.enroll(env.args(), github=env.gh, root=env.wf, developer=reader)
                self.assertIn(expect, str(refused.exception))
                ctl = env.controller()
                ctl._developer = reader
                with self.assertRaises(ar.Stop) as stop:  # report admission
                    ctl.accept_report(report(env, "final"))
                self.assertIn(expect, stop.exception.reason)

    def test_an_omitted_mode_selects_foreground_only_in_an_interactive_session(self):
        args = ar.build_parser().parse_args(["enroll", "--project", "p", "--worktree", "w", "--plan", "single",
                                             "--mission", "m"])
        self.assertIsNone(args.mode)
        self.assertEqual("headless", ar.resolve_enroll_mode("headless"))
        env = self.fg_env()
        states = sorted(p.name for p in (env.root / "state").iterdir())
        os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
        try:
            with self.assertRaises(ar.UsageError) as refused:
                ar.enroll(env.args(mode=None), github=env.gh, root=env.wf, developer=env.developer)
            self.assertIn("pass --mode headless explicitly", str(refused.exception))
            with contextlib.redirect_stderr(io.StringIO()) as err:  # the real CLI path: refused, no network used
                self.assertEqual(ar.EXIT_USAGE, ar.main(["enroll", "--project", "development-process", "--worktree",
                                                         str(env.work), "--plan", "single", "--mission",
                                                         str(env.mission)], root=env.wf))
            self.assertIn("--mode was omitted", err.getvalue())
        finally:
            os.environ["CLAUDE_CODE_SESSION_ID"] = FOREGROUND_SESSION
        self.assertEqual(states, sorted(p.name for p in (env.root / "state").iterdir()))
        ctl = env.controller()
        ctl.verify_inputs()
        self.assertEqual("CANCELLED", ctl.cancel("re-enroll with the mode omitted"))
        folder, state = ar.enroll(env.args(mode=None), github=env.gh, root=env.wf, developer=env.developer)
        self.assertEqual(("foreground", FOREGROUND_SESSION), (state["mode"], state["foreground_session"]))

    def test_watch_shows_a_headless_jobs_activity_and_stalls_read_only(self):
        env = Env("headless")
        self.addCleanup(env.cleanup)
        state = self.state(env)  # labeled: a running headless invocation recorded by the controller
        state["developer"].update(invocations=1, launch={"n": 1, "at": ar.now_iso(), "returned": False})
        ar.atomic_write_json(env.dir / "state.json", state)
        stream = env.dir / "developer" / "stream-001.jsonl"
        stream.parent.mkdir(parents=True, exist_ok=True)
        stream.write_text("\n".join(json.dumps(e) for e in (  # SIMULATED stream-json events
            {"type": "assistant", "message": {"content": [{"type": "thinking", "thinking": "PRIVATE-THOUGHT"}]}},
            {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash",
                                                           "input": {"command": "python -m unittest -v"}}]}},
            {"type": "user", "message": {"content": [{"type": "tool_result", "content": "Ran 3 tests OK"}]}},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "Tests pass; committing."}]}})) + "\n",
            encoding="utf-8")
        before = self.state_bytes(env)
        rows = []
        ar.watch_enrollment(env.dir, rows.append, once=True)
        text = "\n".join(rows)
        self.assertIn("Claude ▸ Bash: python -m unittest -v", text)
        self.assertIn("↳ Ran 3 tests OK", text)
        self.assertNotIn("PRIVATE-THOUGHT", text)
        head = git(env.work, "rev-parse", "HEAD")[:12]
        self.assertIn(f"ACTIVE/develop | developer Claude, invocation 1 for", text)
        self.assertIn(f"candidate {head}", text)
        self.assertIn("latest action: Claude: Tests pass; committing.", text)
        later = lambda: ar.dt.datetime.now(ar.dt.timezone.utc) + ar.dt.timedelta(minutes=30)  # noqa: E731
        rows = []
        ar.watch_enrollment(env.dir, rows.append, once=True, stall_minutes=10, now=later)
        self.assertTrue(any("no new agent events for" in r and "not proof of progress" in r for r in rows), rows)
        self.assertEqual(before, self.state_bytes(env))  # read-only

    def test_correction_instructions_name_the_projects_push_route(self):
        for label, cfg, expect in (("repository wrapper", {}, "repository push wrapper"),
                                   ("built-in helper", {"push_command": None}, "push --enrollment")):
            with self.subTest(label):
                env = self.fg_env(**cfg)
                env.commit("feature.txt", "v2\n", "feature v2")
                env.push()
                env.reviewer.script = [{"decision": "changes_required", "findings": [finding("R1-F1")]}]
                self.assertIn(expect, self.review_cmd(env)[1]["review"]["next"])

    def test_an_unreadable_transcript_is_reported_and_keeps_admission_closed(self):
        env = self.fg_env()
        env.commit("feature.txt", "v2\n", "feature v2")
        env.push()
        env.reviewer.script = [{"decision": "ready_for_owner_review"}]
        self.review_cmd(env)
        self.finalize_cmd(env)
        out = self.amended(env)
        env.developer.show(json.dumps(out, indent=2))
        env.developer.transcript_error = PermissionError(13, "simulated unreadable transcript")
        status = env.controller().status(remote=True)  # parseable, with the problem stated
        selected = status["amendments"]["selected"]
        self.assertIsNone(selected["shown_in_foreground_session_at"])
        self.assertIn("could not be read", selected["foreground_delivery_problem"])
        json.dumps(status)
        with self.assertRaises(ar.UsageError) as refused:
            self.review_cmd(env, cite=out["effective_task"]["amendments"]["report_citation"])
        self.assertIn("could not be read", str(refused.exception))


class SimulatedCrash(BaseException):
    """SIMULATED abrupt controller exit (not caught by the command path)."""


def fake_token():
    return "gh" + "p_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9"  # assembled at run time; key-shaped, not a key


def key_block(body_lines=8):
    begin, end = "-----" + "BEGIN RSA " + "PRIVATE KEY-----", "-----" + "END RSA " + "PRIVATE KEY-----"
    body = [("SIMULATEDKEYBODY%02d" % i) + "Q" * 44 for i in range(body_lines)]
    return "\n".join([begin, *body, end]), body


class ForegroundRoundTwoTests(ForegroundFixture, Base):
    """Round-2 corrections (PR #7): the accepted-round baseline before any guard, foreground reviewer launches only by
    the enrolled session (also on recovery), the round-cap block persisted with the amendment, transcript records split
    on their physical delimiter, positive gate EOF, a sanitized and identity-checked `watch` that reports the current
    role's activity and never writes into what it observes, part-wise delivery of a long amendment, and status
    without a resolvable Claude executable."""

    def flaky_verdict_posts(self, env):
        """SIMULATED GitHub outage for verdict comments only, until `.on = False`."""
        original, gate = env.gh.post_comment, type("Gate", (), {"on": True})()

        def post(number, body_file):
            if gate.on and "Codex GPT-6.2 Astra — review" in Path(body_file).read_text(encoding="utf-8"):
                raise ar.NotDelivered("simulated transient GitHub failure (request rejected; nothing stored)")
            return original(number, body_file)
        env.gh.post_comment = post
        return gate

    def preserved_result(self, env):
        """A validated, unpublished review result preserved after a publication outage (PAUSED)."""
        env.commit("feature.txt", "v2\n", "feature v2")
        env.push()
        env.reviewer.script = [{"decision": "changes_required", "findings": [finding("R1-F1")],
                                "override": {"decision_rationale": self.CONTINUATION}}]
        gate = self.flaky_verdict_posts(env)
        code, out, _ = self.review_cmd(env)
        self.assertEqual(ar.EXIT_PAUSED, code, out)
        self.assertEqual("validated", self.state(env)["rounds"][-1]["status"])
        gate.on = False
        return gate

    def test_an_early_stop_never_presents_an_earlier_round_as_newly_accepted(self):
        env = self.fg_env()
        env.commit("feature.txt", "v2\n", "feature v2")
        env.push()
        env.reviewer.script = [{"decision": "changes_required", "findings": [finding("R1-F1")],
                                "override": {"decision_rationale": self.CONTINUATION}}]
        self.assertEqual("changes_required", self.review_cmd(env)[1]["result"])
        accepted_lines = self.live_text(env).count("review round 1 accepted")
        ar.write_text(env.dir / "STOP", "owner stop (simulated)\n")
        code, out, _ = self.review_cmd(env, dispositions=[fixed("R1-F1", git(env.work, "rev-parse", "HEAD"))])
        self.assertEqual(ar.EXIT_PAUSED, code)
        self.assertIn("stop requested", out["reason"])
        self.assertIsNone(out["review"])  # round 1 is history, not this command's result
        self.assertIn("no review round was accepted", out["review_note"])
        self.assertEqual(accepted_lines, self.live_text(env).count("review round 1 accepted"))
        self.assertEqual({"final": 1}, self.state(env)["rounds_completed"])
        (env.dir / "STOP").unlink()
        mission = env.mission.read_bytes()  # labeled: a pre-callback failure on resume (the mission file changed)
        env.mission.write_bytes(mission + b"\nunreviewed edit\n")
        try:
            code, out = self.resume(env.controller(), "resume after the stop")
        finally:
            env.mission.write_bytes(mission)
        self.assertEqual(ar.EXIT_BLOCKED, code, out)
        self.assertIsNone(out["review"])
        self.assertEqual({"final": 1}, self.state(env)["rounds_completed"])

    def test_recovery_publishes_an_intact_result_but_never_launches_a_replacement_from_another_session(self):
        for label, tamper in (("intact preserved result", False), ("invalidated preserved result", True)):
            with self.subTest(label):
                env = self.fg_env()
                self.preserved_result(env)
                if tamper:  # labeled: the private envelope no longer matches its recorded digest
                    path = Path(self.state(env)["rounds"][-1]["envelope_path"])
                    path.write_bytes(path.read_bytes() + b" ")
                for caller in ("another-session", None):
                    if caller:
                        os.environ["CLAUDE_CODE_SESSION_ID"] = caller
                    else:
                        os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
                    try:
                        if tamper:
                            with self.assertRaises(ar.UsageError) as refused:
                                self.resume(env.controller(), "owner recovery from another terminal")
                            self.assertIn("No reviewer was launched", str(refused.exception))
                        else:
                            code, out = self.resume(env.controller(), "owner recovery from another terminal")
                            self.assertEqual(ar.EXIT_OK, code, out)
                            self.assertEqual((1, self.CONTINUATION), (out["review"]["round"],
                                                                     out["review"]["continuation"]))
                            break  # recovered once; nothing left to recover
                    finally:
                        os.environ["CLAUDE_CODE_SESSION_ID"] = FOREGROUND_SESSION
                self.assertEqual(1, len(env.reviewer.calls))  # never a replacement from another session
                if tamper:
                    self.assertEqual({}, self.state(env)["rounds_completed"])
                    self.assertEqual("invalidated", self.state(env)["rounds"][0]["status"])
                    env.reviewer.script = [{"decision": "ready_for_owner_review"}]
                    code, out, _ = self.review_cmd(env)  # the enrolled session launches the replacement
                    self.assertEqual((ar.EXIT_OK, "ready_for_owner_review"), (code, out["result"]))
                    self.assertEqual(2, len(env.reviewer.calls))
                else:
                    self.assertEqual({"final": 1}, self.state(env)["rounds_completed"])

    def test_the_round_cap_block_is_saved_with_the_amendment_even_if_the_controller_exits(self):
        env = Env("foreground", max_rounds=1, plan={"schema_version": "agent-review.plan.v1", "mission_id": "f",
                                                    "title": "f", "checkpoints": [{"id": "final", "type": "final",
                                                                                   "scope": "s", "exit_conditions": ["e"]}]})
        self.addCleanup(env.cleanup)
        env.commit("feature.txt", "v2\n", "feature v2")
        env.push()
        env.reviewer.script = [{"decision": "ready_for_owner_review"}]
        self.assertEqual("ready_for_owner_review", self.review_cmd(env)[1]["result"])
        self.assertEqual("AWAITING_OWNER_REVIEW", self.finalize_cmd(env)[1]["status"])
        ctl = env.controller()

        def crash():
            raise SimulatedCrash()
        ctl._continue_after_resume = crash  # SIMULATED: the controller exits right after the amendment's state save
        with self.assertRaises(SimulatedCrash):
            self.resume(ctl, "owner amends at the cap", amendment=self.doc(env, "u1.md", self.A1))
        state = self.state(env)  # reloaded from disk
        self.assertEqual(("BLOCKED", "develop", {"final": 1}, 1, None, None),
                         (state["status"], state["phase"], state["rounds_completed"], state["amendments"]["current"],
                          state["ready_review"], state["handoff"]))
        self.assertIn("budget for final is exhausted", state["status_reason"])
        self.assertTrue(any("helpers act only during development" in p
                            for p in env.controller().helper_authority_problems()))
        with self.assertRaises(ar.UsageError):  # report admission is closed
            self.review_cmd(env)
        code, out = self.resume(env.controller(), "owner extends the budget", max_rounds=2)  # separately authorized
        self.assertEqual(ar.EXIT_OK, code, out)
        self.assertEqual("ACTIVE", self.state(env)["status"])
        self.assertTrue(self.headings_with(env, "Workflow — blocked"))  # the queued notice was sent on recovery

    def test_transcript_records_are_split_only_on_their_physical_delimiter(self):
        env = self.fg_env()
        reader, transcript = self.real_reader(env)
        hidden = cli_assistant("m2", effort=None).replace('"simulated"', '"text with a ' + " " + ' separator"')
        hidden = hidden.replace("\\u2028", " ")  # the record holds a literal U+2028 inside a JSON string
        self.assertIn(" ", hidden)
        cases = (("a separator-bearing turn without effort", [cli_assistant("m1"), hidden], "lack a recorded model"),
                 ("an unreadable completed record", [cli_assistant("m1"), '{"type": "assistant", "message": {'],
                  "could not be read"),
                 ("a synthetic message with another effort", [cli_assistant("m1"),
                                                              cli_assistant("s1", model="<synthetic>", effort="low")],
                  None))
        mode = json.dumps({"type": "permission-mode", "permissionMode": "auto"})
        for label, records, expect in cases:
            with self.subTest(label):
                data = "\n".join(records + [mode]) + "\n" + '{"type": "assistant", "message": {"id": "in-progress"'
                transcript.write_bytes(data.encode("utf-8"))  # the final record is still being written
                prov = reader.session_provenance(FOREGROUND_SESSION)
                problems = ar.foreground_session_problems(prov, env.controller().cfg["developer"])
                if expect is None:
                    self.assertEqual(([], ["high"]), (problems, prov["efforts"]))
                    continue
                self.assertTrue(any(expect in p for p in problems), problems)
                with self.assertRaises(ar.UsageError) as refused:
                    ar.enroll(env.args(), github=env.gh, root=env.wf, developer=reader)
                self.assertIn(expect, str(refused.exception))
                ctl = env.controller()
                ctl._developer = reader
                with self.assertRaises(ar.Stop) as stop:
                    ctl.accept_report(report(env, "final"))
                self.assertIn(expect, stop.exception.reason)

    def test_a_failing_progress_display_never_cuts_the_gate_evidence(self):
        env = self.fg_env(gates={"unit": {"argv": [sys.executable, "-u", "-c",
                                                   "print('line one'); print('line two'); print('line three')"],
                                          "timeout_minutes": 1}}, required_gates=["unit"])
        ctl = env.controller()

        class BrokenDisplay(ar.LiveLog):
            def line(self, text):
                if "gate unit |" in text:
                    raise RuntimeError("SIMULATED display failure")
                super().line(text)
        ctl._live = BrokenDisplay(ctl.live_path)
        receipt = ctl.run_gate("unit")
        self.assertEqual((0, True), (receipt["exit_code"], receipt["passed"]))
        self.assertEqual("line one\nline two\nline three\n",
                         (ctl.dir / "evidence" / receipt["log"]).read_text(encoding="utf-8"))

    def test_watch_sanitizes_whole_events_and_reports_the_current_roles_activity(self):
        env = Env("headless", plan={"schema_version": "agent-review.plan.v1", "mission_id": "f", "title": "f",
                                    "checkpoints": [{"id": "phase-1", "type": "intermediate", "scope": "s",
                                                     "exit_conditions": ["e"]},
                                                    {"id": "final", "type": "final", "scope": "s",
                                                     "exit_conditions": ["e"]}]})
        self.addCleanup(env.cleanup)
        block, body = key_block(10)  # longer than any excerpt limit
        token = fake_token()
        state = self.state(env)  # labeled: a correction in progress after an earlier review of phase-1
        state.update(checkpoint_index=1, rounds_completed={"phase-1": 3, "final": 1})
        state["developer"].update(invocations=2, launch={"n": 2, "at": ar.now_iso(), "returned": False})
        state["rounds"] = [{"round": 4, "status": "accepted", "decision": "changes_required", "H": "0" * 40,
                            "attempts": [{"n": 1, "started": ar.now_iso(), "ended": ar.now_iso()}]}]
        ar.atomic_write_json(env.dir / "state.json", state)
        events = env.dir / "rounds" / "r04" / "events-1.jsonl"
        events.parent.mkdir(parents=True)
        events.write_text(json.dumps({"type": "item.completed", "item": {"type": "agent_message",
                                                                         "text": f"old review note {token}"}}) + "\n",
                          encoding="utf-8")
        old = time.time() - 3600
        os.utime(events, (old, old))  # the reviewer finished an hour ago
        stream = env.dir / "developer" / "stream-002.jsonl"
        stream.parent.mkdir(parents=True, exist_ok=True)
        stream.write_text("\n".join(json.dumps(e) for e in (
            {"type": "user", "message": {"content": [{"type": "tool_result", "content": "key dump:\n" + block}]}},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": f"pushing now {token}"}]}})) + "\n",
            encoding="utf-8")
        pending = env.dir / "evidence" / "gate-unit-x.pending"  # a marker whose helper is gone
        pending.parent.mkdir(parents=True, exist_ok=True)
        ar.write_text(pending, json.dumps({"gate": "unit", "candidate": "1" * 40, "started": ar.now_iso(),
                                           "pid": 999999}) + "\n")
        with contextlib.redirect_stdout(io.StringIO()) as shown:
            self.assertEqual(ar.EXIT_OK, ar.main(["watch", "--enrollment", self.state(env)["enrollment_id"], "--once"],
                                                 root=env.wf))
        for text in (shown.getvalue(),):
            self.assertNotIn(token, text)
            for line in body:
                self.assertNotIn(line, text)
            self.assertIn("key dump:", text)  # ordinary activity stays readable
            self.assertIn("(earlier) Claude: pushing now [REDACTED-CREDENTIAL]", text)
        status = [r for r in shown.getvalue().splitlines() if "| developer Claude, invocation 2" in r][-1]
        self.assertIn("latest action: Claude: pushing now [REDACTED-CREDENTIAL]", status)  # the current role's action
        self.assertIn("final rounds 1/", status)  # the current checkpoint, not a sum across checkpoints
        self.assertIn("has no receipt and its helper is not running (interrupted)", status)
        self.assertNotIn("old review note", status)

    def test_a_long_amendment_is_delivered_in_parts_and_a_missing_part_keeps_admission_closed(self):
        env = self.fg_env()
        enrollment = self.state(env)["enrollment_id"]
        env.commit("feature.txt", "v2\n", "feature v2")
        env.push()
        text = "".join(f"Owner amendment line {i:05d} (simulated long update).\n" for i in range(450))  # ~22 KB
        code, out = self.resume(env.controller(), "a long owner update", amendment=self.doc(env, "long.md", text))
        self.assertEqual(ar.EXIT_OK, code)
        task = out["effective_task"]["amendments"]
        self.assertEqual((None, 3), (task["text"], task["parts"]))
        displayed = []
        for k in (1, 2, 3):
            with contextlib.redirect_stdout(io.StringIO()) as part:
                self.assertEqual(ar.EXIT_OK, ar.main(["status", "--enrollment", enrollment, "--instructions",
                                                      "--part", str(k)], root=env.wf))
            self.assertLess(len(part.getvalue()), 12000)  # each part fits one displayed tool result
            displayed.append(part.getvalue())
        data = (env.dir / "amendments" / f"{task['sha256']}.md").read_text(encoding="utf-8")
        self.assertEqual(data, "".join(json.loads(p)["effective_task_part"]["text_part"] for p in displayed))
        env.developer.show(json.dumps(out, indent=2))
        env.developer.show(displayed[0])
        env.developer.show(displayed[2])  # part 2 never reached the session
        with self.assertRaises(ar.UsageError) as refused:
            self.review_cmd(env, cite=task["report_citation"])
        self.assertIn("not been verifiably displayed", str(refused.exception))
        env.developer.show(displayed[1])
        env.reviewer.script = [{"decision": "ready_for_owner_review"}]
        code, result, _ = self.review_cmd(env, cite=task["report_citation"])
        self.assertEqual((ar.EXIT_OK, "ready_for_owner_review"), (code, result["result"]))
        self.assertEqual(data.encode("utf-8"), env.reviewer.calls[-1]["amendments"])

    def test_status_and_recovery_work_without_a_resolvable_claude_executable(self):
        base = ar.read_json(HERE / "projects" / "kingmaker-gunslinger.json")["developer"]
        env = self.fg_env(developer=dict(base, executable="no-such-claude-executable-7c1"))
        self.preserved_result(env)
        bare = ar.Controller(env.dir, github=env.gh, reviewer=env.reviewer, sleep=lambda s: None,
                             workflow_root=env.wf)  # the real Claude boundary, as the owner's shell builds it
        code, out = self.resume(bare, "GitHub is back")  # owner recovery of an intact result
        self.assertEqual(ar.EXIT_OK, code, out)
        self.assertEqual((1, self.CONTINUATION), (out["review"]["round"], out["review"]["continuation"]))
        self.assertTrue(out["foreground_session"]["problems"])  # reported, not raised
        self.assertEqual({"final": 1}, self.state(env)["rounds_completed"])
        env.reviewer.script = [{"decision": "ready_for_owner_review", "assessments": [("R1-F1", "fix_verified")]}]
        fix = env.commit("feature.txt", "v3\n", "fix R1-F1")
        env.push()
        self.review_cmd(env, dispositions=[fixed("R1-F1", fix)])
        self.assertEqual("AWAITING_OWNER_REVIEW", self.finalize_cmd(env)[1]["status"])
        bare = ar.Controller(env.dir, github=env.gh, reviewer=env.reviewer, sleep=lambda s: None, workflow_root=env.wf)
        status = bare.status(remote=True)
        self.assertTrue(status["handoff_current"])
        json.dumps(status)


class ForegroundRoundThreeTests(ForegroundFixture, Base):
    """Round-3 corrections (PR #7): queued corrections finish at the round cap, the headless executable is resolved
    before any charge, foreground provenance is re-checked before every reviewer attempt, instruction display and
    watch are bound to the requested enrollment, watch attributes activity per invocation and attempt and never
    writes into protected records, and amendment parts are sized by their serialized display."""

    def handoff_at_cap(self):
        env = Env("foreground", max_rounds=1, plan={"schema_version": "agent-review.plan.v1", "mission_id": "f",
                                                    "title": "f", "checkpoints": [{"id": "final", "type": "final",
                                                                                   "scope": "s", "exit_conditions": ["e"]}]})
        self.addCleanup(env.cleanup)
        env.commit("feature.txt", "v2\n", "feature v2")
        env.push()
        env.reviewer.script = [{"decision": "ready_for_owner_review"}]
        self.assertEqual("ready_for_owner_review", self.review_cmd(env)[1]["result"])
        self.assertEqual("AWAITING_OWNER_REVIEW", self.finalize_cmd(env)[1]["status"])
        return env

    def test_an_ordinary_resume_at_the_cap_finishes_the_queued_corrections_and_stays_blocked(self):
        env = self.handoff_at_cap()
        ctl = env.controller()

        def crash():
            raise SimulatedCrash()
        ctl._continue_after_resume = crash  # SIMULATED: exit right after the amendment's state save
        with self.assertRaises(SimulatedCrash):
            self.resume(ctl, "owner amends at the cap", amendment=self.doc(env, "u1.md", self.A1))
        self.assertFalse(self.headings_with(env, "Workflow — reopened"))  # nothing public yet
        before = self.state(env)
        for attempt in (1, 2):  # the original limit, twice: idempotent
            with self.subTest(attempt=attempt):
                with self.assertRaises(ar.UsageError) as refused:
                    self.resume(env.controller(), "owner recovery after the interruption")
                self.assertIn("budget for final is exhausted (1/1)", str(refused.exception))
                self.assertEqual(1, len(self.headings_with(env, "Workflow — reopened")))
                self.assertEqual(1, len(self.headings_with(env, "the owner-review handoff above is not current")))
                self.assertEqual(1, len(self.headings_with(env, "Workflow — blocked")))
                self.assertIn("handoff superseded by owner amendment 1", env.gh.body)
                state = self.state(env)
                self.assertEqual(("BLOCKED", before["rounds_completed"], 1, before["developer"]["invocations"]),
                                 (state["status"], state["rounds_completed"],
                                  state["limits"]["max_review_rounds_per_checkpoint"], state["developer"]["invocations"]))
                self.assertTrue(any("helpers act only during development" in p
                                    for p in env.controller().helper_authority_problems()))
        with self.assertRaises(ar.UsageError):
            self.review_cmd(env)  # report admission stays closed

    def test_a_missing_executable_never_charges_a_headless_invocation(self):
        env = Env("headless")
        self.addCleanup(env.cleanup)

        def missing(_self):
            raise ar.UsageError("executable 'claude' not found on PATH (SIMULATED)")
        type(env.developer).exe = property(missing)  # SIMULATED: the Claude executable cannot be resolved
        self.addCleanup(lambda: delattr(type(env.developer), "exe"))
        env.developer.__dict__.pop("exe", None)
        for attempt in (1, 2):
            with self.subTest(attempt=attempt):
                if attempt == 1:
                    code, out = self.run_command(env.controller())
                else:
                    code, out = self.resume(env.controller(), "retry after the executable problem")
                self.assertEqual(ar.EXIT_BLOCKED, code, out)
                self.assertIn("developer executable could not be resolved", out["reason"])
                state = self.state(env)
                self.assertEqual((0, None), (state["developer"]["invocations"], state["developer"].get("launch")))
                self.assertEqual([], env.developer.calls)

    def test_provenance_is_checked_again_before_an_automatic_reviewer_retry(self):
        env = self.fg_env()
        env.commit("feature.txt", "v2\n", "feature v2")
        env.push()

        def turns_ineligible():  # SIMULATED: the session records a turn at another effort while Codex runs
            env.developer.foreground = dict(env.developer.foreground, efforts=["high", "low"])
        env.reviewer.during_run = turns_ineligible
        env.reviewer.script = [{"raw": "not json (SIMULATED retryable failure)"}, {"decision": "ready_for_owner_review"}]
        code, out, _ = self.review_cmd(env)
        self.assertEqual(ar.EXIT_BLOCKED, code, out)
        self.assertIn("recorded provenance does not match", out["reason"])
        self.assertEqual(1, len(env.reviewer.calls))  # the retry never started
        state = self.state(env)
        self.assertEqual(({}, "BLOCKED"), (state["rounds_completed"], state["status"]))

    def test_instruction_display_never_reads_another_enrollments_amendment(self):
        other = self.fg_env()
        other.commit("feature.txt", "v2\n", "feature v2")
        other.push()
        secret = "Owner amendment (simulated) that belongs to the OTHER job: OTHER-JOB-7d2.\n"
        self.assertEqual(ar.EXIT_OK, self.resume(other.controller(), "other job", amendment=self.doc(other, "o.md",
                                                                                                    secret))[0])
        env = self.fg_env()
        enrollment = self.state(env)["enrollment_id"]
        claim = ar.registry_path("owner/repo", env.branch)  # labeled: the claim now points at the other job's state
        data = ar.read_json(claim)
        data["dir"] = str(other.dir)
        ar.atomic_write_json(claim, data)
        for extra in ([], ["--part", "1"]):
            with self.subTest(extra=extra):
                with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
                    self.assertEqual(ar.EXIT_USAGE, ar.main(["status", "--enrollment", enrollment, "--instructions",
                                                             *extra], root=env.wf))
                self.assertNotIn("OTHER-JOB-7d2", out.getvalue() + err.getvalue())
                self.assertNotIn("delivery_marker", out.getvalue())
                self.assertIn("belongs to another enrollment", err.getvalue())

    def test_watch_attributes_activity_to_the_current_attempt(self):
        env = Env("headless")
        self.addCleanup(env.cleanup)
        state = self.state(env)  # labeled: round 2 is retrying; attempt 1 ended earlier, attempt 2 just started
        state["rounds"] = [{"round": 2, "status": "reviewing", "H": "0" * 40,
                            "attempts": [{"n": 1, "started": ar.now_iso(), "ended": ar.now_iso()},
                                         {"n": 2, "started": ar.now_iso()}]}]
        ar.atomic_write_json(env.dir / "state.json", state)
        folder = env.dir / "rounds" / "r02"
        folder.mkdir(parents=True)
        (folder / "events-1.jsonl").write_text(json.dumps({"type": "item.completed", "item": {
            "type": "agent_message", "text": "ATTEMPT-ONE final note"}}) + "\n", encoding="utf-8")
        (folder / "events-2.jsonl").write_text(json.dumps({"type": "thread.started", "thread_id": "t"}) + "\n",
                                               encoding="utf-8")
        pending = env.dir / "evidence" / "gate-unit-y.pending"  # a marker whose PID now belongs to another process
        pending.parent.mkdir(parents=True, exist_ok=True)
        ar.write_text(pending, json.dumps({"gate": "unit", "candidate": "2" * 40, "started": ar.now_iso(),
                                           "pid": os.getpid()}) + "\n")
        rows = []
        ar.watch_enrollment(env.dir, rows.append, once=True)
        status = [r for r in rows if "| reviewer Codex, round 2 attempt 2" in r][-1]
        self.assertIn("latest action: none observed yet in this attempt", status)
        self.assertNotIn("ATTEMPT-ONE", status)
        self.assertIn("helper PID", status)
        self.assertIn("identity unconfirmed", status)
        with open(folder / "events-2.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"type": "item.completed", "item": {"type": "agent_message",
                                                                    "text": "ATTEMPT-TWO first note"}}) + "\n")
        rows = []
        ar.watch_enrollment(env.dir, rows.append, once=True)
        status = [r for r in rows if "| reviewer Codex, round 2 attempt 2" in r][-1]
        self.assertIn("latest action: Codex: ATTEMPT-TWO first note", status)

    def test_amendment_parts_are_sized_by_their_serialized_display(self):
        env = self.fg_env()
        enrollment = self.state(env)["enrollment_id"]
        env.commit("feature.txt", "v2\n", "feature v2")
        env.push()
        # under 8,000 source characters, but escape-heavy: supplementary characters print as 12 ASCII characters
        text = "Owner amendment (simulated, escape-heavy UTF-8): " + ("\U0001F600漢字 " * 1700) + "\n"
        self.assertLess(len(text), 8000)
        code, out = self.resume(env.controller(), "an escape-heavy update", amendment=self.doc(env, "utf8.md", text))
        self.assertEqual(ar.EXIT_OK, code)
        self.assertLess(len(json.dumps(out, indent=2)), 12000)  # the resume display itself stays bounded
        task = out["effective_task"]["amendments"]
        self.assertIsNone(task["text"])
        self.assertGreater(task["parts"], 1)
        displays = []
        for k in range(1, task["parts"] + 1):
            with contextlib.redirect_stdout(io.StringIO()) as part:
                self.assertEqual(ar.EXIT_OK, ar.main(["status", "--enrollment", enrollment, "--instructions",
                                                      "--part", str(k)], root=env.wf))
            self.assertLess(len(part.getvalue()), 12000)  # the whole printed display, framing included
            displays.append(part.getvalue())
        data = (env.dir / "amendments" / f"{task['sha256']}.md").read_text(encoding="utf-8")
        self.assertEqual(data, "".join(json.loads(p)["effective_task_part"]["text_part"] for p in displays))
        for d in displays[:-1]:
            env.developer.show(d)
        with self.assertRaises(ar.UsageError):  # one part missing
            self.review_cmd(env, cite=task["report_citation"])
        env.developer.show(displays[-1])
        env.reviewer.script = [{"decision": "ready_for_owner_review"}]
        self.assertEqual("ready_for_owner_review", self.review_cmd(env, cite=task["report_citation"])[1]["result"])



class ForegroundRoundFourTests(ForegroundFixture, Base):
    """Round-4 corrections (PR #7): watch opens no file for writing (the console feed is redirected by the owner's
    shell if wanted) and is identity-checked; the capped amendment's blocker is restored after a resolved publication
    outage; a transcript failure at reviewer admission publishes no private filename; watch measures silence from the
    latest complete event and finds the latest displayable action on attachment."""

    def test_watch_has_no_file_output_and_leaves_every_record_untouched(self):
        other = self.fg_env()  # first: each fixture points the host registry at its own folder
        env = self.fg_env()
        enrollment = self.state(env)["enrollment_id"]
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            ar.build_parser().parse_args(["watch", "--enrollment", enrollment, "--log", "x.log"])  # no such option
        claim = ar.registry_path("owner/repo", env.branch)
        marker = Path(git(env.work, "rev-parse", "--absolute-git-dir")) / "agent-review-enrollment.json"
        roots = (env.dir, env.work, Path(git(env.work, "rev-parse", "--absolute-git-dir")), claim.parent)
        before = {p: p.read_bytes() for root in roots for p in root.rglob("*") if p.is_file()}
        self.assertIn(claim, before)
        self.assertIn(marker, before)
        with contextlib.redirect_stdout(io.StringIO()) as shown:
            self.assertEqual(ar.EXIT_OK, ar.main(["watch", "--enrollment", enrollment, "--once"], root=env.wf))
        self.assertIn("ACTIVE/develop", shown.getvalue())
        after = {p: p.read_bytes() for root in roots for p in root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)  # nothing created, changed or removed in any protected location
        rows = []
        ar.watch_enrollment(other.dir, rows.append, once=True, expected_id=enrollment)
        self.assertEqual(1, len(rows))
        self.assertIn("identity mismatch", rows[0])
        for field in ("ACTIVE", "candidate", "rounds", "latest action"):
            self.assertNotIn(field, rows[0])

    def test_a_resolved_publication_outage_at_the_cap_restores_the_budget_blocker(self):
        env = Env("foreground", max_rounds=1, plan={"schema_version": "agent-review.plan.v1", "mission_id": "f",
                                                    "title": "f", "checkpoints": [{"id": "final", "type": "final",
                                                                                   "scope": "s", "exit_conditions": ["e"]}]})
        self.addCleanup(env.cleanup)
        env.commit("feature.txt", "v2\n", "feature v2")
        env.push()
        env.reviewer.script = [{"decision": "ready_for_owner_review"}]
        self.assertEqual("ready_for_owner_review", self.review_cmd(env)[1]["result"])
        self.assertEqual("AWAITING_OWNER_REVIEW", self.finalize_cmd(env)[1]["status"])
        original, failures = env.gh.edit_body, {"left": 1}

        def edit_body(number, body_file):  # SIMULATED: the queued PR-body edit fails once
            if failures["left"]:
                failures["left"] -= 1
                raise ar.CommandError(["gh", "pr", "edit"], subprocess.CompletedProcess([], 1, "", "simulated outage"))
            return original(number, body_file)
        env.gh.edit_body = edit_body
        code, out = self.resume(env.controller(), "owner amends at the cap", amendment=self.doc(env, "u1.md", self.A1))
        self.assertEqual(ar.EXIT_PAUSED, code, out)  # the outage is reported while it lasts
        self.assertNotIn("handoff superseded by owner amendment 1", env.gh.body)
        for attempt in (1, 2):  # recovery with the original limit, then a replay
            with self.subTest(attempt=attempt):
                with self.assertRaises(ar.UsageError):
                    self.resume(env.controller(), "owner recovery after the outage")
                state = self.state(env)
                self.assertEqual(("BLOCKED", env.controller().budget_block_reason()),
                                 (state["status"], state["status_reason"]))
                self.assertIn("handoff superseded by owner amendment 1", env.gh.body)
                self.assertEqual(1, len(self.headings_with(env, "Workflow — reopened")))
                self.assertEqual(1, len(self.headings_with(env, "the owner-review handoff above is not current")))
                blocked = [h for h in env.gh.headings() if "Workflow — blocked" in h]
                self.assertEqual(2, len(blocked))  # the original block, then exactly one restored after the outage
                self.assertEqual(({"final": 1}, 0), (state["rounds_completed"], state["developer"]["invocations"]))
                self.assertTrue(env.controller().helper_authority_problems())
        with self.assertRaises(ar.UsageError):
            self.review_cmd(env)

    def test_a_transcript_failure_at_reviewer_admission_publishes_no_private_filename(self):
        env = self.fg_env()
        env.commit("feature.txt", "v2\n", "feature v2")
        env.push()
        secret = str(env.root / "private-dir" / "SECRET-TRANSCRIPT-NAME-91.jsonl")
        original = env.developer.session_provenance
        state = {"fail": False}

        def provenance(session_id, since=None):
            if state["fail"]:
                raise PermissionError(13, "Permission denied", secret)  # SIMULATED unreadable transcript
            return original(session_id, since)
        env.developer.session_provenance = provenance

        def break_transcript():
            state["fail"] = True
        env.reviewer.during_run = break_transcript
        env.reviewer.script = [{"raw": "not json (SIMULATED retryable failure)"}, {"decision": "ready_for_owner_review"}]
        code, out, _ = self.review_cmd(env)
        self.assertEqual(ar.EXIT_BLOCKED, code, out)
        self.assertEqual(1, len(env.reviewer.calls))
        self.assertEqual({}, self.state(env)["rounds_completed"])
        public = "\n".join(c["body"] for c in env.gh.comments_list)
        self.assertNotIn("SECRET-TRANSCRIPT-NAME-91", public)
        self.assertNotIn("SECRET-TRANSCRIPT-NAME-91", out["reason"])
        self.assertIn("PermissionError", out["reason"])
        self.assertTrue(any("SECRET-TRANSCRIPT-NAME-91" in n for n in self.state(env)["notes"]))  # local diagnosis

    def test_watch_measures_silence_from_the_latest_event_and_finds_the_latest_action(self):
        env = Env("headless")
        self.addCleanup(env.cleanup)
        state = self.state(env)  # labeled: an aged reviewer attempt is running
        started = (ar.dt.datetime.now(ar.dt.timezone.utc) - ar.dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        state["rounds"] = [{"round": 1, "status": "reviewing", "H": "0" * 40, "attempts": [{"n": 1, "started": started}]}]
        ar.atomic_write_json(env.dir / "state.json", state)
        events = env.dir / "rounds" / "r01" / "events-1.jsonl"
        events.parent.mkdir(parents=True)
        records = [{"type": "item.started", "item": {"type": "command_execution", "command": "rg -n VISIBLE-CMD-4e"}}]
        records += [{"type": "item.completed", "item": {"type": "reasoning", "text": "filtered"}}] * 20
        events.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
        old = time.time() - 3600
        os.utime(events, (old, old))
        rows = []
        ar.watch_enrollment(env.dir, rows.append, once=True, stall_minutes=10)
        status = [r for r in rows if "reviewer Codex, round 1 attempt 1" in r][-1]
        self.assertIn("latest action: Codex ▸ $ rg -n VISIBLE-CMD-4e", status)  # despite 20 later filtered records
        self.assertTrue(any("no new agent events for 1h00m" in r for r in rows), rows)  # genuinely quiet
        with open(events, "a", encoding="utf-8") as f:  # a fresh, non-displayable metadata event
            f.write(json.dumps({"type": "turn.started"}) + "\n")
        rows = []
        ar.watch_enrollment(env.dir, rows.append, once=True, stall_minutes=10)
        status = [r for r in rows if "reviewer Codex, round 1 attempt 1" in r][-1]
        self.assertIn("latest action: Codex ▸ $ rg -n VISIBLE-CMD-4e", status)
        self.assertFalse(any("no new agent events" in r for r in rows), rows)  # a record just arrived
        later = lambda: ar.dt.datetime.now(ar.dt.timezone.utc) + ar.dt.timedelta(minutes=30)  # noqa: E731
        rows = []
        ar.watch_enrollment(env.dir, rows.append, once=True, stall_minutes=10, now=later)
        self.assertTrue(any("no new agent events for" in r for r in rows), rows)


class ForegroundRoundSixTests(ForegroundFixture, Base):
    """Round-6 corrections (PR #7): a proposed round limit is distinguished from the persisted authorized limit, so a
    refused proposal changes no status, reason, admission or accounting; a capped amendment's blocker is restored only
    when durable state marks that amendment's interrupted recovery, in one transaction with its queued notice; a single
    continuing watch times newly observed events by observation, ignores blank and partial records, orders sources by
    the controller's recorded execution history and treats streams created after attachment as live."""

    SINGLE = {"schema_version": "agent-review.plan.v1", "mission_id": "f", "title": "f",
              "checkpoints": [{"id": "final", "type": "final", "scope": "s", "exit_conditions": ["e"]}]}

    def amend_and_show(self, env, name="u1.md"):
        code, out = self.resume(env.controller(), "owner amends the task", amendment=self.doc(env, name, self.A1))
        self.assertEqual(ar.EXIT_OK, code, out)
        env.developer.show(json.dumps(out, indent=2))  # SIMULATED: the full update reached the session
        return out["effective_task"]["amendments"]["report_citation"]

    @staticmethod
    def accounting(state):
        return (state["status"], state.get("status_reason"), state["phase"], state["limits"],
                {k: v.get("rounds_open") for k, v in state.get("findings", {}).items()})

    def test_a_refused_proposed_limit_changes_no_authorization_status_or_admission(self):
        env = self.fg_env()
        env.commit("feature.txt", "v2\n", "feature v2")
        env.push()
        cite = self.amend_and_show(env)  # an older amendment, applied before any review
        env.reviewer.script = [{"decision": "changes_required", "findings": [finding("R1-F1")]}]
        self.assertEqual("changes_required", self.review_cmd(env, cite=cite)[1]["result"])  # 1 of 5 rounds spent
        before, posted = self.state(env), len(env.gh.comments_list)
        with self.assertRaises(ar.UsageError) as refused:
            self.resume(env.controller(), "a proposed limit below the rounds spent", max_rounds=1)
        after = self.state(env)
        self.assertEqual(self.accounting(before), self.accounting(after))  # status, reason, limit, streaks
        self.assertEqual(("ACTIVE", 5), (after["status"], after["limits"]["max_review_rounds_per_checkpoint"]))
        self.assertEqual(posted, len(env.gh.comments_list))  # no false "budget exhausted" notice
        self.assertEqual([], env.controller().helper_authority_problems())  # admission stays open
        self.assertIn("authorized limit stays 5", str(refused.exception))

    def test_a_refused_resume_at_a_no_progress_cap_keeps_the_reason_and_a_later_extension_resets_the_streak(self):
        env = Env("foreground", max_rounds=2, plan=self.SINGLE)
        self.addCleanup(env.cleanup)
        env.commit("feature.txt", "v2\n", "feature v2")
        env.push()
        cite = self.amend_and_show(env)
        env.reviewer.script = [{"decision": "changes_required", "findings": [finding("R1-F1")]},
                               {"decision": "changes_required", "findings": [finding("R1-F1")],
                                "assessments": [("R1-F1", "rebuttal_rejected")]}]
        self.assertEqual("changes_required", self.review_cmd(env, cite=cite)[1]["result"])
        code, out, _ = self.review_cmd(env, cite=cite, dispositions=[{
            "finding_id": "R1-F1", "disposition": "rebutted", "commits": [], "evidence": "simulated rebuttal"}])
        self.assertEqual(ar.EXIT_BLOCKED, code, out)
        stopped = self.state(env)
        self.assertTrue(stopped["status_reason"].startswith("no progress"), stopped["status_reason"])
        self.assertEqual({"final": 2}, stopped["rounds_completed"])  # the genuine cap
        with self.assertRaises(ar.UsageError):
            self.resume(env.controller(), "resume without a new authorization")
        self.assertEqual(self.accounting(stopped), self.accounting(self.state(env)))  # the no-progress reason survives
        code, out = self.resume(env.controller(), "owner extends the budget", max_rounds=3)
        self.assertEqual(ar.EXIT_OK, code, out)
        state = self.state(env)
        self.assertEqual(("ACTIVE", 0), (state["status"], state["findings"]["R1-F1"]["rounds_open"]))  # streak reset

    def outage_at_cap(self):
        """A handed-off final round at its cap, then an amendment whose queued PR-body edit fails once."""
        env = Env("foreground", max_rounds=1, plan=self.SINGLE)
        self.addCleanup(env.cleanup)
        env.commit("feature.txt", "v2\n", "feature v2")
        env.push()
        env.reviewer.script = [{"decision": "ready_for_owner_review"}]
        self.assertEqual("ready_for_owner_review", self.review_cmd(env)[1]["result"])
        self.assertEqual("AWAITING_OWNER_REVIEW", self.finalize_cmd(env)[1]["status"])
        original, failures = env.gh.edit_body, {"left": 1}

        def edit_body(number, body_file):  # SIMULATED: the queued PR-body edit fails once
            if failures["left"]:
                failures["left"] -= 1
                raise ar.CommandError(["gh", "pr", "edit"], subprocess.CompletedProcess([], 1, "", "simulated outage"))
            return original(number, body_file)
        env.gh.edit_body = edit_body
        code, out = self.resume(env.controller(), "owner amends at the cap", amendment=self.doc(env, "u1.md", self.A1))
        self.assertEqual(ar.EXIT_PAUSED, code, out)
        return env

    def test_an_interrupted_restoration_delivers_exactly_one_restored_notice(self):
        env = self.outage_at_cap()
        reviews, developer_calls = len(env.reviewer.calls), len(env.developer.calls)
        ctl = env.controller()
        original_settle, calls = ctl.settle_publications, {"n": 0}

        def settle():
            calls["n"] += 1
            if calls["n"] == 2:  # SIMULATED exit: the restored state and its notice intent are saved, not delivered
                raise SimulatedCrash()
            return original_settle()

        def publish_status(*_args, **_kwargs):  # an immediate (unqueued) delivery path would be interrupted too
            raise SimulatedCrash()
        ctl.settle_publications, ctl.publish_status = settle, publish_status
        with self.assertRaises(SimulatedCrash):
            self.resume(ctl, "owner recovery after the outage")
        self.assertEqual("BLOCKED", self.state(env)["status"])  # durably restored before the interruption
        for attempt in (1, 2):
            with self.subTest(attempt=attempt):
                with self.assertRaises(ar.UsageError):
                    self.resume(env.controller(), "owner recovery, again")
                state = self.state(env)
                self.assertEqual(("BLOCKED", env.controller().budget_block_reason()),
                                 (state["status"], state["status_reason"]))
                blocked = [h for h in env.gh.headings() if "Workflow — blocked" in h]
                self.assertEqual(2, len(blocked))  # the original block and exactly one restored notice
                self.assertIn("handoff superseded by owner amendment 1", env.gh.body)
                self.assertEqual(({"final": 1}, reviews, developer_calls),
                                 (state["rounds_completed"], len(env.reviewer.calls), len(env.developer.calls)))

    # ---- watch: a single continuing observer with real files and a controlled clock
    def reviewer_attempts(self, env, attempts):
        state = self.state(env)
        state["rounds"] = [{"round": 1, "status": "reviewing", "H": "0" * 40, "attempts": attempts}]
        ar.atomic_write_json(env.dir / "state.json", state)

    @staticmethod
    def record(kind, **item):
        return json.dumps({"type": kind, "item": item}) + "\n"

    def test_a_continuing_watch_times_new_events_by_observation_and_ignores_incomplete_records(self):
        env = Env("headless")
        self.addCleanup(env.cleanup)
        clock = {"t": ar.dt.datetime.now(ar.dt.timezone.utc)}
        self.reviewer_attempts(env, [{"n": 1, "started": (clock["t"] - ar.dt.timedelta(hours=1)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")}])
        events = env.dir / "rounds" / "r01" / "events-1.jsonl"
        events.parent.mkdir(parents=True)
        events.write_text(self.record("item.started", type="command_execution", command="rg -n FIRST-CMD"),
                          encoding="utf-8")
        old = time.time() - 3600

        def append(text):
            with open(events, "a", encoding="utf-8") as f:
                f.write(text)
            os.utime(events, (old, old))  # the sampled modification time stays old
        os.utime(events, (old, old))

        def advance(minutes):
            clock["t"] += ar.dt.timedelta(minutes=minutes)
        rows, steps = [], [
            lambda: (append(self.record("item.completed", type="agent_message", text="SECOND-NOTE")), advance(1)),
            lambda: (advance(8), append(self.record("item.completed", type="reasoning", text="filtered"))),
            lambda: advance(8),
            lambda: (append("\n   \n" + '{"type": "item.completed", "item": {"type": "agent_mes'), advance(11)),
            lambda: (append('sage", "text": "THIRD-NOTE"}}\n'), advance(1)),
        ]

        def sleep(_interval):
            rows.append(f"== step {sum(1 for r in rows if r.startswith('== step')) + 1}")
            steps[sum(1 for r in rows if r.startswith("== step")) - 1]()
        ar.watch_enrollment(env.dir, rows.append, interval=0, stall_minutes=10, now=lambda: clock["t"], sleep=sleep,
                            max_polls=6)
        segments, current = [[]], 0
        for row in rows:
            if row.startswith("== step"):
                segments.append([])
                current += 1
            else:
                segments[current].append(row)
        attach = "\n".join(segments[0])
        self.assertIn("latest action: Codex ▸ $ rg -n FIRST-CMD (before this watch started)", attach)
        self.assertRegex(attach, r"no new agent events for (59m5\ds|1h00m)")  # genuinely quiet at attachment
        new = "\n".join(segments[1])
        self.assertIn("Codex: SECOND-NOTE", new)
        self.assertNotIn("(earlier)", new)
        self.assertIn("latest action: Codex: SECOND-NOTE (0m00s ago)", new)  # observation time, not the old mtime
        for k in (2, 3):  # the filtered complete event reset the silence clock
            self.assertFalse(any("no new agent events" in r for r in segments[k]), segments[k])
        self.assertTrue(any("no new agent events for 19m" in r for r in segments[4]), segments[4])  # blank/partial
        self.assertFalse(any("no new agent events" in r for r in segments[5]), segments[5])  # completed record
        self.assertIn("Codex: THIRD-NOTE", "\n".join(segments[5]))

    def test_attachment_selects_the_latest_source_by_recorded_execution_order(self):
        env = Env("headless")
        self.addCleanup(env.cleanup)
        base = ar.dt.datetime.now(ar.dt.timezone.utc)
        stamp = lambda minutes: (base - ar.dt.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa
        state = self.state(env)  # labeled: a developer invocation, then two ended reviewer attempts
        state["developer"].update(invocations=1, launch={"n": 1, "at": stamp(30), "returned": True})
        state["rounds"] = [{"round": 1, "status": "accepted", "H": "0" * 40, "decision": "changes_required",
                            "attempts": [{"n": 1, "started": stamp(20), "ended": stamp(18)},
                                         {"n": 2, "started": stamp(15), "ended": stamp(10)}]}]
        ar.atomic_write_json(env.dir / "state.json", state)
        (env.dir / "developer").mkdir(parents=True, exist_ok=True)
        (env.dir / "developer" / "stream-001.jsonl").write_text(json.dumps(
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "DEV-ACTION"}]}}) + "\n",
            encoding="utf-8")
        folder = env.dir / "rounds" / "r01"
        folder.mkdir(parents=True)
        for n in (1, 2):
            (folder / f"events-{n}.jsonl").write_text(self.record("item.completed", type="agent_message",
                                                                  text=f"ATTEMPT-{n}-NOTE"), encoding="utf-8")
        rows = []
        ar.watch_enrollment(env.dir, rows.append, once=True)
        status = [r for r in rows if "| no agent running" in r][-1]
        self.assertIn("latest action: Codex: ATTEMPT-2-NOTE (before this watch started)", status)
        state = self.state(env)  # labeled: an older record without the times needed to order its sources
        state["developer"]["launch"].pop("at")
        for attempt in state["rounds"][0]["attempts"]:
            attempt.pop("started")
        ar.atomic_write_json(env.dir / "state.json", state)
        rows = []
        ar.watch_enrollment(env.dir, rows.append, once=True)
        status = [r for r in rows if "| no agent running" in r][-1]
        self.assertIn("latest action: uncertain", status)  # no false "latest"

    def test_a_stream_created_after_attachment_is_live_activity(self):
        env = Env("headless")
        self.addCleanup(env.cleanup)
        clock = {"t": ar.dt.datetime.now(ar.dt.timezone.utc)}
        iso = lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
        self.reviewer_attempts(env, [{"n": 1, "started": iso(clock["t"] - ar.dt.timedelta(minutes=9)),
                                      "ended": iso(clock["t"] - ar.dt.timedelta(minutes=5))}])
        folder = env.dir / "rounds" / "r01"
        folder.mkdir(parents=True)
        (folder / "events-1.jsonl").write_text(self.record("item.completed", type="agent_message", text="OLD-ATTEMPT"),
                                               encoding="utf-8")
        rows = []

        def new_attempt(_interval):  # a retry starts after the watch attached
            rows.append("== step 1")
            clock["t"] += ar.dt.timedelta(minutes=1)
            self.reviewer_attempts(env, [{"n": 1, "started": iso(clock["t"] - ar.dt.timedelta(minutes=10)),
                                          "ended": iso(clock["t"] - ar.dt.timedelta(minutes=6))},
                                         {"n": 2, "started": iso(clock["t"])}])
            (folder / "events-2.jsonl").write_text(self.record("item.completed", type="agent_message",
                                                               text="NEW-ATTEMPT-NOTE"), encoding="utf-8")
        ar.watch_enrollment(env.dir, rows.append, interval=0, now=lambda: clock["t"], sleep=new_attempt, max_polls=2)
        after = rows[rows.index("== step 1") + 1:]
        self.assertIn("Codex: NEW-ATTEMPT-NOTE", after)  # emitted as live, not replayed history
        status = [r for r in after if "| reviewer Codex, round 1 attempt 2" in r][-1]
        self.assertIn("latest action: Codex: NEW-ATTEMPT-NOTE (0m00s ago)", status)
        self.assertNotIn("OLD-ATTEMPT", status)


class ForegroundRoundSevenTests(ForegroundFixture, Base):
    """Round-7 corrections (PR #7): a proposed round limit is admitted (or refused) at the locked, read-only
    command-admission boundary before any guard, rebinding, resend, reopening, stop consumption or publication; the
    capped amendment's blocker is marked for recovery by the one shared path that saves a displacing publication stop,
    and its restoration notice keeps one durable identity; watch reads retained reviewer attempts."""

    SINGLE = {"schema_version": "agent-review.plan.v1", "mission_id": "f", "title": "f",
              "checkpoints": [{"id": "final", "type": "final", "scope": "s", "exit_conditions": ["e"]}]}

    def one_round_spent(self, decision="changes_required"):
        env = self.fg_env()
        env.commit("feature.txt", "v2\n", "feature v2")
        env.push()
        env.reviewer.script = [{"decision": decision, "findings": [finding("R1-F1")] if decision == "changes_required"
                                else []}]
        self.assertEqual(decision, self.review_cmd(env)[1]["result"])  # 1 of 5 rounds spent
        return env

    def snapshot(self, env):
        state = self.state(env)
        return {"status": state["status"], "reason": state.get("status_reason"), "phase": state["phase"],
                "limits": state["limits"], "handoff": state.get("handoff"), "workflow": state["workflow"],
                "settings": state.get("developer_settings_file"), "publications": state.get("publications"),
                "rounds": state["rounds_completed"], "notes": len(state.get("notes", [])),
                "stop": (env.dir / "STOP").exists(), "comments": len(env.gh.comments_list), "body": env.gh.body,
                "reviews": len(env.reviewer.calls), "developer_calls": len(env.developer.calls)}

    def assert_refused_unchanged(self, env, before, **kw):
        with self.assertRaises(ar.UsageError) as refused:
            self.resume(env.controller(), "a proposal that does not extend the spent budget", **kw)
        self.assertEqual(before, self.snapshot(env))
        return str(refused.exception)

    def test_an_explicit_zero_from_paused_develop_is_refused_before_anything_changes(self):
        env = self.one_round_spent()
        ar.write_text(env.dir / "STOP", "owner stop (simulated)\n")
        self.assertEqual(ar.EXIT_PAUSED, self.review_cmd(env)[0])  # PAUSED in develop, stop request in place
        before = self.snapshot(env)
        self.assertEqual(("PAUSED", "develop", True), (before["status"], before["phase"], before["stop"]))
        message = self.assert_refused_unchanged(env, before, max_rounds=0)
        self.assertIn("--max-rounds 0", message)
        self.assertTrue(env.controller().helper_authority_problems())  # admission stays closed

    def test_an_exhausted_proposal_with_resend_never_clears_an_uncertain_delivery(self):
        env = self.one_round_spent()
        state = self.state(env)  # labeled: a publication whose POST outcome is unknown (absent from the PR)
        chunk = "simulated body whose POST outcome is unknown\n"
        marker = (f"<!-- agent-review:v1 enrollment={state['enrollment_id']} key=r09-request part=1/1 "
                  f"sha256={ar.sha256_text(chunk)} -->")
        body_file = env.dir / "outbox" / "r09-request-part1.md"
        ar.write_text(body_file, f"{marker}\n{chunk}")
        state["publications"]["r09-request"] = {"key": "r09-request", "state": "pending", "seq": 99, "redactions": [],
                                                "parts": [{"marker": marker, "body_file": str(body_file),
                                                           "sha256": ar.sha256_text(chunk), "comment_id": None,
                                                           "url": None, "posting_since": ar.now_iso()}]}
        state.update(status="PAUSED", status_reason="uncertain delivery (simulated)")
        ar.atomic_write_json(env.dir / "state.json", state)
        before = self.snapshot(env)
        self.assert_refused_unchanged(env, before, max_rounds=1, resend_undelivered=True)
        self.assertTrue(self.state(env)["publications"]["r09-request"]["parts"][0]["posting_since"])

    def test_an_exhausted_proposal_never_reopens_a_superseded_handoff(self):
        env = self.one_round_spent("ready_for_owner_review")
        self.assertEqual("AWAITING_OWNER_REVIEW", self.finalize_cmd(env)[1]["status"])
        env.commit("feature.txt", "v3\n", "a real source change after the handoff")
        env.push()
        before = self.snapshot(env)
        self.assertTrue(before["handoff"])
        self.assert_refused_unchanged(env, before, max_rounds=1)
        self.assertEqual(5, self.state(env)["limits"]["max_review_rounds_per_checkpoint"])

    def test_an_exhausted_proposal_saves_no_due_rebinding(self):
        env = self.one_round_spent()
        state = self.state(env)  # labeled: the same version recorded at another installed package location
        state["workflow"]["root"] = str(env.wf) + "-earlier-install"
        ar.atomic_write_json(env.dir / "state.json", state)
        before = self.snapshot(env)
        self.assert_refused_unchanged(env, before, max_rounds=1)
        self.assertEqual(str(env.wf) + "-earlier-install", self.state(env)["workflow"]["root"])

    # ---- R6-F1: one shared path records the displaced capped blocker
    def capped_handoff(self):
        env = Env("foreground", max_rounds=1, plan=self.SINGLE)
        self.addCleanup(env.cleanup)
        env.commit("feature.txt", "v2\n", "feature v2")
        env.push()
        env.reviewer.script = [{"decision": "ready_for_owner_review"}]
        self.assertEqual("ready_for_owner_review", self.review_cmd(env)[1]["result"])
        self.assertEqual("AWAITING_OWNER_REVIEW", self.finalize_cmd(env)[1]["status"])
        return env

    def fail_body_edits(self, env, times):
        original, left = env.gh.edit_body, {"n": times}

        def edit_body(number, body_file):  # SIMULATED: queued PR-body edits fail `times` times
            if left["n"]:
                left["n"] -= 1
                raise ar.CommandError(["gh", "pr", "edit"], subprocess.CompletedProcess([], 1, "", "simulated outage"))
            return original(number, body_file)
        env.gh.edit_body = edit_body

    def fail_blocked_posts(self, env, times):
        original, left = env.gh.post_comment, {"n": times}

        def post(number, body_file):  # SIMULATED: BLOCKED status comments are rejected `times` times
            if left["n"] and "Workflow — blocked" in Path(body_file).read_text(encoding="utf-8"):
                left["n"] -= 1
                raise ar.NotDelivered("simulated transient GitHub failure (request rejected; nothing stored)")
            return original(number, body_file)
        env.gh.post_comment = post

    @staticmethod
    def statuses(env):
        return [h for h in env.gh.headings() if h.startswith("### Workflow —") and
                any(word in h for word in ("blocked", "paused", "reopened"))]

    def assert_recovered(self, env, blocked_notices, reviews, developer_calls):
        for attempt in (1, 2):  # recovery after success, repeated
            with self.subTest(attempt=attempt):
                with self.assertRaises(ar.UsageError):
                    self.resume(env.controller(), "owner recovery")
                state, status = self.state(env), env.controller().status()
                self.assertEqual(("BLOCKED", env.controller().budget_block_reason()),
                                 (state["status"], state["status_reason"]))
                self.assertIn("Workflow — blocked", self.statuses(env)[-1])  # the latest public status
                self.assertEqual(blocked_notices, sum("Workflow — blocked" in h for h in env.gh.headings()))
                self.assertEqual([], status["pending_publications"])
                self.assertIn("handoff superseded by owner amendment 1", env.gh.body)
                self.assertTrue(env.controller().helper_authority_problems())
                self.assertEqual(({"final": 1}, reviews, developer_calls),
                                 (state["rounds_completed"], len(env.reviewer.calls), len(env.developer.calls)))

    def amend(self, ctl, env):
        return self.resume(ctl, "owner amends at the cap", amendment=self.doc(env, "u1.md", self.A1))

    def test_an_initial_publication_failure_then_success_restores_the_capped_blocker(self):
        env = self.capped_handoff()
        counts = len(env.reviewer.calls), len(env.developer.calls)
        self.fail_body_edits(env, 1)
        self.assertEqual(ar.EXIT_PAUSED, self.amend(env.controller(), env)[0])
        self.assert_recovered(env, 2, *counts)  # the original block and one restored notice

    def test_a_crash_after_the_amendment_then_a_replay_failure_then_success(self):
        env = self.capped_handoff()
        counts = len(env.reviewer.calls), len(env.developer.calls)
        ctl = env.controller()

        def crash():
            raise SimulatedCrash()
        ctl._continue_after_resume = crash  # SIMULATED exit right after the amendment's transaction
        with self.assertRaises(SimulatedCrash):
            self.amend(ctl, env)
        self.fail_body_edits(env, 1)
        code, out = self.resume(env.controller(), "first ordinary resume: the PR-body edit fails")
        self.assertEqual(ar.EXIT_PAUSED, code, out)
        self.assert_recovered(env, 2, *counts)

    def test_a_crash_after_the_restoration_then_success(self):
        env = self.capped_handoff()
        counts = len(env.reviewer.calls), len(env.developer.calls)
        self.fail_body_edits(env, 1)
        self.assertEqual(ar.EXIT_PAUSED, self.amend(env.controller(), env)[0])
        ctl = env.controller()
        original_settle, calls = ctl.settle_publications, {"n": 0}

        def settle():
            calls["n"] += 1
            if calls["n"] == 2:
                raise SimulatedCrash()  # SIMULATED exit after the restoration's save, before delivery
            return original_settle()
        ctl.settle_publications = settle
        with self.assertRaises(SimulatedCrash):
            self.resume(ctl, "owner recovery, interrupted")
        self.assert_recovered(env, 2, *counts)

    def test_a_failed_restored_notice_then_success_keeps_one_restoration_notice(self):
        env = self.capped_handoff()
        counts = len(env.reviewer.calls), len(env.developer.calls)
        self.fail_body_edits(env, 1)
        self.assertEqual(ar.EXIT_PAUSED, self.amend(env.controller(), env)[0])
        self.fail_blocked_posts(env, 4)  # every delivery attempt of the restored notice fails in this command
        code, out = self.resume(env.controller(), "owner recovery: the restored notice cannot be delivered")
        self.assertEqual(ar.EXIT_PAUSED, code, out)
        env.gh.post_comment = type(env.gh).post_comment.__get__(env.gh)  # GitHub accepts comments again
        self.assert_recovered(env, 2, *counts)

    # ---- R5-F3: retained attempts
    def test_watch_reads_attempts_retained_by_resume(self):
        env = Env("headless")
        self.addCleanup(env.cleanup)

        def develop(e):
            e.commit("phase1.txt", "p1\n", "phase 1")
            e.push()
            stream = e.dir / "developer" / "stream-001.jsonl"  # SIMULATED stream-json of the developer invocation
            stream.parent.mkdir(parents=True, exist_ok=True)
            stream.write_text(json.dumps({"type": "assistant", "message": {"content": [
                {"type": "text", "text": "DEVELOPER-NOTE"}]}}) + "\n", encoding="utf-8")
            time.sleep(1.2)  # the reviewer starts in a later recorded second than the developer launch
            return report(e, "phase-1")
        env.developer.script = [develop]
        original_run = env.reviewer.run

        def run(prompt, workdir, schema, result_path, events_path, *args, **kwargs):
            info = original_run(prompt, workdir, schema, result_path, events_path, *args, **kwargs)
            with open(events_path, "a", encoding="utf-8") as f:  # SIMULATED reviewer activity of this attempt
                f.write(self.record_line(f"REVIEWER-NOTE-{Path(events_path).stem}"))
            return info
        env.reviewer.run = run
        env.reviewer.script = [{"raw": "not json (SIMULATED failure)"}] * 3
        code, out = self.run_command(env.controller())
        self.assertEqual(ar.EXIT_BLOCKED, code, out)  # three failed reviewer attempts
        (env.work / "dirty.txt").write_text("uncommitted\n", encoding="utf-8")  # capture will pause on it
        code, out = self.resume(env.controller(), "retry the review")
        self.assertEqual(ar.EXIT_PAUSED, code, out)
        state = self.state(env)
        self.assertEqual(([], 3), (state["rounds"][-1]["attempts"], len(state["rounds"][-1]["earlier_attempts"])))
        rows = []
        ar.watch_enrollment(env.dir, rows.append, once=True)
        status = [r for r in rows if "| no agent running" in r][-1]
        self.assertIn("latest action: Codex: REVIEWER-NOTE-events-3 (before this watch started)", status)
        self.assertIn("(earlier) Codex: REVIEWER-NOTE-events-1", rows)

    @staticmethod
    def record_line(text):
        return json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": text}}) + "\n"


class ForegroundRoundEightTests(ForegroundFixture, Base):
    """Round-8 corrections (PR #7), from the owner-supplied acceptance cases for R7-F1, R7-F2 and R5-F3 (bodies
    integrated unchanged apart from module prefixes): pending publications replay in their persisted numeric order;
    after recovery the latest public status agrees with the restored BLOCKED state, without a further correction on
    repeated recovery; and an empty replacement review request does not hide the latest recorded reviewer
    execution."""

    SINGLE = ForegroundRoundSevenTests.SINGLE
    capped_handoff = ForegroundRoundSevenTests.capped_handoff
    fail_body_edits = ForegroundRoundSevenTests.fail_body_edits
    amend = ForegroundRoundSevenTests.amend

    def test_both_deferred_status_notices_recover_to_public_and_local_blocked(self):
        env = self.capped_handoff()
        calls_before = (len(env.reviewer.calls), len(env.developer.calls))
        rounds_before = dict(self.state(env)["rounds_completed"])

        # First, displace the capped amendment's blocker with a real controller
        # pause caused by a simulated one-time GitHub PR-body edit failure.
        self.fail_body_edits(env, 1)
        code, out = self.amend(env.controller(), env)
        self.assertEqual(ar.EXIT_PAUSED, code, out)

        # The next resume repairs the body edit, but the same simulated outage
        # rejects every permitted POST for BOTH the restored BLOCKED notice and
        # the subsequent PAUSED notice. Both remain durably pending.
        original_post = env.gh.post_comment
        remaining = {"count": 2 * env.controller().limits["publication_attempts"]}
        rejected_headings = []

        def reject_both_statuses(number, body_file):
            body = Path(body_file).read_text(encoding="utf-8")
            heading = body.splitlines()[1]
            if remaining["count"] and any(
                phrase in heading for phrase in ("Workflow — blocked", "Workflow — paused")
            ):
                remaining["count"] -= 1
                rejected_headings.append(heading)
                raise ar.NotDelivered(
                    "SIMULATED shared outage: status POST rejected; nothing stored"
                )
            return original_post(number, body_file)

        env.gh.post_comment = reject_both_statuses
        code, out = self.resume(env.controller(), "recover body edit while both status POSTs fail")
        self.assertEqual(ar.EXIT_PAUSED, code, out)
        self.assertEqual(0, remaining["count"], rejected_headings)
        self.assertTrue(any("Workflow — blocked" in h for h in rejected_headings))
        self.assertTrue(any("Workflow — paused" in h for h in rejected_headings))
        state = self.state(env)
        self.assertEqual(2, sum(p["state"] == "pending" for p in state["publications"].values()))

        # GitHub recovers. Use fresh controller objects so each attempt reloads
        # persisted state, and verify the public chronology after each replay.
        env.gh.post_comment = original_post
        count_after_first_recovery = None
        for recovery in (1, 2):
            with self.assertRaises(ar.UsageError):
                self.resume(env.controller(), "GitHub recovered; resume at unchanged cap")
            state = self.state(env)
            ctl = env.controller()
            expected_reason = ctl.budget_block_reason()
            statuses = [
                comment for comment in env.gh.comments_list
                if comment["body"].splitlines()[1].startswith("### Workflow —")
            ]
            self.assertTrue(statuses)
            latest_body = statuses[-1]["body"]
            latest_heading = latest_body.splitlines()[1]
            markers = [comment["body"].splitlines()[0] for comment in env.gh.comments_list]

            self.assertEqual(("BLOCKED", expected_reason), (state["status"], state["status_reason"]))
            self.assertEqual([], [key for key, pub in state["publications"].items() if pub["state"] == "pending"])
            self.assertEqual([], state.get("public_ops", []))
            self.assertTrue(ctl.helper_authority_problems(), "the saved cap must keep helper admission closed")
            self.assertEqual(rounds_before, state["rounds_completed"])
            self.assertEqual(calls_before, (len(env.reviewer.calls), len(env.developer.calls)))
            self.assertEqual(len(markers), len(set(markers)), "one public comment per durable marker")
            if count_after_first_recovery is None:
                count_after_first_recovery = len(env.gh.comments_list)
            else:
                self.assertEqual(count_after_first_recovery, len(env.gh.comments_list),
                                 "recovery after success must not create another status correction")

            with self.subTest(recovery=recovery):
                self.assertIn("Workflow — blocked", latest_heading,
                              "the last public status must agree with the recovered local BLOCKED state")
                self.assertIn(expected_reason, latest_body)

    def test_the_dual_failure_recovery_leaves_this_public_chronology(self):
        """The supplied R7-F1 lifecycle, then the actual order and content of this enrollment's status comments:
        both deferred notices are delivered in their queued order, and exactly one new BLOCKED correction (its own
        durable identity) follows the late PAUSED notice."""
        seen = {}

        def capture():
            seen["env"] = ForegroundRoundSevenTests.capped_handoff(self)
            return seen["env"]
        self.capped_handoff = capture
        self.test_both_deferred_status_notices_recover_to_public_and_local_blocked()
        env, state = seen["env"], self.state(seen["env"])
        rows = []
        for comment in env.gh.comments_list:  # GitHub order (the simulated listing is chronological)
            marker, heading = comment["body"].splitlines()[:2]
            key = marker.split("key=")[1].split(" ")[0]
            if key.startswith("status-"):
                rows.append((key, heading.split(" — ")[1], state["publications"][key]["seq"]))
        self.assertEqual(["reopened", "blocked", "paused", "blocked", "paused", "blocked"], [r[1] for r in rows])
        self.assertEqual(sorted(r[2] for r in rows), [r[2] for r in rows])  # delivered in queued numeric order
        self.assertEqual(len(rows), len({r[0] for r in rows}))
        self.assertEqual(rows[-1][0], state["capped_amendment"]["notice_key"])  # the correction is the current notice
        self.assertIn(env.controller().budget_block_reason(), env.gh.comments_list[-1]["body"])

    def test_reloaded_amendment_publishes_reopened_before_blocked(self):
        env = Env("foreground", max_rounds=3, plan=self.SINGLE)
        self.addCleanup(env.cleanup)
        env.reviewer.script = [
            {"decision": "changes_required", "findings": [finding("R1-F1")]},
            {
                "decision": "changes_required",
                "findings": [finding("R2-F1")],
                "assessments": [("R1-F1", "fix_verified")],
            },
            {
                "decision": "ready_for_owner_review",
                "assessments": [("R2-F1", "fix_verified")],
            },
        ]

        # Three actual reviews produce a handoff whose amendment status keys
        # cross a digit boundary (7 -> 10 on the reviewed candidate). No state
        # counters or publication records are fabricated to create this case.
        for number in range(1, 4):
            candidate = env.commit(
                "feature.txt", f"v{number + 1}\n", f"SIMULATED correction {number}"
            )
            env.push()
            dispositions = [] if number == 1 else [fixed(f"R{number - 1}-F1", candidate)]
            code, output, _ = self.review_cmd(env, dispositions=dispositions)
            self.assertEqual(ar.EXIT_OK, code, output)

        self.assertEqual("AWAITING_OWNER_REVIEW", self.finalize_cmd(env)[1]["status"])
        self.assertEqual({"final": 3}, self.state(env)["rounds_completed"])
        model_calls = (len(env.reviewer.calls), len(env.developer.calls))
        comments_before = len(env.gh.comments_list)
        controller = env.controller()

        def exit_after_amendment_save():
            raise SimulatedCrash("SIMULATED exit after the amendment transaction")

        controller._continue_after_resume = exit_after_amendment_save
        with self.assertRaises(SimulatedCrash):
            self.resume(
                controller,
                "owner amendment at the three-round cap",
                amendment=self.doc(env, "amendment-at-cap.md", self.A1),
            )

        expected_statuses = [
            "### Workflow — reopened — checkpoint final",
            "### Workflow — blocked — checkpoint final",
        ]
        first_recovery_comments = None
        for recovery in (1, 2):
            # A fresh controller on each pass reads the actual sorted-key state
            # file. The saved cap still forbids another review or model launch.
            with self.assertRaises(ar.UsageError):
                self.resume(env.controller(), "recover at the unchanged saved cap")

            state = self.state(env)
            comments = env.gh.comments_list[comments_before:]
            headings = [comment["body"].splitlines()[1] for comment in comments]
            markers = [comment["body"].splitlines()[0] for comment in comments]
            statuses = [
                heading
                for heading in headings
                if "Workflow — reopened" in heading or "Workflow — blocked" in heading
            ]

            with self.subTest(recovery=recovery):
                self.assertEqual("BLOCKED", state["status"])
                self.assertEqual(env.controller().budget_block_reason(), state["status_reason"])
                self.assertEqual({"final": 3}, state["rounds_completed"])
                self.assertEqual(
                    model_calls, (len(env.reviewer.calls), len(env.developer.calls))
                )
                self.assertTrue(env.controller().helper_authority_problems())
                self.assertEqual([], env.controller().status()["pending_publications"])
                self.assertEqual([], state.get("public_ops", []))
                self.assertEqual(len(markers), len(set(markers)))
                self.assertIn("handoff superseded by owner amendment 1", env.gh.body)
                if first_recovery_comments is not None:
                    self.assertEqual(first_recovery_comments, comments)
                self.assertEqual(expected_statuses, statuses)
                self.assertEqual(expected_statuses[-1], headings[-1])

            if first_recovery_comments is None:
                first_recovery_comments = [dict(comment) for comment in comments]

    def test_replacement_request_preserves_latest_reviewer_action(self):
        env = Env("headless")
        self.addCleanup(env.cleanup)
        flow = OwnerFlowFixture()
        target_advance = git(env.work, "rev-parse", "HEAD")

        def develop(fixture):
            fixture.commit("phase1.txt", "p1\n", "SIMULATED developer phase 1")
            fixture.push()
            stream = fixture.dir / "developer" / "stream-001.jsonl"
            stream.parent.mkdir(parents=True, exist_ok=True)
            stream.write_text(json.dumps({
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "OLDER-DEVELOPER-ACTION"}]},
            }) + "\n", encoding="utf-8")
            # Recorded timestamps have second precision. Allow the actual
            # reviewer invocation to begin in a later recorded second.
            time.sleep(1.1)
            return report(fixture, "phase-1")

        env.developer.script = [develop]
        original_review = env.reviewer.run

        def reviewer(prompt, workdir, schema, result_path, events_path, *args, **kwargs):
            result = original_review(prompt, workdir, schema, result_path, events_path, *args, **kwargs)
            path = Path(events_path)
            note = f"RETAINED-REVIEWER-{path.parent.name}-{path.stem}"
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": note},
                }) + "\n")
            return result

        env.reviewer.run = reviewer
        env.reviewer.script = [{"raw": "not JSON (SIMULATED model response)"}] * 3
        code, outcome = flow.run_command(env.controller())
        self.assertEqual(ar.EXIT_BLOCKED, code, outcome)
        before = flow.state(env)
        self.assertEqual(3, len(before["rounds"][-1]["attempts"]))
        candidate = git(env.work, "rev-parse", "HEAD")
        historical_events = env.dir / "rounds" / "r01" / "events-3.jsonl"
        historical_bytes = historical_events.read_bytes()
        calls_before = (len(env.developer.calls), len(env.reviewer.calls))
        self.assertEqual((1, 3), calls_before)

        expected_action = "Codex: RETAINED-REVIEWER-r01-events-3"
        rows_before = []
        ar.watch_enrollment(env.dir, rows_before.append, once=True)
        status_before = next(row for row in rows_before if " | latest action:" in row)
        self.assertIn("latest action: " + expected_action, status_before)

        # Fast-forward the temporary target to an ancestor of unchanged H.
        # The changed merge base forces a replacement review request; failure
        # to publish it pauses after that request is saved, before an attempt.
        git(env.work, "push", "--quiet", "origin", f"{target_advance}:refs/heads/master")
        env.gh.fail_next = env.controller().limits["publication_attempts"]
        code, outcome = flow.resume(env.controller(), "owner retries against advanced target")
        self.assertEqual(ar.EXIT_PAUSED, code, outcome)
        self.assertIn("publication of r02-request failed", outcome["reason"])
        after = flow.state(env)
        prior, replacement = after["rounds"][-2:]
        self.assertEqual((1, 2), (prior["round"], replacement["round"]))
        self.assertEqual("superseded", prior["status"])
        self.assertEqual([1, 2, 3], [attempt["n"] for attempt in prior["earlier_attempts"]])
        self.assertEqual([], replacement["attempts"])
        self.assertEqual(0, replacement["attempt_seq"])
        self.assertEqual((candidate, candidate), (prior["H"], replacement["H"]))
        self.assertNotEqual(prior["M"], replacement["M"])
        self.assertEqual(target_advance, replacement["M"])
        self.assertEqual(historical_bytes, historical_events.read_bytes())
        self.assertEqual(calls_before, (len(env.developer.calls), len(env.reviewer.calls)))
        self.assertEqual(before["rounds_completed"], after["rounds_completed"])

        rows_after = []
        ar.watch_enrollment(env.dir, rows_after.append, once=True)
        status_after = next(row for row in rows_after if " | latest action:" in row)
        self.assertIn("no agent running", status_after)
        self.assertIn(
            "latest action: " + expected_action + " (before this watch started)",
            status_after,
            "An empty replacement request must not hide the last actual reviewer execution.",
        )
        self.assertIn("(earlier) " + expected_action, rows_after)
        self.assertNotIn("latest action: Claude: OLDER-DEVELOPER-ACTION", status_after)


class ForegroundRoundNineVisibilityTests(ForegroundFixture, unittest.TestCase):
    """R8-F1 (owner-supplied): an acknowledged status that the comment listing omits leaves the public order unresolved; it never settles reuse of an older BLOCKED notice."""

    SINGLE = ForegroundRoundSevenTests.SINGLE
    capped_handoff = ForegroundRoundSevenTests.capped_handoff
    fail_body_edits = ForegroundRoundSevenTests.fail_body_edits
    amend = ForegroundRoundSevenTests.amend

    def recover_at_unchanged_cap(self, env):
        # A valid implementation can refuse at the cap after recovery, or pause
        # while a remote observation is unsettled. Neither authorizes work.
        try:
            code, output = self.resume(env.controller(), "recover at the unchanged saved cap")
        except ar.UsageError:
            return
        self.assertIn(code, (ar.EXIT_PAUSED, ar.EXIT_BLOCKED), output)

    @staticmethod
    def status_comments(env):
        return [
            comment for comment in env.gh.comments_list
            if comment["body"].splitlines()[1].startswith("### Workflow —")
        ]

    def test_acknowledged_paused_missing_from_listing_cannot_settle_stale_blocked(self):
        env = self.capped_handoff()
        before = self.state(env)
        rounds_before = dict(before["rounds_completed"])
        limit_before = before["limits"]["max_review_rounds_per_checkpoint"]
        calls_before = (len(env.reviewer.calls), len(env.developer.calls))

        # Real controller path: original BLOCKED is posted, a one-time simulated
        # GitHub PR-body edit failure displaces it, and PAUSED is accepted.
        self.fail_body_edits(env, 1)
        code, output = self.amend(env.controller(), env)
        self.assertEqual(ar.EXIT_PAUSED, code, output)
        state = self.state(env)
        paused = self.status_comments(env)[-1]
        self.assertIn("Workflow — paused", paused["body"])
        paused_id = paused["id"]
        matching_publications = [
            pub for pub in state["publications"].values()
            if any(part.get("comment_id") == paused_id for part in pub["parts"])
        ]
        self.assertEqual(1, len(matching_publications))
        self.assertEqual("posted", matching_publications[0]["state"])
        self.assertTrue(state["capped_amendment"]["restore_needed"])

        # SIMULATED eventual visibility: collection reads omit ONLY the PAUSED
        # ID despite the successful POST. Direct lookup remains available; the
        # implementation may safely use it, or persist a recoverable pause.
        original_comments = env.gh.comments
        env.gh.comments = lambda number: [
            comment for comment in original_comments(number) if comment["id"] != paused_id
        ]
        self.assertIsNotNone(env.gh.comment(paused_id))
        self.recover_at_unchanged_cap(env)
        state = self.state(env)
        expected_reason = env.controller().budget_block_reason()
        latest_body = self.status_comments(env)[-1]["body"]
        correct_public_blocker = "Workflow — blocked" in latest_body and expected_reason in latest_body
        queued_blocker = any(
            key.startswith("status-") and key.endswith("-blocked") and pub["state"] == "pending"
            for key, pub in state["publications"].items()
        )

        with self.subTest(stage="listing still omits acknowledged PAUSED"):
            self.assertIn(state["status"], ("PAUSED", "BLOCKED"))
            self.assertTrue(
                correct_public_blocker or state.get("capped_amendment", {}).get("restore_needed") or queued_blocker,
                "an acknowledged-but-unlisted status must not silently finalize reuse of an older BLOCKED notice",
            )
        self.assertTrue(env.controller().helper_authority_problems())
        self.assertEqual(rounds_before, state["rounds_completed"])
        self.assertEqual(limit_before, state["limits"]["max_review_rounds_per_checkpoint"])
        self.assertEqual(calls_before, (len(env.reviewer.calls), len(env.developer.calls)))

        # The collection now contains the acknowledged comment. Fresh controller
        # objects reload the saved state on each attempt; successful recovery must
        # leave the actual PR chronology correct, and the next resume adds none.
        env.gh.comments = original_comments
        comments_after_first_recovery = None
        for recovery in (1, 2):
            self.recover_at_unchanged_cap(env)
            state = self.state(env)
            ctl = env.controller()
            latest_body = self.status_comments(env)[-1]["body"]
            markers = [comment["body"].splitlines()[0] for comment in env.gh.comments_list]
            with self.subTest(stage="acknowledged comment visible", recovery=recovery):
                self.assertEqual(("BLOCKED", expected_reason), (state["status"], state["status_reason"]))
                self.assertIn("Workflow — blocked", latest_body)
                self.assertIn(expected_reason, latest_body)

            self.assertEqual([], ctl.status()["pending_publications"])
            self.assertEqual([], state.get("public_ops", []))
            self.assertTrue(ctl.helper_authority_problems())
            self.assertEqual(rounds_before, state["rounds_completed"])
            self.assertEqual(limit_before, state["limits"]["max_review_rounds_per_checkpoint"])
            self.assertEqual(calls_before, (len(env.reviewer.calls), len(env.developer.calls)))
            self.assertEqual(len(markers), len(set(markers)), "one public comment per durable marker")
            self.assertIn("handoff superseded by owner amendment 1", env.gh.body)
            if comments_after_first_recovery is None:
                comments_after_first_recovery = len(env.gh.comments_list)
            else:
                self.assertEqual(comments_after_first_recovery, len(env.gh.comments_list),
                                 "recovery after success must not create another correction")


class ForegroundRoundNineIntegrityTests(ForegroundFixture, unittest.TestCase):
    """R8-F2 (owner-supplied): a notice is reused only when its visible body still matches the preserved outbox body; an intact delayed notice that really posts last is reused without reposting."""

    SINGLE = ForegroundRoundSevenTests.SINGLE
    capped_handoff = ForegroundRoundSevenTests.capped_handoff
    fail_body_edits = ForegroundRoundSevenTests.fail_body_edits
    fail_blocked_posts = ForegroundRoundSevenTests.fail_blocked_posts
    amend = ForegroundRoundSevenTests.amend

    def pending_blocker(self):
        env = self.capped_handoff()
        initial = self.state(env)
        counts = (len(env.reviewer.calls), len(env.developer.calls))
        rounds = dict(initial["rounds_completed"])
        authorized = initial["limits"]["max_review_rounds_per_checkpoint"]

        # The amendment's PR-body edit fails, then the restoration's BLOCKED
        # POST fails. Its following PAUSED POST succeeds. The next ordinary
        # resume will therefore deliver the preserved BLOCKED notice last.
        self.fail_body_edits(env, 1)
        code, output = self.amend(env.controller(), env)
        self.assertEqual(ar.EXIT_PAUSED, code, output)
        original_post = env.gh.post_comment
        self.fail_blocked_posts(env, env.controller().limits["publication_attempts"])
        code, output = self.resume(env.controller(), "SIMULATED restored-notice publication outage")
        self.assertEqual(ar.EXIT_PAUSED, code, output)
        env.gh.post_comment = original_post

        state = self.state(env)
        marker = state["capped_amendment"]
        key = marker["notice_key"]
        publication = state["publications"][key]
        self.assertEqual("PAUSED", state["status"])
        self.assertTrue(marker["restore_needed"])
        self.assertEqual("pending", publication["state"])
        self.assertEqual(1, len(publication["parts"]))
        part = publication["parts"][0]
        self.assertIsNone(part["comment_id"])
        self.assertEqual([key], [k for k, p in state["publications"].items() if p["state"] == "pending"])
        self.assertIn("Workflow — paused", self.status_comments(env)[-1]["body"])
        self.assertFalse(any(c["body"].startswith(part["marker"]) for c in env.gh.comments_list))
        preserved = env.controller().outbox_body(key, part)
        reason = env.controller().budget_block_reason()
        self.assertIn(reason, preserved)
        return env, key, part["marker"], preserved, reason, counts, rounds, authorized

    @staticmethod
    def status_comments(env):
        return [c for c in env.gh.comments_list
                if len(c["body"].splitlines()) > 1
                and c["body"].splitlines()[1].startswith("### Workflow —")]

    def recover(self, env):
        try:
            code, output = self.resume(env.controller(), "SIMULATED GitHub recovery at unchanged cap")
            return {"exit_code": code, "output": output}
        except ar.UsageError as exc:
            return {"usage_error": str(exc)}

    def assert_authority_unchanged(self, env, counts, rounds, authorized):
        state = self.state(env)
        self.assertEqual(rounds, state["rounds_completed"])
        self.assertEqual(authorized, state["limits"]["max_review_rounds_per_checkpoint"])
        self.assertEqual(counts, (len(env.reviewer.calls), len(env.developer.calls)))
        self.assertTrue(env.controller().helper_authority_problems())
        self.assertIsNone(state.get("handoff"))

    def is_intact_budget_notice(self, env, comment, reason):
        """Check the public result against the controller's preserved message."""
        state = self.state(env)
        for key, publication in state["publications"].items():
            if not key.startswith("status-"):
                continue
            for part in publication["parts"]:
                if part.get("comment_id") != comment["id"]:
                    continue
                expected = env.controller().outbox_body(key, part)
                return (comment.get("user") == env.controller().cfg["expected_actor"]
                        and comment["body"].startswith(part["marker"])
                        and ar.normalize_body(comment["body"]) == ar.normalize_body(expected)
                        and "Workflow — blocked" in comment["body"].splitlines()[1]
                        and reason in comment["body"])
        return False

    def test_intact_delayed_blocked_notice_can_be_reused_without_reposting(self):
        env, key, marker, preserved, reason, counts, rounds, authorized = self.pending_blocker()
        comments_after_recovery = None
        for _ in range(2):
            self.recover(env)
            state = self.state(env)
            latest = self.status_comments(env)[-1]
            self.assertEqual(("BLOCKED", reason), (state["status"], state["status_reason"]))
            self.assertFalse(state["capped_amendment"]["restore_needed"])
            self.assertEqual(key, state["capped_amendment"]["notice_key"])
            self.assertEqual(preserved, latest["body"])
            self.assertTrue(self.is_intact_budget_notice(env, latest, reason))
            self.assertEqual(1, sum(c["body"].startswith(marker) for c in env.gh.comments_list))
            self.assertEqual([], [k for k, p in state["publications"].items() if p["state"] == "pending"])
            if comments_after_recovery is None:
                comments_after_recovery = len(env.gh.comments_list)
            else:
                self.assertEqual(comments_after_recovery, len(env.gh.comments_list))
            self.assert_authority_unchanged(env, counts, rounds, authorized)

    def test_edited_visible_body_cannot_complete_recovery_by_id_and_marker_alone(self):
        env, key, marker, preserved, reason, counts, rounds, authorized = self.pending_blocker()
        original_post = env.gh.post_comment
        edited = {}
        wrong_reason = "SIMULATED REMOTE EDIT: the saved budget reason was removed."

        def post_then_simulate_edit(number, body_file):
            response = original_post(number, body_file)
            comment = next(c for c in env.gh.comments_list if c["id"] == response["id"])
            if not edited and comment["body"].startswith(marker):
                # External edit after GitHub accepted the preserved notice,
                # before recovery decides whether it can reuse that notice.
                # The author, id, heading, and COMPLETE hidden marker survive.
                self.assertEqual(preserved, comment["body"])
                self.assertIn(reason, comment["body"])
                edited.update(id=comment["id"], user=comment["user"], original_body=comment["body"])
                comment["body"] = comment["body"].replace(reason, wrong_reason, 1)
                edited["edited_body"] = comment["body"]
                self.assertEqual(marker, comment["body"].splitlines()[0])
                self.assertNotIn(reason, comment["body"])
            return response

        env.gh.post_comment = post_then_simulate_edit
        self.observation = {"notice_key": key, "expected_reason": reason, "recoveries": []}
        for recovery in (1, 2):
            outcome = self.recover(env)
            state = self.state(env)
            latest = self.status_comments(env)[-1]
            self.assertTrue(edited, "the delayed BLOCKED notice must actually be posted and edited")
            edited_remote = next(c for c in env.gh.comments_list if c["id"] == edited["id"])
            self.assertEqual(edited["user"], edited_remote["user"])
            self.assertEqual(edited["edited_body"], edited_remote["body"],
                             "the controller must preserve the existing public comment")
            self.assertEqual(marker, edited_remote["body"].splitlines()[0])
            corrected = self.is_intact_budget_notice(env, latest, reason)
            self.observation["recoveries"].append({
                "recovery": recovery, "outcome": outcome, "state_status": state["status"],
                "state_reason": state["status_reason"],
                "restore_needed": state["capped_amendment"]["restore_needed"],
                "latest_comment_id": latest["id"], "latest_body": latest["body"],
                "edited_comment_id": edited["id"], "full_marker_preserved": True,
                "corrective_notice_present": corrected,
            })
            self.assert_authority_unchanged(env, counts, rounds, authorized)

            with self.subTest(recovery=recovery):
                if corrected:
                    # An independently preserved corrective comment is permitted.
                    self.assertNotEqual(edited["id"], latest["id"])
                    self.assertEqual(("BLOCKED", reason), (state["status"], state["status_reason"]))
                    self.assertFalse(state["capped_amendment"]["restore_needed"])
                else:
                    # The existing publication-integrity stop is also permitted:
                    # an altered body must not be treated as successful recovery.
                    self.assertTrue(state["capped_amendment"]["restore_needed"],
                                    "the public reason was edited, but recovery was falsely marked complete")
                    self.assertIn(state["status"], ("BLOCKED", "PAUSED"))
                    self.assertRegex(state["status_reason"].lower(), r"comment|publication|message|body")
                    self.assertRegex(state["status_reason"].lower(), r"differ|integrity|alter|mismatch|modif|duplicat|corrupt")


class WatchRoundNineUnlaunchedTests(unittest.TestCase):
    """R8-F3 (owner-supplied): an attempt recorded as launched=false is not an execution for watch; records without the field and a genuinely open attempt are unaffected. The directory faults stay present during the tests."""

    ACTION = "ACTUAL-DEVELOPER-BEFORE-UNLAUNCHED-REVIEWER"

    def _environment(self):
        env = Env("headless")
        self.addCleanup(env.cleanup)
        return env, OwnerFlowFixture()

    def _developer(self, env, separate_second=True):
        def develop(fixture):
            fixture.commit("phase1.txt", "p1\n", "SIMULATED developer phase 1")
            fixture.push()
            stream = fixture.dir / "developer" / "stream-001.jsonl"
            stream.parent.mkdir(parents=True, exist_ok=True)
            stream.write_text(json.dumps({
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": self.ACTION}]},
            }) + "\n", encoding="utf-8")
            # The actual launch/attempt records use second precision. This
            # makes the later reviewer attempt unambiguously later without
            # changing saved state or substituting controller timestamps.
            if separate_second:
                time.sleep(1.1)
            return report(fixture, "phase-1")
        env.developer.script = [develop]

    def _stream_failure(self, env, invoke, fault, round_number):
        obstacle = env.dir / "rounds" / f"r{round_number:02d}" / fault
        obstacle.mkdir(parents=True)
        ctl = env.controller()
        executable = str(env.root / "never-started.exe")
        ctl._reviewer = ar.CodexReviewer({**ctl.cfg["reviewer"], "executable": executable})
        self.assertEqual(executable, ctl._reviewer.exe)
        original_popen = subprocess.Popen
        process_dispatches = []

        def guarded_popen(argv, *args, **kwargs):
            # The only intercepted external process is this test's Codex
            # executable. Real Git and controller subprocesses still run.
            if isinstance(argv, (list, tuple)) and str(argv[0]) == executable:
                process_dispatches.append(list(argv))
                raise AssertionError("Reviewer stream failure must precede process creation")
            return original_popen(argv, *args, **kwargs)

        with mock.patch.object(subprocess, "Popen", side_effect=guarded_popen):
            code, outcome = invoke(ctl)
        self.assertEqual(ar.EXIT_BLOCKED, code, outcome)
        self.assertIn(f"reviewer launch setup for round {round_number} failed", outcome["reason"])
        self.assertEqual([], process_dispatches, "no reviewer process was even dispatched")
        state = ar.read_json(env.dir / "state.json")
        attempt = state["rounds"][-1]["attempts"][-1]
        self.assertIs(False, attempt["launched"])
        self.assertIn("ended", attempt)
        self.assertNotIn("pid", attempt)
        self.assertTrue(obstacle.is_dir(), "the triggering filesystem fault must remain present")
        return state, obstacle

    def _historical_action(self, env, expected):
        state = ar.read_json(env.dir / "state.json")
        before = (env.dir / "state.json").read_bytes()
        calls = (len(env.developer.calls), len(env.reviewer.calls))
        rows = []
        try:
            ar.watch_enrollment(env.dir, rows.append, once=True)
        finally:
            self.assertEqual(before, (env.dir / "state.json").read_bytes())
            self.assertEqual(calls, (len(env.developer.calls), len(env.reviewer.calls)))
        status = next(row for row in rows if " | latest action:" in row)
        self.assertTrue(status.startswith(state["status"] + "/"), status)
        self.assertIn("no agent running", status)
        self.assertIn("blocker: " + ar.clean_text(state["status_reason"], 300), status)
        self.assertIn("latest action: " + expected + " (before this watch started)", status)
        self.assertIn("(earlier) " + expected, rows)

    def _unlaunched_then_replacement(self, fault):
        env, flow = self._environment()
        target_advance = git(env.work, "rev-parse", "HEAD")
        self._developer(env)
        initial, obstacle = self._stream_failure(env, flow.run_command, fault, 1)
        self.assertEqual((1, 0), (len(env.developer.calls), len(env.reviewer.calls)))

        # Check the watcher while the original failure and its blocker are
        # still present, then after resume preserves this attempt as history.
        with self.subTest(stage="initial closed unlaunched attempt"):
            self._historical_action(env, "Claude: " + self.ACTION)

        git(env.work, "push", "--quiet", "origin", f"{target_advance}:refs/heads/master")
        env.gh.fail_next = env.controller().limits["publication_attempts"]
        code, outcome = flow.resume(env.controller(), "owner retries against advanced target")
        self.assertEqual(ar.EXIT_PAUSED, code, outcome)
        self.assertIn("publication of r02-request failed", outcome["reason"])
        after = flow.state(env)
        prior, replacement = after["rounds"][-2:]
        self.assertEqual((1, 2), (prior["round"], replacement["round"]))
        self.assertEqual("superseded", prior["status"])
        self.assertEqual([False], [a["launched"] for a in prior["earlier_attempts"]])
        self.assertEqual([], replacement["attempts"])
        self.assertEqual(0, replacement["attempt_seq"])
        self.assertEqual(initial["rounds_completed"], after["rounds_completed"])
        self.assertEqual((1, 0), (len(env.developer.calls), len(env.reviewer.calls)))
        self.assertTrue(obstacle.is_dir())
        with self.subTest(stage="unlaunched history before empty replacement request"):
            self._historical_action(env, "Claude: " + self.ACTION)

    def test_event_directory_fault_does_not_crash_watch_before_or_after_replacement(self):
        self._unlaunched_then_replacement("events-1.jsonl")

    def test_stderr_directory_fault_does_not_replace_latest_real_action_with_none(self):
        # Codex opens its events stream first, then fails opening stderr. The
        # empty event file exists, but no reviewer execution occurred.
        self._unlaunched_then_replacement("stderr-1.txt")

    def test_newer_unlaunched_round_does_not_hide_older_executed_reviewer_attempt(self):
        env, flow = self._environment()
        target_advance = git(env.work, "rev-parse", "HEAD")
        self._developer(env)
        original_review = env.reviewer.run

        def reviewer(prompt, workdir, schema, result_path, events_path, *args, **kwargs):
            result = original_review(prompt, workdir, schema, result_path, events_path, *args, **kwargs)
            path = Path(events_path)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": "ACTUAL-REVIEWER-" + path.stem},
                }) + "\n")
            return result

        env.reviewer.run = reviewer
        env.reviewer.script = [{"raw": "not JSON (SIMULATED model response)"}] * 3
        code, outcome = flow.run_command(env.controller())
        self.assertEqual(ar.EXIT_BLOCKED, code, outcome)
        initial = flow.state(env)
        self.assertEqual(3, len(initial["rounds"][-1]["attempts"]))
        for attempt in initial["rounds"][-1]["attempts"]:
            # This is the real persisted shape of a completed execution; do
            # not require launched=True, since ordinary/older attempts omit it.
            self.assertIn("ended", attempt)
            self.assertNotIn("launched", attempt)
        self.assertEqual((1, 3), (len(env.developer.calls), len(env.reviewer.calls)))
        self._historical_action(env, "Codex: ACTUAL-REVIEWER-events-3")

        git(env.work, "push", "--quiet", "origin", f"{target_advance}:refs/heads/master")
        after, obstacle = self._stream_failure(
            env, lambda ctl: flow.resume(ctl, "retry against advanced target"), "stderr-1.txt", 2
        )
        self.assertEqual([1, 2, 3], [a["n"] for a in after["rounds"][-2]["earlier_attempts"]])
        self.assertEqual(initial["rounds_completed"], after["rounds_completed"])
        self.assertEqual((1, 3), (len(env.developer.calls), len(env.reviewer.calls)))
        self.assertTrue(obstacle.is_dir())
        self._historical_action(env, "Codex: ACTUAL-REVIEWER-events-3")

    def test_open_attempt_without_events_still_has_current_reviewer_role(self):
        env, flow = self._environment()
        self._developer(env, separate_second=False)
        observed = []

        def during_reviewer():
            state = flow.state(env)
            attempt = state["rounds"][-1]["attempts"][-1]
            self.assertNotIn("ended", attempt)
            self.assertNotIn("launched", attempt)
            self.assertFalse((env.dir / "rounds" / "r01" / "events-1.jsonl").exists())
            rows = []
            before = flow.state_bytes(env)
            ar.watch_enrollment(env.dir, rows.append, once=True)
            self.assertEqual(before, flow.state_bytes(env))
            status = next(row for row in rows if " | latest action:" in row)
            self.assertIn("reviewer Codex, round 1 attempt 1", status)
            self.assertIn("latest action: none observed yet in this attempt", status)
            self.assertNotIn("latest action: Claude: " + self.ACTION, status)
            observed.append(status)

        env.reviewer.during_run = during_reviewer
        env.reviewer.script = [{"decision": "blocked"}]
        code, outcome = flow.run_command(env.controller())
        self.assertEqual(ar.EXIT_BLOCKED, code, outcome)
        self.assertEqual(1, len(observed))
        self.assertEqual((1, 1), (len(env.developer.calls), len(env.reviewer.calls)))


class ForegroundRoundTenTests(ForegroundFixture, unittest.TestCase):
    """Round-10 corrections (PR #7): the status-notice reuse decision applies the controller's established publication
    check (CRLF-only differences are intact; a competing copy of the marker is a conflict); a continuing watch keeps an
    execution that had already finished at attachment historical when selection first reaches it later; the status
    line names a last reviewed candidate only from an accepted review."""

    SINGLE = ForegroundRoundSevenTests.SINGLE
    capped_handoff = ForegroundRoundSevenTests.capped_handoff
    fail_body_edits = ForegroundRoundSevenTests.fail_body_edits
    fail_blocked_posts = ForegroundRoundSevenTests.fail_blocked_posts
    amend = ForegroundRoundSevenTests.amend
    pending_blocker = ForegroundRoundNineIntegrityTests.pending_blocker
    status_comments = staticmethod(ForegroundRoundNineIntegrityTests.status_comments)
    recover = ForegroundRoundNineIntegrityTests.recover
    assert_authority_unchanged = ForegroundRoundNineIntegrityTests.assert_authority_unchanged
    is_intact_budget_notice = ForegroundRoundNineIntegrityTests.is_intact_budget_notice

    def test_a_crlf_only_delayed_notice_is_reused(self):
        env, key, marker, preserved, reason, counts, rounds, authorized = self.pending_blocker()
        original_post = env.gh.post_comment

        def post_with_crlf(number, body_file):  # SIMULATED: GitHub returns this notice's body with CRLF line endings
            response = original_post(number, body_file)
            comment = next(c for c in env.gh.comments_list if c["id"] == response["id"])
            if comment["body"].startswith(marker):
                comment["body"] = comment["body"].replace("\n", "\r\n")
            return response
        env.gh.post_comment = post_with_crlf
        comments_after_recovery = None
        for recovery in (1, 2):
            with self.subTest(recovery=recovery):
                self.recover(env)
                state = self.state(env)
                latest = self.status_comments(env)[-1]
                self.assertEqual(("BLOCKED", reason), (state["status"], state["status_reason"]))
                self.assertFalse(state["capped_amendment"]["restore_needed"])
                self.assertEqual(key, state["capped_amendment"]["notice_key"])  # reused, no correction queued
                self.assertTrue(latest["body"].startswith(marker + "\r\n"))
                self.assertEqual(ar.normalize_body(preserved), ar.normalize_body(latest["body"]))
                self.assertEqual(1, sum(c["body"].startswith(marker) for c in env.gh.comments_list))
                self.assertEqual([], [k for k, p in state["publications"].items() if p["state"] == "pending"])
                if comments_after_recovery is None:
                    comments_after_recovery = len(env.gh.comments_list)
                self.assertEqual(comments_after_recovery, len(env.gh.comments_list))
                self.assert_authority_unchanged(env, counts, rounds, authorized)

    def test_a_competing_copy_of_the_marker_forces_a_correction_or_an_integrity_stop(self):
        env, key, marker, preserved, reason, counts, rounds, authorized = self.pending_blocker()
        original_post = env.gh.post_comment
        competing = {}

        def post_then_competing_copy(number, body_file):
            response = original_post(number, body_file)
            body = Path(body_file).read_text(encoding="utf-8")
            if not competing and body.startswith(marker):
                # SIMULATED: a later comment by the expected actor, under another id, repeats the complete marker
                # with a different reason
                env.gh.next_id += 1
                competing.update(id=env.gh.next_id,
                                 body=body.replace(reason, "SIMULATED COMPETING COPY: a different reason.", 1))
                env.gh.comments_list.append({"id": competing["id"], "user": env.gh.poster, "body": competing["body"],
                                             "url": f"https://example.test/c/{competing['id']}"})
            return response
        env.gh.post_comment = post_then_competing_copy
        comments_after_recovery = None
        for recovery in (1, 2):
            with self.subTest(recovery=recovery):
                self.recover(env)
                state = self.state(env)
                self.assertTrue(competing, "the delayed notice must be posted and then copied")
                copy = next(c for c in env.gh.comments_list if c["id"] == competing["id"])
                self.assertEqual(competing["body"], copy["body"])  # the controller never edits public history
                latest = self.status_comments(env)[-1]
                if self.is_intact_budget_notice(env, latest, reason) and latest["id"] != competing["id"]:
                    self.assertFalse(latest["body"].startswith(marker))  # a distinct correction, not the copied one
                    self.assertNotEqual(key, state["capped_amendment"]["notice_key"])
                    self.assertEqual(("BLOCKED", reason), (state["status"], state["status_reason"]))
                    self.assertFalse(state["capped_amendment"]["restore_needed"])
                else:
                    self.assertTrue(state["capped_amendment"]["restore_needed"])
                    self.assertRegex(state["status_reason"].lower(), r"duplicat|altered|integrity")
                if comments_after_recovery is None:
                    comments_after_recovery = len(env.gh.comments_list)
                self.assertEqual(comments_after_recovery, len(env.gh.comments_list))
                self.assert_authority_unchanged(env, counts, rounds, authorized)

    # ---- watch
    def unlaunched_request(self, env, flow, invoke, round_number):
        """A reviewer request whose first attempt is saved open and then closed launched=false at stream setup (real
        CodexReviewer; a directory occupies its stderr path; the test's Codex executable is never started)."""
        obstacle = env.dir / "rounds" / f"r{round_number:02d}" / f"stderr-1.txt"
        obstacle.mkdir(parents=True)
        ctl = env.controller()
        executable = str(env.root / "never-started.exe")
        ctl._reviewer = ar.CodexReviewer({**ctl.cfg["reviewer"], "executable": executable})
        original_popen, dispatched = subprocess.Popen, []

        def guarded_popen(argv, *args, **kwargs):
            if isinstance(argv, (list, tuple)) and str(argv[0]) == executable:
                dispatched.append(list(argv))
                raise AssertionError("the reviewer stream failure must precede process creation")
            return original_popen(argv, *args, **kwargs)
        with mock.patch.object(subprocess, "Popen", side_effect=guarded_popen):
            result = invoke(ctl)
        self.assertEqual([], dispatched)
        attempt = self.state(env)["rounds"][-1]["attempts"][-1]
        self.assertIs(False, attempt["launched"])
        self.assertTrue(obstacle.is_dir())
        return result

    def headless_history(self):
        """Headless developer invocation, then three executed (failed) reviewer attempts that write events."""
        env, flow = Env("headless"), OwnerFlowFixture()
        self.addCleanup(env.cleanup)
        target = git(env.work, "rev-parse", "HEAD")

        def develop(fixture):
            fixture.commit("phase1.txt", "p1\n", "SIMULATED developer phase 1")
            fixture.push()
            stream = fixture.dir / "developer" / "stream-001.jsonl"
            stream.parent.mkdir(parents=True, exist_ok=True)
            stream.write_text(json.dumps({"type": "assistant", "message": {"content": [
                {"type": "text", "text": "DEVELOPER-ACTION"}]}}) + "\n", encoding="utf-8")
            time.sleep(1.1)  # the reviewer attempts start in a later recorded second
            return report(fixture, "phase-1")
        env.developer.script = [develop]
        original_review = env.reviewer.run

        def reviewer(prompt, workdir, schema, result_path, events_path, *args, **kwargs):
            result = original_review(prompt, workdir, schema, result_path, events_path, *args, **kwargs)
            with Path(events_path).open("a", encoding="utf-8") as stream:  # SIMULATED reviewer activity
                stream.write(json.dumps({"type": "item.completed", "item": {
                    "type": "agent_message", "text": "REVIEWER-" + Path(events_path).stem}}) + "\n")
            return result
        env.reviewer.run = reviewer
        env.reviewer.script = [{"raw": "not JSON (SIMULATED model response)"}] * 3
        code, outcome = flow.run_command(env.controller())
        self.assertEqual(ar.EXIT_BLOCKED, code, outcome)
        git(env.work, "push", "--quiet", "origin", f"{target}:refs/heads/master")  # the merge base changes at same H
        return env, flow

    def test_a_continuing_watch_keeps_an_earlier_round_historical_after_a_failed_launch(self):
        env, flow = self.headless_history()
        history = env.dir / "rounds" / "r01" / "events-3.jsonl"
        history_bytes = history.read_bytes()
        rows, problems, attached, release = [], [], threading.Event(), threading.Event()

        def gated_sleep(_):
            attached.set()
            release.wait(30)

        def watch():
            try:
                ar.watch_enrollment(env.dir, rows.append, interval=0, sleep=gated_sleep, max_polls=5)
            except BaseException as exc:  # reported by the test thread
                problems.append(exc)
        thread = threading.Thread(target=watch, daemon=True)

        def invoke(ctl):
            original_run = ctl._reviewer.run

            def run(*args, **kwargs):  # the replacement attempt is saved open: one watch attaches here
                thread.start()
                self.assertTrue(attached.wait(30), "the watch must complete its first poll")
                return original_run(*args, **kwargs)
            ctl._reviewer.run = run
            return flow.resume(ctl, "owner retries against the advanced target")
        code, outcome = self.unlaunched_request(env, flow, invoke, 2)
        self.assertEqual(ar.EXIT_BLOCKED, code, outcome)
        release.set()
        thread.join(30)
        self.assertFalse(thread.is_alive())
        self.assertEqual([], problems)
        self.assertEqual(history_bytes, history.read_bytes())
        attach = next(i for i, r in enumerate(rows) if " | latest action:" in r)
        self.assertIn("reviewer Codex, round 2 attempt 1", rows[attach])  # attached while the attempt was open
        later = rows[attach + 1:]
        self.assertIn("(earlier) Codex: REVIEWER-events-3", later)
        self.assertNotIn("Codex: REVIEWER-events-3", later)  # never replayed as live activity
        status = [r for r in later if " | latest action:" in r][-1]
        self.assertIn("no agent running", status)
        self.assertIn("latest action: Codex: REVIEWER-events-3 (before this watch started)", status)
        self.assertIn("blocker: " + ar.clean_text(self.state(env)["status_reason"], 300), status)
        self.assertIn("reviewer launch setup for round 2 failed", status)

    def test_the_status_line_never_presents_an_unlaunched_request_as_reviewed(self):
        with self.subTest(case="first request, never launched"):
            env, flow = Env("headless"), OwnerFlowFixture()
            self.addCleanup(env.cleanup)

            def develop(fixture):
                fixture.commit("phase1.txt", "p1\n", "SIMULATED developer phase 1")
                fixture.push()
                return report(fixture, "phase-1")
            env.developer.script = [develop]
            code, outcome = self.unlaunched_request(env, flow, flow.run_command, 1)
            self.assertEqual(ar.EXIT_BLOCKED, code, outcome)
            h = self.state(env)["rounds"][-1]["H"][:12]
            rows = []
            ar.watch_enrollment(env.dir, rows.append, once=True)
            status = next(r for r in rows if " | latest action:" in r)
            self.assertIn(f"(no accepted review yet; requested {h}: not reviewed: no reviewer launched)", status)
            self.assertNotIn("last reviewed", status)
        with self.subTest(case="an unlaunched request after an accepted review"):
            env = self.fg_env()
            env.commit("feature.txt", "v2\n", "feature v2")
            env.push()
            env.reviewer.script = [{"decision": "changes_required", "findings": [finding("R1-F1")]}]
            self.assertEqual("changes_required", self.review_cmd(env)[1]["result"])
            first = self.state(env)["rounds"][-1]["H"][:12]
            candidate = env.commit("feature.txt", "v3\n", "feature v3")
            env.push()
            code, out, _ = self.unlaunched_request(
                env, None, lambda ctl: self.review_cmd(env, dispositions=[fixed("R1-F1", candidate)], ctl=ctl), 2)
            self.assertEqual(ar.EXIT_BLOCKED, code, out)
            rows = []
            ar.watch_enrollment(env.dir, rows.append, once=True)
            status = next(r for r in rows if " | latest action:" in r)
            self.assertIn(f"(last reviewed {first}: changes_required; requested {candidate[:12]}: not reviewed: no "
                          "reviewer launched)", status)
            self.assertEqual({"final": 1}, self.state(env)["rounds_completed"])


class ForegroundRoundElevenIdentityTests(ForegroundFixture, unittest.TestCase):
    """R10-F1 (owner-supplied): the recorded comment id, expected actor, complete marker and normalized preserved body
    must identify the same unique comment, at status-notice reuse, verdict acceptance and handoff revalidation."""

    SINGLE = ForegroundRoundSevenTests.SINGLE
    capped_handoff = ForegroundRoundSevenTests.capped_handoff
    fail_body_edits = ForegroundRoundSevenTests.fail_body_edits
    fail_blocked_posts = ForegroundRoundSevenTests.fail_blocked_posts
    amend = ForegroundRoundSevenTests.amend
    pending_blocker = ForegroundRoundNineIntegrityTests.pending_blocker
    status_comments = staticmethod(ForegroundRoundNineIntegrityTests.status_comments)
    recover = ForegroundRoundNineIntegrityTests.recover
    assert_authority_unchanged = ForegroundRoundNineIntegrityTests.assert_authority_unchanged
    is_intact_budget_notice = ForegroundRoundNineIntegrityTests.is_intact_budget_notice

    # Preserve the existing positive control without inheriting its other tests.
    test_crlf_only_intact_notice_is_still_reused = (
        ForegroundRoundTenTests.test_a_crlf_only_delayed_notice_is_reused
    )

    def simulate_cross_comment_conflict(self, env, comment, marker, copied_body):
        """External edit and external expected-actor post, with distinct IDs."""
        original_body = comment["body"]
        self.assertTrue(original_body.startswith(marker))
        self.assertTrue(copied_body.startswith(marker))
        self.assertNotEqual(ar.normalize_body(original_body), ar.normalize_body(copied_body))
        comment["body"] = "\n" + original_body
        self.assertEqual(ar.normalize_body(original_body), ar.normalize_body(comment["body"]))
        self.assertFalse(comment["body"].startswith(marker))
        env.gh.next_id += 1
        rival = {"id": env.gh.next_id, "user": env.gh.poster, "body": copied_body,
                 "url": f"https://example.test/c/{env.gh.next_id}"}
        env.gh.comments_list.append(rival)
        self.assertEqual(env.controller().cfg["expected_actor"], rival["user"])
        self.assertNotEqual(comment["id"], rival["id"])
        matches = [c for c in env.gh.comments_list
                   if c["user"] == rival["user"] and c["body"].startswith(marker)]
        self.assertEqual([rival["id"]], [c["id"] for c in matches])
        return {"recorded_id": comment["id"], "recorded_body": comment["body"],
                "rival_id": rival["id"], "rival_body": rival["body"]}

    def test_delayed_notice_cannot_borrow_another_comments_marker(self):
        env, key, marker, preserved, reason, counts, rounds, authorized = self.pending_blocker()
        original_post, conflict = env.gh.post_comment, {}

        def post_then_edit_and_copy(number, body_file):
            response = original_post(number, body_file)
            comment = next(c for c in env.gh.comments_list if c["id"] == response["id"])
            if not conflict and comment["body"].startswith(marker):
                self.assertEqual(preserved, comment["body"])
                copied_body = preserved.replace(
                    reason, "SIMULATED COMPETING COPY: a different reason.", 1
                )
                conflict.update(self.simulate_cross_comment_conflict(env, comment, marker, copied_body))
            return response

        env.gh.post_comment = post_then_edit_and_copy
        self.observation = {"case": "capped recovery", "notice_key": key, "recoveries": []}
        comments_after_recovery = None
        for recovery in (1, 2):
            outcome = self.recover(env)
            state = self.state(env)
            self.assertTrue(conflict, "the delayed notice must actually be posted, edited and copied")
            recorded = next(c for c in env.gh.comments_list if c["id"] == conflict["recorded_id"])
            rival = next(c for c in env.gh.comments_list if c["id"] == conflict["rival_id"])
            self.assertEqual(conflict["recorded_body"], recorded["body"])
            self.assertEqual(conflict["rival_body"], rival["body"])
            latest = self.status_comments(env)[-1]
            corrected = self.is_intact_budget_notice(env, latest, reason)
            self.observation["recoveries"].append({
                "recovery": recovery, "outcome": outcome, "status": state["status"],
                "reason": state["status_reason"],
                "restore_needed": state["capped_amendment"]["restore_needed"],
                "recorded_id": recorded["id"], "rival_id": rival["id"],
                "latest_id": latest["id"], "latest_body": latest["body"],
                "corrected": corrected,
            })
            self.assert_authority_unchanged(env, counts, rounds, authorized)
            with self.subTest(recovery=recovery):
                if corrected:
                    self.assertNotIn(latest["id"], (recorded["id"], rival["id"]))
                    self.assertNotEqual(key, state["capped_amendment"]["notice_key"])
                    self.assertEqual(("BLOCKED", reason), (state["status"], state["status_reason"]))
                    self.assertFalse(state["capped_amendment"]["restore_needed"])
                else:
                    self.assertTrue(state["capped_amendment"]["restore_needed"],
                                    "recovery falsely settled using different comments for identity and marker")
                    self.assertRegex(state["status_reason"].lower(), r"duplicat|alter|integrity|conflict|mismatch")
            if comments_after_recovery is None:
                comments_after_recovery = len(env.gh.comments_list)
            else:
                self.assertEqual(comments_after_recovery, len(env.gh.comments_list),
                                 "repeat recovery must not keep adding corrective notices")

    def test_verdict_publication_conflict_prevents_round_acceptance(self):
        env = self.fg_env()
        candidate = env.commit("feature.txt", "v2\n", "feature v2")
        env.push()
        env.reviewer.script = [{"decision": "ready_for_owner_review"}]
        conflict = {}

        def after_verdict_post(comment):
            # The model really returned ready_for_owner_review. The fault is
            # solely in publishing that genuine result, not a forged local
            # model response or candidate. GitHub acknowledges its real ID.
            if not conflict and " key=r01-review " in comment["body"].splitlines()[0]:
                body = comment["body"]
                marker = body.splitlines()[0]
                conflict.update(self.simulate_cross_comment_conflict(
                    env, comment, marker,
                    body + "\nSIMULATED COMPETING COPY: a different result is claimed here.\n"
                ))

        env.gh.on_post = after_verdict_post
        code, outcome, stderr = self.review_cmd(env)
        state = self.state(env)
        self.assertTrue(conflict, "the actual verdict POST must be reached and then externally conflicted")
        self.assertEqual((1, 0), (len(env.reviewer.calls), len(env.developer.calls)))
        rnd = state["rounds"][-1]
        self.assertEqual(candidate, rnd["H"])
        publication = state["publications"]["r01-review"]
        self.assertEqual(conflict["recorded_id"], publication["parts"][0]["comment_id"])
        self.assertEqual(conflict["recorded_body"],
                         next(c["body"] for c in env.gh.comments_list if c["id"] == conflict["recorded_id"]))
        self.assertEqual(conflict["rival_body"],
                         next(c["body"] for c in env.gh.comments_list if c["id"] == conflict["rival_id"]))
        self.observation = {
            "case": "verdict acceptance", "candidate": candidate, "conflict": conflict,
            "command_exit": code, "command_outcome": outcome, "command_stderr": stderr,
            "round_status": rnd["status"], "round_decision": rnd.get("decision"),
            "rounds_completed": state["rounds_completed"], "ready_review": state.get("ready_review"),
            "reviewer_calls": len(env.reviewer.calls), "developer_calls": len(env.developer.calls),
        }
        with self.subTest(boundary="accepted round"):
            self.assertNotEqual("accepted", rnd["status"],
                                "the genuine verdict was accepted before its conflicting publication was resolved")
        with self.subTest(boundary="review spending"):
            # an uncharged checkpoint has no key (the controller's established representation)
            self.assertEqual(0, state["rounds_completed"].get("final", 0))
        with self.subTest(boundary="ready result"):
            self.assertIsNone(state.get("ready_review"))
        self.assertIsNone(state.get("handoff"))

    def test_handoff_recheck_rejects_the_same_conflict_in_verdict_and_receipt(self):
        self.observation = {"case": "handoff recheck", "publications": []}
        for kind in ("accepted verdict", "handoff receipt"):
            with self.subTest(kind=kind):
                env = self.capped_handoff()
                initial = self.state(env)
                before_calls = (len(env.reviewer.calls), len(env.developer.calls))
                before_rounds = dict(initial["rounds_completed"])
                before_limit = initial["limits"]["max_review_rounds_per_checkpoint"]
                self.assertTrue(env.controller().status(remote=True)["handoff_current"])
                key = "r01-review" if kind == "accepted verdict" else (
                    "final-status-" + ar.short(initial["handoff"]["A"])
                )
                publication = initial["publications"][key]
                self.assertEqual("posted", publication["state"])
                self.assertEqual(1, len(publication["parts"]))
                part = publication["parts"][0]
                recorded = next(c for c in env.gh.comments_list if c["id"] == part["comment_id"])
                body = env.controller().outbox_body(key, part)
                self.assertEqual(body, recorded["body"])
                conflict = self.simulate_cross_comment_conflict(
                    env, recorded, part["marker"],
                    body + "\nSIMULATED COMPETING COPY: a different result is claimed here.\n"
                )

                ctl = env.controller()
                remote_status = ctl.status(remote=True)
                helper_result = ctl.publication_problems(key, publication, env.gh.comments(1))
                inventory_result = ctl.missing_publications(
                    include_receipt="final-status-" + ar.short(initial["handoff"]["A"])
                )
                outcome = self.recover(env)
                after = self.state(env)
                self.observation["publications"].append({
                    "kind": kind, "key": key, "conflict": conflict,
                    "publication_problems": helper_result, "missing_publications": inventory_result,
                    "remote_handoff_current": remote_status.get("handoff_current"),
                    "resume": outcome, "status_after_resume": after["status"],
                    "reason_after_resume": after["status_reason"],
                    "handoff_preserved_after_resume": bool(after.get("handoff")),
                    "accepted_local_review_unchanged": initial["rounds"] == after["rounds"],
                })
                self.assertEqual(before_calls, (len(env.reviewer.calls), len(env.developer.calls)))
                self.assertEqual(before_rounds, after["rounds_completed"])
                self.assertEqual(before_limit, after["limits"]["max_review_rounds_per_checkpoint"])
                self.assertTrue(env.controller().helper_authority_problems())
                self.assertFalse(remote_status.get("handoff_current"),
                                 "the handoff was claimed current despite a cross-comment integrity conflict")
                self.assertNotEqual("AWAITING_OWNER_REVIEW", after["status"],
                                    "ordinary resume must not reaffirm the conflicted public handoff")


class CallbackLiveReviewerR11(LiveReviewer):
    """The external reviewer boundary, with a confirmed simulated start."""

    def run(self, *args, **kwargs):
        callback = kwargs.get("on_start")
        if callback is None:
            raise AssertionError("the controller must pass its process-start callback")
        callback(424242)  # SIMULATED external reviewer PID, never a live model.
        self.log_after_start = self.live_path.read_text(encoding="utf-8")
        return super().run(*args, **kwargs)


class ForegroundRoundElevenLiveLaunchTests(ForegroundFixture, unittest.TestCase):
    """R10-F2 (owner-supplied): the foreground live log announces a reviewer only after the confirmed process start
    and records a never-launched attempt's failure for its candidate and attempt."""

    unlaunched_request = ForegroundRoundTenTests.unlaunched_request

    def test_foreground_setup_failure_has_no_running_claim_and_a_terminal_log_line(self):
        env = self.fg_env()
        candidate = env.commit("feature.txt", "v2\n", "SIMULATED foreground feature v2")
        env.push()
        before = self.state(env)
        rounds_before = dict(before["rounds_completed"])
        limits_before = dict(before["limits"])
        calls_before = (len(env.developer.calls), len(env.reviewer.calls))

        # Existing real stream-setup fixture: stderr-1.txt is a directory;
        # the Codex Popen boundary is intercepted only for that executable
        # and asserted never dispatched. Real Git subprocesses remain real.
        code, outcome, stderr = self.unlaunched_request(
            env, None, lambda ctl: self.review_cmd(env, ctl=ctl), 1
        )
        self.assertEqual(ar.EXIT_BLOCKED, code, outcome)
        self.assertEqual("BLOCKED", outcome["status"])
        self.assertIn("reviewer launch setup for round 1 failed", outcome["reason"])
        self.assertIn("no reviewer was launched", outcome["reason"])

        state = self.state(env)
        attempt = state["rounds"][-1]["attempts"][-1]
        self.assertIs(False, attempt["launched"])
        self.assertIn("ended", attempt)
        self.assertNotIn("pid", attempt)
        self.assertEqual(rounds_before, state["rounds_completed"])
        self.assertEqual(limits_before, state["limits"])
        self.assertEqual(calls_before, (len(env.developer.calls), len(env.reviewer.calls)))
        self.assertTrue(env.controller().helper_authority_problems())

        rows = []
        ar.watch_enrollment(env.dir, rows.append, once=True)
        status = next(row for row in rows if " | latest action:" in row)
        self.assertIn("no agent running", status)
        self.assertIn("not reviewed: no reviewer launched", status)
        self.assertIn("reviewer launch setup for round 1 failed", status)

        live = self.live_text(env)
        self.observation = {
            "candidate": candidate,
            "command": {"exit_code": code, "status": outcome["status"], "reason": outcome["reason"]},
            "attempt": attempt,
            "live_log": live,
            "watch_status": status,
            "rounds_before": rounds_before,
            "rounds_after": state["rounds_completed"],
            "model_calls_before": calls_before,
            "model_calls_after": (len(env.developer.calls), len(env.reviewer.calls)),
            "zero_reviewer_process_dispatch_verified_by_fixture": True,
        }

        with self.subTest(behavior="no false running claim"):
            self.assertNotIn("is reviewing candidate", live,
                             "the reviewer never launched, so the live feed must not claim it is reviewing")
        with self.subTest(behavior="terminal failure visible on same feed"):
            failure_lines = [line for line in live.splitlines()
                             if "review round 1 attempt 1" in line
                             and candidate[:10] in line
                             and any(word in line.lower() for word in ("failed", "not launched", "never launched"))]
            self.assertTrue(failure_lines,
                            "the foreground live feed must identify this candidate and attempt's failed launch")
        self.assertNotIn(str(env.root), live, "private setup paths belong in the saved attempt, not the progress feed")

    def test_confirmed_start_keeps_running_status_and_activity_visible_before_return(self):
        env = self.fg_env()
        env.reviewer = CallbackLiveReviewerR11(env.dir / "live.log")
        env.reviewer.script = [{"decision": "ready_for_owner_review"}]
        candidate = env.commit("feature.txt", "v2\n", "SIMULATED foreground feature v2")
        env.push()
        code, outcome, _ = self.review_cmd(env)
        self.assertEqual((ar.EXIT_OK, "ready_for_owner_review"), (code, outcome["result"]))
        self.assertIn("review round 1 attempt 1", env.reviewer.log_after_start)
        self.assertIn("is reviewing candidate " + candidate[:10], env.reviewer.log_after_start)
        self.assertEqual([True], env.reviewer.seen_while_running)
        live = self.live_text(env)
        self.assertIn("review round 1 attempt 1 ended: valid result, decision ready_for_owner_review", live)
        self.assertNotIn("PRIVATE-THOUGHT", live)
        state = self.state(env)
        self.assertEqual({"final": 1}, state["rounds_completed"])
        self.assertEqual((0, 1), (len(env.developer.calls), len(env.reviewer.calls)))


if __name__ == "__main__":
    unittest.main()
