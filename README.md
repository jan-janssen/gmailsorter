# Sort your emails automatically 
[![Python package](https://github.com/jan-janssen/gmailsorter/actions/workflows/unittest.yml/badge.svg?branch=main)](https://github.com/jan-janssen/gmailsorter/actions/workflows/unittest.yml)
[![Coverage Status](https://coveralls.io/repos/github/jan-janssen/gmailsorter/badge.svg?branch=main)](https://coveralls.io/github/jan-janssen/gmailsorter?branch=main)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

The `gmailsorter` is a python module to automate the filtering of emails on the Google mail service using the their API. It assigns 
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
The `gmailsorter` is available on the conda-forge or pypi repositories and can be installed using either:
```
conda install -c conda-forge gmailsorter
```
or alternatively: 
```
pip install gmailsorter
```

# Configuration 
The `gmailsorter` requires two steps of configuration:
* The user has to create a Google Mail API credentials file `credentials.json` following the 
  [Google Mail API documentation](https://support.google.com/googleapi/answer/6158862). 
* Access to an SQL database, this can be provided as `connection string`, alternatively `gmailsorter` is going to use
  a local SQLite database named `email.db` located in the current directory. This results in the following 
  `connection string`: `sqlite:///email.db`

# Python interface 
Import the `Gmail` class and the function `load_client_secrets_file` from the `gmailsorter` module 
```
from gmailsorter import Gmail, load_client_secrets_file
```

## Initialize gmailsorter
Create a `gmail` object from the `Gmail()` class:
```
gmail = Gmail(
    client_config=load_client_secrets_file(
        client_secrets_file="/absolute/path/to/credentials.json"
    ),
    connection_str="sqlite:////absolute/path/to/email.db",
)
```
Based on the configuration from the previous section, the function `load_client_secrets_file` is used to load the
`credentials.json` file and provide its content as python dictionary to the `client_config` parameter of the `Gmail()`
class. In addition to the `client_config` parameter the `Gmail()` class also requires a connection to an SQL database
which is provided as `connection_str`. In addition the `email_download_format` can be specified as either `metadata` or 
`full`, where the primary difference is whether the content of the email is stored or not. Finally, as optional 
parameter the `port` can be specified which is used to authenticate the Google Mail API via a web browser, by default 
this `8080`.  

## Sync local database with email account
To reduce the communication overhead, the emails are stored locally in an SQLite database.
```
gmail.update_database(quick=False)
```
By setting the optional flag `quick` to `True` only new emails are downloaded while changes to existing emails are 
ignored.

## Generate pandas dataframe for emails
Load all emails from the local SQLite database and combine them in a pandas DataFrame for further postprocessing: 
```
df = gmail.get_all_emails_in_database()
```

## Download specific label from email server
Download emails with the label `"MyLabel"` from the email server:
```
df = gmail.download_emails_for_label(label="MyLabel")
```
In this case the emails are not stored in the local SQLite database. 

## Filter emails using machine learning
Assign new email labels to the emails with the label `"MyLabel"`:
```
gmail.filter_messages_from_server
    label="MyLabel",
    recommendation_ratio=0.9,
)
```
This functionality is based on the `download_emails_for_label()` function above. It checks the server for new emails for
a selected label `"MyLabel"`. Then reloads the machine learning model from the local SQLite database and trys to predict
the correct labels for these emails. The `recommendation_ratio` defines the level of certainty required to actually move
the email, with `0.9` equalling a certainty of 90%. 

# Command Line interface 
The command line interface implements the same functionality as the Python interface, it supports the following options: 

- `gmailsorter -c/--credentials` path to credentials file provided by Google e.g. `credentials.json` .  
- `gmailsorter -d/--database` connection string to connect to database e.g. `sqlite:///email.db` .
- `gmailsorter -u/--update` update the local email database and retrain the machine learning model.  
- `gmailsorter -l/--label=MyLabel` assign new labels to the emails with label `MyLabel`.
- `gmailsorter -p/--port` port for authentication webserver to run e.g. `8080` .

