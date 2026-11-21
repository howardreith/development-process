"""Live headless smoke: REAL Claude Opus developer and REAL Codex GPT-6.2 Astra reviewer.

Skipped unless AGENT_REVIEW_LIVE=1. It exercises the exact `run` continuation
path used for feature missions (headless Claude launch with explicit session,
dontAsk permission profile, structured report, controller review round, Astra
review, finalize and archive) against a harmless temporary repository. Only
GitHub is simulated (FakeGitHub, clearly not a real PR); both model exchanges
are real and consume subscription quota.

    $env:AGENT_REVIEW_LIVE = "1"; $env:AGENT_REVIEW_LIVE_OUT = "<dir>"
    python -m unittest agent_review/test_live_smoke.py -v
"""
import json
import os
import shutil
import sys
import tempfile
import uuid
import time
import unittest
from pathlib import Path

import agent_review as ar
from test_agent_review import Env, git

MISSION = """# Fixture mission: calculator helper

Add `calc.py` exposing `add(a, b)` that returns the sum of two numbers, and
`test_calc.py` with a `unittest` test covering integers and a negative number.
Run the test with `python -m unittest test_calc`. Commit, push with the push
command your instructions give, then run the required `unit` gate. Keep the change minimal; nothing else is required.
"""

EXTRA_PERMISSIONS = {"allow": ["Bash(python -m unittest*)", "PowerShell(python -m unittest*)"], "deny": []}

PLAN = {"schema_version": "agent-review.plan.v1", "mission_id": "live-smoke", "title": "Live smoke fixture",
        "notes": "Harmless fixture repository; no game or product code.",
        "checkpoints": [{"id": "final", "type": "final", "scope": "The complete fixture mission.",
                         "exit_conditions": ["calc.add exists and is tested; the test passes; work is pushed."],
                         "required_gates": ["unit"]}]}


FAKE_GH = r'''"""SIMULATED gh for the live smoke's helper subprocesses: answers `api user` and `pr view` only."""
import json, subprocess, sys
from pathlib import Path
cfg = json.loads((Path(__file__).parent / "fake-gh.json").read_text(encoding="utf-8"))
args = sys.argv[1:]
if args[:2] == ["api", "user"]:
    print(json.dumps({"login": cfg["actor"]}))
elif args[:2] == ["pr", "view"]:
    head = subprocess.run(["git", "-C", cfg["origin"], "rev-parse", "refs/heads/" + cfg["branch"]],
                          capture_output=True, text=True).stdout.strip()
    owner, name = cfg["repo"].split("/")
    print(json.dumps({"number": int(args[2]), "url": "https://github.com/%s/pull/%s" % (cfg["repo"], args[2]),
                      "state": "OPEN", "isDraft": True, "headRefName": cfg["branch"], "headRefOid": head,
                      "baseRefName": "master", "author": {"login": cfg["actor"]}, "reviewRequests": [], "body": "",
                      "isCrossRepository": False, "headRepository": {"name": name},
                      "headRepositoryOwner": {"login": owner}}))
else:
    sys.stderr.write("simulated gh: unsupported command " + " ".join(args))
    sys.exit(1)
'''


@unittest.skipUnless(os.environ.get("AGENT_REVIEW_LIVE") == "1", "live model smoke; set AGENT_REVIEW_LIVE=1")
class LiveHeadlessSmoke(unittest.TestCase):
    def test_real_models_headless_cycle_with_simulated_github(self):
        base = ar.read_json(Path(__file__).resolve().parent / "projects" / "kingmaker-gunslinger.json")
        developer = dict(base["developer"], permissions=EXTRA_PERMISSIONS, soft_deadline_minutes=30)
        limits = dict(base["limits"], max_review_rounds_per_checkpoint=2, max_developer_invocations=4,
                      retry_backoff_seconds=[10, 30])
        # No push_command: the developer uses the controller's built-in guarded push helper (general-repo path).
        gates = {"unit": {"argv": ["python", "-m", "unittest", "test_calc", "-v"], "timeout_minutes": 5}}
        # The developer's helpers run as separate processes and read GitHub through the project's configurable
        # `gh` executable; point it at a SIMULATED gh backed by the fixture's bare origin (no production hook).
        shim_dir = Path(tempfile.gettempdir()) / f"agent-review-fake-gh-{uuid.uuid4().hex[:8]}"
        shim_dir.mkdir()
        self.addCleanup(shutil.rmtree, shim_dir, True)
        (shim_dir / "fake_gh.py").write_text(FAKE_GH, encoding="utf-8")
        shim = shim_dir / "gh-sim.cmd"
        shim.write_text(f'@"{sys.executable}" "{shim_dir / "fake_gh.py"}" %*\n', encoding="utf-8")
        env = Env("headless", cfg_overrides={"push_command": None, "developer": developer, "limits": limits,
                                             "instructions": [], "gates": gates, "gh": str(shim)},
                  plan=PLAN, mission_text=MISSION, extra_files={".gitignore": "__pycache__/\n"})
        self.addCleanup(env.cleanup)
        (shim_dir / "fake-gh.json").write_text(json.dumps({"origin": str(env.origin), "branch": env.branch,
                                                           "repo": "owner/repo", "actor": "owner"}), encoding="utf-8")
        ctl = ar.Controller(env.dir, github=env.gh, sleep=time.sleep, workflow_root=env.wf)
        started = time.monotonic()
        try:
            outcome = ctl.run_loop()
        except ar.Stop as stop:
            outcome = f"{stop.status}: {stop.reason}"
        summary = {"outcome": outcome, "duration_s": round(time.monotonic() - started),
                   "developer_log": ctl.state["developer"].get("log"),
                   "rounds": [{k: r.get(k) for k in ("round", "status", "decision", "H", "attempts")}
                              for r in ctl.state["rounds"]],
                   "findings": ctl.state.get("findings"),
                   "simulated_github_headings": env.gh.headings(),
                   "files_on_branch": git(env.work, "ls-tree", "-r", "--name-only", "HEAD").splitlines()}
        out = os.environ.get("AGENT_REVIEW_LIVE_OUT")
        if out:
            Path(out).mkdir(parents=True, exist_ok=True)
            Path(out, "live-smoke-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
            for comment in env.gh.comments_list:
                Path(out, f"comment-{comment['id']}.md").write_text(comment["body"], encoding="utf-8")
        print(json.dumps({k: summary[k] for k in ("outcome", "duration_s", "simulated_github_headings")}, indent=2))
        self.assertEqual("AWAITING_OWNER_REVIEW", outcome)
        self.assertTrue(all(m.startswith("claude-opus-") for e in summary["developer_log"] for m in e["main_models"]))
        self.assertIn("calc.py", summary["files_on_branch"])


if __name__ == "__main__":
    unittest.main()
