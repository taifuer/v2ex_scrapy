import unittest

from v2ex_scrapy.utils import parse_id_ranges


class ParseIdRangesTest(unittest.TestCase):
    def test_parses_ids_ranges_and_duplicates(self):
        self.assertEqual(
            parse_id_ranges("5, 2-4, 3, 8-9"),
            [2, 3, 4, 5, 8, 9],
        )

    def test_empty_value(self):
        self.assertEqual(parse_id_ranges(None), [])
        self.assertEqual(parse_id_ranges(""), [])

    def test_rejects_descending_range(self):
        with self.assertRaises(ValueError):
            parse_id_ranges("9-3")


if __name__ == "__main__":
    unittest.main()
