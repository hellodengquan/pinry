import os

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.contrib.auth.models import AnonymousUser

from core.models import Pin, Board, Image
from core.visibility import VisibilityPolicy
from core.tests.helpers import create_user


def _create_image():
    img_path = os.path.join(
        os.path.dirname(__file__), '..', '..', 'docs', 'src', 'imgs', 'logo-dark.png'
    )
    with open(img_path, 'rb') as f:
        return Image.objects.create(image=SimpleUploadedFile('test.png', f.read()))


class VisibilityPolicyFilterVisibleTest(TestCase):
    def setUp(self):
        self.owner = create_user("owner")
        self.other = create_user("other")
        self.anon = AnonymousUser()

    def _create_pin(self, user, private=False):
        image = _create_image()
        return Pin.objects.create(submitter=user, image=image, private=private)

    def _create_board(self, user, private=False):
        return Board.objects.create(
            name=f"board_{user.id}_{private}", submitter=user, private=private
        )

    def test_anonymous_cannot_see_private_pin(self):
        self._create_pin(self.owner, private=True)
        qs = VisibilityPolicy.filter_visible(Pin.objects.all(), self.anon)
        self.assertEqual(qs.count(), 0)

    def test_anonymous_can_see_public_pin(self):
        self._create_pin(self.owner, private=False)
        qs = VisibilityPolicy.filter_visible(Pin.objects.all(), self.anon)
        self.assertEqual(qs.count(), 1)

    def test_owner_can_see_own_private_pin(self):
        self._create_pin(self.owner, private=True)
        qs = VisibilityPolicy.filter_visible(Pin.objects.all(), self.owner)
        self.assertEqual(qs.count(), 1)

    def test_other_user_cannot_see_private_pin(self):
        self._create_pin(self.owner, private=True)
        qs = VisibilityPolicy.filter_visible(Pin.objects.all(), self.other)
        self.assertEqual(qs.count(), 0)

    def test_other_user_can_see_public_pin(self):
        self._create_pin(self.owner, private=False)
        qs = VisibilityPolicy.filter_visible(Pin.objects.all(), self.other)
        self.assertEqual(qs.count(), 1)

    def test_mixed_pins_authenticated_user(self):
        self._create_pin(self.owner, private=True)
        self._create_pin(self.owner, private=False)
        self._create_pin(self.other, private=True)
        qs = VisibilityPolicy.filter_visible(Pin.objects.all(), self.owner)
        self.assertEqual(qs.count(), 2)

    def test_mixed_pins_anonymous(self):
        self._create_pin(self.owner, private=True)
        self._create_pin(self.owner, private=False)
        qs = VisibilityPolicy.filter_visible(Pin.objects.all(), self.anon)
        self.assertEqual(qs.count(), 1)

    def test_anonymous_cannot_see_private_board(self):
        self._create_board(self.owner, private=True)
        qs = VisibilityPolicy.filter_visible(Board.objects.all(), self.anon)
        self.assertEqual(qs.count(), 0)

    def test_anonymous_can_see_public_board(self):
        self._create_board(self.owner, private=False)
        qs = VisibilityPolicy.filter_visible(Board.objects.all(), self.anon)
        self.assertEqual(qs.count(), 1)

    def test_owner_can_see_own_private_board(self):
        self._create_board(self.owner, private=True)
        qs = VisibilityPolicy.filter_visible(Board.objects.all(), self.owner)
        self.assertEqual(qs.count(), 1)

    def test_other_user_cannot_see_private_board(self):
        self._create_board(self.owner, private=True)
        qs = VisibilityPolicy.filter_visible(Board.objects.all(), self.other)
        self.assertEqual(qs.count(), 0)


class VisibilityPolicyCanViewTest(TestCase):
    def setUp(self):
        self.owner = create_user("owner")
        self.other = create_user("other")
        self.anon = AnonymousUser()

    def _create_pin(self, user, private=False):
        image = _create_image()
        return Pin.objects.create(submitter=user, image=image, private=private)

    def _create_board(self, user, private=False):
        return Board.objects.create(
            name=f"board_{user.id}_{private}", submitter=user, private=private
        )

    def test_anonymous_cannot_view_private_object(self):
        pin = self._create_pin(self.owner, private=True)
        self.assertFalse(VisibilityPolicy.can_view(pin, self.anon))

    def test_anonymous_can_view_public_object(self):
        pin = self._create_pin(self.owner, private=False)
        self.assertTrue(VisibilityPolicy.can_view(pin, self.anon))

    def test_owner_can_view_own_private_object(self):
        pin = self._create_pin(self.owner, private=True)
        self.assertTrue(VisibilityPolicy.can_view(pin, self.owner))

    def test_other_user_cannot_view_private_object(self):
        pin = self._create_pin(self.owner, private=True)
        self.assertFalse(VisibilityPolicy.can_view(pin, self.other))

    def test_other_user_can_view_public_object(self):
        pin = self._create_pin(self.owner, private=False)
        self.assertTrue(VisibilityPolicy.can_view(pin, self.other))

    def test_board_anonymous_cannot_view_private(self):
        board = self._create_board(self.owner, private=True)
        self.assertFalse(VisibilityPolicy.can_view(board, self.anon))

    def test_board_owner_can_view_private(self):
        board = self._create_board(self.owner, private=True)
        self.assertTrue(VisibilityPolicy.can_view(board, self.owner))


class VisibilityPolicyCanChangeTest(TestCase):
    def setUp(self):
        self.owner = create_user("owner")
        self.other = create_user("other")
        self.anon = AnonymousUser()

    def _create_pin(self, user, private=False):
        image = _create_image()
        return Pin.objects.create(submitter=user, image=image, private=private)

    def test_anonymous_cannot_change(self):
        pin = self._create_pin(self.owner, private=False)
        self.assertFalse(VisibilityPolicy.can_change(pin, self.anon))

    def test_owner_can_change(self):
        pin = self._create_pin(self.owner, private=False)
        self.assertTrue(VisibilityPolicy.can_change(pin, self.owner))

    def test_other_user_cannot_change(self):
        pin = self._create_pin(self.owner, private=False)
        self.assertFalse(VisibilityPolicy.can_change(pin, self.other))

    def test_owner_can_change_private(self):
        pin = self._create_pin(self.owner, private=True)
        self.assertTrue(VisibilityPolicy.can_change(pin, self.owner))


class VisibilityPolicyCustomOwnerFieldTest(TestCase):
    def setUp(self):
        self.owner = create_user("owner")
        self.other = create_user("other")
        self.anon = AnonymousUser()

    def _create_pin(self, user, private=False):
        image = _create_image()
        return Pin.objects.create(submitter=user, image=image, private=private)

    def test_custom_owner_field_filter_visible(self):
        self._create_pin(self.owner, private=True)
        qs = VisibilityPolicy.filter_visible(
            Pin.objects.all(), self.owner, owner_field="submitter"
        )
        self.assertEqual(qs.count(), 1)

    def test_custom_owner_field_can_view(self):
        pin = self._create_pin(self.owner, private=True)
        self.assertTrue(
            VisibilityPolicy.can_view(pin, self.owner, owner_field="submitter")
        )
        self.assertFalse(
            VisibilityPolicy.can_view(pin, self.other, owner_field="submitter")
        )

    def test_custom_owner_field_can_change(self):
        pin = self._create_pin(self.owner, private=False)
        self.assertTrue(
            VisibilityPolicy.can_change(pin, self.owner, owner_field="submitter")
        )
        self.assertFalse(
            VisibilityPolicy.can_change(pin, self.other, owner_field="submitter")
        )


class VisibilityPolicyIntegrationWithBoardSerializerTest(TestCase):
    def setUp(self):
        self.owner = create_user("owner")
        self.other = create_user("other")

    def _create_pin(self, user, private=False):
        image = _create_image()
        return Pin.objects.create(submitter=user, image=image, private=private)

    def test_get_list_filters_private_pins_of_other_users(self):
        public_pin = self._create_pin(self.other, private=False)
        private_pin = self._create_pin(self.other, private=True)
        own_pin = self._create_pin(self.owner, private=True)
        from core.serializers import BoardSerializer
        valid_pins = BoardSerializer._get_list(
            [public_pin.id, private_pin.id, own_pin.id], self.owner
        )
        valid_ids = [p.id for p in valid_pins]
        self.assertIn(public_pin.id, valid_ids)
        self.assertNotIn(private_pin.id, valid_ids)
        self.assertIn(own_pin.id, valid_ids)

    def test_get_list_allows_all_pins_for_owner(self):
        public_pin = self._create_pin(self.owner, private=False)
        private_pin = self._create_pin(self.owner, private=True)
        from core.serializers import BoardSerializer
        valid_pins = BoardSerializer._get_list(
            [public_pin.id, private_pin.id], self.owner
        )
        self.assertEqual(len(valid_pins), 2)


class VisibilityPolicyIntegrationWithPermissionsTest(TestCase):
    def setUp(self):
        self.owner = create_user("owner")
        self.other = create_user("other")

    def _create_pin(self, user, private=False):
        image = _create_image()
        return Pin.objects.create(submitter=user, image=image, private=private)

    def test_owner_only_if_private_allows_owner_read_private(self):
        from core.permissions import OwnerOnlyIfPrivate
        from rest_framework.test import APIRequestFactory
        pin = self._create_pin(self.owner, private=True)
        factory = APIRequestFactory()
        request = factory.get('/')
        request.user = self.owner
        perm = OwnerOnlyIfPrivate("submitter")()
        self.assertTrue(perm.has_object_permission(request, None, pin))

    def test_owner_only_if_private_denies_other_read_private(self):
        from core.permissions import OwnerOnlyIfPrivate
        from rest_framework.test import APIRequestFactory
        pin = self._create_pin(self.owner, private=True)
        factory = APIRequestFactory()
        request = factory.get('/')
        request.user = self.other
        perm = OwnerOnlyIfPrivate("submitter")()
        self.assertFalse(perm.has_object_permission(request, None, pin))

    def test_owner_only_if_private_allows_other_read_public(self):
        from core.permissions import OwnerOnlyIfPrivate
        from rest_framework.test import APIRequestFactory
        pin = self._create_pin(self.owner, private=False)
        factory = APIRequestFactory()
        request = factory.get('/')
        request.user = self.other
        perm = OwnerOnlyIfPrivate("submitter")()
        self.assertTrue(perm.has_object_permission(request, None, pin))

    def test_is_owner_or_read_only_allows_owner_write(self):
        from core.permissions import IsOwnerOrReadOnly
        from rest_framework.test import APIRequestFactory
        pin = self._create_pin(self.owner, private=False)
        factory = APIRequestFactory()
        request = factory.patch('/')
        request.user = self.owner
        perm = IsOwnerOrReadOnly("submitter")()
        self.assertTrue(perm.has_object_permission(request, None, pin))

    def test_is_owner_or_read_only_denies_other_write(self):
        from core.permissions import IsOwnerOrReadOnly
        from rest_framework.test import APIRequestFactory
        pin = self._create_pin(self.owner, private=False)
        factory = APIRequestFactory()
        request = factory.patch('/')
        request.user = self.other
        perm = IsOwnerOrReadOnly("submitter")()
        self.assertFalse(perm.has_object_permission(request, None, pin))
