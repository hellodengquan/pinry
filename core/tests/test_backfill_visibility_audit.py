import json
import tempfile

from django.core.management import call_command
from django.test import TestCase
from django.core.files.images import ImageFile

from core.models import Pin, Board, Image
from core.visibility import PinVisibilityPolicy, BoardVisibilityPolicy
from core.management.commands.backfill_visibility_audit import (
    classify_severity,
    SEVERITY_CRITICAL,
    SEVERITY_WARNING,
    SEVERITY_INFO,
)
from core.tests.helpers import create_user, TEST_IMAGE_PATH
from django_images.models import Thumbnail
from django.conf import settings


def _create_image():
    image = Image.objects.create(image=ImageFile(open(TEST_IMAGE_PATH, 'rb')))
    Thumbnail.objects.get_or_create_at_sizes(image, settings.IMAGE_SIZES.keys())
    return image


def _create_pin(user, private=False):
    image = _create_image()
    return Pin.objects.create(submitter=user, image=image, private=private)


class ClassifySeverityTest(TestCase):

    def test_public_to_private_is_critical(self):
        self.assertEqual(
            classify_severity(current_private=False, inferred_private=True),
            SEVERITY_CRITICAL,
        )

    def test_private_to_public_is_warning(self):
        self.assertEqual(
            classify_severity(current_private=True, inferred_private=False),
            SEVERITY_WARNING,
        )

    def test_no_change_is_info(self):
        self.assertEqual(
            classify_severity(current_private=True, inferred_private=True),
            SEVERITY_INFO,
        )
        self.assertEqual(
            classify_severity(current_private=False, inferred_private=False),
            SEVERITY_INFO,
        )


class BackfillVisibilityAuditCommandTest(TestCase):

    def setUp(self):
        self.owner_a = create_user("owner_a")
        self.owner_b = create_user("owner_b")

    def _run_audit(self, fix=False, dry_run=False, output_path=None,
                   load_fixture=None, min_severity=None):
        args = []
        if fix:
            args.append("--fix")
        if dry_run:
            args.append("--dry-run")
        if output_path:
            args.extend(["--output", output_path])
        if load_fixture:
            args.extend(["--load-fixture", load_fixture])
        if min_severity is not None:
            args.extend(["--min-severity", min_severity])

        out = tempfile.mktemp(suffix=".json")
        if not output_path:
            args.extend(["--output", out])

        call_command("backfill_visibility_audit", *args, verbosity=0)

        result_path = output_path or out
        with open(result_path) as f:
            return json.load(f)

    def test_no_discrepancies_when_consistent(self):
        _create_pin(self.owner_a, private=False)
        _create_pin(self.owner_a, private=True)
        Board.objects.create(name="public_board", submitter=self.owner_a, private=False)

        report = self._run_audit()

        self.assertEqual(report["summary"]["pins_discrepant"], 0)
        self.assertEqual(report["summary"]["boards_discrepant"], 0)
        self.assertEqual(len(report["pins"]), 0)
        self.assertEqual(len(report["boards"]), 0)

    def test_public_pin_in_private_board_is_flagged_as_critical(self):
        pin = _create_pin(self.owner_a, private=False)
        private_board = Board.objects.create(
            name="secret_board", submitter=self.owner_a, private=True
        )
        private_board.pins.add(pin)
        private_board.save()

        report = self._run_audit()

        self.assertEqual(report["summary"]["pins_discrepant"], 1)
        self.assertEqual(len(report["pins"]), 1)
        entry = report["pins"][0]
        self.assertEqual(entry["id"], pin.id)
        self.assertEqual(entry["current_private"], False)
        self.assertEqual(entry["inferred_private"], True)
        self.assertEqual(entry["severity"], SEVERITY_CRITICAL)
        self.assertIn("private board", entry["reason"].lower())
        self.assertIn("critical", entry["reason"].lower())

    def test_public_board_with_all_other_users_private_pins_is_critical(self):
        other_user_pin = _create_pin(self.owner_b, private=True)
        public_board = Board.objects.create(
            name="empty_view_board", submitter=self.owner_a, private=False
        )
        public_board.pins.add(other_user_pin)
        public_board.save()

        report = self._run_audit()

        self.assertEqual(report["summary"]["boards_discrepant"], 1)
        self.assertEqual(len(report["boards"]), 1)
        entry = report["boards"][0]
        self.assertEqual(entry["id"], public_board.id)
        self.assertEqual(entry["current_private"], False)
        self.assertEqual(entry["inferred_private"], True)
        self.assertEqual(entry["severity"], SEVERITY_CRITICAL)
        self.assertIn("all its pins belong to other users", entry["reason"])
        self.assertIn("critical", entry["reason"].lower())

    def test_private_pin_in_public_board_is_flagged_as_warning(self):
        pin = _create_pin(self.owner_a, private=True)
        public_board = Board.objects.create(
            name="shared_board", submitter=self.owner_a, private=False
        )
        public_board.pins.add(pin)
        public_board.save()

        report = self._run_audit()

        self.assertEqual(report["summary"]["pins_discrepant"], 1)
        self.assertEqual(len(report["pins"]), 1)
        entry = report["pins"][0]
        self.assertEqual(entry["id"], pin.id)
        self.assertEqual(entry["current_private"], True)
        self.assertEqual(entry["inferred_private"], False)
        self.assertEqual(entry["severity"], SEVERITY_WARNING)
        self.assertIn("public board", entry["reason"].lower())
        self.assertIn("warning", entry["reason"].lower())

    def test_private_board_with_public_pin_is_flagged_as_warning(self):
        public_pin = _create_pin(self.owner_a, private=False)
        private_board = Board.objects.create(
            name="private_board", submitter=self.owner_a, private=True
        )
        private_board.pins.add(public_pin)
        private_board.save()

        report = self._run_audit()

        self.assertEqual(report["summary"]["boards_discrepant"], 1)
        self.assertEqual(len(report["boards"]), 1)
        entry = report["boards"][0]
        self.assertEqual(entry["id"], private_board.id)
        self.assertEqual(entry["current_private"], True)
        self.assertEqual(entry["inferred_private"], False)
        self.assertEqual(entry["severity"], SEVERITY_WARNING)
        self.assertIn("public pin", entry["reason"].lower())
        self.assertIn("warning", entry["reason"].lower())

    def test_public_board_with_own_private_pin_not_flagged(self):
        own_pin = _create_pin(self.owner_a, private=True)
        public_board = Board.objects.create(
            name="my_board", submitter=self.owner_a, private=False
        )
        public_board.pins.add(own_pin)
        public_board.save()

        report = self._run_audit()

        self.assertEqual(report["summary"]["boards_discrepant"], 0)

    def test_public_board_with_public_pin_from_other_user_not_flagged(self):
        other_pin = _create_pin(self.owner_b, private=False)
        public_board = Board.objects.create(
            name="shared_board", submitter=self.owner_a, private=False
        )
        public_board.pins.add(other_pin)
        public_board.save()

        report = self._run_audit()

        self.assertEqual(report["summary"]["boards_discrepant"], 0)

    def test_dry_run_does_not_modify_database(self):
        pin = _create_pin(self.owner_a, private=False)
        private_board = Board.objects.create(
            name="secret_board", submitter=self.owner_a, private=True
        )
        private_board.pins.add(pin)
        private_board.save()

        pin_before = Pin.objects.get(pk=pin.pk)
        self.assertFalse(pin_before.private)

        report = self._run_audit(fix=True, dry_run=True)

        pin_after = Pin.objects.get(pk=pin.pk)
        self.assertFalse(pin_after.private)

        self.assertEqual(len(report["pins"]), 1)
        entry = report["pins"][0]
        self.assertFalse(entry["fix_applied"])
        self.assertEqual(entry["fix_would_be"], True)

    def test_fix_actually_updates_database(self):
        pin = _create_pin(self.owner_a, private=False)
        private_board = Board.objects.create(
            name="secret_board", submitter=self.owner_a, private=True
        )
        private_board.pins.add(pin)
        private_board.save()

        self.assertFalse(Pin.objects.get(pk=pin.pk).private)

        report = self._run_audit(fix=True, dry_run=False)

        pin_after = Pin.objects.get(pk=pin.pk)
        self.assertTrue(pin_after.private)

        self.assertEqual(len(report["pins"]), 1)
        entry = report["pins"][0]
        self.assertTrue(entry["fix_applied"])

    def test_fix_for_board_updates_database(self):
        pin1 = _create_pin(self.owner_b, private=True)
        pin2 = _create_pin(self.owner_b, private=True)
        public_board = Board.objects.create(
            name="empty_view", submitter=self.owner_a, private=False
        )
        public_board.pins.add(pin1, pin2)
        public_board.save()

        self.assertFalse(Board.objects.get(pk=public_board.pk).private)

        report = self._run_audit(fix=True, dry_run=False)

        board_after = Board.objects.get(pk=public_board.pk)
        self.assertTrue(board_after.private)

        board_entries = [b for b in report["boards"] if b["id"] == public_board.id]
        self.assertEqual(len(board_entries), 1)
        self.assertTrue(board_entries[0]["fix_applied"])

    def test_report_summary_by_severity_breakdown(self):
        pin_critical = _create_pin(self.owner_a, private=False)
        private_board = Board.objects.create(
            name="secret", submitter=self.owner_a, private=True
        )
        private_board.pins.add(pin_critical)

        pin_warning = _create_pin(self.owner_b, private=True)
        public_board_for_warning = Board.objects.create(
            name="shared", submitter=self.owner_b, private=False
        )
        public_board_for_warning.pins.add(pin_warning)

        report = self._run_audit()

        by_sev = report["summary"]["by_severity"]
        self.assertGreaterEqual(by_sev[SEVERITY_CRITICAL], 1)
        self.assertGreaterEqual(by_sev[SEVERITY_WARNING], 1)
        self.assertEqual(by_sev[SEVERITY_INFO], 0)

        pin_severities = {
            e["id"]: e["severity"] for e in report["pins"]
        }
        self.assertEqual(pin_severities[pin_critical.id], SEVERITY_CRITICAL)
        self.assertEqual(pin_severities[pin_warning.id], SEVERITY_WARNING)

    def test_min_severity_warning_includes_warning_and_critical(self):
        pin_critical = _create_pin(self.owner_a, private=False)
        private_board = Board.objects.create(
            name="secret", submitter=self.owner_a, private=True
        )
        private_board.pins.add(pin_critical)

        pin_warning = _create_pin(self.owner_b, private=True)
        public_board = Board.objects.create(
            name="shared", submitter=self.owner_b, private=False
        )
        public_board.pins.add(pin_warning)

        report = self._run_audit(min_severity=SEVERITY_WARNING)

        pin_ids = [e["id"] for e in report["pins"]]
        self.assertIn(pin_warning.id, pin_ids)
        self.assertIn(pin_critical.id, pin_ids)
        self.assertEqual(report["summary"]["min_severity"], SEVERITY_WARNING)

    def test_min_severity_critical_includes_only_critical(self):
        pin_critical = _create_pin(self.owner_a, private=False)
        private_board = Board.objects.create(
            name="secret", submitter=self.owner_a, private=True
        )
        private_board.pins.add(pin_critical)

        pin_warning = _create_pin(self.owner_b, private=True)
        public_board = Board.objects.create(
            name="shared", submitter=self.owner_b, private=False
        )
        public_board.pins.add(pin_warning)

        report = self._run_audit(min_severity=SEVERITY_CRITICAL)

        pin_ids = [e["id"] for e in report["pins"]]
        pin_severities = {e["id"]: e["severity"] for e in report["pins"]}
        self.assertIn(pin_critical.id, pin_ids)
        self.assertNotIn(pin_warning.id, pin_ids)
        for pid, sev in pin_severities.items():
            self.assertEqual(sev, SEVERITY_CRITICAL)

    def test_min_severity_info_includes_all(self):
        pin_critical = _create_pin(self.owner_a, private=False)
        private_board = Board.objects.create(
            name="secret", submitter=self.owner_a, private=True
        )
        private_board.pins.add(pin_critical)

        pin_warning = _create_pin(self.owner_b, private=True)
        public_board = Board.objects.create(
            name="shared", submitter=self.owner_b, private=False
        )
        public_board.pins.add(pin_warning)

        report = self._run_audit(min_severity=SEVERITY_INFO)

        self.assertEqual(len(report["pins"]), 2)
        severities = {e["severity"] for e in report["pins"]}
        self.assertIn(SEVERITY_CRITICAL, severities)
        self.assertIn(SEVERITY_WARNING, severities)

    def test_report_summary_counts(self):
        pin1 = _create_pin(self.owner_a, private=False)
        pin2 = _create_pin(self.owner_a, private=False)
        pin3 = _create_pin(self.owner_b, private=False)

        private_board = Board.objects.create(
            name="secret1", submitter=self.owner_a, private=True
        )
        private_board.pins.add(pin1, pin2)
        private_board.save()

        report = self._run_audit()

        self.assertEqual(report["summary"]["total_pins"], 3)
        self.assertEqual(report["summary"]["dry_run"], False)

        critical_pins = [
            p for p in report["pins"] if p["severity"] == SEVERITY_CRITICAL
        ]
        self.assertIn(pin1.id, [p["id"] for p in critical_pins])
        self.assertIn(pin2.id, [p["id"] for p in critical_pins])

    def test_empty_board_not_flagged(self):
        Board.objects.create(
            name="empty_board", submitter=self.owner_a, private=False
        )

        report = self._run_audit()

        self.assertEqual(report["summary"]["boards_discrepant"], 0)

    def test_json_output_has_severity_fields(self):
        pin = _create_pin(self.owner_a, private=False)
        private_board = Board.objects.create(
            name="secret", submitter=self.owner_a, private=True
        )
        private_board.pins.add(pin)

        report = self._run_audit()

        self.assertIn("by_severity", report["summary"])
        self.assertIn("min_severity", report["summary"])
        self.assertIn("severity", report["pins"][0])

    def test_fixture_loading(self):
        pin = _create_pin(self.owner_a, private=True)
        board = Board.objects.create(
            name="fixture_board", submitter=self.owner_a, private=True
        )
        board.pins.add(pin)

        from django.core.serializers import serialize

        all_objects = [
            self.owner_a,
            pin.image,
            pin,
            board,
        ]
        fixture_data = json.loads(serialize("json", all_objects))

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(fixture_data, f)
            fixture_path = f.name

        Pin.objects.all().delete()
        Board.objects.all().delete()

        report = self._run_audit(load_fixture=fixture_path)

        self.assertGreaterEqual(report["summary"]["total_pins"], 1)
        self.assertGreaterEqual(report["summary"]["total_boards"], 1)


class PinVisibilityPolicyInferTest(TestCase):

    def setUp(self):
        self.owner = create_user("policy_owner")
        self.other = create_user("policy_other")

    def test_infer_privacy_public_pin_no_board(self):
        pin = _create_pin(self.owner, private=False)
        self.assertFalse(PinVisibilityPolicy.infer_privacy(pin))

    def test_infer_privacy_private_pin_no_board(self):
        pin = _create_pin(self.owner, private=True)
        self.assertTrue(PinVisibilityPolicy.infer_privacy(pin))

    def test_infer_privacy_public_pin_in_private_board(self):
        pin = _create_pin(self.owner, private=False)
        board = Board.objects.create(name="priv", submitter=self.owner, private=True)
        board.pins.add(pin)
        self.assertTrue(PinVisibilityPolicy.infer_privacy(pin))

    def test_infer_privacy_public_pin_in_public_board(self):
        pin = _create_pin(self.owner, private=False)
        board = Board.objects.create(name="pub", submitter=self.owner, private=False)
        board.pins.add(pin)
        self.assertFalse(PinVisibilityPolicy.infer_privacy(pin))

    def test_infer_privacy_private_pin_in_public_board_returns_public(self):
        pin = _create_pin(self.owner, private=True)
        board = Board.objects.create(name="pub", submitter=self.owner, private=False)
        board.pins.add(pin)
        self.assertFalse(PinVisibilityPolicy.infer_privacy(pin))

    def test_infer_privacy_private_pin_in_private_board_remains_private(self):
        pin = _create_pin(self.owner, private=True)
        board = Board.objects.create(name="priv", submitter=self.owner, private=True)
        board.pins.add(pin)
        self.assertTrue(PinVisibilityPolicy.infer_privacy(pin))

    def test_infer_privacy_private_pin_in_both_public_and_private_board(self):
        pin = _create_pin(self.owner, private=True)
        pub_board = Board.objects.create(
            name="pub", submitter=self.owner, private=False
        )
        priv_board = Board.objects.create(
            name="priv", submitter=self.owner, private=True
        )
        pub_board.pins.add(pin)
        priv_board.pins.add(pin)
        self.assertTrue(PinVisibilityPolicy.infer_privacy(pin))


class BoardVisibilityPolicyInferTest(TestCase):

    def setUp(self):
        self.owner = create_user("board_owner")
        self.other = create_user("board_other")

    def test_infer_privacy_public_board_no_pins(self):
        board = Board.objects.create(name="empty", submitter=self.owner, private=False)
        self.assertFalse(BoardVisibilityPolicy.infer_privacy(board))

    def test_infer_privacy_private_board_no_pins(self):
        board = Board.objects.create(name="empty", submitter=self.owner, private=True)
        self.assertTrue(BoardVisibilityPolicy.infer_privacy(board))

    def test_infer_privacy_private_board(self):
        board = Board.objects.create(name="priv", submitter=self.owner, private=True)
        self.assertTrue(BoardVisibilityPolicy.infer_privacy(board))

    def test_infer_privacy_public_board_with_own_private_pin(self):
        pin = _create_pin(self.owner, private=True)
        board = Board.objects.create(name="pub", submitter=self.owner, private=False)
        board.pins.add(pin)
        self.assertFalse(BoardVisibilityPolicy.infer_privacy(board))

    def test_infer_privacy_public_board_with_other_users_private_pins_only(self):
        pin = _create_pin(self.other, private=True)
        board = Board.objects.create(name="pub", submitter=self.owner, private=False)
        board.pins.add(pin)
        self.assertTrue(BoardVisibilityPolicy.infer_privacy(board))

    def test_infer_privacy_public_board_with_mixed_pins(self):
        pin_other_private = _create_pin(self.other, private=True)
        pin_own_public = _create_pin(self.owner, private=False)
        board = Board.objects.create(name="mix", submitter=self.owner, private=False)
        board.pins.add(pin_other_private, pin_own_public)
        self.assertFalse(BoardVisibilityPolicy.infer_privacy(board))

    def test_infer_privacy_public_board_with_other_user_public_pin(self):
        pin = _create_pin(self.other, private=False)
        board = Board.objects.create(name="other_pub", submitter=self.owner, private=False)
        board.pins.add(pin)
        self.assertFalse(BoardVisibilityPolicy.infer_privacy(board))

    def test_infer_privacy_private_board_with_public_pin_returns_public(self):
        pin = _create_pin(self.owner, private=False)
        board = Board.objects.create(name="priv", submitter=self.owner, private=True)
        board.pins.add(pin)
        self.assertFalse(BoardVisibilityPolicy.infer_privacy(board))

    def test_infer_privacy_private_board_with_own_private_pins_only(self):
        pin = _create_pin(self.owner, private=True)
        board = Board.objects.create(name="priv", submitter=self.owner, private=True)
        board.pins.add(pin)
        self.assertTrue(BoardVisibilityPolicy.infer_privacy(board))
