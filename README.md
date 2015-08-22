# uledger
Minimalist python clone of ledger-cli.

This is a small, pure-python implementation that supports some of the `ledger-cli` file format.

It primarily exists because `ledger-cli` does not sort by date.  This makes it difficult to import
transactions out-of-order, and perform balance assertions periodically in the journal. `hledger`
supports this, but I found the installation rather onerous for my needs.

This implementation currently supports the following:

    alias groceries Expenses:Groceries
    bucket Asssets:Bank1
    YYYY-MM-DD Example description
        groceries                     ($123 * 1.05)

Also supported is the "include" keyword.
