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
    批量导入 skipped 原因 + Board 归属策略 单元测试

    ┌─────────────────────────────────────────────────────────────────┐
    │ 【Skipped 原因 × 测试覆盖映射表】                                │
    ├────┬───────────────────────────┬────────────────────────────────┤
    │ #  │ Skipped 原因               │ 对应测试方法                   │
    ├────┼───────────────────────────┼────────────────────────────────┤
    │ 1  │ url_became_404           │ test_skip_reason_url_became_404│
    │ 2  │ duplicate_fingerprint    │ test_skip_reason_duplicate_    │
    │    │                           │        fingerprint             │
    │ 3  │ board_became_invalid     │ test_skip_reason_board_        │
    │    │                           │        became_invalid           │
    │ 混 │ 以上三种 + 一个正常创建   │ test_mixed_skipped_and_created │
    └────┴───────────────────────────┴────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────┐
    │ 【Board 归属策略 × 测试覆盖映射表】                              │
    ├──────────────────────────────┬─────────────────────────────────┤
    │ 策略 / Tiebreaker 场景        │ 对应测试方法                    │
    ├──────────────────────────────┼─────────────────────────────────┤
    │ 缺少 board 归属（warning）    │ test_precheck_missing_board    │
    │                                │        _warning                │
    │ default_board_ids fallback    │ test_default_board_fallback    │
    │ 去重 + 优先级（Tiebreaker a） │ test_board_dedupe_preserves_   │
    │                                │        order                    │
    │ 用户∩default 交集按用户优先    │ test_board_user_default_       │
    │   （Tiebreaker b）             │        intersection_tiebreaker  │
    │ max_boards_per_pin 裁剪       │ test_max_boards_per_pin_trim   │
    │ allow_multiple_boards=False  │ test_single_board_only_mode     │
    └──────────────────────────────┴─────────────────────────────────┘
    """

    _JSON_TYPE = "application/json"

    def setUp(self):
        super(BatchImportSkippedTests, self).setUp()
        self.user = create_user("batch_test")
        self.client.login(username=self.user.username, password='password')
        self.board1 = Board.objects.create(name="board_1", submitter=self.user)
        self.board2 = Board.objects.create(name="board_2", submitter=self.user)
        self.board3 = Board.objects.create(name="board_3", submitter=self.user)
        self.batch_import_url = reverse("pin-batch-import")
        self.batch_precheck_url = reverse("pin-batch-precheck")

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

    # ============================================================
    #  Board 归属策略 / Warning 触发测试（batch-precheck）
    # ============================================================

    @mock.patch('requests.head', mock_requests_head_ok)
    @mock.patch('requests.get', mock_requests_get)
    def test_precheck_missing_board_warning(self):
        """
        Board 归属策略（缺少 board 归属）
        场景: 用户未传 board_ids 且未配置 default_board_ids
        → 预检测结果中 warnings 应包含 'missing_board'
        → can_import 仍为 True（仅 warning，不阻止）
        """
        url = 'http://example.com/no-board.png'
        payload = {
            "pins": [
                {"url": url, "board_ids": []}
            ],
            "fingerprint_policy": {
                "enable_exact_match": False,
                "enable_phash_match": False,
            },
            "url_policy": {
                "check_404_on_precheck": False,
                "check_404_on_import": False,
            }
        }
        response = self.client.post(
            self.batch_precheck_url, data=payload, format="json"
        )
        resp = response.json()
        self.assertEqual(response.status_code, 200, response.json())
        first_result = resp['results'][0]
        self.assertIn(
            'missing_board', first_result['warnings'],
            f"warnings 应包含 'missing_board', 实际: {first_result['warnings']}"
        )
        self.assertTrue(
            first_result['can_import'],
            "缺少 board 仅是 warning，不应阻止 can_import"
        )

    @mock.patch('requests.head', mock_requests_head_ok)
    @mock.patch('requests.get', mock_requests_get)
    def test_default_board_fallback(self):
        """
        Board 归属策略（default_board_ids fallback）
        场景: 用户未传 board_ids，但 board_policy 提供了 default_board_ids
        → 预检测结果应触发 'used_default_board' warning
        → processed board_ids 应等于 default_board_ids
        """
        url = 'http://example.com/with-default.png'
        payload = {
            "pins": [
                {"url": url, "board_ids": []}
            ],
            "board_policy": {
                "default_board_ids": [self.board2.id, self.board3.id],
            },
            "fingerprint_policy": {
                "enable_exact_match": False,
                "enable_phash_match": False,
            },
            "url_policy": {
                "check_404_on_precheck": False,
                "check_404_on_import": False,
            }
        }
        response = self.client.post(
            self.batch_precheck_url, data=payload, format="json"
        )
        resp = response.json()
        first_result = resp['results'][0]
        self.assertIn(
            'used_default_board', first_result['warnings'],
            f"应触发 'used_default_board' warning, 实际: {first_result['warnings']}"
        )
        self.assertEqual(
            first_result['board_ids'],
            [self.board2.id, self.board3.id],
            "应正确回退到 default_board_ids 并保持原顺序"
        )

    @mock.patch('requests.head', mock_requests_head_ok)
    @mock.patch('requests.get', mock_requests_get)
    def test_board_dedupe_preserves_order(self):
        """
        Tiebreaker (a): board_ids 内部重复去重后保留首次出现（即原优先级顺序）
        场景: board_ids = [B2, B1, B2, B3]（B2 在位置 0 和 2 重复）
        → 去重后应为 [B2, B1, B3]（保留 B2 首次出现的最高优先级）
        → 应触发 'duplicate_boards' warning
        """
        url = 'http://example.com/dedup-order.png'
        payload = {
            "pins": [
                {
                    "url": url,
                    "board_ids": [self.board2.id, self.board1.id, self.board2.id, self.board3.id],
                }
            ],
            "fingerprint_policy": {
                "enable_exact_match": False,
                "enable_phash_match": False,
            },
            "url_policy": {
                "check_404_on_precheck": False,
                "check_404_on_import": False,
            }
        }
        response = self.client.post(
            self.batch_precheck_url, data=payload, format="json"
        )
        resp = response.json()
        first_result = resp['results'][0]
        self.assertIn(
            'duplicate_boards', first_result['warnings'],
            f"应触发 'duplicate_boards' warning, 实际: {first_result['warnings']}"
        )
        self.assertEqual(
            first_result['board_ids'],
            [self.board2.id, self.board1.id, self.board3.id],
            "去重后应保留首次出现的顺序: [B2, B1, B3]"
        )

    @mock.patch('requests.head', mock_requests_head_ok)
    @mock.patch('requests.get', mock_requests_get)
    def test_board_user_default_intersection_tiebreaker(self):
        """
        Tiebreaker (b): 用户 board_ids ∩ default_board_ids 有交集时
                        以用户 board_ids 中的位置为准
        场景: user=[B3, B1], default=[B1, B2]（B1 在 default 中也出现）
        → 合并后应为 [B3, B1, B2]（B1 位置按用户的 index 1，default 中不重复追加）
        → 应触发 'appended_default_boards' warning（B2 被追加）
        """
        url = 'http://example.com/tiebreaker-b.png'
        payload = {
            "pins": [
                {
                    "url": url,
                    "board_ids": [self.board3.id, self.board1.id],
                }
            ],
            "board_policy": {
                "default_board_ids": [self.board1.id, self.board2.id],
            },
            "fingerprint_policy": {
                "enable_exact_match": False,
                "enable_phash_match": False,
            },
            "url_policy": {
                "check_404_on_precheck": False,
                "check_404_on_import": False,
            }
        }
        response = self.client.post(
            self.batch_precheck_url, data=payload, format="json"
        )
        resp = response.json()
        first_result = resp['results'][0]
        self.assertIn(
            'appended_default_boards', first_result['warnings'],
            f"应触发 'appended_default_boards' warning, 实际: {first_result['warnings']}"
        )
        self.assertEqual(
            first_result['board_ids'],
            [self.board3.id, self.board1.id, self.board2.id],
            "Tiebreaker (b): B1 按用户位置(1)，B2 从 default 追加，结果 [B3, B1, B2]"
        )

    @mock.patch('requests.head', mock_requests_head_ok)
    @mock.patch('requests.get', mock_requests_get)
    def test_max_boards_per_pin_trim(self):
        """
        Board 裁剪策略: max_boards_per_pin=N 时按优先级保留前 N 个
        场景: board_ids=[B1, B2, B3]，配置 max_boards_per_pin=2
        → 应保留 [B1, B2]（前 2 个最高优先级）
        → 应触发 'max_boards_exceeded' warning
        """
        url = 'http://example.com/max-boards.png'
        payload = {
            "pins": [
                {
                    "url": url,
                    "board_ids": [self.board1.id, self.board2.id, self.board3.id],
                }
            ],
            "board_policy": {
                "max_boards_per_pin": 2,
            },
            "fingerprint_policy": {
                "enable_exact_match": False,
                "enable_phash_match": False,
            },
            "url_policy": {
                "check_404_on_precheck": False,
                "check_404_on_import": False,
            }
        }
        response = self.client.post(
            self.batch_precheck_url, data=payload, format="json"
        )
        resp = response.json()
        first_result = resp['results'][0]
        self.assertIn(
            'max_boards_exceeded', first_result['warnings'],
            f"应触发 'max_boards_exceeded' warning, 实际: {first_result['warnings']}"
        )
        self.assertEqual(
            first_result['board_ids'],
            [self.board1.id, self.board2.id],
            "max_boards_per_pin=2 时应裁剪为前 2 个"
        )

    @mock.patch('requests.head', mock_requests_head_ok)
    @mock.patch('requests.get', mock_requests_get)
    def test_single_board_only_mode(self):
        """
        Board 裁剪策略: allow_multiple_boards=False 只保留最高优先级一个
        场景: board_ids=[B3, B1, B2]，allow_multiple_boards=False
        → 应仅保留 [B3]（最高优先级，index=0）
        → 应触发 'multiple_boards_trimmed' warning
        """
        url = 'http://example.com/single-board.png'
        payload = {
            "pins": [
                {
                    "url": url,
                    "board_ids": [self.board3.id, self.board1.id, self.board2.id],
                }
            ],
            "board_policy": {
                "allow_multiple_boards": False,
            },
            "fingerprint_policy": {
                "enable_exact_match": False,
                "enable_phash_match": False,
            },
            "url_policy": {
                "check_404_on_precheck": False,
                "check_404_on_import": False,
            }
        }
        response = self.client.post(
            self.batch_precheck_url, data=payload, format="json"
        )
        resp = response.json()
        first_result = resp['results'][0]
        self.assertIn(
            'multiple_boards_trimmed', first_result['warnings'],
            f"应触发 'multiple_boards_trimmed' warning, 实际: {first_result['warnings']}"
        )
        self.assertEqual(
            first_result['board_ids'],
            [self.board3.id],
            "allow_multiple_boards=False 时应裁剪为最高优先级 [B3]"
        )
