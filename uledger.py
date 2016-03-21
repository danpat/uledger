#!/usr/bin/env python

import argparse
import re
import decimal
import sys
from collections import namedtuple
import datetime

Amount = namedtuple("Amount", ["commodity","value"])
Post = namedtuple('Post', ['account', "amount","filename","linenum"])
Transaction = namedtuple("Transaction",["date","description","linenum","filename"])
Entry = namedtuple('Entry',['description','amount'])

class ParseError(Exception):
    def __init__(self, filename, linenum, msg):
        self.msg = msg
        self.filename = filename
        self.linenum = linenum
    def __str__(self):
        return "ERROR: %s:%s: %s" % (self.filename, self.linenum, self.msg)

class AssertionError(Exception):
    def __init__(self, filename, linenum, msg):
        self.msg = msg
        self.filename = filename
        self.linenum = linenum
    def __str__(self):
        return "ASSERT FAILED: %s:%s: %s" % (self.filename, self.linenum, self.msg)


class AccountNotFoundError(Exception):
    def __init__(self, account):
        self.account = account
    def __str__(self):
        return "ERROR: Account '%s' not found" % (self.account)


class Ledger(object):

    # This is a dict of dates
    #   each member is a transaction, sorted by parse order
    transactions = {}
    accounts = {}
    aliases = {}
    commodities = set()

    def __init__(self, assertions=True):
        self.transactions = {}
        self.accounts = {}
        self.aliases = {}
        self.commodities = set()
        self.assertions = assertions

    def parseamount(self, amountstr, filename, linenum):
        m = re.match("\((.*?)\)",amountstr)
        if m:
            # $1234.12 + $123432.23
            m = re.match("\(\s*(?P<left>.*?)\s+\+\s+(?P<right>.*?)\s*\)",amountstr)
            if m:
                a = self.parseamount(m.group("left"),filename,linenum)
                b = self.parseamount(m.group("right"),filename,linenum)
                return Amount(a.commodity,a.value+b.value)

            m = re.match("\(\s*(?P<left>.*?)\s+\*\s+(?P<right>-?\d+(\.\d+)?)\s*\)",amountstr)
            if m:
                a = self.parseamount(m.group("left"),filename,linenum)
                b = decimal.Decimal(m.group("right"))
                return Amount(a.commodity,(a.value*b).quantize(decimal.Decimal('.01'), rounding=decimal.ROUND_HALF_UP))

        # $-1234.34
        m = re.match("(?P<commodity>\$)\s*(?P<value>-?[\d,]+(\.\d+)?)",amountstr)
        if m:
            return Amount(m.group("commodity"),decimal.Decimal(m.group("value").replace(",","")))

        # -123.43 CAD
        m = re.match("(?P<value>-?[\d,]+(\.\d+)?) (?P<commodity>\w+)",amountstr)
        if m:
            return Amount(m.group("commodity"),decimal.Decimal(m.group("value").replace(",","")))

        raise ParseError(filename, linenum, "Don't know how to interpret '%s' as a value, did you include a commodity type ($, USD, etc)?" % amountstr)
        return None

    def makepost(self, account,date,description,commodity,value):
        self.commodities.add(commodity)
        if account not in self.accounts:
            self.accounts[account] = {}
        if date not in self.accounts[account]:
            self.accounts[account][date] = []

        self.accounts[account][date].append(Entry(description,Amount(commodity,value)))


    # We lexically sort the date keys, and start from
    # the beginning to get the current balance
    def balance(self, account, asof=None):

        if account not in self.accounts:
            raise AccountNotFoundError(account)

        balances = {}
        datekeys = self.accounts[account].keys()
        datekeys.sort()
        for date in datekeys:
            # We assumd 2015-02-32 which will compare lexically
            if asof is None or date <= asof:
                for entry in self.accounts[account][date]:
                    if entry.amount.commodity not in balances:
                        balances[entry.amount.commodity] = decimal.Decimal(0)
                    balances[entry.amount.commodity] += entry.amount.value
            else:
                break
        return balances

    def balances(self, asof=None):
        result = {}
        for account in self.accounts:
            result[account] = self.balance(account, asof)
        return result

    # Fetches the balance of all sub-accounts that have this name as
    # a prefix
    def balance_children(self, prefix, asof=None):
        b = self.balances(asof)
        result = {}
        if prefix not in b:
            for account in [i for i in self.accounts if i.startswith(prefix)]:
                for commodity in b[account]:
                    if commodity not in result:
                        result[commodity] = decimal.Decimal(0)
                    result[commodity] += b[account][commodity]
        return result

    def commodities(self):
        return self.commodities

    def startdate(self):
        start = None
        for account in self.accounts:
            datekeys = self.accounts[account].keys()
            datekeys.sort()
            if start is None or start > datekeys[0]:
                start = datekeys[0]
        return start

    def enddate(self):
        start = None
        for account in self.accounts:
            datekeys = self.accounts[account].keys()
            datekeys.sort()
            if start < datekeys[-1]:
                start = datekeys[-1]
        return start


    def maketransaction(self, transaction, posts, bucket = None):
        balanceaccount = bucket
        values = {}
        if len(posts) == 0 or len(posts) == 1 and posts[0].amount.commodity is None:
            raise ParseError(transaction.filename, transaction.linenum, "No transactions")

        for post in posts:
            account = post.account
            if account in self.aliases:
                account = self.aliases[post.account]
            if post.amount is None or post.amount.value is None:
                if balanceaccount is None or balanceaccount == bucket:
                    balanceaccount = account
                else:
                    raise ParseError(post.filename, post.linenum, "Cannot have multiple empty posts")
            else:
                if post.amount.commodity not in values:
                    values[post.amount.commodity] = 0

                values[post.amount.commodity] += post.amount.value

                self.makepost(account, transaction.date, transaction.description, post.amount.commodity, post.amount.value)

        for commodity in values:
            if values[commodity] != decimal.Decimal("0"):
                if balanceaccount is not None:
                    self.makepost(balanceaccount, transaction.date, transaction.description, commodity, -values[commodity])
                else:
                    raise ParseError(post.filename, post.linenum, "Transaction does not balance: %f %s outstanding" % (values[commodity], commodity))

    # Parses a file, can be called recursively
    def parse(self, reader,filename=None):

        bucket = None
        transaction = None
        accountdef = None
        posts = []
        for linenum, line in enumerate(reader):
            linenum += 1

            line = line.rstrip()
            m = re.match(" *;", line)
            if line == '' or m:
                continue


            if transaction is not None:
                m = re.match("^\s+(?P<account>.*?)(\s\s+(?P<amount>.*))?$", line)
                if m:
                    amount = None
                    if m.group("amount") is not None:
                        amount = self.parseamount(m.group("amount"),filename,linenum)
                    post = Post(m.group("account"),amount,filename,linenum)
                    posts.append(post)
                    continue
                else:
                    try:
                        self.maketransaction(transaction, posts, bucket)
                    except Exception as e:
                        e.args = (ParseError(filename, linenum, "Parse error: %s" % e),)
                        raise

                    posts = []
                    transaction = None

            if accountdef is not None:
                # Ignore things under accountdef for now
                m = re.match("^\s+(.*)$",line)
                if m:
                    continue
                else:
                    accountdef = None

            m = re.match("(?P<date>\d{4}-\d{2}-\d{2})(=(?P<postdate>\d{4}-\d{2}-\d{2}))?\s+(?P<description>.*)", line)
            if m:
                if m.group("postdate") is not None:
                    transaction = Transaction(m.group("postdate"),m.group("description"),filename,linenum)
                else:
                    transaction = Transaction(m.group("date"),m.group("description"),filename,linenum)
                continue

            m = re.match("commodity\s+(?P<commodity>.*)", line)
            if m:
                continue

            m = re.match("account\s+(?P<account>.*)", line)
            if m:
                accountdef = m.groups()
                continue

            m = re.match("include\s+(?P<filename>.*)",line)
            if m:
                includefile = m.group("filename")
                with open(includefile) as f:
                    self.parse(f,includefile)
                continue

            m = re.match("bucket\s+(?P<account>.*)",line)
            if m:
                bucket = m.group("account")
                continue

            m = re.match("print\s+(?P<str>.*)",line)
            if m:
                print m.group("str")
                continue

            m = re.match("alias\s+(?P<alias>.*?)\s+(?P<account>.*)",line)
            if m:
                self.aliases[m.group("alias")] = m.group("account")
                continue

            m = re.match("closeall\s+(?P<asof>\d{4}-\d{2}-\d{2})\s+(?P<prefix>.+?)\s\s+(?P<closingaccount>.*)",line)
            if m:
                transaction = Transaction(m.group("asof"),"Automatic closing transaction",filename,linenum)
                posts = []
                closing = {}
                for account in self.accounts:
                    if account.startswith(m.group("prefix")):
                        balance = self.balance(account,m.group("asof"))
                        for commodity,value in balance.items():
                            if commodity not in closing:
                                closing[commodity] = decimal.Decimal(0)
                            closing[commodity] += value
                            posts.append(Post(account,Amount(commodity,-1*value),filename,linenum))

                self.maketransaction(transaction, posts, m.group("closingaccount"))
                transaction = None
                posts = None
                continue


            m = re.match("assert\s+balance\s+(?P<asof>\d{4}-\d{2}-\d{2})?\s*(?P<account>.*?)\s\s+(?P<amount>.*)$",line)
            if m:
                if not self.assertions:
                    continue
                try:
                    balance = self.balance(m.group("account"),m.group("asof"))
                except AccountNotFoundError:
                    balance = self.balance_children(m.group("account"),m.group("asof"))
                amount = self.parseamount(m.group("amount"),filename,linenum)

                if not (amount.value == 0 and amount.commodity not in balance) and \
                    (amount.commodity not in balance or balance[amount.commodity] != amount.value):
                    raise AssertionError(filename, linenum, "Account %s actual balance of %s on %s does not match assertion value %s" % (m.group("account"),m.group("asof"), repr(balance), repr(amount)))

                continue

            m = re.match("assert\s+equation\s+(?P<asof>\d{4}-\d{2}-\d{2})?\s*(?P<assetsaccount>.*?)\s+-\s+(?P<liabilitiesaccount>.*?)\s+=\s+(?P<equityaccount>.*?)\s+\+\s+(?P<incomeaccount>.*?)\s+-\s+(?P<expenseaccount>.*?)$", line)
            if m:
                if not self.assertions:
                    continue
                data = {}
                for acct in ["assets","liabilities","equity","income","expense"]:
                    try:
                        balance = self.balance(m.group("%saccount" % acct),m.group("asof"))
                    except AccountNotFoundError:
                        balance = self.balance_children(m.group("%saccount" % acct),m.group("asof"))
                    data[acct] = balance


                # Assets + liabilities
                left = {}
                right = {}
                for commodity in self.commodities:
                    left[commodity] = decimal.Decimal(0)
                    right[commodity] = decimal.Decimal(0)

                    # Left
                    if commodity in data["assets"]:
                        left[commodity] += data["assets"][commodity]
                    if commodity in data["liabilities"]:
                        left[commodity] += data["liabilities"][commodity]

                    # Right
                    if commodity in data["equity"]:
                        right[commodity] -= data["equity"][commodity]
                    if commodity in data["income"]:
                        right[commodity] -= data["income"][commodity]
                    if commodity in data["expense"]:
                        right[commodity] -= data["expense"][commodity]



                if left != right:
                    print data
                    raise AssertionError(filename, linenum, "Accounting equation not satisified: %s != %s" % (repr(left), repr(right)))

                continue


            raise ParseError(filename, linenum, "Don't know how to parse \"%s\"" % line)

        if transaction is not None:
            self.maketransaction(transaction,posts,bucket)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description=' some integers.')
    parser.add_argument('-f','--filename', required=True, help='filename to load')
    parser.add_argument("command", default='balance', choices=['balance','register', 'web'])
    parser.add_argument('-a','--account', help='Apply to which account')
    parser.add_argument('-s','--start', help='Start at which date')
    parser.add_argument('-e','--end', help='End at which date')

    args = parser.parse_args()

    if args.command == "register":
        ledger = Ledger(assertions=False)
    else:
        ledger = Ledger()

    try:
        with open(args.filename) as f:
            ledger.parse(f,args.filename)
    except AssertionError,e:
        print e
        sys.exit(1)
    except ParseError,e:
        print e
        sys.exit(1)

    if args.command == "balance":
        accountkeys = ledger.accounts.keys()
        accountkeys.sort()

        enddate = args.end
        # TODO: validate date formats

        maxlen = 0
        for account in accountkeys:
            maxlen = max(maxlen,len(account))

        for commodity in ledger.commodities:
            print commodity.rjust(10," "),

        if enddate:
            print "Balances asof %s" % enddate
        print "Account".ljust(maxlen+1," ")
        print "-" * (maxlen+1 + len(ledger.commodities)*11)
        balances = ledger.balances(enddate)
        for account in accountkeys:
            b = balances[account]
            for i, commodity in enumerate(ledger.commodities):
                if commodity in b:
                    print str(b[commodity]).rjust(10," "),
                else:
                    print "-".rjust(10," "),
            print account

    elif args.command == "web":
        import web
        web.make_report(ledger, ".")

    elif args.command == "register":
        accountkeys = ledger.accounts.keys()
        accountkeys.sort()

        firstdate = None
        startdate = args.start
        enddate = args.end
        balances = {}
        # If no start date, find the earliest/last as bounds
        for account in ledger.accounts:
            balances[account] = {}
            datekeys = ledger.accounts[account].keys()
            datekeys.sort()
            if firstdate is None or datekeys[0] < firstdate:
                firstdate = datekeys[0]
            if args.end is None and (enddate is None or datekeys[-1] > enddate):
                enddate = datekeys[-1]

        if startdate is None:
            startdate = firstdate

        firstdate = datetime.datetime.strptime( firstdate, "%Y-%m-%d" )
        startdate = datetime.datetime.strptime( startdate, "%Y-%m-%d" )
        enddate = datetime.datetime.strptime( enddate, "%Y-%m-%d" )


        while firstdate <= enddate:
            today = firstdate.strftime("%Y-%m-%d")
            for account in ledger.accounts:
                if args.account is None or account.startswith(args.account):
                    if today in ledger.accounts[account]:
                        for transaction in ledger.accounts[account][today]:
                            if transaction.amount.commodity not in balances[account]:
                                balances[account][transaction.amount.commodity] = 0
                            balances[account][transaction.amount.commodity] += transaction.amount.value

                            if firstdate >= startdate:
                                print today, str(balances[account][transaction.amount.commodity]).rjust(8," "), transaction.amount.commodity, str(transaction.amount.value).rjust(8," "), transaction.description
                                if args.account is None or account.startswith(args.account):
                                    print "\t",account

            firstdate += datetime.timedelta(days=1)
