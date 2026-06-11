import json

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.exceptions import ErrorCode
from core.models import Board, Pin
from core.tests.helpers import create_user


def assert_error_format(test_case, response, expected_status=None, expected_code=None):
    data = response.json()
    test_case.assertIn("code", data, "Response missing 'code' field")
    test_case.assertIn("message", data, "Response missing 'message' field")
    test_case.assertIn("detail", data, "Response missing 'detail' field")
    test_case.assertIsInstance(data["code"], int, "'code' should be an integer")
    test_case.assertIsInstance(data["message"], str, "'message' should be a string")
    if expected_status is not None:
        test_case.assertEqual(response.status_code, expected_status)
    if expected_code is not None:
        test_case.assertEqual(data["code"], expected_code)
    return data


class UserCreateErrorFormatTests(APITestCase):
    def test_missing_password_and_password_repeat_returns_unified_format(self):
        url = reverse("users:user-list")
        response = self.client.post(url, data={"username": "testuser"}, format="json")
        data = assert_error_format(self, response, status.HTTP_400_BAD_REQUEST, ErrorCode.VALIDATION_ERROR)
        self.assertIn("password", data)
        self.assertIn("password_repeat", data)
        self.assertIsInstance(data["detail"], dict)

    def test_password_mismatch_returns_unified_format(self):
        url = reverse("users:user-list")
        response = self.client.post(
            url,
            data={
                "username": "testuser",
                "email": "test@example.com",
                "password": "password1",
                "password_repeat": "password2",
            },
            format="json",
        )
        data = assert_error_format(self, response, status.HTTP_400_BAD_REQUEST, ErrorCode.VALIDATION_ERROR)
        self.assertIn("password_repeat", data)
        self.assertIn("password_repeat", data["detail"])

    @override_settings(ALLOW_NEW_REGISTRATIONS=False)
    def test_registration_disabled_returns_401_with_unified_format(self):
        url = reverse("users:user-list")
        response = self.client.post(
            url,
            data={
                "username": "testuser",
                "email": "test@example.com",
                "password": "password",
                "password_repeat": "password",
            },
            format="json",
        )
        assert_error_format(self, response, status.HTTP_401_UNAUTHORIZED)


class PinCreationErrorFormatTests(APITestCase):
    def setUp(self):
        self.user = create_user("pin_tester")
        self.client.login(username=self.user.username, password="password")

    def test_anonymous_user_create_pin_returns_401_format(self):
        self.client.logout()
        url = reverse("pin-list")
        response = self.client.post(url, data={}, format="json")
        data = assert_error_format(self, response, status.HTTP_401_UNAUTHORIZED)
        self.assertIsInstance(data["code"], int)

    def test_missing_url_and_image_returns_validation_format(self):
        url = reverse("pin-list")
        response = self.client.post(url, data={"description": "test"}, format="json")
        data = assert_error_format(self, response, status.HTTP_400_BAD_REQUEST, ErrorCode.VALIDATION_ERROR)
        self.assertTrue(
            "url-or-image" in data or "url" in data["detail"] or "url-or-image" in data["detail"],
            f"Expected field error in response, got keys: {list(data.keys())}, detail keys: {list(data.get('detail', {}).keys())}",
        )

    def test_get_nonexistent_pin_returns_404_format(self):
        url = reverse("pin-detail", kwargs={"pk": 99999})
        response = self.client.get(url)
        assert_error_format(self, response, status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND)


class BoardErrorFormatTests(APITestCase):
    def setUp(self):
        self.owner = create_user("board_owner")
        self.other_user = create_user("board_other")
        self.private_board = Board.objects.create(
            name="Private Board",
            submitter=self.owner,
            private=True,
        )
        self.public_board = Board.objects.create(
            name="Public Board",
            submitter=self.owner,
            private=False,
        )

    def test_anonymous_user_access_private_board_returns_404(self):
        self.client.logout()
        url = reverse("board-detail", kwargs={"pk": self.private_board.pk})
        response = self.client.get(url)
        assert_error_format(self, response, status.HTTP_404_NOT_FOUND)

    def test_non_owner_access_private_board_returns_404(self):
        self.client.login(username=self.other_user.username, password="password")
        url = reverse("board-detail", kwargs={"pk": self.private_board.pk})
        response = self.client.get(url)
        assert_error_format(self, response, status.HTTP_404_NOT_FOUND)

    def test_create_duplicate_board_name_returns_validation_format(self):
        self.client.login(username=self.owner.username, password="password")
        Board.objects.create(name="Unique Name", submitter=self.owner, private=False)
        url = "/api/v2/boards/"
        response = self.client.post(
            url,
            data={"name": "Unique Name", "private": False},
            format="json",
        )
        data = assert_error_format(self, response, status.HTTP_400_BAD_REQUEST, ErrorCode.VALIDATION_ERROR)
        self.assertIn("name", data)

    def test_anonymous_delete_board_returns_401(self):
        self.client.logout()
        url = reverse("board-detail", kwargs={"pk": self.public_board.pk})
        response = self.client.delete(url)
        assert_error_format(self, response, status.HTTP_401_UNAUTHORIZED)

    def test_non_owner_patch_public_board_returns_403(self):
        self.client.login(username=self.other_user.username, password="password")
        url = reverse("board-detail", kwargs={"pk": self.public_board.pk})
        response = self.client.patch(url, data={"name": "hacked"}, format="json")
        assert_error_format(self, response, status.HTTP_403_FORBIDDEN, ErrorCode.PERMISSION_DENIED)


class ImageUploadErrorFormatTests(APITestCase):
    def test_anonymous_upload_image_returns_401_format(self):
        url = reverse("image-list")
        response = self.client.post(url, data={}, format="json")
        data = assert_error_format(self, response, status.HTTP_401_UNAUTHORIZED)
        self.assertIsInstance(data["code"], int)
        self.assertIsInstance(data["message"], str)


class LoginErrorFormatTests(TestCase):
    def _post_login(self, payload):
        return self.client.post(
            "/api/v2/profile/login/",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_invalid_json_returns_unified_format(self):
        response = self.client.post(
            "/api/v2/profile/login/",
            data="not valid json",
            content_type="application/json",
        )
        data = assert_error_format(self, response, status.HTTP_400_BAD_REQUEST, ErrorCode.PARSE_ERROR)
        self.assertIn("non_field_errors", data)

    def test_missing_username_returns_unified_format(self):
        response = self._post_login({"password": "pw"})
        data = assert_error_format(self, response, status.HTTP_400_BAD_REQUEST, ErrorCode.VALIDATION_ERROR)
        self.assertIn("username", data)
        self.assertIn("username", data["detail"])

    def test_missing_password_returns_unified_format(self):
        response = self._post_login({"username": "u"})
        data = assert_error_format(self, response, status.HTTP_400_BAD_REQUEST, ErrorCode.VALIDATION_ERROR)
        self.assertIn("password", data)
        self.assertIn("password", data["detail"])

    def test_wrong_credentials_returns_unified_format(self):
        create_user("login_tester")
        response = self._post_login({
            "username": "user_login_tester",
            "password": "wrongpassword",
        })
        data = assert_error_format(self, response, status.HTTP_400_BAD_REQUEST, ErrorCode.AUTHENTICATION_FAILED)
        self.assertIn("password", data)
        self.assertIn("password", data["detail"])

    def test_missing_both_fields_returns_both_errors(self):
        response = self._post_login({})
        data = assert_error_format(self, response, status.HTTP_400_BAD_REQUEST, ErrorCode.VALIDATION_ERROR)
        self.assertIn("username", data)
        self.assertIn("password", data)


class PublicMiddlewareErrorFormatTests(TestCase):
    @override_settings(PUBLIC=False)
    def test_anonymous_access_non_acceptable_path_returns_403_format(self):
        response = self.client.get("/api/v2/pins/")
        data = assert_error_format(self, response, status.HTTP_403_FORBIDDEN, ErrorCode.FORBIDDEN)
        self.assertIsInstance(data["message"], str)
        self.assertIsInstance(data["detail"], dict)

    @override_settings(PUBLIC=False)
    def test_anonymous_access_profile_still_allowed(self):
        response = self.client.get("/api/v2/profile/login/")
        self.assertNotEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class BackwardCompatibilityTests(APITestCase):
    def test_field_errors_available_at_top_level_for_old_clients(self):
        url = reverse("users:user-list")
        response = self.client.post(url, data={"username": "u"}, format="json")
        data = response.json()
        self.assertIn("password", data)
        self.assertIn("password_repeat", data)
        self.assertIsInstance(data["password"], str)
        self.assertIsInstance(data["password_repeat"], str)

    def test_field_errors_also_available_in_detail_for_new_clients(self):
        url = reverse("users:user-list")
        response = self.client.post(url, data={"username": "u"}, format="json")
        data = response.json()
        self.assertIn("password", data["detail"])
        self.assertIn("password_repeat", data["detail"])
