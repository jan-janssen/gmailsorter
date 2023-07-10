# Configuration 
Choose a gmailsorter version 

## Web service 
- Sign up to waiting / mailing list 
- Authenticate by login via google 
- Get your email sorted

## Docker container 
- Boot container 
- Authenticate by login via google 
- Get your email sorted

## Python interface

### Install package 
The `gmailsorter` is available on the conda-forge or pypi repositories and can be installed using either:
```
conda install -c conda-forge gmailsorter
```
or alternatively: 
```
pip install gmailsorter
```

### Authenticate by login via Google
The `gmailsorter` requires two steps of configuration:
* The user has to create a Google Mail API credentials file `credentials.json` following the 
  [Google Mail API documentation](https://support.google.com/googleapi/answer/6158862). 
* Access to an SQL database, this can be provided as `connection string`, alternatively `gmailsorter` is going to use
  a local SQLite database named `email.db` located in the current directory. This results in the following 
  `connection string`: `sqlite:///email.db`

### Get your email sorted 
The command line interface implements the same functionality as the Python interface, it supports the following options: 

- `gmailsorter -c/--credentials` path to credentials file provided by Google e.g. `credentials.json` .  
- `gmailsorter -d/--database` connection string to connect to database e.g. `sqlite:///email.db` .
- `gmailsorter -u/--update` update the local email database and retrain the machine learning model.  
- `gmailsorter -l/--label=MyLabel` assign new labels to the emails with label `MyLabel`.
- `gmailsorter -p/--port` port for authentication webserver to run e.g. `8080` .

