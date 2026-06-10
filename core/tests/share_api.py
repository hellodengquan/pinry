from django.urls import reverse
from django.test import override_settings
from django.utils import timezone
from datetime import timedelta
from unittest import mock
from rest_framework import status
from rest_framework.test import APITestCase

from taggit.models import Tag

from .helpers import create_image, create_user, create_pin
from core.models import Pin, Image, Board, BoardShareToken
from users.models import User


def _teardown_share_models():
    BoardShareToken.objects.all().delete()
    Pin.objects.all().delete()
    Image.objects.all().delete()
    Tag.objects.all().delete()
    Board.objects.all().delete()
    User.objects.all().delete()


class BoardShareTokenCreateTests(APITestCase):
    """令牌生成相关测试"""

    def setUp(self):
        super().setUp()
        self.owner = create_user("owner")
        self.other_user = create_user("other")
        self.board = Board.objects.create(
            name="share_test_board",
            submitter=self.owner,
            private=False,
        )
        self.create_url = reverse(
            "board-create-share-token",
            kwargs={"pk": self.board.pk},
        )
        self.list_url = reverse(
            "board-list-share-tokens",
            kwargs={"pk": self.board.pk},
        )

    def tearDown(self):
        _teardown_share_models()

    def test_owner_can_create_share_token_without_expiry(self):
        self.client.login(username=self.owner.username, password='password')
        resp = self.client.post(self.create_url, data={}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        data = resp.json()
        self.assertIn('token', data)
        self.assertIn('share_url', data)
        self.assertIsNone(data['expires_at'])
        self.assertFalse(data['is_revoked'])
        self.assertTrue(data['is_valid'])
        self.assertEqual(data['board_id'], self.board.pk)
        self.assertEqual(BoardShareToken.objects.count(), 1)

    def test_owner_can_create_share_token_with_expiry(self):
        self.client.login(username=self.owner.username, password='password')
        resp = self.client.post(
            self.create_url,
            data={"expires_days": 7},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        data = resp.json()
        self.assertIsNotNone(data['expires_at'])
        created = BoardShareToken.objects.get(token=data['token'])
        expected_expiry = created.created_at + timedelta(days=7)
        self.assertAlmostEqual(
            created.expires_at.timestamp(),
            expected_expiry.timestamp(),
            delta=2,
        )

    def test_non_owner_cannot_create_share_token(self):
        self.client.login(username=self.other_user.username, password='password')
        resp = self.client.post(self.create_url, data={}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, resp.content)
        self.assertEqual(BoardShareToken.objects.count(), 0)

    def test_anonymous_cannot_create_share_token(self):
        resp = self.client.post(self.create_url, data={}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED, resp.content)
        self.assertEqual(BoardShareToken.objects.count(), 0)

    def test_create_share_token_rejects_invalid_expiry(self):
        self.client.login(username=self.owner.username, password='password')
        resp = self.client.post(
            self.create_url,
            data={"expires_days": -1},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)

        resp = self.client.post(
            self.create_url,
            data={"expires_days": 0},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)

        resp = self.client.post(
            self.create_url,
            data={"expires_days": 1000},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)

    def test_generated_tokens_are_unique(self):
        self.client.login(username=self.owner.username, password='password')
        tokens = set()
        for _ in range(20):
            resp = self.client.post(self.create_url, data={}, format='json')
            self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
            tokens.add(resp.json()['token'])
        self.assertEqual(len(tokens), 20)

    def test_create_private_board_share_token(self):
        private_board = Board.objects.create(
            name="private_board",
            submitter=self.owner,
            private=True,
        )
        create_url = reverse(
            "board-create-share-token",
            kwargs={"pk": private_board.pk},
        )
        self.client.login(username=self.owner.username, password='password')
        resp = self.client.post(create_url, data={}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)


class BoardShareTokenListTests(APITestCase):
    """令牌列表相关测试"""

    def setUp(self):
        super().setUp()
        self.owner = create_user("owner")
        self.other_user = create_user("other")
        self.board = Board.objects.create(
            name="share_list_board",
            submitter=self.owner,
            private=False,
        )
        self.list_url = reverse(
            "board-list-share-tokens",
            kwargs={"pk": self.board.pk},
        )

    def tearDown(self):
        _teardown_share_models()

    def _create_tokens(self, count):
        self.client.login(username=self.owner.username, password='password')
        create_url = reverse(
            "board-create-share-token",
            kwargs={"pk": self.board.pk},
        )
        for i in range(count):
            self.client.post(
                create_url,
                data={"expires_days": 7 if i % 2 == 0 else None},
                format='json',
            )
        self.client.logout()

    def test_owner_can_list_share_tokens(self):
        self._create_tokens(3)
        self.client.login(username=self.owner.username, password='password')
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.json()), 3)

    def test_non_owner_cannot_list_share_tokens(self):
        self._create_tokens(2)
        self.client.login(username=self.other_user.username, password='password')
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, resp.content)

    def test_anonymous_cannot_list_share_tokens(self):
        self._create_tokens(2)
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED, resp.content)

    def test_list_sorted_by_created_at_desc(self):
        self._create_tokens(5)
        self.client.login(username=self.owner.username, password='password')
        resp = self.client.get(self.list_url)
        tokens = resp.json()
        created_times = [t['created_at'] for t in tokens]
        self.assertEqual(created_times, sorted(created_times, reverse=True))


class BoardShareTokenRevokeTests(APITestCase):
    """令牌撤销相关测试"""

    def setUp(self):
        super().setUp()
        self.owner = create_user("owner")
        self.other_user = create_user("other")
        self.board = Board.objects.create(
            name="revoke_test_board",
            submitter=self.owner,
            private=False,
        )
        self.client.login(username=self.owner.username, password='password')
        create_url = reverse(
            "board-create-share-token",
            kwargs={"pk": self.board.pk},
        )
        resp = self.client.post(create_url, data={}, format='json')
        self.share_token_id = resp.json()['id']
        self.share_token_value = resp.json()['token']
        self.client.logout()

    def tearDown(self):
        _teardown_share_models()

    def test_owner_can_revoke_share_token(self):
        self.client.login(username=self.owner.username, password='password')
        revoke_url = reverse(
            "board-revoke-share-token",
            kwargs={"pk": self.board.pk, "token_id": self.share_token_id},
        )
        resp = self.client.post(revoke_url, data={}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        data = resp.json()
        self.assertTrue(data['is_revoked'])
        self.assertFalse(data['is_valid'])
        self.assertIsNotNone(data['revoked_at'])

        token = BoardShareToken.objects.get(pk=self.share_token_id)
        self.assertTrue(token.is_revoked)
        self.assertFalse(token.is_valid)

    def test_cannot_revoke_already_revoked_token(self):
        self.client.login(username=self.owner.username, password='password')
        revoke_url = reverse(
            "board-revoke-share-token",
            kwargs={"pk": self.board.pk, "token_id": self.share_token_id},
        )
        resp = self.client.post(revoke_url, data={}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        resp = self.client.post(revoke_url, data={}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)

    def test_non_owner_cannot_revoke_share_token(self):
        self.client.login(username=self.other_user.username, password='password')
        revoke_url = reverse(
            "board-revoke-share-token",
            kwargs={"pk": self.board.pk, "token_id": self.share_token_id},
        )
        resp = self.client.post(revoke_url, data={}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, resp.content)
        token = BoardShareToken.objects.get(pk=self.share_token_id)
        self.assertFalse(token.is_revoked)

    def test_anonymous_cannot_revoke_share_token(self):
        revoke_url = reverse(
            "board-revoke-share-token",
            kwargs={"pk": self.board.pk, "token_id": self.share_token_id},
        )
        resp = self.client.post(revoke_url, data={}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED, resp.content)

    def test_revoke_token_returns_404_on_invalid_token_id(self):
        self.client.login(username=self.owner.username, password='password')
        revoke_url = reverse(
            "board-revoke-share-token",
            kwargs={"pk": self.board.pk, "token_id": 99999},
        )
        resp = self.client.post(revoke_url, data={}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND, resp.content)


class BoardShareTokenRegenerateTests(APITestCase):
    """令牌更换(regenerate)相关测试"""

    def setUp(self):
        super().setUp()
        self.owner = create_user("owner")
        self.other_user = create_user("other")
        self.board = Board.objects.create(
            name="regenerate_test_board",
            submitter=self.owner,
            private=False,
        )
        self.client.login(username=self.owner.username, password='password')
        create_url = reverse(
            "board-create-share-token",
            kwargs={"pk": self.board.pk},
        )
        resp = self.client.post(create_url, data={}, format='json')
        self.share_token_id = resp.json()['id']
        self.original_token_value = resp.json()['token']
        self.client.logout()

    def tearDown(self):
        _teardown_share_models()

    def test_owner_can_regenerate_share_token(self):
        self.client.login(username=self.owner.username, password='password')
        regenerate_url = reverse(
            "board-regenerate-share-token",
            kwargs={"pk": self.board.pk, "token_id": self.share_token_id},
        )
        resp = self.client.post(regenerate_url, data={}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        data = resp.json()
        self.assertNotEqual(data['token'], self.original_token_value)
        self.assertFalse(data['is_revoked'])
        self.assertTrue(data['is_valid'])
        self.assertIsNone(data['revoked_at'])
        self.assertEqual(data['access_count'], 0)
        self.assertIsNone(data['last_accessed_at'])

    def test_regenerate_with_new_expiry(self):
        self.client.login(username=self.owner.username, password='password')
        regenerate_url = reverse(
            "board-regenerate-share-token",
            kwargs={"pk": self.board.pk, "token_id": self.share_token_id},
        )
        resp = self.client.post(
            regenerate_url,
            data={"expires_days": 30},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        token = BoardShareToken.objects.get(pk=self.share_token_id)
        self.assertIsNotNone(token.expires_at)
        expected = token.created_at + timedelta(days=30)
        self.assertAlmostEqual(
            token.expires_at.timestamp(),
            expected.timestamp(),
            delta=2,
        )

    def test_regenerate_clears_revoke_status(self):
        self.client.login(username=self.owner.username, password='password')
        revoke_url = reverse(
            "board-revoke-share-token",
            kwargs={"pk": self.board.pk, "token_id": self.share_token_id},
        )
        self.client.post(revoke_url, data={}, format='json')

        regenerate_url = reverse(
            "board-regenerate-share-token",
            kwargs={"pk": self.board.pk, "token_id": self.share_token_id},
        )
        resp = self.client.post(regenerate_url, data={}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        data = resp.json()
        self.assertFalse(data['is_revoked'])
        self.assertTrue(data['is_valid'])

    def test_non_owner_cannot_regenerate_share_token(self):
        self.client.login(username=self.other_user.username, password='password')
        regenerate_url = reverse(
            "board-regenerate-share-token",
            kwargs={"pk": self.board.pk, "token_id": self.share_token_id},
        )
        resp = self.client.post(regenerate_url, data={}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, resp.content)
        token = BoardShareToken.objects.get(pk=self.share_token_id)
        self.assertEqual(token.token, self.original_token_value)


class BoardShareTokenExpiryTests(APITestCase):
    """令牌过期相关测试"""

    def setUp(self):
        super().setUp()
        self.owner = create_user("owner")
        self.board = Board.objects.create(
            name="expiry_test_board",
            submitter=self.owner,
            private=False,
        )
        self.client.login(username=self.owner.username, password='password')
        create_url = reverse(
            "board-create-share-token",
            kwargs={"pk": self.board.pk},
        )
        resp = self.client.post(
            create_url,
            data={"expires_days": 1},
            format='json',
        )
        self.share_token_id = resp.json()['id']
        self.share_token_value = resp.json()['token']
        self.client.logout()

    def tearDown(self):
        _teardown_share_models()

    def test_token_is_valid_before_expiry(self):
        token = BoardShareToken.objects.get(pk=self.share_token_id)
        self.assertTrue(token.is_valid)

    def test_token_is_invalid_after_expiry(self):
        token = BoardShareToken.objects.get(pk=self.share_token_id)
        with mock.patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = token.expires_at + timedelta(minutes=1)
            self.assertFalse(token.is_valid)

    def test_anonymous_access_returns_404_for_expired_token(self):
        token = BoardShareToken.objects.get(pk=self.share_token_id)
        with mock.patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = token.expires_at + timedelta(minutes=1)
            share_url = reverse(
                "board-share-detail",
                kwargs={"token": self.share_token_value},
            )
            resp = self.client.get(share_url)
            self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND, resp.content)


class AnonymousShareAccessTests(APITestCase):
    """匿名访问接口核心测试 - 字段裁剪和私有Pin过滤"""

    def setUp(self):
        super().setUp()
        self.owner = create_user("owner")
        self.board = Board.objects.create(
            name="anon_test_board",
            submitter=self.owner,
            private=False,
        )
        self.private_board = Board.objects.create(
            name="anon_private_board",
            submitter=self.owner,
            private=True,
        )

        image = create_image()
        self.public_pin = create_pin(self.owner, image=image, tags=[])
        self.public_pin.description = "Public Pin Description"
        self.public_pin.private = False
        self.public_pin.save()
        self.board.pins.add(self.public_pin)
        self.private_board.pins.add(self.public_pin)

        self.private_pin = create_pin(self.owner, image=image, tags=[])
        self.private_pin.description = "Private Pin Description"
        self.private_pin.private = True
        self.private_pin.save()
        self.board.pins.add(self.private_pin)
        self.private_board.pins.add(self.private_pin)

        self.client.login(username=self.owner.username, password='password')
        create_url = reverse(
            "board-create-share-token",
            kwargs={"pk": self.board.pk},
        )
        resp = self.client.post(create_url, data={}, format='json')
        self.share_token = resp.json()['token']

        private_create_url = reverse(
            "board-create-share-token",
            kwargs={"pk": self.private_board.pk},
        )
        resp = self.client.post(private_create_url, data={}, format='json')
        self.private_board_share_token = resp.json()['token']
        self.client.logout()

    def tearDown(self):
        _teardown_share_models()

    def test_anonymous_access_share_board_with_public_pin(self):
        url = reverse(
            "board-share-detail",
            kwargs={"token": self.share_token},
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        data = resp.json()
        self.assertIn('board', data)
        self.assertIn('pins', data)
        self.assertIn('share_info', data)

    def test_anonymous_access_board_field_censorship(self):
        url = reverse(
            "board-share-detail",
            kwargs={"token": self.share_token},
        )
        resp = self.client.get(url)
        board_data = resp.json()['board']
        allowed_fields = {
            'id', 'name', 'total_pins', 'cover', 'published', 'submitter_username',
            'resource_link',
        }
        self.assertTrue(
            set(board_data.keys()).issubset(allowed_fields),
            f"Unexpected fields: {set(board_data.keys()) - allowed_fields}",
        )
        self.assertNotIn('submitter', board_data)
        self.assertNotIn('private', board_data)
        self.assertNotIn('pins', board_data)
        self.assertNotIn('pins_to_add', board_data)
        self.assertEqual(board_data['submitter_username'], self.owner.username)

    def test_anonymous_access_private_pin_is_filtered(self):
        url = reverse(
            "board-share-detail",
            kwargs={"token": self.share_token},
        )
        resp = self.client.get(url)
        pins = resp.json()['pins']['results']
        pin_ids = [p['id'] for p in pins]
        self.assertIn(self.public_pin.id, pin_ids)
        self.assertNotIn(self.private_pin.id, pin_ids)
        self.assertEqual(resp.json()['pins']['count'], 1)
        self.assertEqual(resp.json()['board']['total_pins'], 1)

    def test_anonymous_access_private_board_still_filters_private_pins(self):
        url = reverse(
            "board-share-detail",
            kwargs={"token": self.private_board_share_token},
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        pins = resp.json()['pins']['results']
        pin_ids = [p['id'] for p in pins]
        self.assertIn(self.public_pin.id, pin_ids)
        self.assertNotIn(self.private_pin.id, pin_ids)

    def test_anonymous_access_pin_field_censorship(self):
        url = reverse(
            "board-share-detail",
            kwargs={"token": self.share_token},
        )
        resp = self.client.get(url)
        pins = resp.json()['pins']['results']
        self.assertEqual(len(pins), 1)
        pin_data = pins[0]
        allowed_fields = {
            'url', 'id', 'description', 'image', 'tags', 'published',
            'submitter_username', 'resource_link',
        }
        actual_fields = set(pin_data.keys())
        self.assertTrue(
            actual_fields.issubset(allowed_fields),
            f"Unexpected fields exposed: {actual_fields - allowed_fields}",
        )
        self.assertNotIn('submitter', pin_data)
        self.assertNotIn('private', pin_data)
        self.assertNotIn('referer', pin_data)
        self.assertNotIn('image_by_id', pin_data)
        self.assertEqual(pin_data['submitter_username'], self.owner.username)

    def test_anonymous_access_invalid_token_returns_404(self):
        url = reverse(
            "board-share-detail",
            kwargs={"token": "definitely-not-a-valid-token-12345"},
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND, resp.content)

    def test_anonymous_access_pins_separate_endpoint(self):
        url = reverse(
            "board-share-list-pins",
            kwargs={"token": self.share_token},
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        data = resp.json()
        self.assertIn('count', data)
        self.assertIn('results', data)
        self.assertEqual(data['count'], 1)
        self.assertEqual(len(data['results']), 1)

        pin_data = data['results'][0]
        self.assertNotIn('submitter', pin_data)
        self.assertNotIn('private', pin_data)
        self.assertNotIn('referer', pin_data)

    def test_access_count_increments(self):
        token = BoardShareToken.objects.get(token=self.share_token)
        initial_count = token.access_count
        url = reverse(
            "board-share-detail",
            kwargs={"token": self.share_token},
        )
        for _ in range(5):
            self.client.get(url)
        token.refresh_from_db()
        self.assertEqual(token.access_count, initial_count + 5)
        self.assertIsNotNone(token.last_accessed_at)

    def test_pins_endpoint_pagination(self):
        image = create_image()
        for i in range(35):
            pin = create_pin(self.owner, image=image, tags=[])
            pin.private = False
            pin.save()
            self.board.pins.add(pin)

        url = reverse(
            "board-share-list-pins",
            kwargs={"token": self.share_token},
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        data = resp.json()
        self.assertEqual(len(data['results']), 30)
        self.assertIsNotNone(data['next'])

        resp2 = self.client.get(url + "?limit=10&offset=5")
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp2.json()['results']), 10)


class ShareTokenRevokeImmediateEffectTests(APITestCase):
    """撤销立即生效的核心边界条件测试"""

    def setUp(self):
        super().setUp()
        self.owner = create_user("owner")
        self.board = Board.objects.create(
            name="revoke_effect_board",
            submitter=self.owner,
            private=False,
        )
        image = create_image()
        pin = create_pin(self.owner, image=image, tags=[])
        pin.private = False
        pin.save()
        self.board.pins.add(pin)

        self.client.login(username=self.owner.username, password='password')
        create_url = reverse(
            "board-create-share-token",
            kwargs={"pk": self.board.pk},
        )
        resp = self.client.post(create_url, data={}, format='json')
        self.share_token_id = resp.json()['id']
        self.share_token_value = resp.json()['token']

    def tearDown(self):
        _teardown_share_models()

    def test_revoked_token_immediately_unaccessible(self):
        self.client.logout()
        share_detail_url = reverse(
            "board-share-detail",
            kwargs={"token": self.share_token_value},
        )
        resp_before = self.client.get(share_detail_url)
        self.assertEqual(resp_before.status_code, status.HTTP_200_OK)

        self.client.login(username=self.owner.username, password='password')
        revoke_url = reverse(
            "board-revoke-share-token",
            kwargs={"pk": self.board.pk, "token_id": self.share_token_id},
        )
        self.client.post(revoke_url, data={}, format='json')
        self.client.logout()

        resp_after = self.client.get(share_detail_url)
        self.assertEqual(resp_after.status_code, status.HTTP_404_NOT_FOUND, resp_after.content)

        pins_url = reverse(
            "board-share-list-pins",
            kwargs={"token": self.share_token_value},
        )
        resp_pins = self.client.get(pins_url)
        self.assertEqual(resp_pins.status_code, status.HTTP_404_NOT_FOUND, resp_pins.content)

    def test_regenerated_token_old_value_immediately_unaccessible(self):
        self.client.logout()
        share_detail_url = reverse(
            "board-share-detail",
            kwargs={"token": self.share_token_value},
        )
        resp_before = self.client.get(share_detail_url)
        self.assertEqual(resp_before.status_code, status.HTTP_200_OK)

        self.client.login(username=self.owner.username, password='password')
        regenerate_url = reverse(
            "board-regenerate-share-token",
            kwargs={"pk": self.board.pk, "token_id": self.share_token_id},
        )
        new_resp = self.client.post(regenerate_url, data={}, format='json')
        new_token_value = new_resp.json()['token']
        self.client.logout()

        resp_old = self.client.get(share_detail_url)
        self.assertEqual(resp_old.status_code, status.HTTP_404_NOT_FOUND, resp_old.content)

        new_share_url = reverse(
            "board-share-detail",
            kwargs={"token": new_token_value},
        )
        resp_new = self.client.get(new_share_url)
        self.assertEqual(resp_new.status_code, status.HTTP_200_OK, resp_new.content)


class ShareBoardDeletionCascadeTests(APITestCase):
    """Board 删除时分享 Token 级联删除测试"""

    def setUp(self):
        super().setUp()
        self.owner = create_user("owner")
        self.board = Board.objects.create(
            name="cascade_test_board",
            submitter=self.owner,
            private=False,
        )
        self.client.login(username=self.owner.username, password='password')
        create_url = reverse(
            "board-create-share-token",
            kwargs={"pk": self.board.pk},
        )
        for _ in range(5):
            self.client.post(create_url, data={}, format='json')
        self.client.logout()

    def tearDown(self):
        _teardown_share_models()

    def test_deleting_board_cascades_to_share_tokens(self):
        self.assertEqual(BoardShareToken.objects.filter(board=self.board).count(), 5)
        self.board.delete()
        self.assertEqual(BoardShareToken.objects.filter(board=self.board).count(), 0)

    def test_deleted_board_token_returns_404(self):
        tokens = list(BoardShareToken.objects.filter(board=self.board).values_list('token', flat=True))
        self.board.delete()
        for token_value in tokens:
            url = reverse("board-share-detail", kwargs={"token": token_value})
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND, resp.content)


class ShareTokenCoverageEdgeCases(APITestCase):
    """额外边界条件覆盖"""

    def setUp(self):
        super().setUp()
        self.owner = create_user("owner")
        self.board = Board.objects.create(
            name="edge_board",
            submitter=self.owner,
            private=False,
        )

    def tearDown(self):
        _teardown_share_models()

    def test_empty_board_share_no_crash(self):
        self.client.login(username=self.owner.username, password='password')
        create_url = reverse(
            "board-create-share-token",
            kwargs={"pk": self.board.pk},
        )
        resp = self.client.post(create_url, data={}, format='json')
        token_value = resp.json()['token']
        self.client.logout()

        share_url = reverse("board-share-detail", kwargs={"token": token_value})
        resp = self.client.get(share_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        data = resp.json()
        self.assertEqual(data['board']['total_pins'], 0)
        self.assertIsNone(data['board']['cover'])
        self.assertEqual(data['pins']['count'], 0)
        self.assertEqual(len(data['pins']['results']), 0)

    def test_pins_limit_parameter_max_100(self):
        image = create_image()
        for i in range(150):
            pin = create_pin(self.owner, image=image, tags=[])
            pin.private = False
            pin.save()
            self.board.pins.add(pin)

        self.client.login(username=self.owner.username, password='password')
        create_url = reverse(
            "board-create-share-token",
            kwargs={"pk": self.board.pk},
        )
        resp = self.client.post(create_url, data={}, format='json')
        token_value = resp.json()['token']
        self.client.logout()

        pins_url = reverse(
            "board-share-list-pins",
            kwargs={"token": token_value},
        )
        resp = self.client.get(pins_url + "?limit=200")
        self.assertEqual(len(resp.json()['results']), 100)

    def test_regenerate_uses_valid_expiry_range(self):
        self.client.login(username=self.owner.username, password='password')
        create_url = reverse(
            "board-create-share-token",
            kwargs={"pk": self.board.pk},
        )
        resp = self.client.post(create_url, data={}, format='json')
        token_id = resp.json()['id']

        regenerate_url = reverse(
            "board-regenerate-share-token",
            kwargs={"pk": self.board.pk, "token_id": token_id},
        )
        resp = self.client.post(
            regenerate_url,
            data={"expires_days": -5},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)

        resp = self.client.post(
            regenerate_url,
            data={"expires_days": 500},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
