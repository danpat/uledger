import os
import shutil

def make_category(f,org,category,balances,ledger,asof,positive):
    accountnames = balances.keys()
    accountnames.sort()
    f.write("<table>")
    f.write("<thead><tr><td colspan='2'>%s</td></tr></thead>" % category)
    f.write("<tbody>")
    for account in [i[len(org+":"+category)+1:] for i in accountnames if (org+":"+category in i and org+":"+category != i)]:
        if len(balances[org+":"+category+":"+account]) == 0 or \
                sum(balances[org+":"+category+":"+account].values()) == 0:
                    continue

        f.write("<tr><td class='subcat'>%s</td><td class='total'>" % account)
        if len(balances[org+":"+category+":"+account]) == 0:
            f.write("-")
        else:
            f.write("<br/>".join(
                "%s %.2f" % (commodity, amount * (1 if positive else -1)) for (commodity,amount) in balances[org+":"+category+":"+account].items() if amount != 0
            ))
        f.write("</tr>")

    f.write("</tbody>")
    f.write("<tfoot><tr><td>Total</td><td class='total'>")
    if len(ledger.balance_children(org+":"+category,asof)) == 0:
        f.write("-")
    else:
        f.write("<br/>".join(
            "%s %.2f" % (commodity, amount * (1 if positive else -1)) for (commodity,amount) in ledger.balance_children(org+":"+category,asof).items()
        ))
    f.write("</tr></tfoot>")
    f.write("</table>")

def make_report(ledger,destdir):

    startdate = ledger.startdate()
    enddate = ledger.enddate()

    firstyear = startdate.split("-")[0]
    endyear = enddate.split("-")[0]

    # Year by year

    categories = ["Expenses","Assets","Liabilities","Income","Equity"]

    positive = { "Expenses": True, "Assets":True, "Liabilities":False, "Income": False, "Equity":False }

    if not os.path.isdir(os.path.join(destdir,"css")):
        shutil.copytree(os.path.join(os.path.dirname(__file__), "css"), os.path.join(destdir,"css"))

    with open(os.path.join(destdir,"report.html"),"w") as f:
        f.write("<!DOCTYPE html>")
        f.write("<html><head><title>Report</title>")

        f.write("""
        <link href="http://fonts.googleapis.com/css?family=Raleway:400,300,600" rel="stylesheet" type="text/css">

        <!-- CSS -->
        <link rel="stylesheet" href="css/normalize.css">
        <link rel="stylesheet" href="css/skeleton.css">


        <style type='text/css'>
        * { font-family: sans-serif; margin: 0; padding: 0;}
        html { font-size: 50%; }
        h3 { border-bottom: 3px solid black; background: black; color: white; }
        h4 { border-bottom: 1px solid black; }
        table { border-collapse: collapse; width: 100%}
        td { vertical-align: top; }
        td.subcat { padding-left: 1em; }
        .total { text-align: right; white-space: nowrap; }
        thead td { font-weight: bold; border-bottom: 2px solid black; padding-left: 1.25rem }
        tfoot td { font-weight: bold; border-top: 3px double black;  padding-left: 1.25rem }
        td { padding-top: 0.1rem; padding-bottom: 0.1rem; }
        .category { float: left; padding: 1em; margin: 1em; width: 50% }
        .year { page-break-after:always; }
        </style>""")
        f.write("</head>");
        f.write("<body>")

        for year in range(int(endyear),int(firstyear)-1,-1):
            asof = "%d-12-31" % year
            balances = ledger.balances(asof)

            orgs = set()
            for account in balances.keys():
                orgs.add(account.split(":")[0])

            for org in orgs:
                f.write("<div class='container year'>")
                f.write("<h4>%s %d</h4>" % (org, year))
                f.write("<div class='row'>")
                for categories in [["Assets"],["Liabilities","Equity"]]:
                    f.write("<div class='six columns'>")
                    for category in categories:
                        make_category(f, org, category, balances, ledger, asof, positive[category])
                    f.write("</div>")
                f.write("</div>")

                f.write("<div class='row'>")
                for categories in [["Income"],["Expenses"]]:
                    f.write("<div class='six columns'>")
                    for category in categories:
                        make_category(f, org, category, balances, ledger, asof, positive[category])
                    f.write("</div>")
                f.write("</div>")


                f.write("</div>")
        f.write("</body>")
        f.write("</html>")

    print "Report written to %s" % os.path.join(destdir,"report.html")
