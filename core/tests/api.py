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


class BoardCoverPrivacyTests(APITestCase):
    """
    Regression tests for BoardSerializer.get_cover() permission filtering.
    Ensures cover pins respect private pin access control.
    """

    def setUp(self):
        super(BoardCoverPrivacyTests, self).setUp()
        self.owner = create_user("owner_cover")
        self.other_user = create_user("other_cover")

        image_own_private = create_image()
        image_own_public = create_image()
        image_other_private = create_image()
        image_other_public = create_image()

        self.pin_own_public = Pin.objects.create(
            submitter=self.owner,
            image=image_own_public,
            private=False,
            description="owner public pin",
        )
        self.pin_other_public = Pin.objects.create(
            submitter=self.other_user,
            image=image_other_public,
            private=False,
            description="other public pin",
        )
        self.pin_own_private = Pin.objects.create(
            submitter=self.owner,
            image=image_own_private,
            private=True,
            description="owner private pin",
        )
        self.pin_other_private = Pin.objects.create(
            submitter=self.other_user,
            image=image_other_private,
            private=True,
            description="other private pin",
        )

        self.public_board = Board.objects.create(
            name="cover_board_public",
            submitter=self.owner,
            private=False,
        )
        self.public_board.pins.add(
            self.pin_other_private,
            self.pin_own_private,
            self.pin_other_public,
            self.pin_own_public,
        )
        self.public_board.save()
        self.board_url = reverse("board-detail", kwargs={"pk": self.public_board.pk})

    def tearDown(self):
        _teardown_models()

    def test_anonymous_cover_not_private_pin(self):
        resp = self.client.get(self.board_url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        cover = data.get('cover')
        self.assertIsNotNone(cover, "cover should not be None (has public pins)")
        self.assertFalse(cover.get('private'),
                         "anonymous user should not receive a private pin as cover")
        cover_id = cover.get('id')
        self.assertIn(cover_id, [self.pin_own_public.id, self.pin_other_public.id],
                      "cover should be one of the public pins")

    def test_non_owner_cover_not_other_private_pin(self):
        self.client.login(username=self.other_user.username, password='password')
        resp = self.client.get(self.board_url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        cover = data.get('cover')
        self.assertIsNotNone(cover)
        cover_id = cover.get('id')
        self.assertIn(cover_id, [self.pin_own_public.id, self.pin_other_public.id, self.pin_other_private.id],
                      "non-owner should see their own private pin or public pins as cover, not others' private")
        self.assertNotEqual(cover_id, self.pin_own_private.id,
                            "non-owner should not receive board owner's private pin as cover")

    def test_owner_cover_can_be_own_private_pin(self):
        self.client.login(username=self.owner.username, password='password')
        resp = self.client.get(self.board_url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        cover = data.get('cover')
        self.assertIsNotNone(cover)
        cover_id = cover.get('id')
        self.assertIn(cover_id,
                      [self.pin_other_public.id, self.pin_own_public.id, self.pin_own_private.id],
                      "owner should see their own private and public pins, plus others' public pins as cover")
        self.assertNotEqual(cover_id, self.pin_other_private.id,
                            "owner should not receive other user's private pin as cover")

    def test_board_with_only_private_pins_of_others_cover_none_for_anonymous(self):
        exclusive_board = Board.objects.create(
            name="exclusive_board",
            submitter=self.owner,
            private=False,
        )
        exclusive_board.pins.add(self.pin_other_private)
        exclusive_board.save()
        exclusive_url = reverse("board-detail", kwargs={"pk": exclusive_board.pk})

        resp = self.client.get(exclusive_url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNone(data.get('cover'),
                          "cover should be None when board only contains other users' private pins")
        self.assertEqual(data.get('total_pins'), 0,
                         "total_pins should be 0 for anonymous on board with only others' private pins")


class PinPaginationCountPermissionTests(APITestCase):
    """
    Regression tests for Pin pagination count consistency under permission filtering.
    Ensures DRF's paginator 'count' field matches the actual accessible pin count,
    and is consistent across different users viewing the same Board/tag.
    """

    def setUp(self):
        super(PinPaginationCountPermissionTests, self).setUp()
        self.owner = create_user("pager_owner")
        self.other_user = create_user("pager_other")

        image_op = create_image()
        image_oPr = create_image()
        image_otp = create_image()
        image_otPr = create_image()

        self.pin_own_public = Pin.objects.create(
            submitter=self.owner, image=image_op, private=False,
            description="pager owner public apple banana cherry",
        )
        self.pin_own_private = Pin.objects.create(
            submitter=self.owner, image=image_oPr, private=True,
            description="pager owner private apple durian elderberry",
        )
        self.pin_other_public = Pin.objects.create(
            submitter=self.other_user, image=image_otp, private=False,
            description="pager other public apple fig grape",
        )
        self.pin_other_private = Pin.objects.create(
            submitter=self.other_user, image=image_otPr, private=True,
            description="pager other private apple honeydew iced",
        )

        tag_apple, _ = Tag.objects.get_or_create(name="tag_apple", slug="tag_apple")
        tag_banana, _ = Tag.objects.get_or_create(name="tag_banana", slug="tag_banana")

        self.pin_own_public.tags.add(tag_apple, tag_banana)
        self.pin_own_private.tags.add(tag_apple)
        self.pin_other_public.tags.add(tag_apple)
        self.pin_other_private.tags.add(tag_apple)

        self.public_board = Board.objects.create(
            name="pager_board",
            submitter=self.owner,
            private=False,
        )
        self.public_board.pins.add(
            self.pin_own_public, self.pin_own_private,
            self.pin_other_public, self.pin_other_private,
        )
        self.public_board.save()

        self.pin_list_url = reverse("pin-list")

    def tearDown(self):
        _teardown_models()

    def _extract(self, resp):
        data = resp.json()
        return data.get('count'), data.get('results'), data.get('next')

    def test_anonymous_board_pins_count_matches_results(self):
        resp = self.client.get(self.pin_list_url, {"pins__id": self.public_board.id})
        self.assertEqual(resp.status_code, 200)
        count, results, _ = self._extract(resp)
        self.assertEqual(count, 2, f"anonymous should count 2 public pins, got count={count}")
        self.assertEqual(len(results), 2, f"anonymous should receive 2 public pins, got {len(results)}")
        result_ids = {r["id"] for r in results}
        self.assertEqual(result_ids, {self.pin_own_public.id, self.pin_other_public.id})

    def test_owner_board_pins_count_matches_results(self):
        self.client.login(username=self.owner.username, password='password')
        resp = self.client.get(self.pin_list_url, {"pins__id": self.public_board.id})
        self.assertEqual(resp.status_code, 200)
        count, results, _ = self._extract(resp)
        self.assertEqual(count, 3, f"owner should count 3 pins (own + other public), got {count}")
        self.assertEqual(len(results), 3)
        result_ids = {r["id"] for r in results}
        self.assertEqual(result_ids, {self.pin_own_public.id, self.pin_own_private.id, self.pin_other_public.id})

    def test_other_user_board_pins_count_matches_results(self):
        self.client.login(username=self.other_user.username, password='password')
        resp = self.client.get(self.pin_list_url, {"pins__id": self.public_board.id})
        self.assertEqual(resp.status_code, 200)
        count, results, _ = self._extract(resp)
        self.assertEqual(count, 3, f"other user should count 3 (own private + all public), got {count}")
        self.assertEqual(len(results), 3)
        result_ids = {r["id"] for r in results}
        self.assertEqual(result_ids, {self.pin_own_public.id, self.pin_other_public.id, self.pin_other_private.id})

    def test_anonymous_tag_filter_count_matches_results_no_duplicates(self):
        resp = self.client.get(self.pin_list_url, {"tags__name": "tag_apple"})
        self.assertEqual(resp.status_code, 200)
        count, results, _ = self._extract(resp)
        self.assertEqual(count, 2, f"anonymous via tag should count 2 public pins, got {count}")
        self.assertEqual(len(results), 2, f"anonymous via tag should get 2 pins, got {len(results)}")

    def test_owner_tag_filter_count_matches_results_no_duplicates(self):
        self.client.login(username=self.owner.username, password='password')
        resp = self.client.get(self.pin_list_url, {"tags__name": "tag_apple"})
        self.assertEqual(resp.status_code, 200)
        count, results, _ = self._extract(resp)
        self.assertEqual(count, 3, f"owner via tag should count 3, got {count}")
        self.assertEqual(len(results), 3, "distinct should prevent duplicate rows from tag M2M join")

    def test_multi_tag_pin_appears_once_in_results(self):
        resp = self.client.get(self.pin_list_url, {"tags__name": "tag_banana"})
        self.assertEqual(resp.status_code, 200)
        count, results, _ = self._extract(resp)
        self.assertEqual(count, 1, "single public pin with tag_banana, count=1")
        self.assertEqual(len(results), 1, "single public pin with tag_banana, results len=1")

        self.pin_own_public.tags.add(
            *[Tag.objects.get_or_create(name=f"tag_extra_{i}", slug=f"tag_extra_{i}")[0]
              for i in range(3)]
        )
        resp = self.client.get(self.pin_list_url, {"tags__name": "tag_banana"})
        count, results, _ = self._extract(resp)
        self.assertEqual(len(results), 1,
                         "even with many tags on the same pin, distinct should ensure only one result row")
        self.assertEqual(count, 1)

    def test_owner_list_pins_count_matches_results(self):
        self.client.login(username=self.owner.username, password='password')
        resp = self.client.get(self.pin_list_url)
        count, results, _ = self._extract(resp)
        expected_ids = {self.pin_own_public.id, self.pin_own_private.id, self.pin_other_public.id}
        self.assertEqual(count, len(expected_ids))
        self.assertEqual(len(results), len(expected_ids))
        self.assertEqual({r["id"] for r in results}, expected_ids)

    def test_pagination_next_consistent_with_count_owner(self):
        for i in range(70):
            image = create_image()
            Pin.objects.create(
                submitter=self.owner, image=image, private=(i % 5 == 0),
                description=f"bulk pin {i} unique marker",
            )
        self.client.login(username=self.owner.username, password='password')
        resp = self.client.get(self.pin_list_url, {"limit": 20})
        count, results, nxt = self._extract(resp)
        self.assertEqual(len(results), 20, "first page should contain exactly limit=20 pins")
        self.assertIsNotNone(nxt, "next should be present since total > 20")
        resp2 = self.client.get(nxt.replace("http://testserver", ""))
        count2, results2, nxt2 = self._extract(resp2)
        self.assertEqual(count2, count, "count should be consistent across pages")
        self.assertEqual(len(results2), 20, "second page should also contain 20")


class PinSearchFieldsTests(APITestCase):
    """
    Regression tests for PinViewSet search_fields (description search)
    with private pin permission filtering and pagination count consistency.
    """

    def setUp(self):
        super(PinSearchFieldsTests, self).setUp()
        self.owner = create_user("srch_owner")
        self.other = create_user("srch_other")

        image_ap = create_image()
        image_aPr = create_image()
        image_bp = create_image()
        image_bPr = create_image()

        self.pin_alpha_own_public = Pin.objects.create(
            submitter=self.owner, image=image_ap, private=False,
            description="alpha beta gamma public",
        )
        self.pin_alpha_own_private = Pin.objects.create(
            submitter=self.owner, image=image_aPr, private=True,
            description="alpha delta epsilon private owner",
        )
        self.pin_beta_other_public = Pin.objects.create(
            submitter=self.other, image=image_bp, private=False,
            description="alpha zeta eta public other",
        )
        self.pin_beta_other_private = Pin.objects.create(
            submitter=self.other, image=image_bPr, private=True,
            description="alpha theta iota private other",
        )
        self.pin_unrelated = Pin.objects.create(
            submitter=self.other, image=create_image(), private=False,
            description="unrelated kappa lambda mu",
        )
        self.pin_list_url = reverse("pin-list")

    def tearDown(self):
        _teardown_models()

    def test_search_anonymous_matches_only_public_description(self):
        resp = self.client.get(self.pin_list_url, {"search": "alpha"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['count'], 2, "anonymous should find 2 public pins containing 'alpha'")
        ids = {r['id'] for r in data['results']}
        self.assertEqual(ids, {self.pin_alpha_own_public.id, self.pin_beta_other_public.id})

    def test_search_owner_matches_own_private_plus_public(self):
        self.client.login(username=self.owner.username, password='password')
        resp = self.client.get(self.pin_list_url, {"search": "alpha"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['count'], 3, "owner should find own private + all public pins (3 total)")
        ids = {r['id'] for r in data['results']}
        self.assertEqual(ids, {
            self.pin_alpha_own_public.id,
            self.pin_alpha_own_private.id,
            self.pin_beta_other_public.id,
        })

    def test_search_other_user_matches_own_private_plus_public(self):
        self.client.login(username=self.other.username, password='password')
        resp = self.client.get(self.pin_list_url, {"search": "alpha"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['count'], 3, "other user should find own private + all public pins")
        ids = {r['id'] for r in data['results']}
        self.assertEqual(ids, {
            self.pin_alpha_own_public.id,
            self.pin_beta_other_public.id,
            self.pin_beta_other_private.id,
        })

    def test_search_count_matches_results_length(self):
        self.client.login(username=self.owner.username, password='password')
        resp = self.client.get(self.pin_list_url, {"search": "alpha"})
        data = resp.json()
        self.assertEqual(data['count'], len(data['results']),
                         "count should match number of returned entries when within one page")

    def test_search_no_match_returns_zero(self):
        resp = self.client.get(self.pin_list_url, {"search": "zzzzzzzzzzzzzzzz"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['count'], 0)
        self.assertEqual(data['results'], [])

    def test_search_keyword_in_own_private_excluded_for_anonymous(self):
        resp = self.client.get(self.pin_list_url, {"search": "delta"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['count'], 0,
                         "'delta' only appears in owner's private pin, anonymous should see 0")


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
