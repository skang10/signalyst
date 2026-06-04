from src.services.hashing import canonical_json, stable_hash


def test_stable_hash_is_deterministic():
    assert stable_hash("a", "b") == stable_hash("a", "b")


def test_stable_hash_differs_on_different_input():
    assert stable_hash("a", "b") != stable_hash("b", "a")


def test_stable_hash_length():
    assert len(stable_hash("anything")) == 24


def test_canonical_json_sorts_keys():
    a = canonical_json({"b": 1, "a": 2})
    b = canonical_json({"a": 2, "b": 1})
    assert a == b


def test_canonical_json_nested():
    result = canonical_json({"windows": [5, 20], "lags": [1]})
    assert result == '{"lags":[1],"windows":[5,20]}'
