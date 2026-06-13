from django.conf import settings
from django.contrib.auth import login
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from users.models import User, UserSettings, create_token_if_necessary


class PublicUserSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = User
        fields = (
            'username',
            'gravatar',
            settings.DRF_URL_FIELD_NAME,
        )
        extra_kwargs = {
            settings.DRF_URL_FIELD_NAME: {
                "view_name": "public-users:user-detail",
            },
        }


class UserSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = User
        fields = (
            'username',
            'token',
            'email',
            'gravatar',
            'password',
            'password_repeat',
            'language',
            settings.DRF_URL_FIELD_NAME,
        )
        extra_kwargs = {
            settings.DRF_URL_FIELD_NAME: {
                "view_name": "users:user-detail",
            },
        }

    password = serializers.CharField(
        write_only=True,
        required=True,
        allow_blank=False,
        min_length=6,
        max_length=32,
    )
    password_repeat = serializers.CharField(
        write_only=True,
        required=True,
        allow_blank=False,
        min_length=6,
        max_length=32,
    )
    token = serializers.SerializerMethodField(read_only=True)
    language = serializers.CharField(source="settings.language", allow_null=True, required=False)

    def create(self, validated_data):
        if validated_data['password'] != validated_data['password_repeat']:
            raise ValidationError(
                detail={
                    "password_repeat": "Tow password doesn't match",
                }
            )
        validated_data.pop('password_repeat')
        password = validated_data.pop('password')
        settings_data = validated_data.pop("settings", None)
        user = super(UserSerializer, self).create(
            validated_data,
        )
        user.set_password(password)
        user.save()
        if settings_data and "language" in settings_data:
            UserSettings.objects.update_or_create(
                user=user, defaults={"language": settings_data["language"]}
            )
        login(
            self.context['request'],
            user=user,
            backend=settings.AUTHENTICATION_BACKENDS[0],
        )
        return user

    def update(self, instance, validated_data):
        settings_data = validated_data.pop("settings", None)
        if settings_data and "language" in settings_data:
            UserSettings.objects.update_or_create(
                user=instance, defaults={"language": settings_data["language"]}
            )
        return super().update(instance, validated_data)

    def get_token(self, obj: User):
        if self.context['request'].user == obj:
            return create_token_if_necessary(obj).key
        return None
