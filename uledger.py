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
            m = re.match("\(\s*(.*?)\s+\+\s+(.*?)\s*\)",amountstr)
            if m:
                a = self.parseamount(m.groups()[0],filename,linenum)
                b = self.parseamount(m.groups()[1],filename,linenum)
                return Amount(a.commodity,a.value+b.value)
    
            m = re.match("\(\s*(.*?)\s+\*\s+(-?\d+(\.\d+)?)\s*\)",amountstr)
            if m:
                a = self.parseamount(m.groups()[0],filename,linenum)
                b = decimal.Decimal(m.groups()[1])
                return Amount(a.commodity,(a.value*b).quantize(decimal.Decimal('.01'), rounding=decimal.ROUND_HALF_UP))
    
        # $-1234.34
        m = re.match("(\$)\s*(-?\d+(\.\d+)?)",amountstr)
        if m:
            return Amount(m.groups()[0],decimal.Decimal(m.groups()[1]))
    
        # -123.43 CAD
        m = re.match("(-?\d+(\.\d+)?) (\w+)",amountstr)
        if m:
            return Amount(m.groups()[-1],decimal.Decimal(m.groups()[0]))

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
            if asof is None or date < asof:
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
                if post.amount is None:
                    raise ParseError(post.filename, post.linenum, "Could not understand \"%s\"" % p[2])
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
    
            line = line.rstrip()
            m = re.match(" *;", line)
            if line == '' or m:
                continue
    

            if transaction is not None:
                m = re.match("^\s+(.*?)(\s\s+(.*))?$", line)
                if m:
                    amount = None
                    if m.groups()[2] is not None:
                        amount = self.parseamount(m.groups()[2],filename,linenum)
                    post = Post(m.groups()[0],amount,filename,linenum)
                    posts.append(post)
                    continue
                else:
                    self.maketransaction(transaction, posts, bucket)
                    posts = []
                    transaction = None
    
            if accountdef is not None:
                m = re.match("^\s+(.*)$",line)
                if m:
                    continue
                else:
                    accountdef = None
    
            m = re.match("(\d{4}-\d{2}-\d{2})(=\d{4}-\d{2}-\d{2})?\s+(.*)", line)
            if m:
                transaction = Transaction(m.groups()[0],m.groups()[1],filename,linenum)
                continue
    
            m = re.match("commodity\s+(.*)", line)
            if m:
                continue
    
            m = re.match("account\s+(.*)", line)
            if m:
                accountdef = m.groups()
                continue
    
            m = re.match("include\s+(.*)",line)
            if m:
                includefile = m.groups()[0]
                with open(includefile) as f:
                    self.parse(f,includefile)
                continue
    
            m = re.match("bucket\s+(.*)",line)
            if m:
                bucket = m.groups()[0]
                continue
    
            m = re.match("alias\s+(.*?)\s+(.*)",line)
            if m:
                self.aliases[m.groups()[0]] = m.groups()[1]
                continue
    
            raise ParseError(filename, linenum, "Don't know how to process \"%s\"" % line)
    
        if transaction is not None:
            self.maketransaction(transaction,posts,bucket)
    

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description=' some integers.')
    parser.add_argument('-f','--filename', required=True, help='filename to load')
    parser.add_argument('-r','--reverse', help='reverse order of transactions')
    parser.add_argument("command", default='validate', choices=['balance', 'parse', 'validate'])

    args = parser.parse_args()

    ledger = Ledger()
    with open(args.filename) as f:
        ledger.parse(f,args.filename)

    if args.command == "balance":
        accountkeys = ledger.accounts.keys()
        accountkeys.sort()

        maxlen = 0
        for account in accountkeys:
            maxlen = max(maxlen,len(account))

        print "Account".ljust(maxlen+1," "),
        for commodity in ledger.commodities:
            print commodity.rjust(10," "),
        print

        print "-" * (maxlen+1 + len(ledger.commodities)*11)
        for account in accountkeys:
            #print ":".join(reversed(account.split(":"))).rjust(maxlen+1," "),
            print account.ljust(maxlen+1,"."),
            b = ledger.balance(account)
            for i, commodity in enumerate(b):
                if commodity in b:
                    print str(b[commodity]).rjust(10," "),
                else:
                    print " " * 10,
            print
