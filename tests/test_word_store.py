import unittest
from unittest.mock import MagicMock

from classificator.word_store import WordStore


class _FakeCursor:
    def __init__(self):
        self.executemany_calls: list[tuple[str, list[tuple[int, int]]]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def executemany(self, sql: str, payload: list[tuple[int, int]]) -> None:
        self.executemany_calls.append((sql, payload))


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor):
        self._cursor = cursor
        self.commit_calls = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self._cursor

    def commit(self) -> None:
        self.commit_calls += 1


class WordStoreTest(unittest.TestCase):
    def test_update_rarity_levels_chunked_updates_only_rarity_column(self):
        store = WordStore(db_url="postgresql://example.invalid/db", db_user="u", db_password="p")
        fake_cursor = _FakeCursor()
        fake_conn = _FakeConnection(fake_cursor)
        store._connect = MagicMock(return_value=fake_conn)

        updates = {
            101: 2,
            102: 5,
            103: 1,
        }
        store.update_rarity_levels_chunked(updates, chunk_size=2)

        self.assertEqual(fake_conn.commit_calls, 1)
        self.assertEqual(len(fake_cursor.executemany_calls), 2)
        self.assertEqual(
            fake_cursor.executemany_calls[0],
            (
                "UPDATE words SET rarity_level = %s WHERE id = %s",
                [(2, 101), (5, 102)],
            ),
        )
        self.assertEqual(
            fake_cursor.executemany_calls[1],
            (
                "UPDATE words SET rarity_level = %s WHERE id = %s",
                [(1, 103)],
            ),
        )
        for _, payload in fake_cursor.executemany_calls:
            for item in payload:
                self.assertEqual(len(item), 2)

    def test_update_rarity_levels_chunked_empty_updates_does_not_connect(self):
        store = WordStore(db_url="postgresql://example.invalid/db", db_user="u", db_password="p")
        store._connect = MagicMock()

        store.update_rarity_levels_chunked({}, chunk_size=2)

        store._connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
