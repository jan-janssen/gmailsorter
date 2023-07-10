# Developer
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