# tests for the c++ ac engine via the pybind11 wrapper

import ac_engine


def test_basic_match_offsets():
    s = ac_engine.Scanner(["he", "she", "his", "hers"])
    hits = s.scan("ushers")
    # 'she' at [1,4), 'he' at [2,4), 'hers' at [2,6)
    spans = {(pid, start, end) for pid, start, end in hits}
    assert (1, 1, 4) in spans  # she
    assert (0, 2, 4) in spans  # he
    assert (3, 2, 6) in spans  # hers


def test_case_insensitive():
    s = ac_engine.Scanner(["ignore previous instructions"])
    hits = s.scan("Please IGNORE Previous Instructions now")
    assert len(hits) == 1
    assert hits[0][0] == 0


def test_no_match():
    s = ac_engine.Scanner(["foo", "bar"])
    assert s.scan("nothing here") == []


def test_pattern_count():
    s = ac_engine.Scanner(["a", "b", "c"])
    assert s.pattern_count == 3


def test_overlapping_and_repeated():
    s = ac_engine.Scanner(["ab", "abc"])
    hits = s.scan("xabcabc")
    # two 'abc', two 'ab'
    ids = sorted(pid for pid, _, _ in hits)
    assert ids.count(0) == 2  # 'ab'
    assert ids.count(1) == 2  # 'abc'
