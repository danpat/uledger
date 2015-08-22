#!/usr/bin/env python

import unittest
import uledger
import textwrap


class Parsing(unittest.TestCase):

    def test_baddata1(self):
        data = """
        Line1
            Line2
            Line3
        """

        with self.assertRaises(uledger.ParseError):
            uledger.parse(data.splitlines(),"TESTDATA")

    def test_ok(self):
        data = """2015-06-01 Dummy Transaction"""
        with self.assertRaises(uledger.ParseError):
            uledger.parse(data.splitlines(),"TESTDATA")


if __name__ == '__main__':
    unittest.main()
