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


# This is a dict of dates
#   each member is a transaction, sorted by parse order
transactions = {}
accounts = {}
aliases = {}
commodities = set()

def parseamount(amountstr):
    m = re.match("\((.*?)\)",amountstr)
    if m:
        # $1234.12 + $123432.23
        m = re.match("\((.*?) +\+ +(.*?)\)",amountstr)
        if m:
            a = parseamount(m.groups()[0])
            b = parseamount(m.groups()[1])
            return Amount(a.commodity,a.value+b.value)

        m = re.match("\((.*?) +\* +(-?\d+(\.\d+)?) *\)",amountstr)
        if m:
            a = parseamount(m.groups()[0])
            b = decimal.Decimal(m.groups()[1])
            return Amount(a.commodity,(a.value*b).quantize(decimal.Decimal('.01'), rounding=decimal.ROUND_HALF_UP))

    # $-1234.34
    m = re.match("(\$) *(-?\d+(\.\d+)?)",amountstr)
    if m:
        return Amount(m.groups()[0],decimal.Decimal(m.groups()[1]))

    # -123.43 CAD
    m = re.match("(-?\d+(\.\d+)?) (\w+)",amountstr)
    if m:
        return Amount(m.groups()[-1],decimal.Decimal(m.groups()[0]))

def makepost(account,date,commodity,amount):

    commodities.add(commodity)

    if account not in accounts:
        accounts[account] = {}

    if date not in accounts[account]:
        accounts[account][date] = {}

    if commodity not in accounts[account][date]:
        accounts[account][date][commodity] = []

    accounts[account][date][commodity].append(amount)


# We lexically sort the date keys, and start from
# the beginning to get the current balance
def balance(account,asof=None):

    balances = {}
    datekeys = accounts[account].keys()
    datekeys.sort()
    for date in datekeys:
        # We assumd 2015-02-32 which will compare lexically
        if asof is None or date < asof:
            for commodity in accounts[account][date]:
                if commodity not in balances:
                    balances[commodity] = 0
                balances[commodity] += sum(accounts[account][date][commodity])
        else:
            break
    return balances

def maketransaction(transaction, posts, bucket = None):
    balanceaccount = bucket
    amounts = {}
    if len(posts) == 0 or len(posts) == 1 and posts[0].amount.commodity is None:
        raise ParseError(transaction.filename, transaction.linenum, "No transactions")

    for post in posts:
        account = post.account
        if account in aliases:
            account = aliases[post.account]
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

            makepost(account, transaction.date, post.amount.commodity, post.amount.value)
            #print (transaction[0],) + (acct,) + amount

    for commodity in amounts:
        if amounts[commodity] != decimal.Decimal("0"):
            if balanceaccount is not None:
                #print "Balancing post:", (transaction[0],) + (balanceacct,) + (key, amounts[key]*-1)
                makepost(balanceaccount, transaction.date, commodity, -amounts[commodity])
            else:
                raise ParseError(post.filename, post.linenum, "Transaction does not balance: %f %s outstanding" % (amounts[commodity], commodity))

# Parses a file, can be called recursively
def parse(reader,filename=None):

    bucket = None
    transaction = None
    accountdef = None
    posts = []
    for linenum, line in enumerate(reader):

        line = line.rstrip()
        # print "#%s" % line
        m = re.match(" *;", line)
        if line == '' or m:
            continue


        if transaction is not None:
            m = re.match("^ +(\w.+?)(  +(.*))?$", line)
            if m:
                print m.groups()
                amount = None
                if m.groups()[2] is not None:
                    amount = parseamount(m.groups()[2])
                post = Post(m.groups()[0],amount,filename,linenum)
                posts.append(post)
                continue
            else:
                maketransaction(transaction, posts, bucket)
                posts = []
                transaction = None

        if accountdef is not None:
            m = re.match("^ +(.*)$",line)
            if m:
                continue
            else:
                accountdef = None

        m = re.match("(\d{4}-\d{2}-\d{2})(=\d{4}-\d{2}-\d{2})? +(.*)", line)
        if m:
            transaction = Transaction(m.groups()[0],m.groups()[1],filename,linenum)
            continue

        m = re.match("commodity +(.*)", line)
        if m:
            continue

        m = re.match("account +(.*)", line)
        if m:
            accountdef = m.groups()
            continue

        m = re.match("include (.*)",line)
        if m:
            includefile = m.groups()[0]
            with open(includefile) as f:
                parse(f,includefile)
            continue

        m = re.match("bucket (.*)",line)
        if m:
            bucket = m.groups()[0]
            continue

        m = re.match("alias +(.*?) +(.*)",line)
        if m:
            aliases[m.groups()[0]] = m.groups()[1]
            continue

        raise ParseError(filename, linenum, "Don't know how to process \"%s\"" % line)

    if transaction is not None:
        maketransaction(transaction,posts,bucket)



if __name__ == "__main__":

    parser = argparse.ArgumentParser(description=' some integers.')
    parser.add_argument('-f','--filename', required=True, help='filename to load')
    parser.add_argument('-r','--reverse', help='reverse order of transactions')
    parser.add_argument("command", default='validate', choices=['balance', 'parse', 'validate'])

    args = parser.parse_args()

    with open(args.filename) as f:
        parse(f,args.filename)

    if args.command == "balance":
        accountkeys = accounts.keys()
        accountkeys.sort()

        maxlen = 0
        for account in accountkeys:
            maxlen = max(maxlen,len(account))

        print "Account".ljust(maxlen+1," "),
        for commodity in commodities:
            print commodity.rjust(10," "),
        print

        print "-" * (maxlen+1 + len(commodities)*11)
        for account in accountkeys:
            #print ":".join(reversed(account.split(":"))).rjust(maxlen+1," "),
            print account.ljust(maxlen+1,"."),
            b = balance(account)
            for i, commodity in enumerate(b):
                if commodity in b:
                    print str(b[commodity]).rjust(10," "),
                else:
                    print " " * 10,
            print
