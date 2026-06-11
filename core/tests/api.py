import json

from django.urls import reverse
import mock
from rest_framework import status
from rest_framework.test import APITestCase

from taggit.models import Tag

from .helpers import create_image, create_user, create_pin
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
        self.assertEqual(Pin.objects.count(), 2)

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


class BoardVisibilityMatrixTests(APITestCase):
    """跨用户 Board 可见性权限矩阵测试"""

    def setUp(self):
        super(BoardVisibilityMatrixTests, self).setUp()
        self.owner = create_user("owner")
        self.other_user = create_user("other")
        self.third_user = create_user("third")

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

        with mock.patch('requests.get', mock_requests_get):
            self.image = create_image()
        self.public_pin = create_pin(self.owner, self.image, [])
        self.public_pin.private = False
        self.public_pin.save()

        self.private_pin = create_pin(self.owner, self.image, [])
        self.private_pin.private = True
        self.private_pin.save()

        self.public_board.pins.add(self.public_pin, self.private_pin)
        self.private_board.pins.add(self.public_pin, self.private_pin)

        self.public_board_url = reverse("board-detail", kwargs={"pk": self.public_board.pk})
        self.private_board_url = reverse("board-detail", kwargs={"pk": self.private_board.pk})
        self.boards_list_url = reverse("board-list")

    def tearDown(self):
        _teardown_models()

    def test_anonymous_can_list_only_public_boards(self):
        resp = self.client.get(self.boards_list_url)
        self.assertEqual(resp.status_code, 200)
        board_ids = [b['id'] for b in resp.json()]
        self.assertIn(self.public_board.id, board_ids)
        self.assertNotIn(self.private_board.id, board_ids)

    def test_owner_can_list_all_own_boards(self):
        self.client.login(username=self.owner.username, password='password')
        resp = self.client.get(self.boards_list_url)
        self.assertEqual(resp.status_code, 200)
        board_ids = [b['id'] for b in resp.json()]
        self.assertIn(self.public_board.id, board_ids)
        self.assertIn(self.private_board.id, board_ids)

    def test_other_user_can_list_only_public_boards(self):
        self.client.login(username=self.other_user.username, password='password')
        resp = self.client.get(self.boards_list_url)
        self.assertEqual(resp.status_code, 200)
        board_ids = [b['id'] for b in resp.json()]
        self.assertIn(self.public_board.id, board_ids)
        self.assertNotIn(self.private_board.id, board_ids)

    def test_anonymous_can_view_public_board(self):
        resp = self.client.get(self.public_board_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['id'], self.public_board.id)

    def test_anonymous_cannot_view_private_board(self):
        resp = self.client.get(self.private_board_url)
        self.assertEqual(resp.status_code, 404)

    def test_other_user_can_view_public_board(self):
        self.client.login(username=self.other_user.username, password='password')
        resp = self.client.get(self.public_board_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['id'], self.public_board.id)

    def test_other_user_cannot_view_private_board(self):
        self.client.login(username=self.other_user.username, password='password')
        resp = self.client.get(self.private_board_url)
        self.assertEqual(resp.status_code, 404)

    def test_owner_can_view_private_board(self):
        self.client.login(username=self.owner.username, password='password')
        resp = self.client.get(self.private_board_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['id'], self.private_board.id)

    def test_anonymous_cannot_edit_public_board(self):
        resp = self.client.patch(
            self.public_board_url,
            data={"name": "hacked_name"},
            format='json',
        )
        self.assertEqual(resp.status_code, 401)

    def test_other_user_cannot_edit_public_board(self):
        self.client.login(username=self.other_user.username, password='password')
        resp = self.client.patch(
            self.public_board_url,
            data={"name": "hacked_name"},
            format='json',
        )
        self.assertEqual(resp.status_code, 403)

    def test_other_user_cannot_delete_public_board(self):
        self.client.login(username=self.other_user.username, password='password')
        resp = self.client.delete(self.public_board_url)
        self.assertEqual(resp.status_code, 403)

    def test_owner_can_edit_own_board(self):
        self.client.login(username=self.owner.username, password='password')
        resp = self.client.patch(
            self.public_board_url,
            data={"name": "updated_name"},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.public_board.refresh_from_db()
        self.assertEqual(self.public_board.name, "updated_name")

    def test_owner_can_delete_own_board(self):
        self.client.login(username=self.owner.username, password='password')
        resp = self.client.delete(self.private_board_url)
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(Board.objects.filter(pk=self.private_board.pk).exists())

    def test_public_board_pins_count_excludes_private_pins_for_non_owner(self):
        self.client.login(username=self.other_user.username, password='password')
        resp = self.client.get(self.public_board_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['total_pins'], 1)

    def test_public_board_pins_count_includes_all_pins_for_owner(self):
        self.client.login(username=self.owner.username, password='password')
        resp = self.client.get(self.public_board_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['total_pins'], 2)

    def test_anonymous_sees_only_public_pins_in_public_board(self):
        resp = self.client.get(self.public_board_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['total_pins'], 1)

    def test_filter_boards_by_submitter_anonymous(self):
        resp = self.client.get(
            f"{self.boards_list_url}?submitter__username={self.owner.username}"
        )
        self.assertEqual(resp.status_code, 200)
        board_ids = [b['id'] for b in resp.json()]
        self.assertIn(self.public_board.id, board_ids)
        self.assertNotIn(self.private_board.id, board_ids)

    def test_board_autocomplete_excludes_private_boards_for_non_owner(self):
        self.client.login(username=self.other_user.username, password='password')
        autocomplete_url = "/api/v2/boards-auto-complete/"
        resp = self.client.get(autocomplete_url)
        self.assertEqual(resp.status_code, 200)
        board_ids = [b['id'] for b in resp.json()]
        self.assertIn(self.public_board.id, board_ids)
        self.assertNotIn(self.private_board.id, board_ids)


class PinVisibilityAndThumbnailTests(APITestCase):
    """Pin 可见性和缩略图访问权限测试"""

    def setUp(self):
        super(PinVisibilityAndThumbnailTests, self).setUp()
        self.owner = create_user("owner")
        self.other_user = create_user("other")

        with mock.patch('requests.get', mock_requests_get):
            self.image = create_image()

        self.public_pin = create_pin(self.owner, self.image, [])
        self.public_pin.private = False
        self.public_pin.save()

        self.private_pin = create_pin(self.owner, self.image, [])
        self.private_pin.private = True
        self.private_pin.save()

        self.other_public_pin = create_pin(self.other_user, self.image, [])
        self.other_public_pin.private = False
        self.other_public_pin.save()

        self.other_private_pin = create_pin(self.other_user, self.image, [])
        self.other_private_pin.private = True
        self.other_private_pin.save()

        self.public_pin_url = reverse("pin-detail", kwargs={"pk": self.public_pin.pk})
        self.private_pin_url = reverse("pin-detail", kwargs={"pk": self.private_pin.pk})
        self.pins_list_url = reverse("pin-list")

    def tearDown(self):
        _teardown_models()

    def test_anonymous_can_list_public_pins_only(self):
        resp = self.client.get(self.pins_list_url)
        self.assertEqual(resp.status_code, 200)
        pin_ids = [p['id'] for p in resp.json()['results']]
        self.assertIn(self.public_pin.id, pin_ids)
        self.assertIn(self.other_public_pin.id, pin_ids)
        self.assertNotIn(self.private_pin.id, pin_ids)
        self.assertNotIn(self.other_private_pin.id, pin_ids)

    def test_owner_can_list_own_private_and_all_public(self):
        self.client.login(username=self.owner.username, password='password')
        resp = self.client.get(self.pins_list_url)
        self.assertEqual(resp.status_code, 200)
        pin_ids = [p['id'] for p in resp.json()['results']]
        self.assertIn(self.public_pin.id, pin_ids)
        self.assertIn(self.private_pin.id, pin_ids)
        self.assertIn(self.other_public_pin.id, pin_ids)
        self.assertNotIn(self.other_private_pin.id, pin_ids)

    def test_anonymous_can_view_public_pin(self):
        resp = self.client.get(self.public_pin_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['id'], self.public_pin.id)

    def test_anonymous_can_access_public_pin_image_data(self):
        resp = self.client.get(self.public_pin_url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('image', data)
        self.assertIsNotNone(data['image'])
        self.assertIn('thumbnail', data['image'])
        self.assertIn('standard', data['image'])
        self.assertIn('square', data['image'])

    def test_anonymous_cannot_view_private_pin(self):
        resp = self.client.get(self.private_pin_url)
        self.assertEqual(resp.status_code, 404)

    def test_other_user_cannot_view_private_pin(self):
        self.client.login(username=self.other_user.username, password='password')
        resp = self.client.get(self.private_pin_url)
        self.assertEqual(resp.status_code, 404)

    def test_owner_can_view_own_private_pin(self):
        self.client.login(username=self.owner.username, password='password')
        resp = self.client.get(self.private_pin_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['id'], self.private_pin.id)

    def test_owner_can_access_private_pin_image_data(self):
        self.client.login(username=self.owner.username, password='password')
        resp = self.client.get(self.private_pin_url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('image', data)
        self.assertIsNotNone(data['image'])
        self.assertIn('thumbnail', data['image'])

    def test_other_user_cannot_edit_public_pin(self):
        self.client.login(username=self.other_user.username, password='password')
        resp = self.client.patch(
            self.public_pin_url,
            data={"description": "hacked"},
            format='json',
        )
        self.assertEqual(resp.status_code, 403)

    def test_owner_can_edit_own_public_pin(self):
        self.client.login(username=self.owner.username, password='password')
        resp = self.client.patch(
            self.public_pin_url,
            data={"description": "updated"},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.public_pin.refresh_from_db()
        self.assertEqual(self.public_pin.description, "updated")

    def test_anonymous_cannot_edit_public_pin(self):
        resp = self.client.patch(
            self.public_pin_url,
            data={"description": "hacked"},
            format='json',
        )
        self.assertEqual(resp.status_code, 401)

    def test_other_user_cannot_delete_public_pin(self):
        self.client.login(username=self.other_user.username, password='password')
        resp = self.client.delete(self.public_pin_url)
        self.assertEqual(resp.status_code, 403)

    def test_owner_can_delete_own_pin(self):
        self.client.login(username=self.owner.username, password='password')
        resp = self.client.delete(self.public_pin_url)
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(Pin.objects.filter(pk=self.public_pin.pk).exists())

    def test_filter_pins_by_submitter_anonymous(self):
        resp = self.client.get(
            f"{self.pins_list_url}?submitter__username={self.owner.username}"
        )
        self.assertEqual(resp.status_code, 200)
        pin_ids = [p['id'] for p in resp.json()['results']]
        self.assertIn(self.public_pin.id, pin_ids)
        self.assertNotIn(self.private_pin.id, pin_ids)

    def test_owner_can_toggle_pin_privacy(self):
        self.client.login(username=self.owner.username, password='password')
        resp = self.client.patch(
            self.public_pin_url,
            data={"private": True},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.public_pin.refresh_from_db()
        self.assertTrue(self.public_pin.private)

        self.client.logout()
        resp = self.client.get(self.public_pin_url)
        self.assertEqual(resp.status_code, 404)

    def test_pin_private_field_not_writable_by_other_user(self):
        self.client.login(username=self.other_user.username, password='password')
        resp = self.client.patch(
            self.public_pin_url,
            data={"private": True},
            format='json',
        )
        self.assertEqual(resp.status_code, 403)

    def test_board_cover_excludes_private_pins_for_non_owner(self):
        board = Board.objects.create(
            name="test_cover_board",
            submitter=self.owner,
            private=False,
        )
        board.pins.add(self.private_pin)
        board.save()

        self.client.login(username=self.other_user.username, password='password')
        board_url = reverse("board-detail", kwargs={"pk": board.pk})
        resp = self.client.get(board_url)
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()['cover'])

    def test_board_cover_includes_private_pins_for_owner(self):
        board = Board.objects.create(
            name="test_cover_board2",
            submitter=self.owner,
            private=False,
        )
        board.pins.add(self.private_pin)
        board.save()

        self.client.login(username=self.owner.username, password='password')
        board_url = reverse("board-detail", kwargs={"pk": board.pk})
        resp = self.client.get(board_url)
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(resp.json()['cover'])


class CrossUserPermissionBoundaryTests(APITestCase):
    """跨用户权限边界场景测试 - 替代偏离的分享链接令牌测试
    涵盖：他人私有图钉添加到自有看板、非所有者修改他人看板、
    私有图钉缩略图访问控制、以及其他跨用户边界场景
    """

    def setUp(self):
        super(CrossUserPermissionBoundaryTests, self).setUp()
        self.owner_a = create_user("alice")
        self.owner_b = create_user("bob")
        self.third_user = create_user("charlie")

        with mock.patch('requests.get', mock_requests_get):
            self.image_a = create_image()
            self.image_b = create_image()

        self.a_public_pin = create_pin(self.owner_a, self.image_a, [])
        self.a_public_pin.private = False
        self.a_public_pin.save()

        self.a_private_pin = create_pin(self.owner_a, self.image_a, [])
        self.a_private_pin.private = True
        self.a_private_pin.save()

        self.b_public_pin = create_pin(self.owner_b, self.image_b, [])
        self.b_public_pin.private = False
        self.b_public_pin.save()

        self.b_private_pin = create_pin(self.owner_b, self.image_b, [])
        self.b_private_pin.private = True
        self.b_private_pin.save()

        self.a_public_board = Board.objects.create(
            name="a_public_board", submitter=self.owner_a, private=False,
        )
        self.a_private_board = Board.objects.create(
            name="a_private_board", submitter=self.owner_a, private=True,
        )
        self.b_public_board = Board.objects.create(
            name="b_public_board", submitter=self.owner_b, private=False,
        )
        self.b_private_board = Board.objects.create(
            name="b_private_board", submitter=self.owner_b, private=True,
        )

        self.a_public_board.pins.add(self.a_public_pin, self.a_private_pin)

    def tearDown(self):
        _teardown_models()

    def test_user_b_cannot_add_as_private_pin_to_bs_board(self):
        self.client.login(username=self.owner_b.username, password='password')
        board_url = reverse("board-detail", kwargs={"pk": self.b_public_board.pk})

        resp = self.client.patch(
            board_url,
            data={"pins_to_add": [self.a_private_pin.id]},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.b_public_board.refresh_from_db()
        self.assertFalse(
            self.b_public_board.pins.filter(pk=self.a_private_pin.pk).exists()
        )

    def test_user_a_cannot_add_bs_private_pin_to_as_board(self):
        self.client.login(username=self.owner_a.username, password='password')
        board_url = reverse("board-detail", kwargs={"pk": self.a_public_board.pk})
        pin_count_before = self.a_public_board.pins.count()

        resp = self.client.patch(
            board_url,
            data={"pins_to_add": [self.b_private_pin.id]},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.a_public_board.refresh_from_db()
        self.assertEqual(self.a_public_board.pins.count(), pin_count_before)
        self.assertFalse(
            self.a_public_board.pins.filter(pk=self.b_private_pin.pk).exists()
        )

    def test_third_user_cannot_add_others_private_pin_to_own_board(self):
        self.client.login(username=self.third_user.username, password='password')
        c_board = Board.objects.create(
            name="charlie_board", submitter=self.third_user, private=False,
        )
        board_url = reverse("board-detail", kwargs={"pk": c_board.pk})

        resp = self.client.patch(
            board_url,
            data={"pins_to_add": [self.a_private_pin.id, self.b_private_pin.id]},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        c_board.refresh_from_db()
        self.assertEqual(c_board.pins.count(), 0)

    def test_user_b_cannot_remove_pin_from_as_board(self):
        self.client.login(username=self.owner_b.username, password='password')
        board_url = reverse("board-detail", kwargs={"pk": self.a_public_board.pk})

        resp = self.client.patch(
            board_url,
            data={"pins_to_remove": [self.a_public_pin.id]},
            format='json',
        )
        self.assertEqual(resp.status_code, 403)
        self.a_public_board.refresh_from_db()
        self.assertTrue(
            self.a_public_board.pins.filter(pk=self.a_public_pin.pk).exists()
        )

    def test_third_user_cannot_remove_pin_from_others_board(self):
        self.client.login(username=self.third_user.username, password='password')
        board_url = reverse("board-detail", kwargs={"pk": self.b_public_board.pk})

        resp = self.client.patch(
            board_url,
            data={"pins_to_remove": [self.b_public_pin.id]},
            format='json',
        )
        self.assertEqual(resp.status_code, 403)

    def test_user_b_cannot_rename_as_public_board(self):
        self.client.login(username=self.owner_b.username, password='password')
        board_url = reverse("board-detail", kwargs={"pk": self.a_public_board.pk})

        resp = self.client.patch(
            board_url,
            data={"name": "stolen_board_name"},
            format='json',
        )
        self.assertEqual(resp.status_code, 403)
        self.a_public_board.refresh_from_db()
        self.assertNotEqual(self.a_public_board.name, "stolen_board_name")

    def test_user_b_cannot_change_as_board_privacy(self):
        self.client.login(username=self.owner_b.username, password='password')
        board_url = reverse("board-detail", kwargs={"pk": self.a_public_board.pk})

        resp = self.client.patch(
            board_url,
            data={"private": True},
            format='json',
        )
        self.assertEqual(resp.status_code, 403)
        self.a_public_board.refresh_from_db()
        self.assertFalse(self.a_public_board.private)

    def test_user_b_cannot_delete_as_public_board(self):
        self.client.login(username=self.owner_b.username, password='password')
        board_url = reverse("board-detail", kwargs={"pk": self.a_public_board.pk})

        resp = self.client.delete(board_url)
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(Board.objects.filter(pk=self.a_public_board.pk).exists())

    def test_anonymous_cannot_modify_any_board(self):
        board_url = reverse("board-detail", kwargs={"pk": self.a_public_board.pk})

        resp = self.client.patch(
            board_url,
            data={"name": "hacked_by_anonymous"},
            format='json',
        )
        self.assertEqual(resp.status_code, 401)

        resp = self.client.delete(board_url)
        self.assertEqual(resp.status_code, 401)

    def test_anonymous_cannot_see_private_pin_image_thumbnail(self):
        resp = self.client.get(
            reverse("pin-detail", kwargs={"pk": self.a_private_pin.id})
        )
        self.assertEqual(resp.status_code, 404)

    def test_third_user_cannot_see_private_pin_image_thumbnail(self):
        self.client.login(username=self.third_user.username, password='password')
        resp = self.client.get(
            reverse("pin-detail", kwargs={"pk": self.a_private_pin.id})
        )
        self.assertEqual(resp.status_code, 404)

    def test_owner_can_see_own_private_pin_image_thumbnail(self):
        self.client.login(username=self.owner_a.username, password='password')
        resp = self.client.get(
            reverse("pin-detail", kwargs={"pk": self.a_private_pin.id})
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('image', data)
        self.assertIsNotNone(data['image'])
        self.assertIn('thumbnail', data['image'])
        self.assertIn('standard', data['image'])
        self.assertIn('square', data['image'])
        self.assertIsNotNone(data['image']['thumbnail'])
        self.assertIsNotNone(data['image']['thumbnail']['image'])

    def test_anonymous_can_see_public_pin_image_thumbnail(self):
        resp = self.client.get(
            reverse("pin-detail", kwargs={"pk": self.a_public_pin.id})
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('image', data)
        self.assertIsNotNone(data['image'])
        self.assertIn('thumbnail', data['image'])
        self.assertIsNotNone(data['image']['thumbnail'])

    def test_third_user_can_see_public_pin_image_thumbnail(self):
        self.client.login(username=self.third_user.username, password='password')
        resp = self.client.get(
            reverse("pin-detail", kwargs={"pk": self.b_public_pin.id})
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('image', data)
        self.assertIsNotNone(data['image'])
        self.assertIn('thumbnail', data['image'])
        self.assertIsNotNone(data['image']['thumbnail']['image'])

    def test_board_cover_no_private_pins_for_anonymous(self):
        board = Board.objects.create(
            name="mixed_cover_board", submitter=self.owner_a, private=False,
        )
        board.pins.add(self.a_private_pin)
        board.save()

        resp = self.client.get(
            reverse("board-detail", kwargs={"pk": board.pk})
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()['cover'])

    def test_board_cover_no_private_pins_for_third_user(self):
        board = Board.objects.create(
            name="mixed_cover_board2", submitter=self.owner_a, private=False,
        )
        board.pins.add(self.a_private_pin)
        board.save()

        self.client.login(username=self.third_user.username, password='password')
        resp = self.client.get(
            reverse("board-detail", kwargs={"pk": board.pk})
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()['cover'])

    def test_board_cover_includes_private_pins_for_owner(self):
        board = Board.objects.create(
            name="mixed_cover_board3", submitter=self.owner_a, private=False,
        )
        board.pins.add(self.a_private_pin)
        board.save()

        self.client.login(username=self.owner_a.username, password='password')
        resp = self.client.get(
            reverse("board-detail", kwargs={"pk": board.pk})
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(resp.json()['cover'])
        self.assertEqual(resp.json()['cover']['id'], self.a_private_pin.id)

    def test_board_total_pins_excludes_private_for_anonymous(self):
        board = Board.objects.create(
            name="mixed_count_board", submitter=self.owner_a, private=False,
        )
        board.pins.add(self.a_public_pin, self.a_private_pin)
        board.save()

        resp = self.client.get(
            reverse("board-detail", kwargs={"pk": board.pk})
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['total_pins'], 1)

    def test_board_total_pins_excludes_private_for_third_user(self):
        board = Board.objects.create(
            name="mixed_count_board2", submitter=self.owner_a, private=False,
        )
        board.pins.add(self.a_public_pin, self.a_private_pin, self.b_public_pin)
        board.save()

        self.client.login(username=self.third_user.username, password='password')
        resp = self.client.get(
            reverse("board-detail", kwargs={"pk": board.pk})
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['total_pins'], 2)

    def test_user_b_cannot_edit_as_public_pin_description(self):
        self.client.login(username=self.owner_b.username, password='password')
        pin_url = reverse("pin-detail", kwargs={"pk": self.a_public_pin.pk})

        resp = self.client.patch(
            pin_url,
            data={"description": "malicious edit"},
            format='json',
        )
        self.assertEqual(resp.status_code, 403)
        self.a_public_pin.refresh_from_db()
        self.assertNotEqual(self.a_public_pin.description, "malicious edit")

    def test_user_b_cannot_delete_as_public_pin(self):
        self.client.login(username=self.owner_b.username, password='password')
        pin_url = reverse("pin-detail", kwargs={"pk": self.a_public_pin.pk})

        resp = self.client.delete(pin_url)
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(Pin.objects.filter(pk=self.a_public_pin.pk).exists())

    def test_anonymous_cannot_create_pin(self):
        url = 'http://testserver.com/mocked/anon-pin.png'
        with mock.patch('requests.get', mock_requests_get):
            resp = self.client.post(
                reverse("pin-list"),
                data={'url': url, 'private': False, 'description': 'test'},
                format='json',
            )
        self.assertEqual(resp.status_code, 401)

    def test_anonymous_cannot_access_create_board_endpoint(self):
        resp = self.client.post(
            reverse("board-list"),
            data={'name': 'hacked_board', 'private': False},
            format='json',
        )
        self.assertIn(resp.status_code, [401, 405])

    def test_user_a_cannot_access_bs_private_board_via_direct_id(self):
        self.client.login(username=self.owner_a.username, password='password')
        board_url = reverse("board-detail", kwargs={"pk": self.b_private_board.pk})

        resp = self.client.get(board_url)
        self.assertEqual(resp.status_code, 404)

    def test_third_user_cannot_access_bs_private_board_via_direct_id(self):
        self.client.login(username=self.third_user.username, password='password')
        board_url = reverse("board-detail", kwargs={"pk": self.b_private_board.pk})

        resp = self.client.get(board_url)
        self.assertEqual(resp.status_code, 404)

    def test_user_a_cannot_view_bs_private_pin_via_direct_id(self):
        self.client.login(username=self.owner_a.username, password='password')
        pin_url = reverse("pin-detail", kwargs={"pk": self.b_private_pin.pk})

        resp = self.client.get(pin_url)
        self.assertEqual(resp.status_code, 404)

    def test_add_multiple_mixed_pins_to_board_filters_private_others(self):
        self.client.login(username=self.owner_a.username, password='password')
        board = Board.objects.create(
            name="test_mixed_board", submitter=self.owner_a, private=False,
        )
        board_url = reverse("board-detail", kwargs={"pk": board.pk})

        resp = self.client.patch(
            board_url,
            data={
                "pins_to_add": [
                    self.a_public_pin.id,
                    self.a_private_pin.id,
                    self.b_public_pin.id,
                    self.b_private_pin.id,
                ]
            },
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        board.refresh_from_db()
        pin_ids = set(board.pins.values_list('id', flat=True))
        self.assertIn(self.a_public_pin.id, pin_ids)
        self.assertIn(self.a_private_pin.id, pin_ids)
        self.assertIn(self.b_public_pin.id, pin_ids)
        self.assertNotIn(self.b_private_pin.id, pin_ids)

    def test_owner_can_toggle_own_board_privacy(self):
        self.client.login(username=self.owner_a.username, password='password')
        board_url = reverse("board-detail", kwargs={"pk": self.a_public_board.pk})

        resp = self.client.patch(
            board_url,
            data={"private": True},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.a_public_board.refresh_from_db()
        self.assertTrue(self.a_public_board.private)

        self.client.logout()
        resp = self.client.get(board_url)
        self.assertEqual(resp.status_code, 404)

    def test_different_users_can_have_same_board_name(self):
        board_b = Board.objects.create(
            name="a_public_board", submitter=self.owner_b, private=False,
        )
        self.assertTrue(
            Board.objects.filter(
                submitter=self.owner_b, name="a_public_board"
            ).exists()
        )
        self.assertEqual(
            Board.objects.filter(name="a_public_board").count(), 2
        )

    def test_owner_can_toggle_own_pin_privacy(self):
        self.client.login(username=self.owner_a.username, password='password')
        pin_url = reverse("pin-detail", kwargs={"pk": self.a_public_pin.pk})

        resp = self.client.patch(
            pin_url,
            data={"private": True},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.a_public_pin.refresh_from_db()
        self.assertTrue(self.a_public_pin.private)

        self.client.logout()
        resp = self.client.get(pin_url)
        self.assertEqual(resp.status_code, 404)

    def test_user_b_cannot_toggle_as_pin_privacy(self):
        self.client.login(username=self.owner_b.username, password='password')
        pin_url = reverse("pin-detail", kwargs={"pk": self.a_public_pin.pk})

        resp = self.client.patch(
            pin_url,
            data={"private": True},
            format='json',
        )
        self.assertEqual(resp.status_code, 403)
        self.a_public_pin.refresh_from_db()
        self.assertFalse(self.a_public_pin.private)

    def test_board_pins_list_only_visible_pins_for_non_owner(self):
        self.client.login(username=self.third_user.username, password='password')
        board = Board.objects.create(
            name="visibility_test_board",
            submitter=self.owner_a,
            private=False,
        )
        board.pins.add(self.a_public_pin, self.a_private_pin, self.b_public_pin)
        board.save()

        resp = self.client.get(
            reverse("board-detail", kwargs={"pk": board.pk})
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['total_pins'], 2)

    def test_owner_can_remove_pins_from_own_board(self):
        self.client.login(username=self.owner_b.username, password='password')
        self.b_public_board.pins.add(self.b_public_pin)

        resp = self.client.patch(
            reverse("board-detail", kwargs={"pk": self.b_public_board.pk}),
            data={"pins_to_remove": [self.b_public_pin.id]},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.b_public_board.refresh_from_db()
        self.assertEqual(self.b_public_board.pins.count(), 0)

    def test_anonymous_can_list_all_public_boards(self):
        resp = self.client.get(reverse("board-list"))
        self.assertEqual(resp.status_code, 200)
        board_names = [b['name'] for b in resp.json()]
        self.assertIn("a_public_board", board_names)
        self.assertIn("b_public_board", board_names)
        self.assertNotIn("a_private_board", board_names)
        self.assertNotIn("b_private_board", board_names)

    def test_three_user_permission_matrix_on_pins(self):
        self.client.login(username=self.third_user.username, password='password')
        resp = self.client.get(reverse("pin-list"))
        results = {p['id']: p for p in resp.json()['results']}

        self.assertIn(self.a_public_pin.id, results)
        self.assertIn(self.b_public_pin.id, results)
        self.assertNotIn(self.a_private_pin.id, results)
        self.assertNotIn(self.b_private_pin.id, results)

    def test_user_a_sees_own_pins_in_board_detail(self):
        self.client.login(username=self.owner_a.username, password='password')
        resp = self.client.get(
            reverse("board-detail", kwargs={"pk": self.a_public_board.pk})
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['total_pins'], 2)

    def test_private_pin_not_in_search_results_for_anonymous(self):
        self.a_private_pin.tags.add("test_search_tag")
        self.a_public_pin.tags.add("test_search_tag")

        resp = self.client.get(f"{reverse('pin-list')}?search=test_search_tag")
        self.assertEqual(resp.status_code, 200)
        pin_ids = [p['id'] for p in resp.json()['results']]
        self.assertIn(self.a_public_pin.id, pin_ids)
        self.assertNotIn(self.a_private_pin.id, pin_ids)

    def test_user_b_cannot_transfer_pin_ownership(self):
        self.client.login(username=self.owner_b.username, password='password')
        pin_url = reverse("pin-detail", kwargs={"pk": self.a_public_pin.pk})

        resp = self.client.patch(
            pin_url,
            data={"submitter": self.owner_b.id},
            format='json',
        )
        self.assertEqual(resp.status_code, 403)
        self.a_public_pin.refresh_from_db()
        self.assertEqual(self.a_public_pin.submitter.id, self.owner_a.id)

    def test_user_a_cannot_rename_bs_private_board_via_forged_request(self):
        self.client.login(username=self.owner_a.username, password='password')
        resp = self.client.patch(
            reverse("board-detail", kwargs={"pk": self.b_private_board.pk}),
            data={"name": "hacked_name"},
            format='json',
        )
        self.assertEqual(resp.status_code, 404)
        self.b_private_board.refresh_from_db()
        self.assertEqual(self.b_private_board.name, "b_private_board")


class BoardDeletionReferenceTests(APITestCase):
    """Board 删除后的引用问题测试"""

    def setUp(self):
        super(BoardDeletionReferenceTests, self).setUp()
        self.owner = create_user("owner")
        self.other_user = create_user("other")

        with mock.patch('requests.get', mock_requests_get):
            self.image = create_image()

        self.pin1 = create_pin(self.owner, self.image, [])
        self.pin2 = create_pin(self.owner, self.image, [])
        self.pin3 = create_pin(self.other_user, self.image, [])

        self.board1 = Board.objects.create(
            name="board1",
            submitter=self.owner,
            private=False,
        )
        self.board2 = Board.objects.create(
            name="board2",
            submitter=self.owner,
            private=True,
        )

        self.board1.pins.add(self.pin1, self.pin2, self.pin3)
        self.board2.pins.add(self.pin1)

        self.board1_url = reverse("board-detail", kwargs={"pk": self.board1.pk})
        self.board2_url = reverse("board-detail", kwargs={"pk": self.board2.pk})

    def tearDown(self):
        _teardown_models()

    def test_deleting_board_does_not_delete_pins(self):
        self.client.login(username=self.owner.username, password='password')
        pin_ids_before = {self.pin1.id, self.pin2.id, self.pin3.id}

        self.client.delete(self.board1_url)

        self.assertFalse(Board.objects.filter(pk=self.board1.pk).exists())
        remaining_pin_ids = set(Pin.objects.values_list('id', flat=True))
        self.assertEqual(remaining_pin_ids, pin_ids_before)

    def test_deleting_board_removes_m2m_relationships(self):
        self.client.login(username=self.owner.username, password='password')
        board1_id = self.board1.id

        self.client.delete(self.board1_url)

        self.assertEqual(self.pin1.pins.count(), 1)
        self.assertEqual(self.pin1.pins.filter(id=board1_id).count(), 0)

    def test_pin_remains_accessible_after_board_deletion(self):
        self.client.login(username=self.owner.username, password='password')
        pin_url = reverse("pin-detail", kwargs={"pk": self.pin1.pk})

        self.client.delete(self.board1_url)
        self.client.delete(self.board2_url)

        resp = self.client.get(pin_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['id'], self.pin1.id)

    def test_image_cascade_deletes_with_pin_not_board(self):
        self.client.login(username=self.owner.username, password='password')
        image_id = self.image.id

        self.client.delete(self.board1_url)
        self.assertTrue(self.image.__class__.objects.filter(pk=image_id).exists())

        pin_url = reverse("pin-detail", kwargs={"pk": self.pin1.pk})
        self.client.delete(pin_url)

        pin1_id = self.pin1.id
        self.client.login(username=self.other_user.username, password='password')
        resp = self.client.get(reverse("pin-list"))
        pin_ids = [p['id'] for p in resp.json()['results']]
        self.assertNotIn(pin1_id, pin_ids)

    def test_other_boards_not_affected_by_deletion(self):
        self.client.login(username=self.owner.username, password='password')
        self.client.delete(self.board1_url)

        resp = self.client.get(self.board2_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['total_pins'], 1)

    def test_deleting_private_board_does_not_affect_public_board_pins(self):
        self.client.login(username=self.owner.username, password='password')
        self.client.delete(self.board2_url)

        self.assertFalse(Board.objects.filter(pk=self.board2.pk).exists())

        resp = self.client.get(self.board1_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['total_pins'], 3)

    def test_cannot_access_deleted_board(self):
        self.client.login(username=self.owner.username, password='password')
        self.client.delete(self.board1_url)

        resp = self.client.get(self.board1_url)
        self.assertEqual(resp.status_code, 404)

    def test_anonymous_cannot_access_deleted_public_board(self):
        self.client.login(username=self.owner.username, password='password')
        self.client.delete(self.board1_url)
        self.client.logout()

        resp = self.client.get(self.board1_url)
        self.assertEqual(resp.status_code, 404)

    def test_add_pin_to_nonexistent_board_returns_404(self):
        self.client.login(username=self.owner.username, password='password')
        self.client.delete(self.board1_url)

        new_pin = create_pin(self.owner, self.image, [])
        resp = self.client.patch(
            self.board1_url,
            data={"pins_to_add": [new_pin.id]},
            format='json',
        )
        self.assertEqual(resp.status_code, 404)


class CrossUserPermissionMatrixTests(APITestCase):
    """跨用户权限矩阵完整测试"""

    def setUp(self):
        super(CrossUserPermissionMatrixTests, self).setUp()
        self.user_a = create_user("alice")
        self.user_b = create_user("bob")
        self.user_c = create_user("charlie")

        with mock.patch('requests.get', mock_requests_get):
            self.image = create_image()

        self.a_public_pin = create_pin(self.user_a, self.image, [])
        self.a_public_pin.private = False
        self.a_public_pin.save()

        self.a_private_pin = create_pin(self.user_a, self.image, [])
        self.a_private_pin.private = True
        self.a_private_pin.save()

        self.b_public_pin = create_pin(self.user_b, self.image, [])
        self.b_public_pin.private = False
        self.b_public_pin.save()

        self.b_private_pin = create_pin(self.user_b, self.image, [])
        self.b_private_pin.private = True
        self.b_private_pin.save()

        self.a_public_board = Board.objects.create(
            name="a_public", submitter=self.user_a, private=False,
        )
        self.a_private_board = Board.objects.create(
            name="a_private", submitter=self.user_a, private=True,
        )
        self.b_public_board = Board.objects.create(
            name="b_public", submitter=self.user_b, private=False,
        )
        self.b_private_board = Board.objects.create(
            name="b_private", submitter=self.user_b, private=True,
        )

        self.a_public_board.pins.add(self.a_public_pin, self.a_private_pin, self.b_public_pin)
        self.a_private_board.pins.add(self.a_public_pin, self.a_private_pin)
        self.b_public_board.pins.add(self.b_public_pin, self.b_private_pin)

    def tearDown(self):
        _teardown_models()

    def test_user_a_can_view_all_own_boards(self):
        self.client.login(username=self.user_a.username, password='password')
        resp = self.client.get(reverse("board-list"))
        self.assertEqual(resp.status_code, 200)
        board_names = [b['name'] for b in resp.json()]
        self.assertIn("a_public", board_names)
        self.assertIn("a_private", board_names)
        self.assertIn("b_public", board_names)
        self.assertNotIn("b_private", board_names)

    def test_user_b_sees_correct_pins_count_in_as_board(self):
        self.client.login(username=self.user_b.username, password='password')
        resp = self.client.get(
            reverse("board-detail", kwargs={"pk": self.a_public_board.pk})
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['total_pins'], 2)

    def test_user_a_sees_all_pins_in_own_public_board(self):
        self.client.login(username=self.user_a.username, password='password')
        resp = self.client.get(
            reverse("board-detail", kwargs={"pk": self.a_public_board.pk})
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['total_pins'], 3)

    def test_user_c_sees_boards_list_without_private_ones(self):
        self.client.login(username=self.user_c.username, password='password')
        resp = self.client.get(reverse("board-list"))
        self.assertEqual(resp.status_code, 200)
        board_names = [b['name'] for b in resp.json()]
        self.assertIn("a_public", board_names)
        self.assertIn("b_public", board_names)
        self.assertNotIn("a_private", board_names)
        self.assertNotIn("b_private", board_names)

    def test_anonymous_boards_list_filtered_correctly(self):
        resp = self.client.get(reverse("board-list"))
        self.assertEqual(resp.status_code, 200)
        board_names = [b['name'] for b in resp.json()]
        self.assertIn("a_public", board_names)
        self.assertIn("b_public", board_names)
        self.assertNotIn("a_private", board_names)
        self.assertNotIn("b_private", board_names)

    def test_anonymous_pins_list_filtered_correctly(self):
        resp = self.client.get(reverse("pin-list"))
        self.assertEqual(resp.status_code, 200)
        pin_ids = [p['id'] for p in resp.json()['results']]
        self.assertIn(self.a_public_pin.id, pin_ids)
        self.assertIn(self.b_public_pin.id, pin_ids)
        self.assertNotIn(self.a_private_pin.id, pin_ids)
        self.assertNotIn(self.b_private_pin.id, pin_ids)

    def test_user_a_cannot_add_b_private_pin_to_as_board(self):
        self.client.login(username=self.user_a.username, password='password')
        resp = self.client.patch(
            reverse("board-detail", kwargs={"pk": self.a_public_board.pk}),
            data={"pins_to_add": [self.b_private_pin.id]},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.a_public_board.refresh_from_db()
        self.assertFalse(self.a_public_board.pins.filter(pk=self.b_private_pin.pk).exists())

    def test_user_a_can_remove_own_pin_from_board(self):
        self.client.login(username=self.user_a.username, password='password')
        self.assertTrue(self.a_public_board.pins.filter(pk=self.a_public_pin.pk).exists())

        resp = self.client.patch(
            reverse("board-detail", kwargs={"pk": self.a_public_board.pk}),
            data={"pins_to_remove": [self.a_public_pin.id]},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.a_public_board.refresh_from_db()
        self.assertFalse(self.a_public_board.pins.filter(pk=self.a_public_pin.pk).exists())

    def test_user_b_cannot_remove_pin_from_as_board(self):
        self.client.login(username=self.user_b.username, password='password')
        resp = self.client.patch(
            reverse("board-detail", kwargs={"pk": self.a_public_board.pk}),
            data={"pins_to_remove": [self.b_public_pin.id]},
            format='json',
        )
        self.assertEqual(resp.status_code, 403)

    def test_user_a_cannot_delete_bs_public_board(self):
        self.client.login(username=self.user_a.username, password='password')
        resp = self.client.delete(
            reverse("board-detail", kwargs={"pk": self.b_public_board.pk})
        )
        self.assertEqual(resp.status_code, 403)

    def test_user_a_cannot_patch_bs_public_board(self):
        self.client.login(username=self.user_a.username, password='password')
        resp = self.client.patch(
            reverse("board-detail", kwargs={"pk": self.b_public_board.pk}),
            data={"name": "hacked_name"},
            format='json',
        )
        self.assertEqual(resp.status_code, 403)

    def test_three_user_permission_combinations_on_pins(self):
        self.client.login(username=self.user_c.username, password='password')
        resp = self.client.get(reverse("pin-list"))
        results = {p['id']: p for p in resp.json()['results']}

        self.assertIn(self.a_public_pin.id, results)
        self.assertIn(self.b_public_pin.id, results)
        self.assertNotIn(self.a_private_pin.id, results)
        self.assertNotIn(self.b_private_pin.id, results)

        resp = self.client.get(
            reverse("pin-detail", kwargs={"pk": self.a_public_pin.id})
        )
        self.assertEqual(resp.status_code, 200)

        resp = self.client.get(
            reverse("pin-detail", kwargs={"pk": self.a_private_pin.id})
        )
        self.assertEqual(resp.status_code, 404)


class MediaDirectLinkPermissionTests(APITestCase):
    """媒体文件直链访问权限测试
    验证匿名用户和第三方用户是否可以绕过 API 接口，
    通过直接请求媒体文件地址来访问私有图钉的原图和缩略图。
    同时验证生产模式下 X-Accel-Redirect 行为正确。
    """

    def setUp(self):
        super(MediaDirectLinkPermissionTests, self).setUp()
        self.owner = create_user("media_owner")
        self.other_user = create_user("media_other")

        with mock.patch('requests.get', mock_requests_get):
            self.image1 = create_image()
            self.image2 = create_image()
            self.image3 = create_image()
            self.image4 = create_image()

        self.public_pin = create_pin(self.owner, self.image1, [])
        self.public_pin.private = False
        self.public_pin.save()

        self.private_pin = create_pin(self.owner, self.image2, [])
        self.private_pin.private = True
        self.private_pin.save()

        self.other_public_pin = create_pin(self.other_user, self.image3, [])
        self.other_public_pin.private = False
        self.other_public_pin.save()

        self.other_private_pin = create_pin(self.other_user, self.image4, [])
        self.other_private_pin.private = True
        self.other_private_pin.save()

    def tearDown(self):
        _teardown_models()

    def _get_image_urls(self, pin):
        from django_images.models import Thumbnail

        original_url = pin.image.image.url

        thumbnail_urls = {}
        try:
            thumbnail = pin.image.get_by_size('thumbnail')
            thumbnail_urls['thumbnail'] = thumbnail.image.url
        except Thumbnail.DoesNotExist:
            pass

        try:
            standard = pin.image.get_by_size('standard')
            thumbnail_urls['standard'] = standard.image.url
        except Thumbnail.DoesNotExist:
            pass

        try:
            square = pin.image.get_by_size('square')
            thumbnail_urls['square'] = square.image.url
        except Thumbnail.DoesNotExist:
            pass

        return original_url, thumbnail_urls

    def test_anonymous_cannot_access_private_pin_original_image(self):
        original_url, _ = self._get_image_urls(self.private_pin)
        resp = self.client.get(original_url)
        self.assertEqual(resp.status_code, 403)

    def test_anonymous_cannot_access_private_pin_thumbnail(self):
        _, thumbnail_urls = self._get_image_urls(self.private_pin)
        for size, url in thumbnail_urls.items():
            resp = self.client.get(url)
            self.assertEqual(
                resp.status_code, 403,
                f"Anonymous could access {size} thumbnail of private pin via {url}"
            )

    def test_other_user_cannot_access_private_pin_original_image(self):
        self.client.login(username=self.other_user.username, password='password')
        original_url, _ = self._get_image_urls(self.private_pin)
        resp = self.client.get(original_url)
        self.assertEqual(resp.status_code, 403)

    def test_other_user_cannot_access_private_pin_thumbnail(self):
        self.client.login(username=self.other_user.username, password='password')
        _, thumbnail_urls = self._get_image_urls(self.private_pin)
        for size, url in thumbnail_urls.items():
            resp = self.client.get(url)
            self.assertEqual(
                resp.status_code, 403,
                f"Other user could access {size} thumbnail of private pin via {url}"
            )

    def test_owner_can_access_own_private_pin_original_image(self):
        self.client.login(username=self.owner.username, password='password')
        original_url, _ = self._get_image_urls(self.private_pin)
        resp = self.client.get(original_url)
        self.assertEqual(resp.status_code, 200)

    def test_owner_can_access_own_private_pin_thumbnail(self):
        self.client.login(username=self.owner.username, password='password')
        _, thumbnail_urls = self._get_image_urls(self.private_pin)
        for size, url in thumbnail_urls.items():
            resp = self.client.get(url)
            self.assertEqual(
                resp.status_code, 200,
                f"Owner could not access {size} thumbnail of own private pin via {url}"
            )

    def test_anonymous_can_access_public_pin_original_image(self):
        original_url, _ = self._get_image_urls(self.public_pin)
        resp = self.client.get(original_url)
        self.assertEqual(resp.status_code, 200)

    def test_anonymous_can_access_public_pin_thumbnail(self):
        _, thumbnail_urls = self._get_image_urls(self.public_pin)
        for size, url in thumbnail_urls.items():
            resp = self.client.get(url)
            self.assertEqual(
                resp.status_code, 200,
                f"Anonymous could not access {size} thumbnail of public pin via {url}"
            )

    def test_other_user_can_access_public_pin_original_image(self):
        self.client.login(username=self.other_user.username, password='password')
        original_url, _ = self._get_image_urls(self.public_pin)
        resp = self.client.get(original_url)
        self.assertEqual(resp.status_code, 200)

    def test_other_user_can_access_other_public_pin_thumbnail(self):
        self.client.login(username=self.other_user.username, password='password')
        _, thumbnail_urls = self._get_image_urls(self.public_pin)
        for size, url in thumbnail_urls.items():
            resp = self.client.get(url)
            self.assertEqual(
                resp.status_code, 200,
                f"Other user could not access {size} thumbnail of public pin via {url}"
            )

    def test_anonymous_cannot_access_other_private_pin_original_image(self):
        original_url, _ = self._get_image_urls(self.other_private_pin)
        resp = self.client.get(original_url)
        self.assertEqual(resp.status_code, 403)

    def test_owner_cannot_access_other_private_pin_original_image(self):
        self.client.login(username=self.owner.username, password='password')
        original_url, _ = self._get_image_urls(self.other_private_pin)
        resp = self.client.get(original_url)
        self.assertEqual(resp.status_code, 403)

    def test_logout_user_cannot_access_private_pin_image(self):
        self.client.login(username=self.owner.username, password='password')
        original_url, _ = self._get_image_urls(self.private_pin)
        resp_before = self.client.get(original_url)
        self.assertEqual(resp_before.status_code, 200)

        self.client.logout()
        resp_after = self.client.get(original_url)
        self.assertEqual(resp_after.status_code, 403)

    def test_pin_privacy_toggle_blocks_media_access(self):
        self.client.login(username=self.owner.username, password='password')
        with mock.patch('requests.get', mock_requests_get):
            image = create_image()
        test_pin = create_pin(self.owner, image, [])
        test_pin.private = False
        test_pin.save()

        original_url, thumbnail_urls = self._get_image_urls(test_pin)

        resp_original = self.client.get(original_url)
        self.assertEqual(resp_original.status_code, 200)

        test_pin.private = True
        test_pin.save()

        self.client.logout()
        resp_original = self.client.get(original_url)
        self.assertEqual(resp_original.status_code, 403)

        for size, url in thumbnail_urls.items():
            resp = self.client.get(url)
            self.assertEqual(
                resp.status_code, 403,
                f"Could still access {size} thumbnail after pin was made private"
            )

    def test_pin_privacy_toggle_to_public_allows_media_access(self):
        with mock.patch('requests.get', mock_requests_get):
            image = create_image()
        test_pin = create_pin(self.owner, image, [])
        test_pin.private = True
        test_pin.save()

        original_url, _ = self._get_image_urls(test_pin)
        resp = self.client.get(original_url)
        self.assertEqual(resp.status_code, 403)

        test_pin.private = False
        test_pin.save()

        resp = self.client.get(original_url)
        self.assertEqual(resp.status_code, 200)

    def test_media_urls_return_consistent_with_api(self):
        pin_url = reverse("pin-detail", kwargs={"pk": self.private_pin.id})

        resp_api = self.client.get(pin_url)
        self.assertEqual(resp_api.status_code, 404)

        original_url, _ = self._get_image_urls(self.private_pin)
        resp_media = self.client.get(original_url)

        self.assertNotEqual(
            resp_media.status_code, 200,
            "API blocks access but media direct link allows it - SECURITY VULNERABILITY"
        )

    def test_nonexistent_media_path_returns_404(self):
        resp = self.client.get('/media/image/original/by-md5/nonexistent/path/image.jpg')
        self.assertEqual(resp.status_code, 404)

    def test_board_private_does_not_affect_pin_media_permissions(self):
        with mock.patch('requests.get', mock_requests_get):
            image = create_image()
        pin = create_pin(self.owner, image, [])
        pin.private = False
        pin.save()

        board = Board.objects.create(
            name="private_media_board",
            submitter=self.owner,
            private=True,
        )
        board.pins.add(pin)

        original_url, _ = self._get_image_urls(pin)
        resp = self.client.get(original_url)
        self.assertEqual(resp.status_code, 200)

    def test_third_user_cannot_access_owners_private_pin_thumbnail(self):
        third_user = create_user("third_media_user")
        self.client.login(username=third_user.username, password='password')

        _, thumbnail_urls = self._get_image_urls(self.private_pin)
        for size, url in thumbnail_urls.items():
            resp = self.client.get(url)
            self.assertEqual(
                resp.status_code, 403,
                f"Third user could access {size} thumbnail of owner's private pin via {url}"
            )

    def test_production_mode_uses_x_accel_redirect_for_public(self):
        from django.test.utils import override_settings

        with override_settings(DEBUG=False, IS_TEST=False):
            original_url, _ = self._get_image_urls(self.public_pin)
            resp = self.client.get(original_url)
            self.assertEqual(resp.status_code, 200)
            self.assertIn('X-Accel-Redirect', resp)
            self.assertTrue(
                resp['X-Accel-Redirect'].startswith('/internal-media/')
            )

    def test_production_mode_uses_x_accel_redirect_for_owner_private(self):
        from django.test.utils import override_settings

        self.client.login(username=self.owner.username, password='password')
        with override_settings(DEBUG=False, IS_TEST=False):
            original_url, _ = self._get_image_urls(self.private_pin)
            resp = self.client.get(original_url)
            self.assertEqual(resp.status_code, 200)
            self.assertIn('X-Accel-Redirect', resp)
            self.assertTrue(
                resp['X-Accel-Redirect'].startswith('/internal-media/')
            )

    def test_production_mode_blocks_anonymous_private_access(self):
        from django.test.utils import override_settings

        with override_settings(DEBUG=False, IS_TEST=False):
            original_url, _ = self._get_image_urls(self.private_pin)
            resp = self.client.get(original_url)
            self.assertEqual(resp.status_code, 403)
            self.assertNotIn('X-Accel-Redirect', resp)

    def test_production_mode_blocks_other_user_private_access(self):
        from django.test.utils import override_settings

        self.client.login(username=self.other_user.username, password='password')
        with override_settings(DEBUG=False, IS_TEST=False):
            original_url, _ = self._get_image_urls(self.private_pin)
            resp = self.client.get(original_url)
            self.assertEqual(resp.status_code, 403)
            self.assertNotIn('X-Accel-Redirect', resp)

    def test_production_mode_x_accel_redirect_path_format(self):
        from django.test.utils import override_settings

        with override_settings(DEBUG=False, IS_TEST=False):
            original_url, _ = self._get_image_urls(self.public_pin)
            resp = self.client.get(original_url)
            redirect_path = resp['X-Accel-Redirect']
            self.assertTrue(
                redirect_path.startswith('/internal-media/'),
                f"Expected redirect to start with /internal-media/ but got {redirect_path}"
            )
            self.assertNotEqual(redirect_path, '/internal-media/')

    def test_production_mode_nonexistent_path_returns_404(self):
        from django.test.utils import override_settings

        with override_settings(DEBUG=False, IS_TEST=False):
            resp = self.client.get('/media/image/original/by-md5/nonexistent/path/image.jpg')
            self.assertEqual(resp.status_code, 404)
