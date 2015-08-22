#!/usr/bin/env python

import unittest
import uledger
import textwrap
import decimal

class LedgerTest(unittest.TestCase):
    def setUp(self):
        self.ledger = uledger.Ledger()


class Parsing(LedgerTest):

    def test_baddata1(self):
        data = textwrap.dedent("""
        Line1
            Line2
            Line3
        """
        )

        with self.assertRaises(uledger.ParseError):
            self.ledger.parse(data.splitlines(),"TESTDATA")

    def test_noposts(self):
        data = """2015-06-01 Dummy Transaction"""
        with self.assertRaises(uledger.ParseError):
            self.ledger.parse(data.splitlines(),"TESTDATA")

    def test_nocommodity(self):
        data = """2015-01-01 Dummy
            Source    50
            Dest"""
        with self.assertRaises(uledger.ParseError):
            self.ledger.parse(data.splitlines(), "TESTDATA")

    def test_multiblank(self):
        data = """2015-01-01 Dummy
            Source
            Dest"""
        with self.assertRaises(uledger.ParseError):
            self.ledger.parse(data.splitlines(), "TESTDATA")

    def test_bucketblank(self):
        data = textwrap.dedent("""
        bucket Dest
        2015-01-01 Dummy
            Source  $50
            Dest""")
        self.ledger.parse(data.splitlines(), "TESTDATA")

    def test_bucketblank(self):
        data = textwrap.dedent("""
        bucket Dest
        2015-01-01 Dummy
            Source  $50
            Dest2""")
        self.ledger.parse(data.splitlines(), "TESTDATA")
        balance = self.ledger.balance("Dest2")
        self.assertEquals(balance, {"$": -50 })
        with self.assertRaises(uledger.AccountNotFoundError):
            balance = self.ledger.balance("Dest")


    def test_bucket(self):
        data = textwrap.dedent("""
        bucket Dest
        2015-01-01 Dummy
            Source  $50
            Dest2
            
        2015-01-02 Dummy2
            Source  $50""")
        self.ledger.parse(data.splitlines(), "TESTDATA")
        balance = self.ledger.balance("Dest2")
        self.assertEquals(balance, {"$": -50 })
        balance = self.ledger.balance("Dest")
        self.assertEquals(balance, {"$": -50 })

    def test_spacing(self):
        data = """2015-06-01\tDuummy transaction
        \tSrc\t\t$1234
        \tDest"""
        self.ledger.parse(data.splitlines(),"TESTDATA")

class Math(LedgerTest):

    def test_basic(self):
        data = textwrap.dedent("""
        2015-01-01 Test
            SourceAccount    $50
            DestAccount""")

        self.ledger.parse(data.splitlines(),"TESTDATA")
        balance = self.ledger.balance("SourceAccount")
        self.assertEquals(balance, {"$": 50 })
        balance = self.ledger.balance("DestAccount")
        self.assertEquals(balance, {"$": -50 })

        with self.assertRaises(uledger.AccountNotFoundError):
            balance = self.ledger.balance("SourceAccount2")

    def test_precision1(self):
        data = """2015-01-01 Dummy
        Source  ($3.20 * 1.06)
        Dest"""

        self.ledger.parse(data.splitlines(),"TESTDATA")
        balance = self.ledger.balance("Source")
        self.assertEquals(balance, {"$": decimal.Decimal("3.39")})

    def test_precision2(self):
        data = textwrap.dedent("""
        2015-01-01 Test
            Source1    ($3.20 * 1.0609)
            Dest
            
        2015-01-02 Test2
            Source2    ($3.20 * 1.0610) 
            Dest""")

        # calculated value should be 3.3952, which should round up because the 3rd digit is >=5
        self.ledger.parse(data.splitlines(),"TESTDATA")
        balance = self.ledger.balance("Source1")
        self.assertEquals(balance, {"$": decimal.Decimal("3.39")})
        balance = self.ledger.balance("Source2")
        self.assertEquals(balance, {"$": decimal.Decimal("3.40")})

        balance = self.ledger.balance("Dest")
        self.assertEquals(balance, {"$": decimal.Decimal("-6.79")})

    def test_assert1(self):
        data = textwrap.dedent("""
        2015-01-01 Test
            SourceAccount   $50
            DestAccount

        assert balance SourceAccount  $50
        assert balance DestAccount  $-50""")

        self.ledger.parse(data.splitlines(),"TESTDATA")

    def test_assert2(self):
        data = textwrap.dedent("""
        2015-01-01 Test
            SourceAccount   $50
            DestAccount

        assert balance SourceAccount  $33
        assert balance DestAccount  $50""")

        with self.assertRaises(uledger.AssertionError):
            self.ledger.parse(data.splitlines(),"TESTDATA")

    def test_assert3(self):
        data = textwrap.dedent("""
        2015-01-01 Test
            SourceAccount   $50
            DestAccount

        assert balance 2014-12-31 SourceAccount  $0
        assert balance 2015-01-02 SourceAccount  $50""")

        self.ledger.parse(data.splitlines(),"TESTDATA")

    def test_assert4(self):
        data = textwrap.dedent("""
        2015-01-01 Test
            SourceAccount   $50
            DestAccount

        assert balance 2014-12-31 SourceAccount  $0
        assert balance 2015-01-02 SourceAccount  $60""")

        with self.assertRaises(uledger.AssertionError):
            self.ledger.parse(data.splitlines(),"TESTDATA")

    def test_assert5(self):
        data = textwrap.dedent("""
        2015-01-01 Test
            SourceAccount   $50
            DestAccount

        assert balance 2014-12-31 SourceAccount  $20""")

        with self.assertRaises(uledger.AssertionError):
            self.ledger.parse(data.splitlines(),"TESTDATA")

    def test_assert6(self):
        data = textwrap.dedent("""
        2015-01-01 Test
            SourceAccount   $50
            DestAccount

        assert balance 2015-01-01 SourceAccount  $50""")

        self.ledger.parse(data.splitlines(),"TESTDATA")


    def test_nobalance(self):
        data = textwrap.dedent("""
        2015-01-01 Test
            SourceAccount    $50
            DestAccount      $40""")

        with self.assertRaises(uledger.ParseError):
            self.ledger.parse(data.splitlines(),"TESTDATA")


    def test_multipleposts(self):
        data = textwrap.dedent("""
        2015-01-01 Test
            SourceAccount    $50
            SourceAccount2    $50
            SourceAccount3    $-50
            DestAccount""")

        self.ledger.parse(data.splitlines(),"TESTDATA")
        balance = self.ledger.balance("SourceAccount")
        self.assertEquals(balance, {"$": 50 })
        balance = self.ledger.balance("DestAccount")
        self.assertEquals(balance, {"$": -50 })
        balance = self.ledger.balance("SourceAccount2")
        self.assertEquals(balance, {"$": 50 })
        balance = self.ledger.balance("SourceAccount3")
        self.assertEquals(balance, {"$": -50 })

    def test_multipletransactions(self):
        data = textwrap.dedent("""
        2015-01-01 Test
            SourceAccount    $50
            SourceAccount2    $50
            SourceAccount3    $-50
            DestAccount
            
        2015-01-02 Test2
            SourceAccount     $25
            DestAccount""")

        self.ledger.parse(data.splitlines(),"TESTDATA")
        balance = self.ledger.balance("SourceAccount")
        self.assertEquals(balance, {"$": 75 })
        balance = self.ledger.balance("DestAccount")
        self.assertEquals(balance, {"$": -75 })
        balance = self.ledger.balance("SourceAccount2")
        self.assertEquals(balance, {"$": 50 })
        balance = self.ledger.balance("SourceAccount3")
        self.assertEquals(balance, {"$": -50 })

    def test_multiplecommodities(self):
        data = textwrap.dedent("""
        2015-01-01 Test
            SourceAccount    $50
            SourceAccount    50 CAD
            DestAccount""")

        self.ledger.parse(data.splitlines(),"TESTDATA")
        balance = self.ledger.balance("SourceAccount")
        self.assertEquals(balance, {"$": 50, "CAD": 50 })
        balance = self.ledger.balance("DestAccount")
        self.assertEquals(balance, {"$": -50, "CAD": -50 })


if __name__ == '__main__':
    unittest.main()
