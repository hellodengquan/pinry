import argparse
import sys

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from core.link_checker import check_single_pin, run_link_check_task
from core.models import LinkCheckTask

User = get_user_model()


class Command(BaseCommand):
    help = "Run link availability checks for saved Pin URLs"

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            type=str,
            help="Username for task submission (required for full scan)",
        )
        parser.add_argument(
            "--pin-id",
            type=int,
            help="Check a single Pin by ID",
        )
        parser.add_argument(
            "--task-id",
            type=int,
            help="Run an existing pending task by ID",
        )
        parser.add_argument(
            "--run-async",
            action="store_true",
            help="Create task and return immediately (requires worker)",
        )

    def handle(self, *args, **options):
        pin_id = options.get("pin_id")
        task_id = options.get("task_id")
        username = options.get("user")
        run_async = options.get("run_async")

        if pin_id is not None:
            self.stdout.write(f"Checking single pin id={pin_id}...")
            result = check_single_pin(pin_id)
            if result is None:
                self.stderr.write(f"Pin {pin_id} not found or has invalid URL")
                sys.exit(1)
            self.stdout.write(
                f"Done. status={result.status} "
                f"http_code={result.http_status_code} "
                f"error={result.error_message}"
            )
            return

        if task_id is not None:
            self.stdout.write(f"Running existing task id={task_id}...")
            run_link_check_task(task_id)
            self.stdout.write("Task finished.")
            return

        if not username:
            self.stderr.write("Error: --user is required for full scan")
            sys.exit(1)

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stderr.write(f"User '{username}' not found")
            sys.exit(1)

        task = LinkCheckTask.objects.create(submitter=user)
        self.stdout.write(f"Created task id={task.id}")

        if run_async:
            self.stdout.write(
                "Task queued. Run `python manage.py link_check --task-id "
                f"{task.id}` or start a worker to process it."
            )
            return

        run_link_check_task(task.id)
        task.refresh_from_db()
        self.stdout.write(
            f"Task {task.id} {task.status}: "
            f"total={task.total_pins} checked={task.checked_count} "
            f"success={task.success_count} failed={task.failed_count}"
        )
