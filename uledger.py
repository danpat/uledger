#!/usr/bin/env python

import argparse
import re
import decimal
import sys


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
            return (a[0],a[1]+b[1])

        m = re.match("\((.*?) +\* +(-?\d+(\.\d+)?) *\)",amountstr)
        if m:
            a = parseamount(m.groups()[0])
            b = decimal.Decimal(m.groups()[1])
            return (a[0],(a[1]*b).quantize(decimal.Decimal('.01'), rounding=decimal.ROUND_HALF_UP))

    # $-1234.34
    m = re.match("(\$) *(-?\d+(\.\d+)?)",amountstr)
    if m:
        return (m.groups()[0],decimal.Decimal(m.groups()[1]))

    # -123.43 CAD
    m = re.match("(-?\d+(\.\d+)?) (\w+)",amountstr)
    if m:
        return (m.groups()[-1],decimal.Decimal(m.groups()[0]))

def post(account,date,commodity,amount):

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


# Parses a file, can be called recursively
def parse(filename):
    bucket = None

    with open(filename) as f:
        transaction = None
        accountdef = None
        posts = []
        for linenum, line in enumerate(f):

            line = line.rstrip()
            # print "#%s" % line
            m = re.match(" *;", line)
            if line == '' or m:
                continue


            if transaction is not None:
                m = re.match("^ +(\w.+?)(  +(.*))?$", line)
                if m:
                    posts.append(m.groups())
                    continue
                else:
                    balanceacct = None
                    amounts = {}
                    if len(posts) == 0 or len(posts) == 1 and posts[0][2] is None:
                        print "ERROR: %s:%d" % (filename, linenum)
                        print "No transactions"
                        sys.exit(1)

                    for p in posts:
                        acct = p[0]
                        if acct in aliases:
                            acct = aliases[p[0]]
                        if p[2] == "" or p[2] is None:
                            if balanceacct is None:
                                balanceacct = acct
                            else:
                                print "ERROR %s:%d" % (filename, linenum)
                                print "Cannot have multiple empty posts"
                                sys.exit(1)
                        else:
                            amount = parseamount(p[2])
                            if amount is None:
                                print "ERROR %s:%d" % (filename, linenum)
                                print "Could not parse \"%s\"" % p[2]
                                sys.exit(1)
                            if amount[0] not in amounts:
                                amounts[amount[0]] = 0

                            amounts[amount[0]] += amount[1]

                            post(acct, transaction[0], amount[0], amount[1])
                            #print (transaction[0],) + (acct,) + amount

                    for key in amounts:
                        if amounts[key] != decimal.Decimal("0"):
                            if balanceacct is not None:
                                #print "Balancing post:", (transaction[0],) + (balanceacct,) + (key, amounts[key]*-1)
                                post(balanceacct, transaction[0], key, amounts[key]*-1)
                            elif bucket is not None:
                                #print "Balancing bucket post:", (transaction[0],) + (bucket,) + (key, amounts[key]*-1)
                                post(bucket, transaction[0], key, amounts[key]*-1)
                            else:
                                print "ERROR %s:%d" % (filename, linenum)
                                print "Transaction does not balance: %f %s outstanding" % (amounts[key], key)
                                sys.exit(1)


                    posts = []
                    transaction = None
                    balanceacct = None

            if accountdef is not None:
                m = re.match("^ +(.*)$",line)
                if m:
                    continue
                else:
                    accountdef = None

            m = re.match("(\d{4}-\d{2}-\d{2})(=\d{4}-\d{2}-\d{2})? +(.*)", line)
            if m:
                transaction = m.groups()
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
                parse(m.groups()[0])
                continue

            m = re.match("bucket (.*)",line)
            if m:
                bucket = m.groups()[0]
                continue

            m = re.match("alias +(.*?) +(.*)",line)
            if m:
                aliases[m.groups()[0]] = m.groups()[1]
                continue

            print "ERROR on line %s:%d" % (filename,linenum+1)
            print "    -> %s" % line
            sys.exit(1)

def balances():
    None



if __name__ == "__main__":

    parser = argparse.ArgumentParser(description=' some integers.')
    parser.add_argument('-f','--filename', required=True, help='filename to load')
    parser.add_argument('-r','--reverse', help='reverse order of transactions')
    parser.add_argument("command", default='validate', choices=['balance', 'parse', 'validate'])

    args = parser.parse_args()

    parse(args.filename)

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
