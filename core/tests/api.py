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


class PinSearchByTagTests(APITestCase):

    def setUp(self):
        super(PinSearchByTagTests, self).setUp()
        self.user = create_user("default")
        self.other_user = create_user("other")
        self.client.login(username=self.user.username, password='password')

    def tearDown(self):
        _teardown_models()

    def _create_pins_with_tag(self, user, tag_name, count, private=False, extra_tags=None):
        pins = []
        for i in range(count):
            image = create_image()
            pin = Pin.objects.create(
                submitter=user,
                image=image,
                private=private,
            )
            pin.tags.add(tag_name)
            if extra_tags:
                for tag in extra_tags:
                    pin.tags.add(tag)
            pins.append(pin)
        return pins

    def test_should_not_return_duplicate_pins_when_filtering_by_tag(self):
        tag_name = "test_tag"
        self._create_pins_with_tag(self.user, tag_name, 5, extra_tags=["tag_a", "tag_b", "tag_c"])

        url = reverse("pin-list") + f"?tags__name={tag_name}"
        response = self.client.get(url)
        results = response.json()['results']

        pin_ids = [pin['id'] for pin in results]
        unique_pin_ids = list(set(pin_ids))
        self.assertEqual(len(pin_ids), len(unique_pin_ids),
                         f"Found duplicate pins: {pin_ids}")
        self.assertEqual(len(unique_pin_ids), 5,
                         f"Expected 5 unique pins, got {len(unique_pin_ids)}")

    def test_should_have_consistent_pagination_when_filtering_by_tag(self):
        tag_name = "pagination_test_tag"
        self._create_pins_with_tag(self.user, tag_name, 35, extra_tags=["extra1", "extra2"])

        url = reverse("pin-list") + f"?tags__name={tag_name}&limit=20"
        response = self.client.get(url)
        data = response.json()

        self.assertEqual(len(data['results']), 20)
        self.assertIsNotNone(data['next'])

        second_url = data['next'].replace('http://testserver', '')
        response2 = self.client.get(second_url)
        data2 = response2.json()

        self.assertEqual(len(data2['results']), 15)
        self.assertIsNone(data2['next'])

        all_ids = [p['id'] for p in data['results']] + [p['id'] for p in data2['results']]
        unique_ids = list(set(all_ids))
        self.assertEqual(len(all_ids), len(unique_ids),
                         "Duplicate pins found across pages")
        self.assertEqual(len(unique_ids), 35)

    def test_should_apply_visibility_filter_consistently_across_pages(self):
        tag_name = "visibility_test_tag"
        extra_tags = ["visible_tag1", "visible_tag2"]
        self._create_pins_with_tag(self.user, tag_name, 15, private=True, extra_tags=extra_tags)
        self._create_pins_with_tag(self.other_user, tag_name, 10, private=False, extra_tags=extra_tags)
        self._create_pins_with_tag(self.other_user, tag_name, 5, private=True, extra_tags=extra_tags)

        self.client.logout()
        url = reverse("pin-list") + f"?tags__name={tag_name}&limit=20"
        response = self.client.get(url)
        data = response.json()

        self.assertEqual(len(data['results']), 10)
        self.assertIsNone(data['next'])

        for pin in data['results']:
            self.assertFalse(pin['private'],
                           f"Private pin found in anonymous user results: {pin['id']}")
            self.assertEqual(pin['submitter']['username'], 'user_other',
                           "Expected only public pins from other user")

    def test_should_owner_see_own_private_pins_in_tag_search(self):
        tag_name = "owner_private_tag"
        extra_tags = ["own_tag1", "own_tag2"]
        self._create_pins_with_tag(self.user, tag_name, 5, private=True, extra_tags=extra_tags)
        self._create_pins_with_tag(self.user, tag_name, 5, private=False, extra_tags=extra_tags)

        url = reverse("pin-list") + f"?tags__name={tag_name}"
        response = self.client.get(url)
        data = response.json()

        self.assertEqual(len(data['results']), 10)
        private_count = sum(1 for p in data['results'] if p['private'])
        public_count = sum(1 for p in data['results'] if not p['private'])
        self.assertEqual(private_count, 5)
        self.assertEqual(public_count, 5)
