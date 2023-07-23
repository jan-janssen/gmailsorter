# Preparation 
The gmailsorter is a python module to automate the filtering of emails on the Google mail service using the their API.
It assigns labels to emails based on their similarity to other emails assigned to the same label.

Many people struggle with the increasing email volume leading to hundreds of unread emails. As the capabilities of even
the best search engine are limited when it comes to large numbers of emails, the only way to keep an overview is 
filtering emails into folders. The manual process of filtering emails into folders is tedious, still most people are too
lazy to create email filters and keep their email filters up to date. Finally, in the age of mobile computing when most
people access their emails from their smartphone, the challenge of sorting emails is more relevant than ever.

The solution to this challenge is to automatically filter emails depending on their similarity to existing emails in a
given folder. This solution was already proposed in a couple of research papers ranging from the filtering of spam
emails `E.G. Dada et al. <https://doi.org/10.1016/j.heliyon.2019.e01802>`_ to the specific case of sorting emails into 
folders `R. Bekkerman et al. <https://people.cs.umass.edu/~mccallum/papers/foldering-tr05.pdf>`_. Even a couple of 
opensource prototypes are available like `ml-email-clustering <https://github.com/anthdm/ml-email-clustering>`_ and
`emailinsight <https://github.com/andreykurenkov/emailinsight>`_.

Gmailsorter is a similar approach specific to the Google Mail API. Before using `gmailsorter` you first have to sort 
your emails manually. This step is necessary for `gmailsorter` to learn your preferences. 

## Sort your emails
While the ordering of information is generally a very personal topic, with no one solution which fits anybody. Still 
some general considerations can be helpful to sort emails your emails: 

* How many emails go into one email folder? And how many email folders do you need? It is typically suggested to start 
  with around ten email folders with each folder containing more or less the same amount of emails. 
* To sort your email folders you can start their names with a number, this enforces the right order of email folders 
  independent of the email client. 
* For `gmailsorter` to be able to learn how to threat any kind of income emails, it makes sense to have an email folder
  for emails you plan to delete. These could be newsletters, spam messages or other unrelated emails. 

Before you activate `gmailsorter` is it essential that you clean up your whole inbox and sort each email into a folder.
Do not delete the emails even if they are irrelevant. To sort your emails you can use your favorite email client or
alternatively you can login to Google Mail and sort your emails using their web interface. 

## Configure your email account 
For the following two steps please login to the Google Mail web interface. 

### Backup and remove your previous email filters 
Having multiple programs filter your emails at the same time can result in conflicts, therefore it is recommended to 
backup all existing email filters and remove them afterwards. Google Mail provides a detailed explanation how to [export
your email filters](https://support.google.com/mail/answer/6579?hl=en) and delete them afterwards. Please also check 
your email clients if you have any email filters configured in the email clients you use to access your Google Mail 
account. If you have email filters configured in your email clients, backup those as well and delete them afterwards. 

### Create one separate label as inbox for gmailsorter
To minimize the interruption of incoming emails, it is recommended to create a new inbox. Create a new email folder in 
Google Mail named `mailsortinbox`. The `gmailsorter` is then going to create one new email filter during the first 
login to redirect all emails from your inbox to this new `mailsortinbox` folder. Emails in the `mailsortinbox` folder
are then periodically sorted using `gmailsorter`, typically every five minutes.