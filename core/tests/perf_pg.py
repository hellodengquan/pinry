"""
PostgreSQL-specific performance benchmarks for COUNT + GROUP BY + permission filtering
queries at scale.  These tests run only when the configured database engine is
PostgreSQL; they are skipped transparently on SQLite.

Run:
    docker-compose -f docker-compose.test.yml up -d
    DJANGO_SETTINGS_MODULE=pinry.settings.test_postgres \
        python -m pytest core/tests/perf_pg.py -v --no-header
"""
import os
import time

import pytest

from django.conf import settings
from django.db import connection
from django.urls import reverse
from rest_framework.test import APITestCase

from core.models import Pin, Board, Image
from taggit.models import Tag
from users.models import User


PG_OK = 'postgresql' in settings.DATABASES.get('default', {}).get('ENGINE', '')

skipUnlessPG = pytest.mark.skipif(not PG_OK, reason='PostgreSQL-only benchmark')


def _make_pin(owner, private, image, tag_set):
    p = Pin.objects.create(
        submitter=owner,
        private=private,
        image=image,
        description=f'desc {owner.id} {private} {int(time.time()*1e6)}',
    )
    for t in tag_set:
        p.tags.add(t)
    return p


@skipUnlessPG
class PostgresCountGroupByBenchmark(APITestCase):
    """
    Validates that the Pin list endpoint count performs correctly at scale
    under PostgreSQL, including COUNT(DISTINCT ...) + GROUP BY scenarios
    introduced by M2M tag/board joins combined with permission filtering.
    """

    DATASET_SIZE = int(os.environ.get('PERF_PIN_COUNT', '2000'))
    TAG_COUNT = 40
    BOARD_COUNT = 20
    PINS_PER_BOARD = 80
    THRESHOLD_MS = int(os.environ.get('PERF_THRESHOLD_MS', '600'))

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not PG_OK:
            return

        cls.owner = User.objects.create_user(
            username=f'pgperf_owner_{int(time.time())}', password='x',
        )
        cls.other = User.objects.create_user(
            username=f'pgperf_other_{int(time.time())}', password='x',
        )

        cls.tags = [
            Tag.objects.get_or_create(name=f'pgperf_tag_{i}', slug=f'pgperf_tag_{i}')[0]
            for i in range(cls.TAG_COUNT)
        ]
        cls.boards = [
            Board.objects.create(name=f'pgperf_board_{i}', submitter=cls.owner, private=False)
            for i in range(cls.BOARD_COUNT)
        ]
        cls._seed_pins()

    @classmethod
    def _seed_pins(cls):
        # Pre-batch image creation to avoid filesystem pressure during benchmark
        images = [
            Image.objects.create(image=None)
            for _ in range(min(cls.DATASET_SIZE, 200))
        ]
        for i in range(cls.DATASET_SIZE):
            image = images[i % len(images)]
            is_owner = (i % 2) == 0
            private = (i % 5) == 0
            submitter = cls.owner if is_owner else cls.other
            # every pin carries 1..3 random tags
            sample_tags = [cls.tags[(i + j) % cls.TAG_COUNT] for j in range((i % 3) + 1)]
            p = _make_pin(submitter, private, image, sample_tags)
            # spread pins across boards
            for j in range((i % 4)):
                cls.boards[(i + j) % cls.BOARD_COUNT].pins.add(p)

    def _timed(self, label, fn):
        start = time.perf_counter()
        result = fn()
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return result, elapsed_ms

    def _explain_analyze(self, sql):
        with connection.cursor() as cur:
            cur.execute(f'EXPLAIN (ANALYZE, FORMAT JSON) {sql}')
            rows = cur.fetchall()
        return rows[0][0]

    def test_anonymous_tag_count_ms(self):
        tag = self.tags[0]
        url = reverse('pin-list')
        (resp, elapsed) = self._timed(
            f'anon tag count n={self.DATASET_SIZE}',
            lambda: self.client.get(url, {'tags__name': tag.name, 'limit': 1}),
        )
        assert resp.status_code == 200
        assert resp.json()['count'] <= self.DATASET_SIZE
        assert elapsed < self.THRESHOLD_MS * 4, (
            f'anonymous tag count took {elapsed:.0f}ms, threshold '
            f'{self.THRESHOLD_MS * 4}ms'
        )

    def test_owner_tag_count_ms(self):
        self.client.login(username=self.owner.username, password='x')
        tag = self.tags[1]
        url = reverse('pin-list')
        (resp, elapsed) = self._timed(
            f'owner tag count n={self.DATASET_SIZE}',
            lambda: self.client.get(url, {'tags__name': tag.name, 'limit': 1}),
        )
        assert resp.status_code == 200
        assert elapsed < self.THRESHOLD_MS * 4, (
            f'owner tag count took {elapsed:.0f}ms'
        )

    def test_owner_board_pin_count_ms(self):
        self.client.login(username=self.owner.username, password='x')
        board = self.boards[0]
        url = reverse('pin-list')
        (resp, elapsed) = self._timed(
            f'owner board count n={self.DATASET_SIZE}',
            lambda: self.client.get(url, {'pins__id': board.id, 'limit': 1}),
        )
        assert resp.status_code == 200
        assert elapsed < self.THRESHOLD_MS * 3, (
            f'owner board pin count took {elapsed:.0f}ms'
        )

    def test_count_matches_results_cardinality_tag_join(self):
        tag = self.tags[5]
        resp = self.client.get(reverse('pin-list'), {'tags__name': tag.name})
        data = resp.json()
        assert data['count'] == len(data['results']), (
            f'count={data["count"]} vs results.len={len(data["results"])}'
        )

    def test_count_matches_results_cardinality_board_join(self):
        self.client.login(username=self.owner.username, password='x')
        board = self.boards[3]
        resp = self.client.get(reverse('pin-list'), {'pins__id': board.id})
        data = resp.json()
        assert data['count'] == len(data['results']), (
            f'count={data["count"]} vs results.len={len(data["results"])}'
        )

    def test_count_auth_transition_consistency(self):
        tag = self.tags[2]
        anon_resp = self.client.get(reverse('pin-list'), {'tags__name': tag.name, 'limit': 1})
        anon_count = anon_resp.json()['count']

        self.client.login(username=self.owner.username, password='x')
        owner_resp = self.client.get(reverse('pin-list'), {'tags__name': tag.name, 'limit': 1})
        owner_count = owner_resp.json()['count']

        assert owner_count >= anon_count, (
            f'owner count {owner_count} should be >= anon {anon_count}'
        )
