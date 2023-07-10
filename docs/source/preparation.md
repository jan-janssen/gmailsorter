# Preparation 
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

Before using `gmailsorter` you first have to sort your emails manually. This step is necessary for `gmailsorter` to 
learn your preferences. 

## Sort your emails
Tips for sorting emails can be found everywhere on the internet. 

## Backup and remove your previous email filters 
Having multiple filters sorting your emails at the same time can result in conflicts, therefore it is recommended to 
backup and remove all existing email filters

## Create one separate label as inbox for gmailsorter
As `gmailsorter` is only checking your emails once every five minutes, it is recommended to transfer all your emails to
a separate label for `gmailsorter` to sort them from there to other labels. 