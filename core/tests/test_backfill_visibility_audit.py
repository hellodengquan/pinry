import json
import tempfile

from django.core.management import call_command
from django.test import TestCase
from django.core.files.images import ImageFile

from core.models import Pin, Board, Image
from core.visibility import PinVisibilityPolicy, BoardVisibilityPolicy
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


class BackfillVisibilityAuditCommandTest(TestCase):

    def setUp(self):
        self.owner_a = create_user("owner_a")
        self.owner_b = create_user("owner_b")

    def _run_audit(self, fix=False, dry_run=False, output_path=None, load_fixture=None):
        args = []
        if fix:
            args.append("--fix")
        if dry_run:
            args.append("--dry-run")
        if output_path:
            args.extend(["--output", output_path])
        if load_fixture:
            args.extend(["--load-fixture", load_fixture])

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

    def test_public_pin_in_private_board_is_flagged(self):
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
        self.assertIn("private board", entry["reason"].lower())

    def test_public_board_with_all_other_users_private_pins_is_flagged(self):
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
        self.assertIn("all its pins belong to other users", entry["reason"])

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
        other_pin = _create_pin(self.owner_b, private=True)
        public_board = Board.objects.create(
            name="empty_view", submitter=self.owner_a, private=False
        )
        public_board.pins.add(other_pin)
        public_board.save()

        self.assertFalse(Board.objects.get(pk=public_board.pk).private)

        report = self._run_audit(fix=True, dry_run=False)

        board_after = Board.objects.get(pk=public_board.pk)
        self.assertTrue(board_after.private)

        self.assertEqual(len(report["boards"]), 1)
        entry = report["boards"][0]
        self.assertTrue(entry["fix_applied"])

    def test_report_summary_counts(self):
        pin1 = _create_pin(self.owner_a, private=False)
        pin2 = _create_pin(self.owner_a, private=False)
        _create_pin(self.owner_b, private=False)

        private_board = Board.objects.create(
            name="secret1", submitter=self.owner_a, private=True
        )
        private_board.pins.add(pin1, pin2)

        report = self._run_audit()

        self.assertEqual(report["summary"]["pins_discrepant"], 2)
        self.assertEqual(report["summary"]["boards_discrepant"], 0)
        self.assertEqual(report["summary"]["total_pins"], 3)
        self.assertEqual(report["summary"]["dry_run"], False)

    def test_empty_board_not_flagged(self):
        Board.objects.create(
            name="empty_board", submitter=self.owner_a, private=False
        )

        report = self._run_audit()

        self.assertEqual(report["summary"]["boards_discrepant"], 0)

    def test_json_output_is_valid(self):
        _create_pin(self.owner_a, private=False)
        report = self._run_audit()

        self.assertIsInstance(report, dict)
        self.assertIn("summary", report)
        self.assertIn("pins", report)
        self.assertIn("boards", report)
        self.assertIn("total_pins", report["summary"])
        self.assertIn("total_boards", report["summary"])
        self.assertIn("pins_discrepant", report["summary"])
        self.assertIn("boards_discrepant", report["summary"])
        self.assertIn("fixes_applied", report["summary"])
        self.assertIn("dry_run", report["summary"])

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


class BoardVisibilityPolicyInferTest(TestCase):

    def setUp(self):
        self.owner = create_user("board_owner")
        self.other = create_user("board_other")

    def test_infer_privacy_public_board_no_pins(self):
        board = Board.objects.create(name="empty", submitter=self.owner, private=False)
        self.assertFalse(BoardVisibilityPolicy.infer_privacy(board))

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
