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


class BatchTagTests(APITestCase):

    def setUp(self):
        super(BatchTagTests, self).setUp()
        self.user = create_user("batch_owner")
        self.other_user = create_user("batch_other")
        self.client.login(username=self.user.username, password='password')

        self.image1 = create_image()
        self.image2 = create_image()
        self.image3 = create_image()

        self.pin1 = create_pin(self.user, self.image1, ["python", "django"])
        self.pin2 = create_pin(self.user, self.image2, ["python", "flask"])
        self.pin3 = create_pin(self.user, self.image3, [])

        self.other_image = create_image()
        self.other_pin = create_pin(self.other_user, self.other_image, ["python"])
        self.other_pin.private = True
        self.other_pin.save()

    def tearDown(self):
        _teardown_models()

    def _batch_add_url(self):
        return reverse("batch-tags-batch-add")

    def _batch_remove_url(self):
        return reverse("batch-tags-batch-remove")

    def _batch_merge_url(self):
        return reverse("batch-tags-batch-merge")

    def _batch_preview_url(self):
        return reverse("batch-tags-preview")

    def test_batch_add_tags_to_pins(self):
        resp = self.client.post(
            self._batch_add_url(),
            data={"pin_ids": [self.pin1.id, self.pin2.id], "tags": ["web"]},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["affected_count"], 2)
        self.assertIn(self.pin1.id, data["affected_pin_ids"])
        self.assertIn(self.pin2.id, data["affected_pin_ids"])

        self.pin1.refresh_from_db()
        self.pin2.refresh_from_db()
        pin1_tags = list(self.pin1.tags.names())
        pin2_tags = list(self.pin2.tags.names())
        self.assertIn("web", pin1_tags)
        self.assertIn("web", pin2_tags)

    def test_batch_add_tags_dry_run(self):
        resp = self.client.post(
            self._batch_add_url(),
            data={"pin_ids": [self.pin1.id], "tags": ["web"], "dry_run": True},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["operation"], "add")
        self.assertIn("web", data["tags"])

        self.pin1.refresh_from_db()
        self.assertNotIn("web", list(self.pin1.tags.names()))

    def test_batch_add_skips_private_pins_of_others(self):
        resp = self.client.post(
            self._batch_add_url(),
            data={"pin_ids": [self.pin1.id, self.other_pin.id], "tags": ["web"]},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertIn(self.pin1.id, data["affected_pin_ids"])
        self.assertIn(self.other_pin.id, data["skipped_pin_ids"])

    def test_batch_add_tag_normalization(self):
        resp = self.client.post(
            self._batch_add_url(),
            data={"pin_ids": [self.pin1.id], "tags": ["Python"], "dry_run": True},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertIn("Python", data["normalized_tags"])

    def test_batch_add_unauthenticated(self):
        self.client.logout()
        resp = self.client.post(
            self._batch_add_url(),
            data={"pin_ids": [self.pin1.id], "tags": ["web"]},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_batch_add_invalid_pin_ids(self):
        resp = self.client.post(
            self._batch_add_url(),
            data={"pin_ids": [99999], "tags": ["web"]},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_batch_add_empty_tags(self):
        resp = self.client.post(
            self._batch_add_url(),
            data={"pin_ids": [self.pin1.id], "tags": []},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_batch_remove_tags_from_pins(self):
        resp = self.client.post(
            self._batch_remove_url(),
            data={"pin_ids": [self.pin1.id, self.pin2.id], "tags": ["python"]},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["affected_count"], 2)

        self.pin1.refresh_from_db()
        self.pin2.refresh_from_db()
        self.assertNotIn("python", list(self.pin1.tags.names()))
        self.assertNotIn("python", list(self.pin2.tags.names()))
        self.assertIn("django", list(self.pin1.tags.names()))
        self.assertIn("flask", list(self.pin2.tags.names()))

    def test_batch_remove_tags_dry_run(self):
        resp = self.client.post(
            self._batch_remove_url(),
            data={"pin_ids": [self.pin1.id], "tags": ["python"], "dry_run": True},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["operation"], "remove")

        self.pin1.refresh_from_db()
        self.assertIn("python", list(self.pin1.tags.names()))

    def test_batch_remove_nonexistent_tags(self):
        resp = self.client.post(
            self._batch_remove_url(),
            data={"pin_ids": [self.pin1.id], "tags": ["nonexistent"]},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["affected_count"], 0)

    def test_batch_remove_skips_private_pins_of_others(self):
        resp = self.client.post(
            self._batch_remove_url(),
            data={"pin_ids": [self.other_pin.id], "tags": ["python"]},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertIn(self.other_pin.id, data["skipped_pin_ids"])

    def test_batch_merge_tags(self):
        resp = self.client.post(
            self._batch_merge_url(),
            data={"source_tags": ["django", "flask"], "target_tag": "web-framework"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertGreater(data["affected_count"], 0)

        self.pin1.refresh_from_db()
        self.pin2.refresh_from_db()
        self.assertIn("web-framework", list(self.pin1.tags.names()))
        self.assertIn("web-framework", list(self.pin2.tags.names()))
        self.assertNotIn("django", list(self.pin1.tags.names()))
        self.assertNotIn("flask", list(self.pin2.tags.names()))

    def test_batch_merge_dry_run(self):
        resp = self.client.post(
            self._batch_merge_url(),
            data={
                "source_tags": ["django"],
                "target_tag": "web-framework",
                "dry_run": True,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["operation"], "merge")

        self.pin1.refresh_from_db()
        self.assertIn("django", list(self.pin1.tags.names()))
        self.assertNotIn("web-framework", list(self.pin1.tags.names()))

    def test_batch_merge_prevents_same_source_and_target(self):
        resp = self.client.post(
            self._batch_merge_url(),
            data={"source_tags": ["python"], "target_tag": "Python"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_batch_merge_tag_already_on_pin(self):
        self.pin3.tags.add("web-framework")
        self.pin3.save()

        resp = self.client.post(
            self._batch_merge_url(),
            data={"source_tags": ["python"], "target_tag": "web-framework"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.pin3.refresh_from_db()
        tag_names = list(self.pin3.tags.names())
        self.assertEqual(tag_names.count("web-framework"), 1)
        self.assertNotIn("python", tag_names)

    def test_batch_merge_cleans_up_orphan_tags(self):
        self.pin1.tags.add("orphan")
        self.pin1.save()
        self.assertTrue(Tag.objects.filter(name="orphan").exists())

        resp = self.client.post(
            self._batch_merge_url(),
            data={"source_tags": ["orphan"], "target_tag": "adopted"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.assertFalse(Tag.objects.filter(name="orphan").exists())
        self.assertTrue(Tag.objects.filter(name="adopted").exists())

    def test_batch_merge_case_normalization(self):
        Tag.objects.create(name="Python", slug="python-case-test")
        resp = self.client.post(
            self._batch_merge_url(),
            data={
                "source_tags": ["Python"],
                "target_tag": "python-lang",
                "dry_run": True,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertIn("normalized_target", data)

    def test_preview_add_operation(self):
        resp = self.client.post(
            self._batch_preview_url(),
            data={
                "operation": "add",
                "pin_ids": [self.pin1.id, self.pin2.id],
                "tags": ["web"],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["operation"], "add")
        self.assertIn("affected_count", data)
        self.assertIn("skipped_count", data)

    def test_preview_remove_operation(self):
        resp = self.client.post(
            self._batch_preview_url(),
            data={
                "operation": "remove",
                "pin_ids": [self.pin1.id],
                "tags": ["python"],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["operation"], "remove")
        self.assertIn("pins_having_tag", data)

    def test_preview_merge_operation(self):
        resp = self.client.post(
            self._batch_preview_url(),
            data={
                "operation": "merge",
                "source_tags": ["django", "flask"],
                "target_tag": "web-framework",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["operation"], "merge")
        self.assertIn("source_pin_counts", data)
        self.assertIn("target_pin_count", data)

    def test_preview_missing_required_fields(self):
        resp = self.client.post(
            self._batch_preview_url(),
            data={"operation": "add"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_batch_add_with_private_board(self):
        private_board = Board.objects.create(
            name="private_test",
            submitter=self.other_user,
            private=True,
        )
        private_board.pins.add(self.pin3)
        private_board.save()

        resp = self.client.post(
            self._batch_add_url(),
            data={"pin_ids": [self.pin3.id], "tags": ["test"]},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertIn(self.pin3.id, data["skipped_pin_ids"])

    def test_batch_add_idempotent(self):
        resp1 = self.client.post(
            self._batch_add_url(),
            data={"pin_ids": [self.pin1.id], "tags": ["new-tag"]},
            format="json",
        )
        self.assertEqual(resp1.status_code, status.HTTP_200_OK)

        resp2 = self.client.post(
            self._batch_add_url(),
            data={"pin_ids": [self.pin1.id], "tags": ["new-tag"]},
            format="json",
        )
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)

        self.pin1.refresh_from_db()
        tag_names = list(self.pin1.tags.names())
        self.assertEqual(tag_names.count("new-tag"), 1)

    def test_batch_add_by_tag_names(self):
        resp = self.client.post(
            self._batch_add_url(),
            data={"pin_tag_names": ["python"], "tags": ["web"]},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["affected_count"], 2)
        self.assertIn(self.pin1.id, data["affected_pin_ids"])
        self.assertIn(self.pin2.id, data["affected_pin_ids"])

        self.pin1.refresh_from_db()
        self.pin2.refresh_from_db()
        self.assertIn("web", list(self.pin1.tags.names()))
        self.assertIn("web", list(self.pin2.tags.names()))

    def test_batch_add_by_tag_names_dry_run(self):
        resp = self.client.post(
            self._batch_add_url(),
            data={"pin_tag_names": ["python"], "tags": ["web"], "dry_run": True},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["selection_mode"], "tag_names")
        self.assertEqual(data["affected_count"], 2)

        self.pin1.refresh_from_db()
        self.assertNotIn("web", list(self.pin1.tags.names()))

    def test_batch_add_pin_ids_and_tag_names_conflict(self):
        resp = self.client.post(
            self._batch_add_url(),
            data={
                "pin_ids": [self.pin1.id],
                "pin_tag_names": ["python"],
                "tags": ["web"],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_batch_remove_by_tag_names(self):
        resp = self.client.post(
            self._batch_remove_url(),
            data={"pin_tag_names": ["django"], "tags": ["python"]},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["affected_count"], 1)
        self.assertIn(self.pin1.id, data["affected_pin_ids"])

        self.pin1.refresh_from_db()
        self.assertNotIn("python", list(self.pin1.tags.names()))

    def test_batch_remove_by_tag_names_dry_run(self):
        resp = self.client.post(
            self._batch_remove_url(),
            data={
                "pin_tag_names": ["python"],
                "tags": ["django"],
                "dry_run": True,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["selection_mode"], "tag_names")
        self.assertEqual(data["affected_count"], 2)

    def test_preview_add_by_tag_names(self):
        resp = self.client.post(
            self._batch_preview_url(),
            data={
                "operation": "add",
                "pin_tag_names": ["python", "django"],
                "tags": ["web"],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["operation"], "add")
        self.assertEqual(data["selection_mode"], "tag_names")
        self.assertEqual(data["affected_count"], 2)

    def test_preview_remove_by_tag_names(self):
        resp = self.client.post(
            self._batch_preview_url(),
            data={
                "operation": "remove",
                "pin_tag_names": ["python"],
                "tags": ["django"],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["operation"], "remove")
        self.assertEqual(data["selection_mode"], "tag_names")
        self.assertIn("pins_having_tag", data)
