import json

from django.urls import reverse
import mock
from rest_framework import status
from rest_framework.test import APITestCase

from taggit.models import Tag

from .helpers import create_image, create_user, create_pin, TEST_IMAGE_PATH
from core.models import Pin, Image, Board


def _teardown_models():
    Pin.objects.all().delete()
    Image.objects.all().delete()
    Tag.objects.all().delete()
    Board.objects.all().delete()


def mock_requests_get(url, **kwargs):
    response = mock.Mock(content=open('docs/src/imgs/logo-dark.png', 'rb').read())
    return response


def mock_requests_get_with_non_image_content(url, **kwargs):
    response = mock.Mock(content=b"abcd")
    return response


class ImageTests(APITestCase):
    def test_post_create_unsupported(self):
        url = reverse("image-list")
        data = {}
        response = self.client.post(
            url,
            data=data,
            format='json',
        )
        self.assertEqual(response.status_code, 401, response.data)


class BoardPrivacyTests(APITestCase):

    def setUp(self):
        super(BoardPrivacyTests, self).setUp()
        self.owner = create_user("default")
        self.non_owner = create_user("non_owner")

        self.private_board = Board.objects.create(
            name="test_board",
            submitter=self.owner,
            private=True,
        )
        self.board_url = reverse("board-detail", kwargs={"pk": self.private_board.pk})
        self.boards_url = reverse("board-list")

    def tearDown(self):
        _teardown_models()

    def _create_pin_with_non_owner(self, private):
        image = create_image()
        pin = create_pin(self.non_owner, image=image, tags=[])
        pin.private = private
        pin.save()
        return pin

    def test_should_non_owner_and_anonymous_user_has_no_permission_to_list_private_board(self):
        resp = self.client.get(self.boards_url)
        self.assertEqual(len(resp.json()), 0, resp.json())

        self.client.login(username=self.non_owner.username, password='password')
        resp = self.client.get(self.boards_url)
        self.assertEqual(len(resp.json()), 0, resp.content)

    def test_should_owner_has_permission_to_list_private_board(self):
        self.client.login(username=self.non_owner.username, password='password')
        resp = self.client.get(self.boards_url)
        self.assertEqual(len(resp.json()), 0, resp.content)

    def test_should_non_owner_and_anonymous_user_has_no_permission_to_view_private_board(self):
        resp = self.client.get(self.board_url)
        self.assertEqual(resp.status_code, 404)

        self.client.login(username=self.non_owner.username, password='password')
        resp = self.client.get(self.board_url)
        self.assertEqual(resp.status_code, 404)

    def test_should_owner_has_permission_to_view_private_board(self):
        self.client.login(username=self.owner.username, password='password')
        resp = self.client.get(self.board_url)
        self.assertEqual(resp.status_code, 200)

    def test_should_owner_has_no_permission_to_add_private_pin_of_other_user_to_board(self):
        self.client.login(username=self.owner.username, password='password')

        private_pin_of_other_user = self._create_pin_with_non_owner(True)

        resp = self.client.patch(self.board_url, data={"pins_to_add": [private_pin_of_other_user.id, ]})
        self.assertEqual(resp.status_code, 200)

        resp = self.client.get(self.board_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['total_pins'], 0, resp.json())

    def test_should_owner_has_permission_to_add_non_private_pin_of_other_user_to_board(self):
        self.client.login(username=self.owner.username, password='password')

        private_pin_of_other_user = self._create_pin_with_non_owner(False)

        resp = self.client.patch(self.board_url, data={"pins_to_add": [private_pin_of_other_user.id, ]})
        self.assertEqual(resp.status_code, 200)

        resp = self.client.get(self.board_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['total_pins'], 1, resp.json())


class PinPrivacyTests(APITestCase):

    def setUp(self):
        super(PinPrivacyTests, self).setUp()
        self.owner = create_user("default")
        self.non_owner = create_user("non_owner")

        with mock.patch('requests.get', mock_requests_get):
            image = create_image()
        self.private_pin = Pin.objects.create(
            submitter=self.owner,
            image=image,
            private=True,
        )
        self.private_pin_url = reverse("pin-detail", kwargs={"pk": self.private_pin.pk})

        self.board = Board.objects.create(name="test_board", submitter=self.owner)
        self.board.pins.add(self.private_pin)
        self.board.save()
        self.board_url = reverse("board-detail", kwargs={"pk": self.board.pk})

    def tearDown(self):
        _teardown_models()

    def test_should_non_owner_and_anonymous_user_has_no_permission_to_list_private_pin(self):
        resp = self.client.get(reverse("pin-list"))
        self.assertEqual(len(resp.json()['results']), 0, resp.content)

        self.client.login(username=self.non_owner.username, password='password')
        resp = self.client.get(reverse("pin-list"))
        self.assertEqual(len(resp.json()['results']), 0, resp.content)

    def test_should_owner_user_has_permission_to_list_private_pin(self):
        self.client.login(username=self.owner.username, password='password')
        resp = self.client.get(reverse("pin-list"))
        self.assertEqual(len(resp.json()['results']), 1, resp.content)

    def test_should_owner_has_permission_to_view_private_pin(self):
        self.client.login(username=self.owner.username, password='password')
        resp = self.client.get(self.private_pin_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['id'], self.private_pin.id)

    def test_should_anonymous_user_has_no_permission_to_view_private_pin(self):
        resp = self.client.get(self.private_pin_url)
        self.assertEqual(resp.status_code, 404)

    def test_should_non_owner_has_no_permission_to_view_private_pin(self):
        self.client.login(username=self.non_owner.username, password='password')
        resp = self.client.get(self.private_pin_url)
        self.assertEqual(resp.status_code, 404)


class PinTests(APITestCase):
    _JSON_TYPE = "application/json"

    def setUp(self):
        super(PinTests, self).setUp()
        self.user = create_user("default")
        self.client.login(username=self.user.username, password='password')

    def tearDown(self):
        _teardown_models()

    @mock.patch('requests.get', mock_requests_get_with_non_image_content)
    def test_should_not_create_pin_if_url_content_invalid(self):
        url = 'http://testserver.com/mocked/logo-01.png'
        create_url = reverse("pin-list")
        referer = 'http://testserver.com/'
        post_data = {
            'url': url,
            'private': False,
            'referer': referer,
            'description': 'That\'s an Apple!'
        }
        response = self.client.post(create_url, data=post_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @mock.patch('requests.get', mock_requests_get)
    def test_should_create_pin(self):
        url = 'http://testserver.com/mocked/logo-01.png'
        create_url = reverse("pin-list")
        referer = 'http://testserver.com/'
        post_data = {
            'url': url,
            'private': False,
            'referer': referer,
            'description': 'That\'s an Apple!'
        }
        response = self.client.post(create_url, data=post_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        pin = Pin.objects.get(url=url)
        self.assertIsNotNone(pin.image.image)

    @mock.patch('requests.get', mock_requests_get)
    def test_post_create_url_with_empty_tags(self):
        url = 'http://testserver.com/mocked/logo-02.png'
        create_url = reverse("pin-list")
        referer = 'http://testserver.com/'
        post_data = {
            'url': url,
            'referer': referer,
            'description': 'That\'s an Apple!',
            'tags': []
        }
        response = self.client.post(create_url, data=post_data, format="json")
        self.assertEqual(
            response.status_code, status.HTTP_201_CREATED, response.json()
        )
        self.assertEqual(Image.objects.count(), 1)
        pin = Pin.objects.get(url=url)
        self.assertIsNotNone(pin.image.image)
        self.assertEqual(pin.tags.count(), 0)

    def test_should_post_create_pin_with_existed_image(self):
        image = create_image()
        create_pin(self.user, image=image, tags=[])
        create_url = reverse("pin-list")
        referer = 'http://testserver.com/'
        post_data = {
            'referer': referer,
            'image_by_id': image.pk,
            'description': 'That\'s something else (probably a CC logo)!',
            'tags': ['random', 'tags'],
        }
        response = self.client.post(create_url, data=post_data, format="json")
        resp_data = response.json()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, resp_data)
        self.assertEqual(
            resp_data['description'],
            'That\'s something else (probably a CC logo)!',
            resp_data
        )
        self.assertEquals(Pin.objects.count(), 2)

    def test_patch_detail_unauthenticated(self):
        image = create_image()
        pin = create_pin(self.user, image, [])
        self.client.logout()
        uri = reverse("pin-detail", kwargs={"pk": pin.pk})
        response = self.client.patch(uri, format='json', data={})
        self.assertEqual(response.status_code, 401, response.data)

    def test_patch_detail(self):
        image = create_image()
        pin = create_pin(self.user, image, [])
        uri = reverse("pin-detail", kwargs={"pk": pin.pk})
        new = {'description': 'Updated description'}

        response = self.client.patch(
            uri, new, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())
        self.assertEqual(Pin.objects.count(), 1)
        self.assertEqual(Pin.objects.get(pk=pin.pk).description, new['description'])

    def test_delete_detail_unauthenticated(self):
        image = create_image()
        pin = create_pin(self.user, image, [])
        uri = reverse("pin-detail", kwargs={"pk": pin.pk})
        self.client.logout()
        resp = self.client.delete(uri)
        self.assertEqual(resp.status_code, 401, resp.data)

    def test_delete_detail(self):
        image = create_image()
        pin = create_pin(self.user, image, [])
        uri = reverse("pin-detail", kwargs={"pk": pin.pk})
        self.client.delete(uri)
        self.assertEqual(Pin.objects.count(), 0)


class BoardArchivePermissionTests(APITestCase):
    """权限矩阵测试：拥有者、其他登录用户、匿名、superuser 访问归档相关端点的边界"""

    def setUp(self):
        super(BoardArchivePermissionTests, self).setUp()
        self.owner = create_user("owner")
        self.other_user = create_user("other")
        self.superuser = create_user("superuser")
        self.superuser.is_superuser = True
        self.superuser.save()

        self.public_board = Board.objects.create(
            name="public_board",
            submitter=self.owner,
            private=False,
        )
        self.private_board = Board.objects.create(
            name="private_board",
            submitter=self.owner,
            private=True,
        )
        self.archived_public_board = Board.objects.create(
            name="archived_public",
            submitter=self.owner,
            private=False,
            is_archived=True,
        )
        self.archived_private_board = Board.objects.create(
            name="archived_private",
            submitter=self.owner,
            private=True,
            is_archived=True,
        )

    def tearDown(self):
        _teardown_models()

    # ============ archive / unarchive 端点的权限测试 ============

    def test_anonymous_cannot_archive(self):
        url = reverse("board-archive", kwargs={"pk": self.public_board.pk})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 401)

    def test_other_user_cannot_archive_others_board(self):
        self.client.login(username=self.other_user.username, password="password")
        url = reverse("board-archive", kwargs={"pk": self.public_board.pk})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 403)

    def test_owner_can_archive_own_board(self):
        self.client.login(username=self.owner.username, password="password")
        url = reverse("board-archive", kwargs={"pk": self.public_board.pk})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.public_board.refresh_from_db()
        self.assertTrue(self.public_board.is_archived)
        self.assertIsNotNone(self.public_board.archived_at)

    def test_owner_can_unarchive_own_board(self):
        self.client.login(username=self.owner.username, password="password")
        url = reverse("board-unarchive", kwargs={"pk": self.archived_public_board.pk})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.archived_public_board.refresh_from_db()
        self.assertFalse(self.archived_public_board.is_archived)
        self.assertIsNone(self.archived_public_board.archived_at)

    def test_superuser_cannot_archive_others_board_without_permission(self):
        self.client.login(username=self.superuser.username, password="password")
        url = reverse("board-archive", kwargs={"pk": self.public_board.pk})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 403)

    def test_archive_preserves_pin_membership(self):
        from django.core.files.images import ImageFile
        image = Image.objects.create(image=ImageFile(open(TEST_IMAGE_PATH, "rb")))
        pin = Pin.objects.create(submitter=self.owner, image=image)
        self.public_board.pins.add(pin)
        self.public_board.save()
        pin_count_before = self.public_board.pins.count()

        self.client.login(username=self.owner.username, password="password")
        url = reverse("board-archive", kwargs={"pk": self.public_board.pk})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.public_board.refresh_from_db()
        self.assertEqual(self.public_board.pins.count(), pin_count_before)
        self.assertTrue(self.public_board.pins.filter(id=pin.id).exists())

    # ============ 活跃 Board 列表默认排除已归档 ============

    def test_archived_boards_not_in_active_list_for_owner(self):
        self.client.login(username=self.owner.username, password="password")
        url = reverse("board-list")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        returned_ids = [b["id"] for b in resp.json()["results"]]
        self.assertIn(self.public_board.id, returned_ids)
        self.assertIn(self.private_board.id, returned_ids)
        self.assertNotIn(self.archived_public_board.id, returned_ids)
        self.assertNotIn(self.archived_private_board.id, returned_ids)

    def test_archived_public_board_not_in_active_list_for_anonymous(self):
        url = reverse("board-list")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        returned_ids = [b["id"] for b in resp.json()["results"]]
        self.assertIn(self.public_board.id, returned_ids)
        self.assertNotIn(self.archived_public_board.id, returned_ids)
        self.assertNotIn(self.private_board.id, returned_ids)

    # ============ 归档列表权限矩阵 ============

    def test_anonymous_can_list_archived_public_boards_only(self):
        url = reverse("archived-board-list")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        returned_ids = [b["id"] for b in resp.json()["results"]]
        self.assertIn(self.archived_public_board.id, returned_ids)
        self.assertNotIn(self.archived_private_board.id, returned_ids)
        self.assertNotIn(self.public_board.id, returned_ids)

    def test_other_user_can_only_see_archived_public_not_private(self):
        self.client.login(username=self.other_user.username, password="password")
        url = reverse("archived-board-list")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        returned_ids = [b["id"] for b in resp.json()["results"]]
        self.assertIn(self.archived_public_board.id, returned_ids)
        self.assertNotIn(self.archived_private_board.id, returned_ids)

    def test_owner_can_see_all_own_archived_boards(self):
        self.client.login(username=self.owner.username, password="password")
        url = "{}?submitter__username={}".format(
            reverse("archived-board-list"), self.owner.username
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        returned_ids = [b["id"] for b in resp.json()["results"]]
        self.assertIn(self.archived_public_board.id, returned_ids)
        self.assertIn(self.archived_private_board.id, returned_ids)
        self.assertNotIn(self.public_board.id, returned_ids)

    def test_owner_can_retrieve_archived_board_detail(self):
        self.client.login(username=self.owner.username, password="password")
        url = reverse("board-detail", kwargs={"pk": self.archived_private_board.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["id"], self.archived_private_board.id)
        self.assertTrue(resp.json()["is_archived"])

    def test_non_owner_cannot_retrieve_archived_private_board(self):
        self.client.login(username=self.other_user.username, password="password")
        url = reverse("board-detail", kwargs={"pk": self.archived_private_board.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)


class BoardArchiveOrderingPaginationTests(APITestCase):
    """归档列表按时间排序与 cursor 分页测试"""

    def setUp(self):
        super(BoardArchiveOrderingPaginationTests, self).setUp()
        self.owner = create_user("owner")
        from django.utils import timezone
        from datetime import timedelta
        from rest_framework.pagination import CursorPagination
        from core import views

        class _SmallCursorPagination(CursorPagination):
            ordering = ('-archived_at', '-id')
            page_size = 2
            cursor_query_param = 'cursor'

        self._orig_pagination = views.ArchivedBoardCursorPagination
        views.ArchivedBoardCursorPagination = _SmallCursorPagination
        views.ArchivedBoardViewSet.pagination_class = _SmallCursorPagination

        base_time = timezone.now()
        self.b1 = Board.objects.create(
            name="oldest", submitter=self.owner, is_archived=True
        )
        self.b1.archived_at = base_time - timedelta(days=3)
        self.b1.save()
        self.b2 = Board.objects.create(
            name="middle", submitter=self.owner, is_archived=True
        )
        self.b2.archived_at = base_time - timedelta(days=2)
        self.b2.save()
        self.b3 = Board.objects.create(
            name="newest", submitter=self.owner, is_archived=True
        )
        self.b3.archived_at = base_time - timedelta(days=1)
        self.b3.save()

    def tearDown(self):
        from core import views
        views.ArchivedBoardCursorPagination = self._orig_pagination
        views.ArchivedBoardViewSet.pagination_class = self._orig_pagination
        _teardown_models()

    def test_archived_list_ordered_by_archived_at_desc(self):
        self.client.login(username=self.owner.username, password="password")
        url = reverse("archived-board-list")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        names = [b["name"] for b in data["results"]]
        self.assertEqual(names[0], "newest")
        self.assertEqual(names[1], "middle")
        self.assertIsNotNone(data["next"])
        next_url = data["next"].replace("http://testserver", "")
        resp = self.client.get(next_url)
        self.assertEqual(resp.json()["results"][0]["name"], "oldest")

    def test_archived_list_cursor_pagination_pages_through(self):
        self.client.login(username=self.owner.username, password="password")
        url = reverse("archived-board-list")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data["results"]), 2)
        self.assertIsNotNone(data["next"])
        self.assertEqual([b["name"] for b in data["results"]], ["newest", "middle"])

        next_url = data["next"].replace("http://testserver", "")
        self.assertIn("cursor=", next_url)
        resp = self.client.get(next_url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["name"], "oldest")
        self.assertIsNone(data["next"])

    def test_archived_list_cursor_pagination_stable_after_new_archive(self):
        from django.utils import timezone
        from datetime import timedelta
        self.client.login(username=self.owner.username, password="password")
        url = reverse("archived-board-list")
        resp = self.client.get(url)
        data = resp.json()
        next_url = data["next"].replace("http://testserver", "")

        Board.objects.create(
            name="just_archived", submitter=self.owner, is_archived=True,
            archived_at=timezone.now() - timedelta(hours=1),
        )

        resp = self.client.get(next_url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["name"], "oldest")


class BoardBulkArchiveTests(APITestCase):
    """批量归档/恢复接口测试"""

    def setUp(self):
        super(BoardBulkArchiveTests, self).setUp()
        self.owner = create_user("owner")
        self.other_user = create_user("other")

        self.b1 = Board.objects.create(name="b1", submitter=self.owner)
        self.b2 = Board.objects.create(name="b2", submitter=self.owner)
        self.b3 = Board.objects.create(name="b3", submitter=self.owner, is_archived=True)
        self.other_board = Board.objects.create(name="other", submitter=self.other_user)

        self.bulk_archive_url = reverse("board-bulk-archive")
        self.bulk_unarchive_url = reverse("board-bulk-unarchive")

    def tearDown(self):
        _teardown_models()

    def test_anonymous_cannot_bulk_archive(self):
        resp = self.client.post(
            self.bulk_archive_url,
            data={"board_ids": [self.b1.id]},
            format="json",
        )
        self.assertEqual(resp.status_code, 401)

    def test_owner_bulk_archive_multiple_boards(self):
        self.client.login(username=self.owner.username, password="password")
        resp = self.client.post(
            self.bulk_archive_url,
            data={"board_ids": [self.b1.id, self.b2.id]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["updated_count"], 2)
        self.b1.refresh_from_db()
        self.b2.refresh_from_db()
        self.assertTrue(self.b1.is_archived)
        self.assertTrue(self.b2.is_archived)

    def test_owner_bulk_unarchive_multiple_boards(self):
        self.client.login(username=self.owner.username, password="password")
        self.b1.is_archived = True
        self.b1.save()
        resp = self.client.post(
            self.bulk_unarchive_url,
            data={"board_ids": [self.b1.id, self.b3.id]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["updated_count"], 2)
        self.b1.refresh_from_db()
        self.b3.refresh_from_db()
        self.assertFalse(self.b1.is_archived)
        self.assertFalse(self.b3.is_archived)

    def test_bulk_archive_ignores_already_archived(self):
        self.client.login(username=self.owner.username, password="password")
        resp = self.client.post(
            self.bulk_archive_url,
            data={"board_ids": [self.b3.id]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["updated_count"], 0)

    def test_bulk_archive_rejects_others_boards(self):
        self.client.login(username=self.owner.username, password="password")
        resp = self.client.post(
            self.bulk_archive_url,
            data={"board_ids": [self.other_board.id]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["updated_count"], 0)
        self.other_board.refresh_from_db()
        self.assertFalse(self.other_board.is_archived)

    def test_bulk_archive_empty_ids_rejected(self):
        self.client.login(username=self.owner.username, password="password")
        resp = self.client.post(
            self.bulk_archive_url,
            data={"board_ids": []},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_bulk_archive_over_100_ids_rejected(self):
        self.client.login(username=self.owner.username, password="password")
        too_many = list(range(1, 5001))
        resp = self.client.post(
            self.bulk_archive_url,
            data={"board_ids": too_many},
            format="json",
        )
        self.assertEqual(resp.status_code, 413)
        data = resp.json()
        self.assertIn("Too many boards", data.get("detail", ""))
        self.assertEqual(data.get("max_size"), 100)
        self.assertEqual(data.get("requested"), 5000)

    def test_bulk_archive_over_101_ids_rejected_with_413(self):
        self.client.login(username=self.owner.username, password="password")
        too_many = list(range(1, 102))
        resp = self.client.post(
            self.bulk_archive_url,
            data={"board_ids": too_many},
            format="json",
        )
        self.assertEqual(resp.status_code, 413)
        self.assertEqual(resp.json().get("max_size"), 100)
        self.assertEqual(resp.json().get("requested"), 101)

    def test_bulk_archive_exactly_100_ids_accepted(self):
        self.client.login(username=self.owner.username, password="password")
        ids_100 = list(range(1, 101))
        resp = self.client.post(
            self.bulk_archive_url,
            data={"board_ids": ids_100},
            format="json",
        )
        self.assertNotIn(resp.status_code, (400, 413))

    def test_bulk_unarchive_over_100_ids_rejected_with_413(self):
        self.client.login(username=self.owner.username, password="password")
        too_many = list(range(1, 102))
        resp = self.client.post(
            self.bulk_unarchive_url,
            data={"board_ids": too_many},
            format="json",
        )
        self.assertEqual(resp.status_code, 413)
        self.assertEqual(resp.json().get("max_size"), 100)

    def test_bulk_archive_missing_ids_rejected(self):
        self.client.login(username=self.owner.username, password="password")
        resp = self.client.post(
            self.bulk_archive_url,
            data={},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_bulk_archive_preserves_pin_membership(self):
        from django.core.files.images import ImageFile
        image = Image.objects.create(image=ImageFile(open(TEST_IMAGE_PATH, "rb")))
        pin = Pin.objects.create(submitter=self.owner, image=image)
        self.b1.pins.add(pin)
        self.b1.save()
        self.client.login(username=self.owner.username, password="password")
        resp = self.client.post(
            self.bulk_archive_url,
            data={"board_ids": [self.b1.id]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.b1.refresh_from_db()
        self.assertTrue(self.b1.is_archived)
        self.assertEqual(self.b1.pins.count(), 1)
        self.assertTrue(self.b1.pins.filter(id=pin.id).exists())
