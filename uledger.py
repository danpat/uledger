#!/usr/bin/env python

import argparse
import re
import decimal
import sys
from collections import namedtuple

Amount = namedtuple("Amount", ["commodity","value"])
Post = namedtuple('Post', ['account', "amount","filename","linenum"])
Transaction = namedtuple("Transaction",["date","description","linenum","filename"])

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

    def __init__(self):
        self.transactions = {}
        self.accounts = {}
        self.aliases = {}
        self.commodities = set()

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
        m = re.match("(?P<commodity>\$)\s*(?P<value>-?\d+(\.\d+)?)",amountstr)
        if m:
            return Amount(m.group("commodity"),decimal.Decimal(m.group("value")))
    
        # -123.43 CAD
        m = re.match("(?P<value>-?\d+(\.\d+)?) (?P<commodity>\w+)",amountstr)
        if m:
            return Amount(m.group("commodity"),decimal.Decimal(m.group("value")))

        raise ParseError(filename, linenum, "Don't know how to interpret '%s' as a value, did you include a commodity type ($, USD, etc)?" % amountstr)
        return None
    
    def makepost(self, account,date,commodity,amount):
        self.commodities.add(commodity)
        if account not in self.accounts:
            self.accounts[account] = {}
        if date not in self.accounts[account]:
            self.accounts[account][date] = {}
        if commodity not in self.accounts[account][date]:
            self.accounts[account][date][commodity] = []
        self.accounts[account][date][commodity].append(amount)
    
    
    # We lexically sort the date keys, and start from
    # the beginning to get the current balance
    def balance(self, account,asof=None):

        if account not in self.accounts:
            raise AccountNotFoundError(account)
    
        balances = {}
        datekeys = self.accounts[account].keys()
        datekeys.sort()
        for date in datekeys:
            # We assumd 2015-02-32 which will compare lexically
            if asof is None or date <= asof:
                for commodity in self.accounts[account][date]:
                    if commodity not in balances:
                        balances[commodity] = 0
                    balances[commodity] += sum(self.accounts[account][date][commodity])
            else:
                break
        return balances

    def maketransaction(self, transaction, posts, bucket = None):
        balanceaccount = bucket
        amounts = {}
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
                if post.amount.commodity not in amounts:
                    amounts[post.amount.commodity] = 0
    
                amounts[post.amount.commodity] += post.amount.value
    
                self.makepost(account, transaction.date, post.amount.commodity, post.amount.value)
    
        for commodity in amounts:
            if amounts[commodity] != decimal.Decimal("0"):
                if balanceaccount is not None:
                    self.makepost(balanceaccount, transaction.date, commodity, -amounts[commodity])
                else:
                    raise ParseError(post.filename, post.linenum, "Transaction does not balance: %f %s outstanding" % (amounts[commodity], commodity))
    
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
                    self.maketransaction(transaction, posts, bucket)
                    posts = []
                    transaction = None
    
            if accountdef is not None:
                # Ignore things under accountdef for now
                m = re.match("^\s+(.*)$",line)
                if m:
                    continue
                else:
                    accountdef = None
    
            m = re.match("(?P<date>\d{4}-\d{2}-\d{2})(?P<postdate>=\d{4}-\d{2}-\d{2})?\s+(?P<description>.*)", line)
            if m:
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
    
            m = re.match("alias\s+(?P<alias>.*?)\s+(?P<account>.*)",line)
            if m:
                self.aliases[m.group("alias")] = m.group("account")
                continue

            m = re.match("assert\s+balance\s+(?P<asof>\d{4}-\d{2}-\d{2})?\s*(?P<account>.*?)\s\s+(?P<amount>.*)$",line)
            if m:
                balance = self.balance(m.group("account"),m.group("asof"))
                amount = self.parseamount(m.group("amount"),filename,linenum)

                if amount.value == 0 and amount.commodity not in balance:
                    None
                elif amount.commodity not in balance or balance[amount.commodity] != amount.value:
                    raise AssertionError(filename, linenum, "Account %s actual balance of %s does not match assertion value %s" % (m.group("account"),repr(balance), repr(amount)))

                continue

            raise ParseError(filename, linenum, "Don't know how to parse \"%s\"" % line)
    
        if transaction is not None:
            self.maketransaction(transaction,posts,bucket)
    

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description=' some integers.')
    parser.add_argument('-f','--filename', required=True, help='filename to load')
    parser.add_argument('-r','--reverse', help='reverse order of transactions')
    parser.add_argument("command", default='balance', choices=['balance'])

    args = parser.parse_args()

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

        maxlen = 0
        for account in accountkeys:
            maxlen = max(maxlen,len(account))

        for commodity in ledger.commodities:
            print commodity.rjust(10," "),
        print "Account".ljust(maxlen+1," ")
        print "-" * (maxlen+1 + len(ledger.commodities)*11)
        for account in accountkeys:
            #print ":".join(reversed(account.split(":"))).rjust(maxlen+1," "),
            b = ledger.balance(account)
            for i, commodity in enumerate(ledger.commodities):
                if commodity in b:
                    print str(b[commodity]).rjust(10," "),
                else:
                    print "-".rjust(10," "),
            print account
