"""Tests for spec and roadmap review in bin/ask-codex.

Specification: docs/specs/second-opinion-document-review.md

Run from the repository root with:  python3 -B -m unittest discover -s tests

These reuse the throwaway-tree and fake-`codex` machinery of test_ask_codex.
"""
import json
from pathlib import Path
import shutil
import unittest

try:
    import test_ask_codex as base
except ImportError:  # run as tests.test_ask_codex_documents
    from tests import test_ask_codex as base

SPEC = """# Widget requirements

Status: Accepted

## Scope

Widgets render.
"""

ROADMAP = """# Roadmap: widgets

Status: Active
Updated: 2026-10-17

## Purpose

Order the widget work.
"""

KINDS = {
    "spec": {"command": "review-spec", "flag": "--spec", "directory": "docs/specs",
             "kind": "spec-review", "text": SPEC},
    "roadmap": {"command": "review-roadmap", "flag": "--roadmap", "directory": "docs/roadmaps",
                "kind": "roadmap-review", "text": ROADMAP},
}


class DocCase(base.RunnerCase):
    def setUp(self):
        super().setUp()
        for info in KINDS.values():
            directory = self.repo / info["directory"]
            directory.mkdir(parents=True)
            (directory / "widget.md").write_text(info["text"])

    def doc_path(self, label, name="widget.md"):
        return "%s/%s" % (KINDS[label]["directory"], name)

    def review_doc(self, label, name="widget.md"):
        info = KINDS[label]
        return self.ok(info["command"], info["flag"], self.doc_path(label, name))

    def reset_fake_codex(self):
        """Start the fake codex's scenario over, so a subTest sees its own call numbers."""
        (self.fakebin / "counter").unlink()
        for call in self.fakebin.glob("call-*.json"):
            call.unlink()

    def doc_args(self, label, name="widget.md"):
        return (KINDS[label]["flag"], self.doc_path(label, name))

    def dirs_for(self, kind):
        return [d for d in self.state_dirs() if d.name.endswith("-%s" % kind)
                or ("-%s-" % kind) in d.name]


class RunTests(DocCase):
    def test_each_kind_runs_a_round_with_its_own_kind_files(self):
        for label, info in KINDS.items():
            with self.subTest(label=label):
                data = self.review_doc(label)
                self.assertEqual(data["outcome"], "converged")
                self.assertEqual(data["round"], 1)
                self.assertIn("-%s" % info["kind"], data["state_dir"])
                call = self.calls()[-1]
                self.assertIn(self.doc_path(label), call["stdin"])
                self.assertNotIn("{{", call["stdin"])
                self.assertTrue(call["argv"][11].endswith("kinds/%s/schema.json" % info["kind"]))
                state = json.loads((self.repo / data["state_dir"] / "state.json").read_text())
                self.assertEqual(state["kind"], info["kind"])
                self.assertEqual(state["plan"], self.doc_path(label))

    def test_any_document_status_is_reviewable(self):
        for status in ("Draft", "Accepted", "Superseded", "Completed"):
            for label, info in KINDS.items():
                with self.subTest(status=status, label=label):
                    name = "status-%s.md" % status.lower()
                    text = info["text"].replace("Accepted", status).replace("Active", status)
                    (self.repo / info["directory"] / name).write_text(text)
                    self.review_doc(label, name)

    def test_the_shared_bound_and_decisions_apply(self):
        self.set_scenario([base.OK([base.F("major", "needs a criterion")])] * 6)
        self.review_doc("spec")
        pending = self.ok("status", *self.doc_args("spec"))["pending_decisions"]
        self.assertEqual(pending, ["R1-F1"])
        code, data, r = self.run_helper("review-spec", "--spec", self.doc_path("spec"))
        self.assertEqual(code, 2, r.stdout)
        self.assertEqual(data["reason"], "undecided_findings")
        self.ok("decide", *self.doc_args("spec"), "R1-F1", "applied")
        self.review_doc("spec")
        self.ok("decide", *self.doc_args("spec"), "R2-F1", "applied")
        self.review_doc("spec")
        self.ok("decide", *self.doc_args("spec"), "R3-F1", "applied")
        code, data, r = self.run_helper("review-spec", "--spec", self.doc_path("spec"))
        self.assertEqual(code, 1, r.stdout)
        self.assertEqual(data["reason"], "bound_reached")

    def test_both_kinds_share_the_loop_bound_ceiling_and_argv(self):
        for label, info in KINDS.items():
            with self.subTest(label=label):
                self.set_scenario([base.OK([base.F("major", "gap")])] * 8)
                first = self.ok(info["command"], info["flag"], self.doc_path(label), "--max-rounds", "9")
                self.assertEqual(first["bound"], 5)  # clamped to the ceiling
                self.ok("decide", *self.doc_args(label), "R1-F1", "applied")
                argv = self.calls()[-1]["argv"]
                self.assertEqual(argv[:10], ["exec", "-s", "read-only", "--ephemeral", "--ignore-user-config",
                                             "--json", "-m", "gpt-6.1-sol", "-c",
                                             'model_reasoning_effort="high"'])
                self.assertEqual(argv[10], "--output-schema")
                self.assertTrue(argv[11].endswith("kinds/%s/schema.json" % info["kind"]))
                self.assertEqual(argv[12], "-o")
                self.assertEqual(argv[14:], ["-C", str(self.repo), "-"])
                stdin = self.calls()[-1]["stdin"]
                self.assertIn("review round 1", stdin)
                self.assertIn("independent reviewer of a %s" % label.replace("spec", "specification"), stdin)
                code, data, r = self.run_helper(info["command"], info["flag"], self.doc_path(label),
                                                "--max-rounds", "2")
                self.assertEqual(code, 2, r.stdout)
                self.assertEqual(data["reason"], "usage")
                self.ok("archive", *self.doc_args(label))
                self.reset_fake_codex()

    def test_a_reraise_without_evidence_is_suppressed_for_a_roadmap(self):
        self.set_scenario([base.OK([base.F("major", "missing trigger")]),
                           base.OK([base.F("major", "missing trigger", reraises="R1-F1")])])
        self.review_doc("roadmap")
        self.ok("decide", *self.doc_args("roadmap"), "R1-F1", "rejected", "--reason", "triggers are optional")
        data = self.review_doc("roadmap")
        self.assertTrue(data["findings"][0]["suppressed"])
        self.assertEqual(data["outcome"], "converged")

    def test_a_second_reraise_escalates_for_a_spec_and_a_roadmap(self):
        for label, info in KINDS.items():
            with self.subTest(label=label):
                self.set_scenario([
                    base.OK([base.F("major", "A")]),
                    base.OK([base.F("major", "A again", reraises="R1-F1", new_evidence="evidence one")]),
                    base.OK([base.F("major", "A yet again", reraises="R2-F1", new_evidence="evidence two")]),
                ])
                self.review_doc(label)
                self.ok("decide", *self.doc_args(label), "R1-F1", "rejected", "--reason", "no")
                self.review_doc(label)
                self.ok("decide", *self.doc_args(label), "R2-F1", "rejected", "--reason", "still no")
                code, data, r = self.run_helper(info["command"], info["flag"], self.doc_path(label))
                self.assertEqual(code, 1, r.stdout)
                self.assertEqual(data["reason"], "reraise_escalation")
                self.ok("archive", *self.doc_args(label))
                self.reset_fake_codex()

    def test_plan_review_is_unchanged_beside_the_new_kinds(self):
        self.review_doc("spec")
        data = self.review()
        self.assertIn("-plan-review", data["state_dir"])
        self.assertEqual(len(self.state_dirs()), 2)


class PathTests(DocCase):
    def refused(self, label, name_or_path, contains=None):
        info = KINDS[label]
        return self.expect_error(info["command"], info["flag"], name_or_path, contains=contains)

    def test_path_is_required(self):
        self.expect_error("review-spec", contains="spec")
        self.expect_error("review-roadmap", contains="roadmap")

    def test_other_directories_are_refused(self):
        self.refused("spec", "docs/plans/next.md")
        self.refused("spec", "docs/roadmaps/widget.md")
        self.refused("roadmap", "docs/specs/widget.md")
        self.refused("roadmap", "docs/plans/next.md")

    def test_readme_subdirectories_archive_and_non_markdown_are_refused(self):
        for label, info in KINDS.items():
            directory = self.repo / info["directory"]
            (directory / "README.md").write_text("# Index\n")
            (directory / "sub").mkdir()
            (directory / "sub" / "deep.md").write_text(info["text"])
            (directory / "archive").mkdir()
            (directory / "archive" / "2026-01-old.md").write_text(info["text"])
            (directory / "notes.txt").write_text(info["text"])
            for name in ("README.md", "sub/deep.md", "archive/2026-01-old.md", "notes.txt"):
                with self.subTest(label=label, name=name):
                    self.refused(label, "%s/%s" % (info["directory"], name))

    def test_outside_symlink_traversal_and_control_characters_are_refused(self):
        outside = Path(self.tmp.name) / "outside.md"
        outside.write_text(SPEC)
        for label, info in KINDS.items():
            directory = self.repo / info["directory"]
            (directory / "link.md").symlink_to(outside)
            with self.subTest(label=label):
                self.refused(label, str(outside), contains="repository")
                self.refused(label, "%s/../../../outside.md" % info["directory"])
                self.refused(label, "%s/link.md" % info["directory"], contains="symlink")
                self.refused(label, "%s/wid\x07get.md" % info["directory"])

    def test_a_symlinked_document_directory_is_refused(self):
        real = self.repo / "elsewhere"
        real.mkdir()
        (real / "widget.md").write_text(SPEC)
        shutil.rmtree(self.repo / "docs" / "specs")
        (self.repo / "docs" / "specs").symlink_to(real)
        self.refused("spec", "docs/specs/widget.md")

    def test_missing_empty_or_headingless_documents_are_refused(self):
        for label, info in KINDS.items():
            directory = self.repo / info["directory"]
            (directory / "empty.md").write_text("  \n")
            (directory / "nohead.md").write_text("Status: Draft\n\nbody\n")
            with self.subTest(label=label):
                self.refused(label, "%s/missing.md" % info["directory"])
                self.refused(label, "%s/empty.md" % info["directory"], contains="empty")
                self.refused(label, "%s/nohead.md" % info["directory"], contains="heading")


class HardeningTests(DocCase):
    """Findings of the adversarial path review (plan increment E)."""

    def test_readme_is_refused_whatever_its_case(self):
        for label, info in KINDS.items():
            directory = self.repo / info["directory"]
            (directory / "README.md").write_text("# Index\n")
            for name in ("README.md", "readme.md", "ReadMe.md", "README.MD"):
                with self.subTest(label=label, name=name):
                    self.expect_error(info["command"], info["flag"], "%s/%s" % (info["directory"], name))

    def test_a_symlinked_parent_of_the_document_directory_is_refused(self):
        shutil.move(str(self.repo / "docs"), str(self.repo / "alt"))
        (self.repo / "docs").symlink_to(self.repo / "alt")
        for label, info in KINDS.items():
            with self.subTest(label=label):
                self.expect_error(info["command"], info["flag"], self.doc_path(label))
                self.expect_error("status", info["flag"], self.doc_path(label))

    def test_hard_links_are_refused(self):
        outside = Path(self.tmp.name) / "outside.md"
        outside.write_text(SPEC)
        for label, info in KINDS.items():
            directory = self.repo / info["directory"]
            (directory / "README.md").write_text("# Index\n")
            import os
            os.link(directory / "README.md", directory / "hl.md")
            os.link(outside, directory / "outhl.md")
            for name in ("hl.md", "outhl.md"):
                with self.subTest(label=label, name=name):
                    self.expect_error(info["command"], info["flag"], "%s/%s" % (info["directory"], name),
                                      contains="link")

    def test_an_empty_document_flag_never_falls_back_to_the_plan(self):
        self.ok("init")
        for flag in ("--spec", "--roadmap"):
            for command in ("status", "init", "extend", "reset", "archive"):
                with self.subTest(flag=flag, command=command):
                    extra = ("1",) if command == "extend" else ()
                    self.expect_error(command, flag, "", *extra)
        self.assertIsNone(self.ok("status")["closed"])
        self.expect_error("decide", "--spec", "", "R1-F1", "applied")

    def test_a_placeholder_in_the_file_name_is_not_expanded(self):
        name = "{{LEDGER}}.md"
        (self.repo / "docs" / "specs" / name).write_text(SPEC)
        self.review_doc("spec", name)
        self.assertIn("docs/specs/{{LEDGER}}.md", self.calls()[-1]["stdin"])


class StateTests(DocCase):
    def test_kinds_keep_separate_reviews_and_directories(self):
        self.review()
        self.review_doc("spec")
        self.review_doc("roadmap")
        self.assertEqual(len(self.state_dirs()), 3)
        self.assertEqual(len(self.dirs_for("plan-review")), 1)
        self.assertEqual(len(self.dirs_for("spec-review")), 1)
        self.assertEqual(len(self.dirs_for("roadmap-review")), 1)
        for label in KINDS:
            self.assertEqual(self.ok("status", *self.doc_args(label))["rounds_used"], 1)

    def test_an_open_review_is_resumed(self):
        self.review_doc("spec")
        data = self.review_doc("spec")
        self.assertEqual(data["rounds_used"], 2)
        self.assertEqual(len(self.dirs_for("spec-review")), 1)

    def test_two_documents_of_one_kind_are_two_reviews(self):
        (self.repo / "docs" / "specs" / "other.md").write_text(SPEC.replace("Widget", "Other"))
        self.review_doc("spec")
        self.review_doc("spec", "other.md")
        self.assertEqual(len(self.dirs_for("spec-review")), 2)

    def test_a_closed_review_does_not_block_a_fresh_one(self):
        for label, info in KINDS.items():
            with self.subTest(label=label):
                self.review_doc(label)
                data = self.ok("archive", *self.doc_args(label))
                self.assertIn("## Codex %s review" % label, data["summary_markdown"])
                self.assertIn(self.doc_path(label), data["summary_markdown"])
                status = self.ok("status", *self.doc_args(label))
                self.assertEqual(status["rounds_used"], 0)
                self.assertEqual(status["bound"], 3)
                self.assertIsNone(status["closed"])
                fresh = self.review_doc(label)
                self.assertEqual(fresh["rounds_used"], 1)
                self.assertEqual(fresh["bound"], 3)
                self.assertEqual(len(self.dirs_for(info["kind"])), 2)

    def test_a_closed_plan_review_still_blocks(self):
        self.review()
        self.ok("archive")
        code, data, r = self.run_helper("review-plan")
        self.assertEqual(code, 2, r.stdout)
        self.assertEqual(data["reason"], "closed")

    def test_renaming_leaves_an_orphaned_open_review(self):
        self.review_doc("roadmap")
        old = self.repo / "docs" / "roadmaps" / "widget.md"
        old.rename(self.repo / "docs" / "roadmaps" / "gadget.md")
        data = self.review_doc("roadmap", "gadget.md")
        self.assertEqual(data["rounds_used"], 1)
        self.assertEqual(len(self.dirs_for("roadmap-review")), 2)
        status = self.ok("status", *self.doc_args("roadmap", "gadget.md"))
        orphans = status["orphaned_reviews"]
        self.assertEqual([o["document"] for o in orphans], ["docs/roadmaps/widget.md"])
        self.assertEqual(self.ok("status", *self.doc_args("spec"))["orphaned_reviews"], [])

    def test_an_orphaned_review_can_be_inspected_and_archived_by_its_old_path(self):
        self.review_doc("roadmap")
        old = self.doc_args("roadmap")
        (self.repo / "docs" / "roadmaps" / "archive").mkdir()
        (self.repo / "docs" / "roadmaps" / "widget.md").rename(
            self.repo / "docs" / "roadmaps" / "archive" / "2026-10-widget.md")
        status = self.ok("status", *old)
        self.assertEqual(status["rounds_used"], 1)
        self.assertIsNone(status["closed"])
        summary = self.ok("archive", *old)["summary_markdown"]
        self.assertIn("## Codex roadmap review", summary)
        self.assertIn("docs/roadmaps/widget.md", summary)
        self.assertIsNotNone(json.loads(
            (self.dirs_for("roadmap-review")[0] / "state.json").read_text())["closed"])

    def test_a_missing_document_without_a_review_is_still_an_error(self):
        self.expect_error("status", "--spec", "docs/specs/never-existed.md", contains="not found")
        self.expect_error("archive", "--roadmap", "docs/roadmaps/never-existed.md", contains="not found")

    def test_only_commands_on_an_existing_review_accept_a_missing_document(self):
        self.review_doc("spec")
        (self.repo / "docs" / "specs" / "widget.md").rename(self.repo / "docs" / "specs" / "gadget.md")
        for command in ("init", "review-spec"):
            with self.subTest(command=command):
                self.expect_error(command, "--spec", "docs/specs/widget.md", contains="not found")
        for path in ("docs/specs/../specs/widget.md", "/docs/specs/widget.md", "docs/specs/wid\x07get.md"):
            with self.subTest(path=path):
                self.expect_error("archive", "--spec", path)

    def test_archive_prints_the_summary_once_for_a_living_document(self):
        self.review_doc("spec")
        self.ok("archive", *self.doc_args("spec"))
        self.expect_error("archive", *self.doc_args("spec"), contains="no review state")

    def test_another_kinds_exhausted_review_does_not_warn_a_plan_review(self):
        self.ok("review-spec", "--spec", self.doc_path("spec"), "--max-rounds", "1")
        data = self.review()
        self.assertEqual(data["warnings"], [])

    def test_lifecycle_commands_take_the_document_flag(self):
        self.review_doc("roadmap")
        data = self.ok("extend", *self.doc_args("roadmap"), "2")
        self.assertEqual(data["bound"], 5)
        self.ok("reset", *self.doc_args("roadmap"))
        self.assertEqual(self.ok("status", *self.doc_args("roadmap"))["rounds_used"], 1)
        self.ok("archive", *self.doc_args("roadmap"))

    def test_only_one_document_flag_is_accepted(self):
        for args in (("--plan", "docs/plans/next.md", "--spec", self.doc_path("spec")),
                     ("--spec", self.doc_path("spec"), "--roadmap", self.doc_path("roadmap"))):
            with self.subTest(args=args):
                self.expect_error("status", *args)

    def test_prune_covers_all_three_directory_families(self):
        old = "2026-01-05T00:00:00Z"
        self.ok("init")
        for label in KINDS:
            self.ok("init", *self.doc_args(label))
        self.assertEqual(len(self.state_dirs()), 3)
        for directory in self.state_dirs():
            state = json.loads((directory / "state.json").read_text())
            state["closed"] = old
            self.save_state(state, directory)
        data = self.ok("prune")
        self.assertEqual(sorted(i["directory"] for i in data["eligible"]),
                         [".debug/%s" % d.name for d in self.state_dirs()])
        self.ok("prune", "--confirm")
        self.assertEqual(self.state_dirs(), [])


if __name__ == "__main__":
    unittest.main()
