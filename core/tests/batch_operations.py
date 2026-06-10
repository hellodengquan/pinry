from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from taggit.models import Tag

from .helpers import create_image, create_user, create_pin
from core.models import Pin, Image, Board
from core.views import BatchOperationResultCodes


def _teardown_models():
    Pin.objects.all().delete()
    Image.objects.all().delete()
    Tag.objects.all().delete()
    Board.objects.all().delete()


class BatchOperationBaseTest(APITestCase):
    """Base test class for batch operation tests with helpers."""

    def setUp(self):
        super().setUp()
        self.owner = create_user("owner")
        self.other_user = create_user("other")

        self.image1 = create_image()
        self.image2 = create_image()
        self.image3 = create_image()

        self.pin_owned_public = create_pin(self.owner, image=self.image1, tags=[])
        self.pin_owned_public.private = False
        self.pin_owned_public.save()

        self.pin_owned_private = create_pin(self.owner, image=self.image2, tags=[])
        self.pin_owned_private.private = True
        self.pin_owned_private.save()

        self.pin_other_public = create_pin(self.other_user, image=self.image3, tags=[])
        self.pin_other_public.private = False
        self.pin_other_public.save()

        self.board_owned = Board.objects.create(
            name="owner_board",
            submitter=self.owner,
            private=False,
        )
        self.board_other = Board.objects.create(
            name="other_board",
            submitter=self.other_user,
            private=False,
        )

    def tearDown(self):
        _teardown_models()

    def _login_owner(self):
        self.client.login(username=self.owner.username, password='password')

    def _login_other(self):
        self.client.login(username=self.other_user.username, password='password')


class BatchMovePinsTests(BatchOperationBaseTest):
    """Tests for POST /batch-operations/move-pins/"""

    def setUp(self):
        super().setUp()
        self.url = reverse("batch-operation-move-pins")
        self.board_owned.pins.add(self.pin_owned_public)
        self.board_owned.pins.add(self.pin_owned_private)

    def test_unauthenticated_returns_401(self):
        data = {
            "pin_ids": [self.pin_owned_public.id],
            "target_board_id": self.board_other.id,
        }
        response = self.client.post(self.url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_target_board_not_found_returns_404_with_code(self):
        self._login_owner()
        data = {
            "pin_ids": [self.pin_owned_public.id],
            "target_board_id": 99999,
        }
        response = self.client.post(self.url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["total"], 1)
        self.assertEqual(response.data["success_count"], 0)
        self.assertEqual(response.data["failed_count"], 1)
        self.assertEqual(
            response.data["results"][0]["code"],
            BatchOperationResultCodes.TARGET_BOARD_NOT_FOUND,
        )

    def test_target_board_no_permission_returns_403(self):
        self._login_other()
        data = {
            "pin_ids": [self.pin_owned_public.id],
            "target_board_id": self.board_owned.id,
        }
        response = self.client.post(self.url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["success_count"], 0)
        self.assertEqual(
            response.data["results"][0]["code"],
            BatchOperationResultCodes.TARGET_BOARD_NO_PERMISSION,
        )

    def test_source_board_not_found_returns_404(self):
        self._login_owner()
        data = {
            "pin_ids": [self.pin_owned_public.id],
            "source_board_id": 99999,
            "target_board_id": self.board_other.id,
        }
        # target_board is other user's but because source_board check comes first...
        # Actually target_board is checked first. Let's fix:
        data["target_board_id"] = self.board_owned.id
        response = self.client.post(self.url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            response.data["results"][0]["code"],
            BatchOperationResultCodes.SOURCE_BOARD_NOT_FOUND,
        )

    def test_source_board_no_permission_returns_403(self):
        self._login_other()
        data = {
            "pin_ids": [self.pin_owned_public.id],
            "source_board_id": self.board_owned.id,
            "target_board_id": self.board_other.id,
        }
        response = self.client.post(self.url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            response.data["results"][0]["code"],
            BatchOperationResultCodes.SOURCE_BOARD_NO_PERMISSION,
        )

    def test_pin_not_found_returns_pin_not_found_code(self):
        self._login_owner()
        target = Board.objects.create(name="target2", submitter=self.owner)
        data = {
            "pin_ids": [99999, self.pin_owned_public.id],
            "target_board_id": target.id,
        }
        response = self.client.post(self.url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total"], 2)
        self.assertEqual(response.data["success_count"], 1)
        self.assertEqual(response.data["failed_count"], 1)
        results_by_id = {r["pin_id"]: r for r in response.data["results"]}
        self.assertEqual(
            results_by_id[99999]["code"],
            BatchOperationResultCodes.PIN_NOT_FOUND,
        )
        self.assertEqual(
            results_by_id[self.pin_owned_public.id]["code"],
            BatchOperationResultCodes.SUCCESS_MOVE,
        )
        self.assertTrue(target.pins.filter(id=self.pin_owned_public.id).exists())

    def test_private_pin_no_access_permission_code(self):
        self._login_other()
        target = Board.objects.create(name="other_target", submitter=self.other_user)
        data = {
            "pin_ids": [self.pin_owned_private.id, self.pin_owned_public.id],
            "target_board_id": target.id,
        }
        response = self.client.post(self.url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["success_count"], 1)
        self.assertEqual(response.data["failed_count"], 1)
        results_by_id = {r["pin_id"]: r for r in response.data["results"]}
        self.assertEqual(
            results_by_id[self.pin_owned_private.id]["code"],
            BatchOperationResultCodes.PIN_NO_PERMISSION_ACCESS,
        )
        self.assertEqual(
            results_by_id[self.pin_owned_public.id]["code"],
            BatchOperationResultCodes.SUCCESS_MOVE,
        )

    def test_move_with_source_removes_from_source(self):
        self._login_owner()
        target = Board.objects.create(name="target_mv", submitter=self.owner)
        self.assertTrue(self.board_owned.pins.filter(id=self.pin_owned_public.id).exists())
        data = {
            "pin_ids": [self.pin_owned_public.id],
            "source_board_id": self.board_owned.id,
            "target_board_id": target.id,
        }
        response = self.client.post(self.url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["success_count"], 1)
        self.assertTrue(target.pins.filter(id=self.pin_owned_public.id).exists())
        self.assertFalse(self.board_owned.pins.filter(id=self.pin_owned_public.id).exists())

    def test_empty_pin_ids_returns_400(self):
        self._login_owner()
        data = {
            "pin_ids": [],
            "target_board_id": self.board_owned.id,
        }
        response = self.client.post(self.url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class BatchCopyPinsTests(BatchOperationBaseTest):
    """Tests for POST /batch-operations/copy-pins/"""

    def setUp(self):
        super().setUp()
        self.url = reverse("batch-operation-copy-pins")

    def test_unauthenticated_returns_401(self):
        data = {
            "pin_ids": [self.pin_owned_public.id],
            "target_board_id": self.board_other.id,
        }
        response = self.client.post(self.url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_target_board_not_found(self):
        self._login_owner()
        data = {
            "pin_ids": [self.pin_owned_public.id],
            "target_board_id": 99999,
        }
        response = self.client.post(self.url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            response.data["results"][0]["code"],
            BatchOperationResultCodes.TARGET_BOARD_NOT_FOUND,
        )

    def test_target_board_no_permission(self):
        self._login_other()
        data = {
            "pin_ids": [self.pin_owned_public.id],
            "target_board_id": self.board_owned.id,
        }
        response = self.client.post(self.url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            response.data["results"][0]["code"],
            BatchOperationResultCodes.TARGET_BOARD_NO_PERMISSION,
        )

    def test_copy_mixed_success_and_failure(self):
        self._login_other()
        target = Board.objects.create(name="copy_target", submitter=self.other_user)
        data = {
            "pin_ids": [
                self.pin_owned_public.id,
                self.pin_owned_private.id,
                99999,
            ],
            "target_board_id": target.id,
        }
        response = self.client.post(self.url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total"], 3)
        self.assertEqual(response.data["success_count"], 1)
        self.assertEqual(response.data["failed_count"], 2)
        results_by_id = {r["pin_id"]: r for r in response.data["results"]}
        self.assertEqual(
            results_by_id[self.pin_owned_public.id]["code"],
            BatchOperationResultCodes.SUCCESS_COPY,
        )
        self.assertEqual(
            results_by_id[self.pin_owned_private.id]["code"],
            BatchOperationResultCodes.PIN_NO_PERMISSION_ACCESS,
        )
        self.assertEqual(
            results_by_id[99999]["code"],
            BatchOperationResultCodes.PIN_NOT_FOUND,
        )
        self.assertTrue(target.pins.filter(id=self.pin_owned_public.id).exists())

    def test_copy_public_pin_to_own_board_succeeds(self):
        self._login_other()
        self.assertFalse(self.board_other.pins.filter(id=self.pin_owned_public.id).exists())
        data = {
            "pin_ids": [self.pin_owned_public.id],
            "target_board_id": self.board_other.id,
        }
        response = self.client.post(self.url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["success_count"], 1)
        self.assertTrue(self.board_other.pins.filter(id=self.pin_owned_public.id).exists())

    def test_copy_pin_already_in_target_board_returns_already_code(self):
        self._login_owner()
        self.board_owned.pins.add(self.pin_owned_public)
        image4 = create_image()
        pin_new = create_pin(self.owner, image=image4, tags=[])
        pin_new.private = False
        pin_new.save()

        data = {
            "pin_ids": [self.pin_owned_public.id, pin_new.id],
            "target_board_id": self.board_owned.id,
        }
        response = self.client.post(self.url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total"], 2)
        self.assertEqual(response.data["success_count"], 1)
        self.assertEqual(response.data["failed_count"], 1)

        results_by_id = {r["pin_id"]: r for r in response.data["results"]}
        self.assertEqual(
            results_by_id[self.pin_owned_public.id]["code"],
            BatchOperationResultCodes.PIN_ALREADY_IN_BOARD,
        )
        self.assertFalse(results_by_id[self.pin_owned_public.id]["success"])
        self.assertEqual(
            results_by_id[pin_new.id]["code"],
            BatchOperationResultCodes.SUCCESS_COPY,
        )
        self.assertTrue(results_by_id[pin_new.id]["success"])

    def test_copy_all_already_in_target_returns_400(self):
        self._login_owner()
        self.board_owned.pins.add(self.pin_owned_public)
        self.board_owned.pins.add(self.pin_owned_private)

        data = {
            "pin_ids": [self.pin_owned_public.id, self.pin_owned_private.id],
            "target_board_id": self.board_owned.id,
        }
        response = self.client.post(self.url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["success_count"], 0)
        self.assertEqual(response.data["failed_count"], 2)
        for r in response.data["results"]:
            self.assertEqual(r["code"], BatchOperationResultCodes.PIN_ALREADY_IN_BOARD)


class BatchDeletePinsTests(BatchOperationBaseTest):
    """Tests for POST /batch-operations/delete-pins/"""

    def setUp(self):
        super().setUp()
        self.url = reverse("batch-operation-delete-pins")

    def test_unauthenticated_returns_401(self):
        data = {"pin_ids": [self.pin_owned_public.id]}
        response = self.client.post(self.url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_delete_own_pin_succeeds(self):
        self._login_owner()
        pin_id = self.pin_owned_public.id
        self.assertTrue(Pin.objects.filter(id=pin_id).exists())
        data = {"pin_ids": [pin_id]}
        response = self.client.post(self.url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["success_count"], 1)
        self.assertEqual(
            response.data["results"][0]["code"],
            BatchOperationResultCodes.SUCCESS_DELETE,
        )
        self.assertFalse(Pin.objects.filter(id=pin_id).exists())

    def test_delete_other_pin_no_permission(self):
        self._login_other()
        pin_id = self.pin_owned_public.id
        self.assertTrue(Pin.objects.filter(id=pin_id).exists())
        data = {"pin_ids": [pin_id]}
        response = self.client.post(self.url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["success_count"], 0)
        self.assertEqual(
            response.data["results"][0]["code"],
            BatchOperationResultCodes.PIN_NO_PERMISSION_OWNER,
        )
        self.assertTrue(Pin.objects.filter(id=pin_id).exists())

    def test_delete_mixed_own_and_other_and_nonexistent(self):
        self._login_owner()
        pin_owned_id = self.pin_owned_public.id
        pin_other_id = self.pin_other_public.id
        nonexistent_id = 99999

        data = {"pin_ids": [pin_owned_id, pin_other_id, nonexistent_id]}
        response = self.client.post(self.url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total"], 3)
        self.assertEqual(response.data["success_count"], 1)
        self.assertEqual(response.data["failed_count"], 2)

        results_by_id = {r["pin_id"]: r for r in response.data["results"]}
        self.assertEqual(
            results_by_id[pin_owned_id]["code"],
            BatchOperationResultCodes.SUCCESS_DELETE,
        )
        self.assertEqual(
            results_by_id[pin_other_id]["code"],
            BatchOperationResultCodes.PIN_NO_PERMISSION_OWNER,
        )
        self.assertEqual(
            results_by_id[nonexistent_id]["code"],
            BatchOperationResultCodes.PIN_NOT_FOUND,
        )
        self.assertFalse(Pin.objects.filter(id=pin_owned_id).exists())
        self.assertTrue(Pin.objects.filter(id=pin_other_id).exists())

    def test_all_failed_returns_400(self):
        self._login_other()
        data = {"pin_ids": [self.pin_owned_public.id]}
        response = self.client.post(self.url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["success_count"], 0)


class BatchUpdatePrivacyTests(BatchOperationBaseTest):
    """Tests for POST /batch-operations/update-privacy/"""

    def setUp(self):
        super().setUp()
        self.url = reverse("batch-operation-update-privacy")

    def test_unauthenticated_returns_401(self):
        data = {"pin_ids": [self.pin_owned_public.id], "private": True}
        response = self.client.post(self.url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_set_to_private_succeeds(self):
        self._login_owner()
        self.assertFalse(self.pin_owned_public.private)
        data = {"pin_ids": [self.pin_owned_public.id], "private": True}
        response = self.client.post(self.url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["success_count"], 1)
        self.assertEqual(
            response.data["results"][0]["code"],
            BatchOperationResultCodes.SUCCESS_PRIVACY_PRIVATE,
        )
        self.pin_owned_public.refresh_from_db()
        self.assertTrue(self.pin_owned_public.private)

    def test_set_to_public_succeeds(self):
        self._login_owner()
        self.assertTrue(self.pin_owned_private.private)
        data = {"pin_ids": [self.pin_owned_private.id], "private": False}
        response = self.client.post(self.url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["success_count"], 1)
        self.assertEqual(
            response.data["results"][0]["code"],
            BatchOperationResultCodes.SUCCESS_PRIVACY_PUBLIC,
        )
        self.pin_owned_private.refresh_from_db()
        self.assertFalse(self.pin_owned_private.private)

    def test_no_permission_for_other_pin(self):
        self._login_other()
        data = {"pin_ids": [self.pin_owned_public.id], "private": True}
        response = self.client.post(self.url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["success_count"], 0)
        self.assertEqual(
            response.data["results"][0]["code"],
            BatchOperationResultCodes.PIN_NO_PERMISSION_OWNER,
        )
        self.pin_owned_public.refresh_from_db()
        self.assertFalse(self.pin_owned_public.private)

    def test_mixed_success_and_failure(self):
        self._login_owner()
        image4 = create_image()
        pin_owned2 = create_pin(self.owner, image=image4, tags=[])
        pin_owned2.private = False
        pin_owned2.save()

        data = {
            "pin_ids": [
                self.pin_owned_public.id,
                pin_owned2.id,
                self.pin_other_public.id,
                99999,
            ],
            "private": True,
        }
        response = self.client.post(self.url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total"], 4)
        self.assertEqual(response.data["success_count"], 2)
        self.assertEqual(response.data["failed_count"], 2)

        results_by_id = {r["pin_id"]: r for r in response.data["results"]}
        self.assertEqual(
            results_by_id[self.pin_owned_public.id]["code"],
            BatchOperationResultCodes.SUCCESS_PRIVACY_PRIVATE,
        )
        self.assertEqual(
            results_by_id[pin_owned2.id]["code"],
            BatchOperationResultCodes.SUCCESS_PRIVACY_PRIVATE,
        )
        self.assertEqual(
            results_by_id[self.pin_other_public.id]["code"],
            BatchOperationResultCodes.PIN_NO_PERMISSION_OWNER,
        )
        self.assertEqual(
            results_by_id[99999]["code"],
            BatchOperationResultCodes.PIN_NOT_FOUND,
        )

        self.pin_owned_public.refresh_from_db()
        pin_owned2.refresh_from_db()
        self.assertTrue(self.pin_owned_public.private)
        self.assertTrue(pin_owned2.private)

    def test_empty_pin_ids_returns_400(self):
        self._login_owner()
        data = {"pin_ids": [], "private": True}
        response = self.client.post(self.url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_result_has_expected_structure(self):
        self._login_owner()
        data = {"pin_ids": [self.pin_owned_public.id], "private": False}
        response = self.client.post(self.url, data=data, format='json')
        self.assertIn("operation", response.data)
        self.assertIn("total", response.data)
        self.assertIn("success_count", response.data)
        self.assertIn("failed_count", response.data)
        self.assertIn("results", response.data)
        self.assertIsInstance(response.data["results"], list)
        result = response.data["results"][0]
        self.assertIn("pin_id", result)
        self.assertIn("success", result)
        self.assertIn("code", result)
        self.assertIn("message", result)
