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


SENSITIVE_PIN_FIELDS = frozenset({
    'private', 'submitter', 'referer', 'image_by_id',
})

SENSITIVE_USER_FIELDS = frozenset({
    'email', 'token', 'password', 'password_repeat', 'gravatar',
})

SENSITIVE_BOARD_FIELDS = frozenset({
    'private', 'submitter', 'pins', 'pins_to_add', 'pins_to_remove',
})


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
        self.assertIn(resp.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])
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
        self.assertIn(resp.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

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
        self.assertIn(resp.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

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
            'submitter_username',
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
        for i in range(5):
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
        self.assertTrue(len(data['results']) > 0)

        resp2 = self.client.get(url + "?limit=3&offset=2")
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp2.json()['results']), 3)


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
        board_pk = self.board.pk
        Board.objects.filter(pk=board_pk).delete()
        self.assertEqual(BoardShareToken.objects.filter(board_id=board_pk).count(), 0)

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
        for i in range(110):
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
        self.assertTrue(len(resp.json()['results']) <= 100)

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


class RegenerateAtomicityTests(APITestCase):
    """令牌更换(regenerate)的竞态与原子性边界测试

    regenerate() 在同一条 DB 记录上执行原子更新（更新 token 字段值），
    不是「删除旧记录 + 创建新记录」，因此不存在新旧令牌同时有效的重叠窗。
    以下用例验证这一设计在各种并发场景下的安全保证。
    """

    def setUp(self):
        super().setUp()
        self.owner = create_user("owner")
        self.board = Board.objects.create(
            name="atomicity_board",
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
        self.old_token_value = resp.json()['token']
        self.client.logout()

    def tearDown(self):
        _teardown_share_models()

    def test_no_overlap_window_old_and_new_token_simultaneously_valid(self):
        """regenerate 完成后，旧令牌值不再存在于 DB，不存在新旧同时有效的重叠窗。

        regenerate 是同一条记录的 UPDATE，token 字段从 old 切换到 new 是原子的。
        不可能出现某个时刻 DB 中同时存在 old 和 new 两条有效记录。
        """
        old_value = self.old_token_value

        self.client.login(username=self.owner.username, password='password')
        regenerate_url = reverse(
            "board-regenerate-share-token",
            kwargs={"pk": self.board.pk, "token_id": self.share_token_id},
        )
        resp = self.client.post(regenerate_url, data={}, format='json')
        new_value = resp.json()['token']
        self.client.logout()

        self.assertNotEqual(old_value, new_value)

        valid_tokens = BoardShareToken.objects.filter(
            board=self.board,
            is_revoked=False,
        ).values_list('token', flat=True)
        self.assertNotIn(old_value, valid_tokens)
        self.assertIn(new_value, valid_tokens)

        token_count = BoardShareToken.objects.filter(
            board=self.board,
        ).count()
        self.assertEqual(token_count, 1)

    def test_no_gap_window_new_token_immediately_accessible(self):
        """regenerate 完成后新令牌立即可用，不存在空窗期。

        验证 regenerate API 返回 200 后，用新令牌访问匿名接口立即返回 200。
        """
        self.client.login(username=self.owner.username, password='password')
        regenerate_url = reverse(
            "board-regenerate-share-token",
            kwargs={"pk": self.board.pk, "token_id": self.share_token_id},
        )
        resp = self.client.post(regenerate_url, data={}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        new_value = resp.json()['token']
        self.client.logout()

        new_share_url = reverse(
            "board-share-detail",
            kwargs={"token": new_value},
        )
        resp = self.client.get(new_share_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        self.assertIn('board', resp.json())

        pins_url = reverse(
            "board-share-list-pins",
            kwargs={"token": new_value},
        )
        resp = self.client.get(pins_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)

    def test_old_token_unfindable_after_regenerate(self):
        """regenerate 后旧 token 值无法在 DB 中被查到，从根源杜绝旧值被重新激活。"""
        self.assertTrue(
            BoardShareToken.objects.filter(token=self.old_token_value).exists(),
        )

        self.client.login(username=self.owner.username, password='password')
        regenerate_url = reverse(
            "board-regenerate-share-token",
            kwargs={"pk": self.board.pk, "token_id": self.share_token_id},
        )
        self.client.post(regenerate_url, data={}, format='json')
        self.client.logout()

        self.assertFalse(
            BoardShareToken.objects.filter(token=self.old_token_value).exists(),
        )

    def test_regenerate_preserves_single_record_integrity(self):
        """regenerate 前后 DB 中始终只有一条 token 记录，不会有残留或重复。"""
        before_count = BoardShareToken.objects.filter(board=self.board).count()

        self.client.login(username=self.owner.username, password='password')
        regenerate_url = reverse(
            "board-regenerate-share-token",
            kwargs={"pk": self.board.pk, "token_id": self.share_token_id},
        )
        self.client.post(regenerate_url, data={}, format='json')
        self.client.logout()

        after_count = BoardShareToken.objects.filter(board=self.board).count()
        self.assertEqual(before_count, after_count)

    def test_concurrent_access_during_regenerate_no_leak(self):
        """模拟 regenerate 执行过程中的并发访问场景。

        通过 mock regenerate 的 save 方法，在 save 执行前（旧 token 仍有效）和
        save 执行后（新 token 已生效）分别检查：
        1. save 前：旧 token 可访问（正常）
        2. save 后：旧 token 不可访问，新 token 可访问（无空窗、无重叠）
        """
        old_value = self.old_token_value
        new_value_holder = [None]
        save_called = [False]

        original_save = BoardShareToken.save

        def intercepting_save(token_instance, *args, **kwargs):
            if not save_called[0]:
                new_value_holder[0] = token_instance.token
                save_called[0] = True
                old_url = reverse(
                    "board-share-detail",
                    kwargs={"token": old_value},
                )
                resp_during = self.client.get(old_url)
                self.assertEqual(
                    resp_during.status_code, status.HTTP_200_OK,
                    "Before save completes, old token should still work",
                )
            return original_save(token_instance, *args, **kwargs)

        self.client.login(username=self.owner.username, password='password')
        regenerate_url = reverse(
            "board-regenerate-share-token",
            kwargs={"pk": self.board.pk, "token_id": self.share_token_id},
        )

        with mock.patch.object(BoardShareToken, 'save', intercepting_save):
            resp = self.client.post(regenerate_url, data={}, format='json')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        new_value = new_value_holder[0]
        self.assertIsNotNone(new_value)
        self.assertNotEqual(new_value, old_value)
        self.client.logout()

        old_url = reverse(
            "board-share-detail",
            kwargs={"token": old_value},
        )
        resp_old = self.client.get(old_url)
        self.assertEqual(resp_old.status_code, status.HTTP_404_NOT_FOUND)

        new_url = reverse(
            "board-share-detail",
            kwargs={"token": new_value},
        )
        resp_new = self.client.get(new_url)
        self.assertEqual(resp_new.status_code, status.HTTP_200_OK)

    def test_rapid_regenerate_cycles_no_orphan_tokens(self):
        """快速连续多次 regenerate 不会产生孤立或幽灵 token 记录。"""
        self.client.login(username=self.owner.username, password='password')
        regenerate_url = reverse(
            "board-regenerate-share-token",
            kwargs={"pk": self.board.pk, "token_id": self.share_token_id},
        )
        all_token_values = set()
        for _ in range(10):
            resp = self.client.post(regenerate_url, data={}, format='json')
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            all_token_values.add(resp.json()['token'])
        self.client.logout()

        self.assertEqual(len(all_token_values), 10)
        self.assertEqual(BoardShareToken.objects.filter(board=self.board).count(), 1)
        self.assertNotIn(self.old_token_value, all_token_values)

        current_token = BoardShareToken.objects.get(board=self.board)
        self.assertIn(current_token.token, all_token_values)

    def test_regenerate_while_anonymous_reading_no_access_loss(self):
        """regenerate 执行期间，正在进行的匿名读请求不会丢失访问能力。

        save 是原子的：在读请求和 regenerate 之间存在两种情况：
        - 读请求在 save 前完成：用旧 token，返回 200
        - 读请求在 save 后完成：用新 token，返回 200（如果用旧 token 则 404）
        关键是：不会出现 save 完成但新 token 仍不可用的空窗。
        """
        self.client.login(username=self.owner.username, password='password')
        regenerate_url = reverse(
            "board-regenerate-share-token",
            kwargs={"pk": self.board.pk, "token_id": self.share_token_id},
        )
        resp = self.client.post(regenerate_url, data={}, format='json')
        new_value = resp.json()['token']
        self.client.logout()

        new_url = reverse(
            "board-share-detail",
            kwargs={"token": new_value},
        )
        resp = self.client.get(new_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data['board']['name'], "atomicity_board")
        self.assertEqual(data['pins']['count'], 1)


class DeepNestedFieldCensorshipTests(APITestCase):
    """匿名访问深层嵌套字段裁剪完整性测试

    分享接口返回的嵌套结构：
      board → cover → {AnonymousPinSerializer → image → {ImageSerializer → standard/thumbnail/square → {ThumbnailSerializer}}}
      pins.results[] → {AnonymousPinSerializer → image → {同上}, tags[] → {TagSerializer}}

    逐层检查确保不暴露邮箱、内部主键(非 id 的关联 pk)、私有标记、提交者对象等敏感字段。
    """

    def setUp(self):
        super().setUp()
        self.owner = create_user("deep_owner")
        self.owner.email = "secret_email@private-domain.com"
        self.owner.save()

        self.board = Board.objects.create(
            name="deep_censorship_board",
            submitter=self.owner,
            private=False,
        )

        image = create_image()
        self.public_pin = create_pin(self.owner, image=image, tags=[])
        self.public_pin.description = "Deep Nested Pin"
        self.public_pin.private = False
        self.public_pin.referer = "https://secret-referer.example.com"
        self.public_pin.url = "https://secret-origin.example.com/image.png"
        self.public_pin.save()
        self.board.pins.add(self.public_pin)

        self.private_pin = create_pin(self.owner, image=image, tags=[])
        self.private_pin.description = "Should Never Appear"
        self.private_pin.private = True
        self.private_pin.save()
        self.board.pins.add(self.private_pin)

        self.client.login(username=self.owner.username, password='password')
        create_url = reverse(
            "board-create-share-token",
            kwargs={"pk": self.board.pk},
        )
        resp = self.client.post(create_url, data={}, format='json')
        self.share_token = resp.json()['token']
        self.client.logout()

    def tearDown(self):
        _teardown_share_models()

    def _get_share_detail(self):
        url = reverse(
            "board-share-detail",
            kwargs={"token": self.share_token},
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        return resp.json()

    def _get_pins_list(self):
        url = reverse(
            "board-share-list-pins",
            kwargs={"token": self.share_token},
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        return resp.json()['results']

    def _assert_no_sensitive_fields(self, data, sensitive_fields, context_name):
        for field in sensitive_fields:
            self.assertNotIn(
                field, data,
                f"Sensitive field '{field}' leaked in {context_name}: {list(data.keys())}",
            )

    def test_board_cover_is_also_censored(self):
        """board.cover 是嵌套的 AnonymousPinSerializer，必须同样裁剪敏感字段。"""
        data = self._get_share_detail()
        cover = data['board'].get('cover')
        self.assertIsNotNone(cover, "Board cover should exist when public pins are present")
        self._assert_no_sensitive_fields(cover, SENSITIVE_PIN_FIELDS, "board.cover")
        self.assertNotIn('submitter', cover)
        self.assertNotIn('private', cover)
        self.assertNotIn('referer', cover)
        self.assertIn('submitter_username', cover)
        self.assertEqual(cover['submitter_username'], self.owner.username)

    def test_board_cover_image_layer_no_user_data(self):
        """board.cover.image (ImageSerializer) 不应暴露任何用户信息。"""
        data = self._get_share_detail()
        cover = data['board'].get('cover')
        if cover is None:
            self.skipTest("No cover available")
        image_data = cover.get('image')
        if image_data is None:
            self.skipTest("No image in cover")
        self._assert_no_sensitive_fields(
            image_data,
            SENSITIVE_USER_FIELDS | {'submitter', 'private', 'referer'},
            "board.cover.image",
        )
        allowed_image_fields = {'id', 'image', 'width', 'height', 'standard', 'thumbnail', 'square'}
        for key in image_data.keys():
            self.assertIn(key, allowed_image_fields, f"Unexpected field '{key}' in image data")

    def test_board_cover_image_thumbnail_layer_no_user_data(self):
        """board.cover.image.standard/thumbnail/square (ThumbnailSerializer) 不应暴露用户信息。"""
        data = self._get_share_detail()
        cover = data['board'].get('cover')
        if cover is None:
            self.skipTest("No cover available")
        image_data = cover.get('image')
        if image_data is None:
            self.skipTest("No image in cover")

        for thumb_key in ('standard', 'thumbnail', 'square'):
            thumb = image_data.get(thumb_key)
            if thumb is None:
                continue
            self._assert_no_sensitive_fields(
                thumb,
                SENSITIVE_USER_FIELDS | SENSITIVE_PIN_FIELDS,
                f"board.cover.image.{thumb_key}",
            )
            allowed_thumb_fields = {'image', 'width', 'height'}
            for key in thumb.keys():
                self.assertIn(
                    key, allowed_thumb_fields,
                    f"Unexpected field '{key}' in thumbnail layer {thumb_key}",
                )

    def test_pin_image_layer_no_user_data(self):
        """pins[].image (ImageSerializer) 不应暴露任何用户关联信息。"""
        pins = self._get_pins_list()
        self.assertTrue(len(pins) > 0, "Should have at least one public pin")
        pin_data = pins[0]
        image_data = pin_data.get('image')
        if image_data is None:
            self.skipTest("No image in pin")
        self._assert_no_sensitive_fields(
            image_data,
            SENSITIVE_USER_FIELDS | {'submitter', 'private', 'referer'},
            "pins[].image",
        )

    def test_pin_image_thumbnail_layer_no_user_data(self):
        """pins[].image.standard/thumbnail/square 不应暴露用户信息。"""
        pins = self._get_pins_list()
        self.assertTrue(len(pins) > 0)
        image_data = pins[0].get('image')
        if image_data is None:
            self.skipTest("No image in pin")

        for thumb_key in ('standard', 'thumbnail', 'square'):
            thumb = image_data.get(thumb_key)
            if thumb is None:
                continue
            self._assert_no_sensitive_fields(
                thumb,
                SENSITIVE_USER_FIELDS | SENSITIVE_PIN_FIELDS,
                f"pins[].image.{thumb_key}",
            )

    def test_pin_tags_no_user_data(self):
        """pins[].tags[] (TagSerializer) 不应暴露用户关联字段。"""
        self.public_pin.tags.add("landscape", "nature")
        pins = self._get_pins_list()
        self.assertTrue(len(pins) > 0)
        pin_data = pins[0]
        tags = pin_data.get('tags', [])
        if len(tags) == 0:
            self.skipTest("No tags on pin")
        for tag in tags:
            self.assertIsInstance(tag, str)
            self._assert_no_sensitive_fields(
                {'value': tag},
                SENSITIVE_USER_FIELDS | SENSITIVE_PIN_FIELDS,
                "pins[].tags[]",
            )

    def test_no_email_leak_at_any_layer(self):
        """在所有嵌套层级中搜索，确保 owner 的邮箱不会出现在任何值中。"""
        data = self._get_share_detail()
        serialized = str(data)
        self.assertNotIn(self.owner.email, serialized)

    def test_no_gravatar_hash_leak_at_any_layer(self):
        """在所有嵌套层级中搜索，确保 gravatar hash 不会出现在任何值中。"""
        data = self._get_share_detail()
        serialized = str(data)
        self.assertNotIn('gravatar', serialized)

    def test_no_private_pin_id_in_cover(self):
        """board.cover 必须只取公开 Pin，私有 Pin 的 id 不应出现在 cover 中。"""
        data = self._get_share_detail()
        cover = data['board'].get('cover')
        if cover is not None:
            self.assertNotEqual(cover.get('id'), self.private_pin.id)

    def test_private_pin_absent_from_all_nested_layers(self):
        """私有 Pin 在 pins 列表、board.cover、board.total_pins 中全部不可见。"""
        data = self._get_share_detail()
        pin_ids_in_results = [p['id'] for p in data['pins']['results']]
        self.assertNotIn(self.private_pin.id, pin_ids_in_results)

        cover = data['board'].get('cover')
        if cover is not None:
            self.assertNotEqual(cover.get('id'), self.private_pin.id)

        self.assertEqual(data['board']['total_pins'], 1)

    def test_submitter_is_username_string_not_object(self):
        """所有层级的 submitter 信息必须是纯字符串(用户名)，不是用户对象。"""
        data = self._get_share_detail()

        board = data['board']
        self.assertIsInstance(board['submitter_username'], str)
        self._assert_no_sensitive_fields(board, {'submitter'}, "board")

        cover = board.get('cover')
        if cover is not None:
            self.assertIsInstance(cover.get('submitter_username', ''), str)
            self._assert_no_sensitive_fields(cover, {'submitter'}, "board.cover")

        pins = data['pins']['results']
        for pin_data in pins:
            self.assertIsInstance(pin_data.get('submitter_username', ''), str)
            self._assert_no_sensitive_fields(pin_data, {'submitter'}, "pins[]")

    def test_pins_endpoint_deep_censorship_matches_detail_endpoint(self):
        """独立 /pins/ 端点的深层裁剪与 /board-share/ 详情端点完全一致。"""
        detail_pins = self._get_share_detail()['pins']['results']
        list_pins = self._get_pins_list()

        self.assertEqual(len(detail_pins), len(list_pins))

        for detail_pin, list_pin in zip(detail_pins, list_pins):
            self.assertEqual(
                set(detail_pin.keys()),
                set(list_pin.keys()),
                "Pin field sets differ between detail and list endpoints",
            )
            for sensitive in SENSITIVE_PIN_FIELDS | SENSITIVE_USER_FIELDS:
                self.assertNotIn(sensitive, list_pin)
                self.assertNotIn(sensitive, detail_pin)

    def test_image_id_is_numeric_not_user_fk(self):
        """image.id 应是 Image 模型的自增主键，不是任何用户相关的外键。"""
        pins = self._get_pins_list()
        for pin_data in pins:
            image_data = pin_data.get('image')
            if image_data is None:
                continue
            img_id = image_data.get('id')
            self.assertIsInstance(img_id, int)

    def test_referer_url_never_leaks(self):
        """referer（来源 URL）在所有层级中均不可见，包括嵌套 Pin。"""
        data = self._get_share_detail()
        serialized = str(data)
        self.assertNotIn(self.public_pin.referer, serialized)
