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


def mock_requests_head_404(url, **kwargs):
    resp = mock.Mock()
    resp.status_code = 404
    return resp


def mock_requests_head_ok(url, **kwargs):
    resp = mock.Mock()
    resp.status_code = 200
    return resp


class BatchImportSkippedTests(APITestCase):
    """
    批量导入三种 skipped 原因的单元测试

    skipped 原因分类：
    1. url_became_404     → 导入时二次检测发现 URL 返回 404
    2. duplicate_fingerprint → 导入时检测到 MD5 与已有或批次内重复
    3. board_became_invalid → 导入时发现所有指定 board 均失效
    """

    _JSON_TYPE = "application/json"

    def setUp(self):
        super(BatchImportSkippedTests, self).setUp()
        self.user = create_user("batch_test")
        self.client.login(username=self.user.username, password='password')
        self.board1 = Board.objects.create(name="board_1", submitter=self.user)
        self.board2 = Board.objects.create(name="board_2", submitter=self.user)
        self.batch_import_url = reverse("pin-batch-import")

    def tearDown(self):
        _teardown_models()

    @mock.patch('requests.head', mock_requests_head_404)
    @mock.patch('requests.get', mock_requests_get)
    def test_skip_reason_url_became_404(self):
        """
        场景 1: url_became_404
        预检通过后，URL 在导入期二次检测（HEAD）时返回 404
        → 该条目应出现在 skipped 中，reason='url_became_404'
        → 不应创建 Pin
        """
        test_url = 'http://example.com/expired-image.png'
        payload = {
            "pins": [
                {
                    "url": test_url,
                    "board_ids": [self.board1.id],
                }
            ],
            "url_policy": {
                "check_404_on_precheck": True,
                "check_404_on_import": True,
                "timeout": 5,
            }
        }
        response = self.client.post(
            self.batch_import_url, data=payload, format="json"
        )
        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
            response.json()
        )
        resp = response.json()
        self.assertEqual(resp['total_created'], 0, "不应创建任何 Pin")
        self.assertEqual(
            resp['total_skipped'], 1,
            f"应有 1 个 skipped，实际 {resp['total_skipped']}: {resp}"
        )
        self.assertEqual(
            resp['skipped'][0]['reason'],
            'url_became_404',
            f"skipped 原因应为 url_became_404, 实际 {resp['skipped'][0]['reason']}"
        )
        self.assertEqual(
            resp['skipped'][0]['url'],
            test_url,
            "skipped 条目应保留原始 URL"
        )
        self.assertEqual(Pin.objects.count(), 0, "数据库中不应有 Pin")

    @mock.patch('requests.head', mock_requests_head_ok)
    @mock.patch('requests.get', mock_requests_get)
    def test_skip_reason_duplicate_fingerprint(self):
        """
        场景 2: duplicate_fingerprint
        导入时第二条与第一条下载后 MD5 完全一致（同一张 mock 图）
        → 第二条应出现在 skipped 中，reason='duplicate_fingerprint'
        → 仅第一条成功创建 Pin
        """
        url_a = 'http://example.com/image-a.png'
        url_b = 'http://example.com/image-b-same-content.png'
        payload = {
            "pins": [
                {"url": url_a, "board_ids": [self.board1.id]},
                {"url": url_b, "board_ids": [self.board2.id]},
            ],
            "fingerprint_policy": {
                "enable_exact_match": True,
                "enable_phash_match": False,
            },
            "url_policy": {
                "check_404_on_precheck": False,
                "check_404_on_import": False,
            }
        }
        response = self.client.post(
            self.batch_import_url, data=payload, format="json"
        )
        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            response.json()
        )
        resp = response.json()
        self.assertEqual(
            resp['total_created'], 1,
            f"仅应创建 1 个 Pin，实际 {resp['total_created']}: {resp}"
        )
        self.assertEqual(
            resp['total_skipped'], 1,
            f"应有 1 个 skipped，实际 {resp['total_skipped']}: {resp}"
        )
        self.assertEqual(
            resp['skipped'][0]['reason'],
            'duplicate_fingerprint',
            f"skipped 原因应为 duplicate_fingerprint, 实际 {resp['skipped'][0]['reason']}"
        )
        self.assertEqual(Pin.objects.count(), 1, "数据库中应只有 1 个 Pin")

    @mock.patch('requests.head', mock_requests_head_ok)
    @mock.patch('requests.get', mock_requests_get)
    def test_skip_reason_board_became_invalid(self):
        """
        场景 3: board_became_invalid
        Pin 指定了 board_id，但在导入期该 Board 已被删除或权限丢失
        → 该条目应出现在 skipped 中，reason='board_became_invalid'
        → 不应创建 Pin
        """
        non_existent_board_id = 99999
        test_url = 'http://example.com/image-no-valid-board.png'
        payload = {
            "pins": [
                {
                    "url": test_url,
                    "board_ids": [non_existent_board_id],
                }
            ],
            "url_policy": {
                "check_404_on_precheck": False,
                "check_404_on_import": False,
            }
        }
        response = self.client.post(
            self.batch_import_url, data=payload, format="json"
        )
        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
            response.json()
        )
        resp = response.json()
        self.assertEqual(resp['total_created'], 0, "不应创建任何 Pin")
        self.assertEqual(
            resp['total_skipped'], 1,
            f"应有 1 个 skipped，实际 {resp['total_skipped']}: {resp}"
        )
        self.assertEqual(
            resp['skipped'][0]['reason'],
            'board_became_invalid',
            f"skipped 原因应为 board_became_invalid, 实际 {resp['skipped'][0]['reason']}"
        )
        self.assertEqual(Pin.objects.count(), 0, "数据库中不应有 Pin")

    @mock.patch('requests.head', mock_requests_head_ok)
    @mock.patch('requests.get', mock_requests_get)
    def test_mixed_skipped_and_created(self):
        """
        混合场景：三个 Pin 分别命中三种 skipped 原因 + 一个正常 Pin
        → 仅正常 Pin 成功创建
        → skipped 数组包含三条，三种原因各一条
        """
        # 场景准备: 先创建一个 Pin 作为 fingerprint 重复源
        with mock.patch('requests.get', mock_requests_get):
            existing_img = create_image()
            create_pin(self.user, image=existing_img, tags=[])

        non_existent_board_id = 88888
        url_normal = 'http://example.com/normal.png'
        url_404 = 'http://example.com/expired.png'
        url_dup = 'http://example.com/dup-fingerprint.png'
        url_invalid_board = 'http://example.com/invalid-board.png'

        payload = {
            "pins": [
                {"url": url_normal, "board_ids": [self.board1.id]},
                {"url": url_404, "board_ids": [self.board1.id]},
                {"url": url_dup, "board_ids": [self.board1.id]},
                {"url": url_invalid_board, "board_ids": [non_existent_board_id]},
            ],
            "fingerprint_policy": {
                "enable_exact_match": True,
                "enable_phash_match": False,
            },
            "url_policy": {
                "check_404_on_precheck": True,
                "check_404_on_import": True,
            }
        }

        # 分别替换：404 的用 head 404，其他用 head 200；下载内容都相同（用于触发 fingerprint 重复）
        def variable_head(url, **kwargs):
            if url == url_404:
                return mock_requests_head_404(url, **kwargs)
            return mock_requests_head_ok(url, **kwargs)

        with mock.patch('requests.head', variable_head):
            response = self.client.post(
                self.batch_import_url, data=payload, format="json"
            )

        resp = response.json()
        self.assertEqual(
            resp['total_created'], 1,
            f"仅应创建 1 个 Pin，实际 {resp['total_created']}: {resp}"
        )
        skipped_reasons = [s['reason'] for s in resp['skipped']]
        self.assertIn(
            'url_became_404', skipped_reasons,
            f"应包含 url_became_404, 实际有: {skipped_reasons}"
        )
        self.assertIn(
            'duplicate_fingerprint', skipped_reasons,
            f"应包含 duplicate_fingerprint, 实际有: {skipped_reasons}"
        )
        self.assertIn(
            'board_became_invalid', skipped_reasons,
            f"应包含 board_became_invalid, 实际有: {skipped_reasons}"
        )
        self.assertEqual(len(resp['skipped']), 3, f"应有 3 个 skipped, 实际 {len(resp['skipped'])}")
