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

    def test_bucketmulti(self):
        data = textwrap.dedent("""
        bucket Dest
        2015-01-01 Dummy
            Source  $50
            Source  50 CAD
            Dest2
            """)
        self.ledger.parse(data.splitlines(), "TESTDATA")
        balance = self.ledger.balance("Dest2")
        self.assertEquals(balance, {"$": -50,"CAD":-50 })

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

    # For example, credit cards.  The event was on the 1st, the charge landed on the 3rd
    def test_postdates(self):
        data = """2015-06-01=2015-06-03  Some kind of payment
        Source  $50
        Dest"""

        self.ledger.parse(data.splitlines(),"TESTDATA")

        balance = self.ledger.balance("Dest")
        self.assertEquals(balance, {"$": -50 })

        balance = self.ledger.balance("Dest","2015-06-02")
        self.assertEquals(balance, {})

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


    def test_assert7(self):
        # Testing out of order transactions
        data = textwrap.dedent("""
        2015-01-07 Test
            SourceAccount   $24
            DestAccount

        2015-01-01 Test
            SourceAccount   $50
            DestAccount

        assert balance 2015-01-02 SourceAccount  $50
        assert balance 2015-01-07 SourceAccount  $74

        2015-01-03 Test
            SourceAccount   $50
            DestAccount

        assert balance 2015-01-07 SourceAccount  $124

        2015-01-01 Test
            SourceAccount   $50
            DestAccount

        assert balance 2015-01-07 SourceAccount  $174
        assert balance 2015-01-03 SourceAccount  $150
        """)

        self.ledger.parse(data.splitlines(),"TESTDATA")

        balance = self.ledger.balance("SourceAccount","2015-01-06")
        self.assertEquals(balance, {"$": 150 })



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

    def test_startend(self):
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

        self.assertEquals("2015-01-01", self.ledger.startdate())
        self.assertEquals("2015-01-02", self.ledger.enddate())

    def test_balance_children(self):
        data = textwrap.dedent("""
        2015-01-01 Test
            Source:Account1    $50
            Source:Account2    50 CAD
            Source:Account3    $50
            DestAccount
            """)

        self.ledger.parse(data.splitlines(),"TESTDATA")

        self.assertEquals(self.ledger.balance("DestAccount"), {"$":-100,"CAD":-50})
        self.assertEquals(self.ledger.balance_children("Source"), {"$":100,"CAD":50})

    def test_closeall(self):
        data = textwrap.dedent("""
        2015-01-01 Test
            Source:Account1    $50
            Source    $50
            Source:Account2    50 CAD
            Source:Account3    $50
            DestAccount

        closeall 2015-01-01 Source  DestAccount2""")

        self.ledger.parse(data.splitlines(),"TESTDATA")

        self.assertEquals(self.ledger.balance("DestAccount"), {"$":-150,"CAD":-50})
        self.assertEquals(self.ledger.balance_children("Source"), {"$":0,"CAD":0})
        self.assertEquals(self.ledger.balance("DestAccount2"), {"$":150,"CAD":50})

    def test_multitotal(self):
        data = textwrap.dedent("""
        bucket Savings
        2015-07-15 July pay
            Personal:Income:Example INC                          $-4,791.67
            Personal:Expenses:US Federal Income Tax              $716.15
            Personal:Expenses:US Social Security                 $297.09
            Personal:Expenses:US Medicare                        $69.48
            Personal:Expenses:US District of Columbia State Income Tax  $338.51	""")

        self.ledger.parse(data.splitlines(),"TESTDATA")
        self.assertEquals(self.ledger.balance("Savings"), {"$": decimal.Decimal("3370.44")})

    def test_account_equation1(self):
        data = textwrap.dedent("""
        2015-01-01 Opening Balance
            Equity:Owners Contributions   $-100
            Assets:Bank                   $100

        2015-01-01 Buying widgets
            Liabilities:Credit Card       $-50
            Expenses:Parts

        2015-01-01 Some Income
            Income:Consulting             $-200
            Assets:Bank                   $200

        assert equation 2015-01-02 Assets - Liabilities = Equity + Income - Expenses""")

        self.ledger.parse(data.splitlines(),"TESTDATA")

    def test_account_equation2(self):
        data = textwrap.dedent("""
        2015-01-01 Opening Balance
            Equity:Owners Contributions   $-100
            Assets:Bank                   $100

        2015-01-01 Buying widgets
            Liabilities:Credit Card       $-50
            Expenses:Parts

        2015-01-01 Buying widgets 2
            Liabilities:Credit Card       $-50
            Something

        2015-01-01 Some Income
            Income:Consulting             $-200
            Assets:Bank                   $200

        assert equation 2015-01-02 Assets - Liabilities = Equity + Income - Expenses""")

        with self.assertRaises(uledger.AssertionError):
            self.ledger.parse(data.splitlines(),"TESTDATA")



if __name__ == '__main__':
    unittest.main()
