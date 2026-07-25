"""Tests for soundweave.utils.natural_sort."""

from soundweave.utils.natural_sort import natural_sort, natural_sort_key


class TestNaturalSort:
    def test_numeric_ordering(self):
        """track2 should sort before track10 (not lexicographic)."""
        files = ["track10.mp3", "track2.mp3", "track1.mp3"]
        assert natural_sort(files) == ["track1.mp3", "track2.mp3", "track10.mp3"]

    def test_docstring_example(self):
        assert natural_sort(["track10.mp3", "track2.mp3", "track1.mp3"]) == [
            "track1.mp3",
            "track2.mp3",
            "track10.mp3",
        ]

    def test_already_sorted(self):
        files = ["a.mp3", "b.mp3", "c.mp3"]
        assert natural_sort(files) == ["a.mp3", "b.mp3", "c.mp3"]

    def test_empty_list(self):
        assert natural_sort([]) == []

    def test_single_item(self):
        assert natural_sort(["solo.mp3"]) == ["solo.mp3"]

    def test_case_insensitive_ordering(self):
        # Non-numeric fragments are lowercased for comparison.
        files = ["Banana.mp3", "apple.mp3", "Cherry.mp3"]
        assert natural_sort(files) == ["apple.mp3", "Banana.mp3", "Cherry.mp3"]

    def test_multi_digit_groups(self):
        files = ["v1-10.mp3", "v1-2.mp3", "v1-1.mp3", "v2-1.mp3"]
        assert natural_sort(files) == ["v1-1.mp3", "v1-2.mp3", "v1-10.mp3", "v2-1.mp3"]

    def test_no_numbers_falls_back_to_alpha(self):
        files = ["gamma.mp3", "alpha.mp3", "beta.mp3"]
        assert natural_sort(files) == ["alpha.mp3", "beta.mp3", "gamma.mp3"]

    def test_leading_zeros(self):
        # int() conversion strips leading zeros, so 01 == 1 numerically,
        # meaning original relative order is preserved for equal values
        # (Python's sort is stable).
        files = ["track01.mp3", "track1.mp3", "track2.mp3"]
        result = natural_sort(files)
        assert result[-1] == "track2.mp3"
        assert set(result[:2]) == {"track01.mp3", "track1.mp3"}

    def test_does_not_mutate_input(self):
        files = ["b.mp3", "a.mp3"]
        original = list(files)
        natural_sort(files)
        assert files == original

    def test_returns_new_list(self):
        files = ["b.mp3", "a.mp3"]
        result = natural_sort(files)
        assert result is not files


class TestNaturalSortKey:
    def test_splits_digits_and_text(self):
        # Note: re.split(r'(\d+)', ...) also splits digits embedded inside
        # the extension (".mp3" contains "3"), so the key has more
        # fragments than one might expect at a glance.
        assert natural_sort_key("track10.mp3") == ["track", 10, ".mp", 3, ""]

    def test_numeric_fragment_is_int(self):
        key = natural_sort_key("track2.wav")
        assert 2 in key
        assert isinstance(key[key.index(2)], int)

    def test_text_fragment_is_lowercased_str(self):
        key = natural_sort_key("ABC")
        assert key == ["abc"]
        assert isinstance(key[0], str)

    def test_no_digits(self):
        assert natural_sort_key("hello.txt") == ["hello.txt"]
