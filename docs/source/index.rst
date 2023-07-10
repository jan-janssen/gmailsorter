.. gmailsorter documentation master file, created by
   sphinx-quickstart on Sun Jul 9 20:20:20 2023.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

gmailsorter - Automatically assign labels to new emails in Google Mail based on their similarity to previous emails assigned to the same label.
===============================================================================================================================================

The gmailsorter is a python module to automate the filtering of emails on the Google mail service using the their API.
It assigns labels to emails based on their similarity to other emails assigned to the same label.

Many people struggle with the increasing email volume leading to hundreds of unread emails. As the capabilities of even
the best search engine are limited when it comes to large numbers of emails, the only way to keep an overview is filing
emails into folders. The manual work of filing emails into folders is tedious, still most people are too lazy to create
email filters and keep their email filters up to date. Finally, in the age of mobile computing when most people access
their emails from their smartphone, the challenge of sorting emails is more relevant than ever.

The solution to this challenge is to automatically filter emails depending on their similarity to existing emails in a
given folder. This solution was already proposed in a couple of research papers ranging from the filtering of spam
emails `1 <https://doi.org/10.1016/j.heliyon.2019.e01802>`_ to the specific case of sorting emails into folders
`2 <https://people.cs.umass.edu/~mccallum/papers/foldering-tr05.pdf>`_. Even a couple of open source prototypes were
available like `3 <https://github.com/anthdm/ml-email-clustering>`_ and
`4 <https://github.com/andreykurenkov/emailinsight>`_.

This is basically a similar approach specific to the Google Mail API. It is a python script, which can be executed
periodically for example with a cron task to sort the emails for the user.

Documentation
-------------

.. toctree::
   :maxdepth: 2

   preparation
   configuration
   support
   developer