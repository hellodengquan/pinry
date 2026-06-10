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


class PinRefreshTests(APITestCase):

    def setUp(self):
        super(PinRefreshTests, self).setUp()
        self.user = create_user("default")
        self.client.login(username=self.user.username, password='password')

    def tearDown(self):
        _teardown_models()

    @mock.patch('requests.get', mock_requests_get)
    def test_url_normalization_on_create(self):
        url = 'HTTP://TESTSERVER.COM/Path/To/Image.PNG#fragment'
        normalized_url = 'http://testserver.com/Path/To/Image.PNG'
        create_url = reverse("pin-list")
        post_data = {
            'url': url,
            'private': False,
            'description': 'Test URL normalization'
        }
        response = self.client.post(create_url, data=post_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        pin = Pin.objects.get(id=response.data['id'])
        self.assertEqual(pin.url, normalized_url)

    @mock.patch('requests.get', mock_requests_get)
    def test_refresh_preview_on_url_change(self):
        url1 = 'http://testserver.com/mocked/logo-01.png'
        url2 = 'http://testserver.com/mocked/logo-02.png'

        create_url = reverse("pin-list")
        post_data = {
            'url': url1,
            'private': False,
            'description': 'First version'
        }
        response = self.client.post(create_url, data=post_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        pin_id = response.data['id']
        old_image_id = response.data['image']['id']
        old_image_name = response.data['image']['image']

        pin_url = reverse("pin-detail", kwargs={"pk": pin_id})
        patch_data = {
            'url': url2,
            'description': 'Updated version'
        }
        response = self.client.patch(pin_url, data=patch_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        pin = Pin.objects.get(id=pin_id)
        self.assertEqual(pin.url, url2)
        self.assertEqual(pin.description, 'Updated version')
        self.assertEqual(pin.image.id, old_image_id)

        new_image_name = response.data['image']['image']
        self.assertNotEqual(old_image_name, new_image_name)

        self.assertIsNotNone(pin.image.image)
        self.assertTrue(pin.image.thumbnail)
        self.assertTrue(pin.image.square)
        self.assertTrue(pin.image.standard)

    @mock.patch('requests.get', mock_requests_get_with_non_image_content)
    def test_refresh_failure_keeps_old_preview(self):
        with mock.patch('requests.get', mock_requests_get):
            url1 = 'http://testserver.com/mocked/logo-01.png'
            create_url = reverse("pin-list")
            post_data = {
                'url': url1,
                'private': False,
                'description': 'First version'
            }
            response = self.client.post(create_url, data=post_data, format="json")
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            pin_id = response.data['id']
            old_image_path = Pin.objects.get(id=pin_id).image.image.name

        invalid_url = 'http://testserver.com/mocked/invalid.txt'
        pin_url = reverse("pin-detail", kwargs={"pk": pin_id})
        patch_data = {
            'url': invalid_url,
        }
        response = self.client.patch(pin_url, data=patch_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('url', response.data)
        self.assertIn('old preview retained', str(response.data['url']).lower())

        pin = Pin.objects.get(id=pin_id)
        self.assertEqual(pin.url, url1)
        self.assertEqual(pin.image.image.name, old_image_path)

    @mock.patch('requests.get', mock_requests_get)
    def test_referer_normalization(self):
        url = 'http://testserver.com/mocked/logo-01.png'
        referer = 'HTTP://EXAMPLE.COM/Source/Page/'
        normalized_referer = 'http://example.com/Source/Page'

        create_url = reverse("pin-list")
        post_data = {
            'url': url,
            'referer': referer,
            'private': False,
        }
        response = self.client.post(create_url, data=post_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        pin = Pin.objects.get(id=response.data['id'])
        self.assertEqual(pin.referer, normalized_referer)

    @mock.patch('requests.get', mock_requests_get)
    def test_same_url_does_not_refresh(self):
        url = 'http://testserver.com/mocked/logo-01.png'

        create_url = reverse("pin-list")
        post_data = {
            'url': url,
            'private': False,
        }
        response = self.client.post(create_url, data=post_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        pin_id = response.data['id']
        old_url = response.data['url']
        old_image_id = response.data['image']['id']

        pin = Pin.objects.get(id=pin_id)
        old_image_path = pin.image.image.name

        pin_url = reverse("pin-detail", kwargs={"pk": pin_id})
        patch_data = {
            'url': url + '#fragment',
            'description': 'Just updating description'
        }
        response = self.client.patch(pin_url, data=patch_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        pin = Pin.objects.get(id=pin_id)
        self.assertEqual(pin.image.image.name, old_image_path)
        self.assertEqual(pin.image.id, old_image_id)
        self.assertEqual(pin.description, 'Just updating description')
        self.assertEqual(pin.url, old_url)


class ThumbnailRefreshTests(APITestCase):

    def setUp(self):
        super(ThumbnailRefreshTests, self).setUp()
        self.user = create_user("default")
        self.client.login(username=self.user.username, password='password')

    def tearDown(self):
        _teardown_models()

    def _create_pin_with_mock(self, url, mock_func):
        with mock.patch('requests.get', mock_func):
            create_url = reverse("pin-list")
            post_data = {
                'url': url,
                'private': False,
            }
            response = self.client.post(create_url, data=post_data, format="json")
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            return response.data

    def _get_file_md5(self, file_field):
        import hashlib
        hasher = hashlib.md5()
        file_field.open()
        for chunk in file_field.chunks():
            hasher.update(chunk)
        file_field.close()
        return hasher.hexdigest()

    @mock.patch('requests.get', mock_requests_get)
    def test_thumbnails_updated_on_refresh(self):
        url1 = 'http://testserver.com/mocked/logo-01.png'
        url2 = 'http://testserver.com/mocked/logo-02.png'

        pin_data = self._create_pin_with_mock(url1, mock_requests_get)
        pin_id = pin_data['id']

        old_thumbnail_name = pin_data['image']['thumbnail']['image']
        old_square_name = pin_data['image']['square']['image']
        old_standard_name = pin_data['image']['standard']['image']

        pin = Pin.objects.get(id=pin_id)
        old_image_md5 = self._get_file_md5(pin.image.image)
        old_thumbnail_md5 = self._get_file_md5(pin.image.thumbnail.image)

        def mock_requests_get_updated(url, **kwargs):
            if 'logo-02' in url:
                response = mock.Mock()
                response.content = open('docs/src/imgs/logo-light.png', 'rb').read()
                return response
            return mock_requests_get(url, **kwargs)

        with mock.patch('requests.get', mock_requests_get_updated):
            pin_url = reverse("pin-detail", kwargs={"pk": pin_id})
            patch_data = {'url': url2}
            response = self.client.patch(pin_url, data=patch_data, format="json")
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        pin.refresh_from_db()
        pin.image.refresh_from_db()

        new_thumbnail_name = response.data['image']['thumbnail']['image']
        new_square_name = response.data['image']['square']['image']
        new_standard_name = response.data['image']['standard']['image']

        self.assertNotEqual(old_thumbnail_name, new_thumbnail_name)
        self.assertNotEqual(old_square_name, new_square_name)
        self.assertNotEqual(old_standard_name, new_standard_name)

        new_image_md5 = self._get_file_md5(pin.image.image)
        new_thumbnail_md5 = self._get_file_md5(pin.image.thumbnail.image)

        self.assertNotEqual(old_image_md5, new_image_md5)
        self.assertNotEqual(old_thumbnail_md5, new_thumbnail_md5)

    @mock.patch('requests.get', mock_requests_get)
    def test_old_thumbnail_files_cleaned_on_refresh(self):
        from django_images.models import Thumbnail as ThumbnailModel

        url1 = 'http://testserver.com/mocked/logo-01.png'
        url2 = 'http://testserver.com/mocked/logo-02.png'

        pin_data = self._create_pin_with_mock(url1, mock_requests_get)
        pin_id = pin_data['id']

        pin = Pin.objects.get(id=pin_id)
        old_thumbnail_paths = [
            pin.image.thumbnail.image.name,
            pin.image.square.image.name,
            pin.image.standard.image.name,
        ]
        old_thumbnail_ids = [
            pin.image.thumbnail.id,
            pin.image.square.id,
            pin.image.standard.id,
        ]

        storage = pin.image.image.storage
        for path in old_thumbnail_paths:
            self.assertTrue(storage.exists(path), f"Old thumbnail should exist: {path}")

        def mock_requests_get_updated(url, **kwargs):
            if 'logo-02' in url:
                response = mock.Mock()
                response.content = open('docs/src/imgs/logo-light.png', 'rb').read()
                return response
            return mock_requests_get(url, **kwargs)

        with mock.patch('requests.get', mock_requests_get_updated):
            pin_url = reverse("pin-detail", kwargs={"pk": pin_id})
            patch_data = {'url': url2}
            response = self.client.patch(pin_url, data=patch_data, format="json")
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        pin.refresh_from_db()

        new_thumbnail_ids = [
            pin.image.thumbnail.id,
            pin.image.square.id,
            pin.image.standard.id,
        ]

        for old_id, new_id in zip(old_thumbnail_ids, new_thumbnail_ids):
            self.assertNotEqual(old_id, new_id, "Thumbnail records should be recreated with new IDs")

        for old_id in old_thumbnail_ids:
            self.assertFalse(
                ThumbnailModel.objects.filter(id=old_id).exists(),
                f"Old thumbnail record should be deleted: {old_id}"
            )

        for path in old_thumbnail_paths:
            self.assertFalse(
                storage.exists(path),
                f"Old thumbnail file should be deleted: {path}"
            )

    @mock.patch('requests.get', mock_requests_get)
    def test_api_returns_updated_thumbnails(self):
        url1 = 'http://testserver.com/mocked/logo-01.png'
        url2 = 'http://testserver.com/mocked/logo-02.png'

        pin_data = self._create_pin_with_mock(url1, mock_requests_get)
        pin_id = pin_data['id']

        old_thumbnail_url = pin_data['image']['thumbnail']['image']

        def mock_requests_get_updated(url, **kwargs):
            if 'logo-02' in url:
                response = mock.Mock()
                response.content = open('docs/src/imgs/logo-light.png', 'rb').read()
                return response
            return mock_requests_get(url, **kwargs)

        with mock.patch('requests.get', mock_requests_get_updated):
            pin_url = reverse("pin-detail", kwargs={"pk": pin_id})
            patch_data = {'url': url2}
            response = self.client.patch(pin_url, data=patch_data, format="json")
            self.assertEqual(response.status_code, status.HTTP_200_OK)

        new_thumbnail_url = response.data['image']['thumbnail']['image']
        self.assertNotEqual(old_thumbnail_url, new_thumbnail_url)

        list_url = reverse("pin-list")
        response = self.client.get(list_url, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        pin_in_list = None
        for result in response.data['results']:
            if result['id'] == pin_id:
                pin_in_list = result
                break

        self.assertIsNotNone(pin_in_list)
        self.assertNotEqual(pin_in_list['image']['thumbnail']['image'], old_thumbnail_url)
        self.assertEqual(pin_in_list['image']['thumbnail']['image'], new_thumbnail_url)
