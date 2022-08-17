# Sort your emails automatically 
[![Python package](https://github.com/jan-janssen/pygmailsorter/actions/workflows/unittest.yml/badge.svg?branch=main)](https://github.com/jan-janssen/pygmailsorter/actions/workflows/unittest.yml)
[![Coverage Status](https://coveralls.io/repos/github/jan-janssen/pygmailsorter/badge.svg?branch=main)](https://coveralls.io/github/jan-janssen/pygmailsorter?branch=main)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

The `pygmailsorter` is a python module to automate the filtering of emails on the Google mail service using the their API. It assigns 
labels to emails based on their similarity to other emails assigned to the same label.

# Motivation 
Many people struggle with the increasing email volume leading to hundreds of unread emails. As the capabilities of even the best search engine are limited when it comes to large numbers of emails, the only way to keep an overview is filing emails into folders. The manual work of filing emails into folders is tedious, still most people are too lazy to create email filters and keep their email filters up to date. Finally, in the age of mobile computing when most people access their emails from their smartphone, the challenge of sorting emails is more relevant than ever. 

The solution to this challenge is to automatically filter emails depending on their similarity to existing emails in a given folder. This solution was already proposed in a couple of research papers ranging from the filtering of spam emails [1] to the specific case of sorting emails into folders [2]. Even a couple of open source prototypes were available like [3] and [4]. 

This is basically a similar approach specific to the Google Mail API. It is a python script, which can be executed periodically for example with a cron task to sort the emails for the user. 

[1]: https://doi.org/10.1016/j.heliyon.2019.e01802
[2]: https://people.cs.umass.edu/~mccallum/papers/foldering-tr05.pdf
[3]: https://github.com/anthdm/ml-email-clustering
[4]: https://github.com/andreykurenkov/emailinsight

# Installation 
The `pygmailsorter` is available on the conda-forge or pypi repositories and can be installed using either:
```
conda install -c conda-forge pygmailsorter
```
or alternatively: 
```
pip install pygmailsorter
```
After the installation the user has to create a Google Mail API credentials file `credentials.json` following the [Google Mail API documentation](https://support.google.com/googleapi/answer/6158862). This file is then stored in the configuration directory `~/.pygmailsorter/credentials.json`.

# Configuration 
The `pygmailsorter` stores the configuration files in the users home directory `~/.pygmailsorter`. This folder contains: 

- `~/.pygmailsorter/credentials.json` the authentication credentials for the Google API, which requires access to Gmail. 
- `~/.pygmailsorter/token_files` the token directory is used to store the active token for accessing the APIs, these are created 
  automatically, there should be no need for the user to modify these. 
- `~/.pygmailsorter/email.db` a local SQLite database to store the emails and machine learning models to accelerate the sorting. 

# Python interface 
Import the `pygmailsorter` module 
```
from pygmailsorter import Gmail
```

## Initialize pygmailsorter
Create a `gmail` object from the `Gmail()` class
```
gmail = Gmail()
```
For testing purposes you can use the optimal `client_service_file` parameter to specify the location of the 
authentication credentials in case they are not stored in `~/.pygmailsorter/credentials.json`.

## Download messages to pandas Dataframe
For offline processing it is helpful to download messages in bulk to pandas dataframes:  
```
gmail.download_messages_to_dataframe(message_id_lst)
```
The `message_id_lst` is a list of message ids, this can be obtained from `gmail.search_email()`. 

## Get email content as dictionary 
The content of the email rendered as python dictionary for further postprocessing: 
```
gmail.get_email_dict(message_id)
```
The `message_id` can be derived from a function like `gmail.search_email()`. 

## Update database
Update local database stored in `~/.pygmailsorter/email.db`:
```
gmail.update_database(quick=False)
```
By setting `quick` to `True` only new emails are downloaded, with `quick` set to `False` all emails are downloaded.

## Filter emails using machine learning
Assign new email labels to the emails with the label `"MyLabel"`:
```
gmail.filter_label_by_machine_learning(
    label="MyLabel", recalculate=True
)
```
By setting the optional parameter `recalculate` to `True` the machine learning models are fitted again to be up to date.

# Command Line interface 
The command line interface is currently rather limited, it supports the following options: 

- `pygmailsorter -c/--config=~/.pygmailsorter` the configuration directory can be specified manually.   
- `pygmailsorter -d/--database` update the local email database.  
- `pygmailsorter -m/--machinelearning=MyLabel` assign new labels to the emails with label `MyLabel`.

