"""The data sources the archiver ingests, all of them public and compliant.

Each source is an adapter that maps an external, *authorized* feed or API onto
one shared row-dict contract, so everything lands in the same ``statuses`` table
and differs only by the ``source`` column:

    federal_register        Executive orders, proclamations, memoranda (public domain)
    presidential_documents  Trump's remarks, statements, messages (public domain)
    whitehouse              whitehouse.gov statements and releases (RSS)
    news                    Third-party coverage about Trump (Google News RSS)
"""
