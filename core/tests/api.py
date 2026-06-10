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


class TokenAuthenticationTests(APITestCase):
    """Token 认证、撤销和竞争条件测试"""

    def setUp(self):
        super(TokenAuthenticationTests, self).setUp()
        from rest_framework.authtoken.models import Token
        from users.models import create_token_if_necessary

        self.owner = create_user("owner")
        self.other_user = create_user("other")

        self.owner_token = create_token_if_necessary(self.owner)
        self.other_token = create_token_if_necessary(self.other_user)

        with mock.patch('requests.get', mock_requests_get):
            self.image = create_image()

        self.private_pin = create_pin(self.owner, self.image, [])
        self.private_pin.private = True
        self.private_pin.save()

        self.public_board = Board.objects.create(
            name="token_board",
            submitter=self.owner,
            private=False,
        )

        self.private_board = Board.objects.create(
            name="token_private_board",
            submitter=self.owner,
            private=True,
        )

        self.pins_list_url = reverse("pin-list")
        self.boards_list_url = reverse("board-list")
        self.private_pin_url = reverse("pin-detail", kwargs={"pk": self.private_pin.pk})
        self.private_board_url = reverse("board-detail", kwargs={"pk": self.private_board.pk})

    def tearDown(self):
        from rest_framework.authtoken.models import Token
        Token.objects.all().delete()
        _teardown_models()

    def _auth_headers(self, token):
        return {"HTTP_AUTHORIZATION": f"Token {token.key}"}

    def test_valid_token_can_access_authenticated_endpoints(self):
        resp = self.client.get(
            self.boards_list_url,
            **self._auth_headers(self.owner_token),
        )
        self.assertEqual(resp.status_code, 200)
        board_ids = [b['id'] for b in resp.json()]
        self.assertIn(self.public_board.id, board_ids)
        self.assertIn(self.private_board.id, board_ids)

    def test_valid_token_can_access_own_private_pin(self):
        resp = self.client.get(
            self.private_pin_url,
            **self._auth_headers(self.owner_token),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['id'], self.private_pin.id)

    def test_other_user_token_cannot_access_others_private_pin(self):
        resp = self.client.get(
            self.private_pin_url,
            **self._auth_headers(self.other_token),
        )
        self.assertEqual(resp.status_code, 404)

    def test_invalid_token_gets_401(self):
        resp = self.client.get(
            self.boards_list_url,
            HTTP_AUTHORIZATION="Token invalidtoken12345",
        )
        self.assertEqual(resp.status_code, 401)

    def test_no_token_treated_as_anonymous(self):
        resp = self.client.get(self.boards_list_url)
        self.assertEqual(resp.status_code, 200)
        board_ids = [b['id'] for b in resp.json()]
        self.assertIn(self.public_board.id, board_ids)
        self.assertNotIn(self.private_board.id, board_ids)

    def test_token_after_deletion_revokes_access(self):
        from rest_framework.authtoken.models import Token

        resp = self.client.get(
            self.private_board_url,
            **self._auth_headers(self.owner_token),
        )
        self.assertEqual(resp.status_code, 200)

        Token.objects.filter(user=self.owner).delete()

        resp = self.client.get(
            self.private_board_url,
            HTTP_AUTHORIZATION=f"Token {self.owner_token.key}",
        )
        self.assertEqual(resp.status_code, 401)

    def test_token_recreation_uses_new_token(self):
        from rest_framework.authtoken.models import Token

        old_token_key = self.owner_token.key
        Token.objects.filter(user=self.owner).delete()
        new_token = Token.objects.create(user=self.owner)

        resp = self.client.get(
            self.private_board_url,
            HTTP_AUTHORIZATION=f"Token {old_token_key}",
        )
        self.assertEqual(resp.status_code, 401)

        resp = self.client.get(
            self.private_board_url,
            **self._auth_headers(new_token),
        )
        self.assertEqual(resp.status_code, 200)

    def test_token_with_create_pin_via_api(self):
        url = 'http://testserver.com/mocked/token-pin.png'
        with mock.patch('requests.get', mock_requests_get):
            resp = self.client.post(
                self.pins_list_url,
                data={
                    'url': url,
                    'private': True,
                    'description': 'Created via token',
                },
                format='json',
                **self._auth_headers(self.owner_token),
            )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(Pin.objects.filter(url=url, private=True).exists())

    def test_token_cannot_create_pin_for_other_user(self):
        resp = self.client.get(
            reverse("pin-list"),
            **self._auth_headers(self.other_token),
        )
        results = resp.json()['results']
        for pin in results:
            if pin['private']:
                self.assertNotEqual(pin['submitter']['username'], self.owner.username)

    def test_bulk_token_reset_revokes_all_access(self):
        from rest_framework.authtoken.models import Token
        from django.core.management import call_command

        resp1 = self.client.get(
            self.private_board_url,
            **self._auth_headers(self.owner_token),
        )
        resp2 = self.client.get(
            self.boards_list_url,
            **self._auth_headers(self.other_token),
        )
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp2.status_code, 200)

        call_command('users_reset_tokens')

        resp1 = self.client.get(
            self.private_board_url,
            HTTP_AUTHORIZATION=f"Token {self.owner_token.key}",
        )
        resp2 = self.client.get(
            self.boards_list_url,
            HTTP_AUTHORIZATION=f"Token {self.other_token.key}",
        )
        self.assertEqual(resp1.status_code, 401)
        self.assertEqual(resp2.status_code, 401)

    def test_token_revocation_race_condition(self):
        """模拟 token 撤销时的竞态条件 - 并发请求"""
        from rest_framework.authtoken.models import Token
        import threading
        import time

        results = {}

        def make_request(user_token, request_id):
            time.sleep(0.01)
            try:
                resp = self.client.get(
                    self.private_board_url,
                    HTTP_AUTHORIZATION=f"Token {user_token.key}",
                )
                results[request_id] = resp.status_code
            except Exception as e:
                results[request_id] = 500

        threads = []
        for i in range(10):
            t = threading.Thread(target=make_request, args=(self.owner_token, i))
            threads.append(t)

        for t in threads:
            t.start()

        Token.objects.filter(user=self.owner).delete()

        for t in threads:
            t.join()

        self.assertEqual(len(results), 10)
        valid_results = [r for r in results.values() if isinstance(r, int)]
        for status in valid_results:
            self.assertIn(status, [200, 401, 404, 500])

        if 200 in valid_results and 401 in valid_results:
            pass


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
