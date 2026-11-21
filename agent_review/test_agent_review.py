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
import time
import uuid
import unittest
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
        self.calls.append({"request": request, "prompt": prompt, "workdir": str(workdir),
                           "inbox": sorted(p.relative_to(inbox).as_posix() for p in inbox.rglob("*") if p.is_file()),
                           "transcript": (inbox / "developer-tool-transcript.md").read_text(encoding="utf-8")})
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
            "prior_finding_assessments": [{"finding_id": f, "assessment": a, "rationale": "simulated"}
                                          for f, a in assessments],
            "evidence_assessment": {"inspected": ["feature.txt"], "executed_verification": [],
                                    "source_inspection_only": ["feature.txt"], "required_gaps": [], "limitations": []},
            "summary": {"delivered_behavior": "simulated", "scope_reviewed": "simulated", "pending_later_phase_work": [],
                        "unresolved_questions": [], "remaining_owner_review": ["simulated visual check"]}}


class FakeDeveloper:
    """Simulated Claude boundary: scripted headless actions commit real changes."""

    def __init__(self, env):
        self.env, self.script, self.calls, self.sessions = env, [], [], set()
        self.foreground = {"models": [OPUS], "efforts": ["high"]}

    @property
    def requested(self):
        return {"model": "opus", "effort": "high"}

    def session_exists(self, session_id):
        return session_id in self.sessions

    def session_provenance(self, session_id, since=None):
        return {"found": True, "session_id": session_id, "source": "SIMULATED", **self.foreground}

    def tool_transcript(self, session_id, since_iso):
        return f"# Developer tool transcript (SIMULATED)\n\nsession {session_id} since {since_iso}\n"

    def run(self, prompt, session_id, resume, cwd, log_path, stderr_path, soft_deadline_s, on_start=None,
            on_soft_deadline=None, grace_s=0, protected=None):
        self.calls.append({"session_id": session_id, "resume": resume, "prompt": prompt})
        Path(stderr_path).write_text("", encoding="utf-8")
        self.sessions.add(session_id)
        action = self.script.pop(0)
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
        self.dir, _ = ar.enroll(self.args(mode=mode, max_rounds=max_rounds), github=self.gh, root=self.wf)

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
            ar.enroll(args, github=env.gh, root=env.wf)
        git(env.work, "remote", "set-url", "origin", str(env.origin))
        git(env.work, "checkout", "--quiet", "-b", "feature/not-allowed")
        with self.assertRaises(ar.UsageError):
            ar.enroll(args, github=env.gh, root=env.wf)
        git(env.work, "checkout", "--quiet", env.branch)
        env.gh.pr_overrides = {"viewer": "mallory"}
        with self.assertRaises(ar.UsageError):
            ar.enroll(args, github=env.gh, root=env.wf)
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
            ar.enroll(env.args(), github=env.gh, root=env.wf)
        self.assertIn("active enrollment", str(refused.exception))

    def test_second_enrollment_for_active_branch_is_refused_across_state_roots(self):
        env = self.env
        with self.assertRaises(ar.UsageError) as refused:
            ar.enroll(env.args(state_root=str(env.root / "elsewhere")), github=env.gh, root=env.wf)
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
        env.developer.foreground = {"models": [OPUS], "efforts": ["high"]}
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
        folder, state = ar.enroll(env.args(), github=env.gh, root=env.wf)  # the branch can be enrolled again
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
        folder, state = ar.enroll(env.args(), github=env.gh, root=env.wf)
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
            ar.enroll(env.args(), github=env.gh, root=env.wf)
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
        folder, state = ar.enroll(env.args(), github=env.gh, root=env.wf)
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
        self.assertEqual(("gpt-6.2-astra", "high"), (cfg["reviewer"]["model"], cfg["reviewer"]["effort"]))
        self.assertEqual(("opus", "high"), (cfg["developer"]["model"], cfg["developer"]["effort"]))
        for name in ("black-tentacles", "agent-review-setup"):
            self.assertEqual("final", ar.load_plan(name)["checkpoints"][-1]["type"])


if __name__ == "__main__":
    unittest.main()
