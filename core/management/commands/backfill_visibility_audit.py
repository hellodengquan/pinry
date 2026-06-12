import json

from django.core.management.base import BaseCommand
from django.core.serializers import serialize

from core.models import Pin, Board
from core.visibility import PinVisibilityPolicy, BoardVisibilityPolicy


class Command(BaseCommand):
    help = (
        "Audit Pin/Board visibility against the new unified policy. "
        "Compares the stored `private` field with the policy-inferred privacy, "
        "reports discrepancies as JSON, and optionally proposes fixes."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--fix",
            action="store_true",
            default=False,
            help="Apply fixes to align stored privacy with the new policy inference.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Show what would be fixed without actually modifying the database. "
                 "Has no effect unless --fix is also specified.",
        )
        parser.add_argument(
            "--output",
            type=str,
            default=None,
            help="Write the JSON report to this file path instead of stdout.",
        )
        parser.add_argument(
            "--load-fixture",
            type=str,
            default=None,
            help="Load a Django fixture file before auditing (useful for testing).",
        )

    def handle(self, *args, **options):
        fix = options["fix"]
        dry_run = options["dry_run"]
        output_path = options["output"]
        fixture_path = options["load_fixture"]

        if fixture_path:
            self._load_fixture(fixture_path)

        report = {
            "summary": {
                "total_pins": 0,
                "total_boards": 0,
                "pins_discrepant": 0,
                "boards_discrepant": 0,
                "fixes_applied": 0,
                "dry_run": dry_run,
            },
            "pins": [],
            "boards": [],
            "fixture_data": [],
        }

        self._audit_pins(report, fix, dry_run)
        self._audit_boards(report, fix, dry_run)

        report["summary"]["total_pins"] = Pin.objects.count()
        report["summary"]["total_boards"] = Board.objects.count()

        report_json = json.dumps(report, indent=2, default=str)

        if output_path:
            with open(output_path, "w") as f:
                f.write(report_json)
            self.stdout.write(
                self.style.SUCCESS(f"Report written to {output_path}")
            )
        else:
            self.stdout.write(report_json)

        total_discrepant = (
            report["summary"]["pins_discrepant"]
            + report["summary"]["boards_discrepant"]
        )
        if total_discrepant > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"Found {total_discrepant} discrepant records "
                    f"({report['summary']['pins_discrepant']} pins, "
                    f"{report['summary']['boards_discrepant']} boards)."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS("All records are consistent with the new policy.")
            )

    def _load_fixture(self, fixture_path):
        from django.core.management import call_command

        self.stdout.write(f"Loading fixture from {fixture_path}...")
        call_command("loaddata", fixture_path, verbosity=0)

        fixture_data = json.loads(
            serialize("json", list(Pin.objects.all()) + list(Board.objects.all()))
        )
        return fixture_data

    def _audit_pins(self, report, fix, dry_run):
        for pin in Pin.objects.select_related("submitter", "image").iterator():
            current_private = pin.private
            inferred_private = PinVisibilityPolicy.infer_privacy(pin)

            if current_private != inferred_private:
                entry = {
                    "model": "Pin",
                    "id": pin.id,
                    "submitter": str(pin.submitter),
                    "current_private": current_private,
                    "inferred_private": inferred_private,
                    "reason": self._pin_discrepancy_reason(pin),
                }
                report["pins"].append(entry)
                report["summary"]["pins_discrepant"] += 1

                if fix and not dry_run:
                    pin.private = inferred_private
                    pin.save(update_fields=["private"])
                    entry["fix_applied"] = True
                    report["summary"]["fixes_applied"] += 1
                elif fix and dry_run:
                    entry["fix_applied"] = False
                    entry["fix_would_be"] = inferred_private

    def _audit_boards(self, report, fix, dry_run):
        for board in Board.objects.select_related("submitter").iterator():
            current_private = board.private
            inferred_private = BoardVisibilityPolicy.infer_privacy(board)

            if current_private != inferred_private:
                entry = {
                    "model": "Board",
                    "id": board.id,
                    "name": board.name,
                    "submitter": str(board.submitter),
                    "current_private": current_private,
                    "inferred_private": inferred_private,
                    "reason": self._board_discrepancy_reason(board),
                }
                report["boards"].append(entry)
                report["summary"]["boards_discrepant"] += 1

                if fix and not dry_run:
                    board.private = inferred_private
                    board.save(update_fields=["private"])
                    entry["fix_applied"] = True
                    report["summary"]["fixes_applied"] += 1
                elif fix and dry_run:
                    entry["fix_applied"] = False
                    entry["fix_would_be"] = inferred_private

    @staticmethod
    def _pin_discrepancy_reason(pin):
        if not pin.private:
            from core.models import Board
            private_boards = Board.objects.filter(pins=pin, private=True)
            if private_boards.exists():
                board_names = list(private_boards.values_list("name", flat=True))
                return (
                    f"Pin is public but belongs to private board(s): {board_names}. "
                    "Under the new policy, this pin should be private."
                )
        return "Stored private flag differs from policy inference."

    @staticmethod
    def _board_discrepancy_reason(board):
        if not board.private:
            owner = board.submitter
            pins = board.pins.select_related("submitter").all()
            if pins.exists():
                all_other_private = all(
                    PinVisibilityPolicy.is_private(p)
                    and PinVisibilityPolicy.get_owner(p) != owner
                    for p in pins
                )
                if all_other_private:
                    return (
                        "Board is public but all its pins belong to other users and "
                        "are private. Under the new policy, this board should be "
                        "private since non-owners see no content."
                    )
        return "Stored private flag differs from policy inference."
