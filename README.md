# Sort your emails automatically 
[![Python package](https://github.com/jan-janssen/pygmailsorter/actions/workflows/unittest.yml/badge.svg?branch=main)](https://github.com/jan-janssen/pygmailsorter/actions/workflows/unittest.yml)
[![Coverage Status](https://coveralls.io/repos/github/jan-janssen/pygmailsorter/badge.svg?branch=main)](https://coveralls.io/github/jan-janssen/pygmailsorter?branch=main)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

The `pygmailsorter` is a python module to automate the filtering of emails on Gmail using the Gmail API. It assigns 
labels to emails based on their similarity to other emails assigned to the same label.

# Configuration 
The `pygmailsorter` stores the configuration files in the users home directory `~/.pygmailsorter`. This folder contains: 

- `credentials.json` the authentication credentials for the Google API, which requires access to Gmail. 
- `token_files` the token directory is used to store the active token for accessing the APIs, these are created 
  automatically, there should be no need for the user to modify these. 
- `email.db` a local SQLite database to store the emails and machine learning models to accelerate the sorting. 

# Installation 
Install the package from github using `pip`: 
```
pip install git+https://github.com/jan-janssen/pygmailsorter.git
```
Finally, setup the `credentials.json` in your Google Apps and store it in `~/.pygmailsorter/credentials.json`.

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

