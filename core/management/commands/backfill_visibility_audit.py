import json

from django.core.management.base import BaseCommand
from django.core.serializers import serialize

from core.models import Pin, Board
from core.visibility import PinVisibilityPolicy, BoardVisibilityPolicy


SEVERITY_CRITICAL = "critical"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"

SEVERITY_ORDER = {
    SEVERITY_INFO: 0,
    SEVERITY_WARNING: 1,
    SEVERITY_CRITICAL: 2,
}


def classify_severity(current_private: bool, inferred_private: bool) -> str:
    """
    根据差异方向分类严重度。

    - public -> private (current=False, inferred=True): critical
      现有用户会失去访问权限，影响面大，需立即处理
    - private -> public (current=True, inferred=False): warning
      可能导致信息意外泄露，需评估确认
    - 其他辅助字段对齐: info（保留，当前场景下未使用）
    """
    if not current_private and inferred_private:
        return SEVERITY_CRITICAL
    if current_private and not inferred_private:
        return SEVERITY_WARNING
    return SEVERITY_INFO


class Command(BaseCommand):
    help = (
        "Audit Pin/Board visibility against the new unified policy. "
        "Compares the stored `private` field with the policy-inferred privacy, "
        "reports discrepancies as JSON with severity classification, "
        "and optionally proposes fixes."
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
        parser.add_argument(
            "--min-severity",
            type=str,
            choices=[SEVERITY_INFO, SEVERITY_WARNING, SEVERITY_CRITICAL],
            default=SEVERITY_INFO,
            help=(
                f"Minimum severity to include in the report. "
                f"Choices: {SEVERITY_INFO} (default), {SEVERITY_WARNING}, "
                f"{SEVERITY_CRITICAL}. Filtered items are still counted in totals."
            ),
        )

    def handle(self, *args, **options):
        fix = options["fix"]
        dry_run = options["dry_run"]
        output_path = options["output"]
        fixture_path = options["load_fixture"]
        min_severity = options["min_severity"]

        if fixture_path:
            self._load_fixture(fixture_path)

        report = {
            "summary": {
                "total_pins": 0,
                "total_boards": 0,
                "pins_discrepant": 0,
                "boards_discrepant": 0,
                "by_severity": {
                    SEVERITY_CRITICAL: 0,
                    SEVERITY_WARNING: 0,
                    SEVERITY_INFO: 0,
                },
                "fixes_applied": 0,
                "dry_run": dry_run,
                "min_severity": min_severity,
            },
            "pins": [],
            "boards": [],
            "fixture_data": [],
        }

        all_pin_entries = self._audit_pins(report, fix, dry_run)
        all_board_entries = self._audit_boards(report, fix, dry_run)

        report["pins"] = self._filter_by_severity(all_pin_entries, min_severity)
        report["boards"] = self._filter_by_severity(all_board_entries, min_severity)

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
        by_sev = report["summary"]["by_severity"]
        if total_discrepant > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"Found {total_discrepant} discrepant records "
                    f"({report['summary']['pins_discrepant']} pins, "
                    f"{report['summary']['boards_discrepant']} boards). "
                    f"Severity breakdown: "
                    f"critical={by_sev[SEVERITY_CRITICAL]}, "
                    f"warning={by_sev[SEVERITY_WARNING]}, "
                    f"info={by_sev[SEVERITY_INFO]}."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS("All records are consistent with the new policy.")
            )

    @staticmethod
    def _filter_by_severity(entries, min_severity):
        min_level = SEVERITY_ORDER[min_severity]
        return [
            e for e in entries
            if SEVERITY_ORDER[e["severity"]] >= min_level
        ]

    def _load_fixture(self, fixture_path):
        from django.core.management import call_command

        self.stdout.write(f"Loading fixture from {fixture_path}...")
        call_command("loaddata", fixture_path, verbosity=0)

        fixture_data = json.loads(
            serialize("json", list(Pin.objects.all()) + list(Board.objects.all()))
        )
        return fixture_data

    def _audit_pins(self, report, fix, dry_run):
        entries = []
        for pin in Pin.objects.select_related("submitter", "image").iterator():
            current_private = pin.private
            inferred_private = PinVisibilityPolicy.infer_privacy(pin)

            if current_private != inferred_private:
                severity = classify_severity(current_private, inferred_private)
                entry = {
                    "model": "Pin",
                    "id": pin.id,
                    "submitter": str(pin.submitter),
                    "current_private": current_private,
                    "inferred_private": inferred_private,
                    "severity": severity,
                    "reason": self._pin_discrepancy_reason(
                        pin, current_private, inferred_private
                    ),
                }
                entries.append(entry)
                report["summary"]["pins_discrepant"] += 1
                report["summary"]["by_severity"][severity] += 1

                if fix and not dry_run:
                    pin.private = inferred_private
                    pin.save(update_fields=["private"])
                    entry["fix_applied"] = True
                    report["summary"]["fixes_applied"] += 1
                elif fix and dry_run:
                    entry["fix_applied"] = False
                    entry["fix_would_be"] = inferred_private
        return entries

    def _audit_boards(self, report, fix, dry_run):
        entries = []
        for board in Board.objects.select_related("submitter").iterator():
            current_private = board.private
            inferred_private = BoardVisibilityPolicy.infer_privacy(board)

            if current_private != inferred_private:
                severity = classify_severity(current_private, inferred_private)
                entry = {
                    "model": "Board",
                    "id": board.id,
                    "name": board.name,
                    "submitter": str(board.submitter),
                    "current_private": current_private,
                    "inferred_private": inferred_private,
                    "severity": severity,
                    "reason": self._board_discrepancy_reason(
                        board, current_private, inferred_private
                    ),
                }
                entries.append(entry)
                report["summary"]["boards_discrepant"] += 1
                report["summary"]["by_severity"][severity] += 1

                if fix and not dry_run:
                    board.private = inferred_private
                    board.save(update_fields=["private"])
                    entry["fix_applied"] = True
                    report["summary"]["fixes_applied"] += 1
                elif fix and dry_run:
                    entry["fix_applied"] = False
                    entry["fix_would_be"] = inferred_private
        return entries

    @staticmethod
    def _pin_discrepancy_reason(pin, current_private, inferred_private):
        from core.models import Board

        if not current_private and inferred_private:
            private_boards = Board.objects.filter(pins=pin, private=True)
            if private_boards.exists():
                board_names = list(private_boards.values_list("name", flat=True))
                return (
                    f"Pin is public but belongs to private board(s): {board_names}. "
                    "Under the new policy, this pin should be private "
                    "(critical: existing users will lose access)."
                )
        if current_private and not inferred_private:
            public_boards = Board.objects.filter(pins=pin, private=False)
            if public_boards.exists():
                board_names = list(public_boards.values_list("name", flat=True))
                return (
                    f"Pin is private but referenced by public board(s): {board_names}. "
                    "Under the new policy, this pin should be public "
                    "(warning: potential information leak risk)."
                )
        return "Stored private flag differs from policy inference."

    @staticmethod
    def _board_discrepancy_reason(board, current_private, inferred_private):
        owner = board.submitter
        pins = board.pins.select_related("submitter").all()

        if not current_private and inferred_private:
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
                        "private since non-owners see no content "
                        "(critical: existing users will lose access)."
                    )
        if current_private and not inferred_private:
            has_public_pin = any(
                not PinVisibilityPolicy.is_private(p) for p in pins
            )
            if has_public_pin:
                return (
                    "Board is private but contains at least one public pin. "
                    "Under the new policy, this board should be public "
                    "(warning: public pins are already visible to everyone)."
                )
        return "Stored private flag differs from policy inference."
