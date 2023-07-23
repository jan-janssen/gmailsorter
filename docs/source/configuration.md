# Configuration 
While the `gmailsorter` package is currently still under development, there are three possible configuration:

* The easiest is currently to use the hosted [gmailsorter.com](https://gmailsorter.com) email service. This service is 
  based on the [Oracle cloud infrastructure](https://www.oracle.com/cloud/).
* The second variant is running a personal gmailsorter instance as docker container. In this configuration your data
  remains on your own docker container and no data is shared with third party providers. 
* Finally, for developers gmailsorter can be installed in any Python environment. This simplifies the development 
  process but is restricted to a single email address to be sorted.

At the current stage the docker container based version is recommended.

## Gmailsorter.com 
The [gmailsorter.com](https://gmailsorter.com) web service is currently in private beta. If you are interested to try it
out please email `jan.janssen@outlook.com` and ask for access to the private beta. 

## Docker container 
The docker container based version is currently recommended for all users.

### Setup Google Cloud Application 
The following GIF gives an overview of the required steps, they are explained in more detail below:
![configure google access token](_static/configure_google_access_token.gif)

* Login to the [Google cloud console](http://console.cloud.google.com).
* Click on the top menu to open the `select a project` dialog. 
* In the `select a project` dialog, click on the `New project` button in the top right corner. 
* In the `New Project` dialog you can specify a name of your project, afterwards the project can be created by clicking 
  on the `create` button.
* Once the project is created, you are redirected to the overview page again. Here you again open the `select a project`
  dialog to select your newly created project. After you selected your new project you should see the `select a project` 
  button in the top left displaying the name of your selected project. 
* Use the `Quick Access` menu to navigate to the `API & Services` section. 
* In the `API & Services` tab click the `+ Enable APIs and services` button to add the Google Mail API. 
* In the `API Library` search for `GMail API` and select the entry `GMail API` from the search results. 
* On the `Product details` page for the `GMail API` click `enable` to enable this API for your project. Afterwards you 
  are redirected to the `API & Services` tab again. 
* From the left menu select the `OAuth consent screen` entry.
* On the initial page of the `OAuth consent screen` dialog select `User Type` as `External`. The option `Internal` is 
  only available for `Google Workspace` accounts, so it is not discussed in more details here. Afterwards click `create`
  to start the four step process to create an `OAuth consent screen` for your project. 
* On the first page you have to enter the `App information`. This includes the name of the application, the selection of
  an `user support email` from the dropdown menu and finally you want to enter your email in the `Developer contact information` 
  field. Afterwards complete the first step by clickling `save and continue`.
* In the next step the `Scopes` for the project can be defined. You can add additional scopes by clicking on `add or remove scopes`. 
  In the `update selected scopes` dialog, select the following scopes: `.../auth/userinfo.email`, 
  `.../auth/userinfo.profile`, `openid`, `.../auth/gmail.modify` and `.../auth/gmail.settings.basic`. The last two are
  on pages three and four respectively. Once all five scopes are selected you can click `update` at the bottom of the 
  `add or remove scopes` dialog. 
* Back on the `Scopes` page you can again click `save and continue`. 
* On the `Test users` page you can add yourself as test user by clicking on `+ add users`, entering your email address
  and confirming with `add`. Once you added your users you can again click `save and continue` to progress.
* On the final `Summary` page all the information are summarized. So you can scroll to the bottom and return to the main
  menu by clicking `Back to dashboard`.
* Finally, select the entry `Credentials` from the left menu and open the `Credentials` dialog. 
* In the `Credentials` dialog click `+ Create credentials` to create a new `OAuth client ID`. 
* In the `Create OAuth client ID` dialog select `Web application` as application type. 
* Afterwards you can specify the name of your application, in addition to the `Authorized Javascript origins` and 
  `Authorized redirect URIs`. As `Authorized Javascript origins` add `http://localhost:8080` and as `Authorized redirect URIs`
  enter `http://localhost:8080/oauth2callback`. This URI changed from the version in the GIF above from `http://localhost:8080/auth2callback`
  to `http://localhost:8080/oauth2callback`. Finish the creation of the oauth client ID by clicking `create`.
* From the `oAuth client created` dialog click the `Download JSON` button to download the credentials file and save it 
  to your `Downloads` folder on your local hard drive.

At this stage the configuration of the Google project is completed and you can exit the Google cloud console. 

### Download and start the docker container
The following GIF gives an overview of the required steps, they are explained in more detail below:
![start docker](_static/start_docker.gif)

At the current stage no pre-build docker images are available. So the docker image is build from the git repository 
directly: 
* Clone the git repository from Github using `git clone https://github.com/jan-janssen/gmailsorter`.
* Navigate into the folder of the repository `cd gmailsorter`.
* Create a `tmp` directory in the repository `mkdir tmp`. This folder is mounted to the docker container to provide easy
  access to the core files. These contain the credentials JSON file `credentials.json`, the SQLite database `email.db` 
  as well as the log files `fetch.err`, `fetch.out`, `update.err` and `update.out`. All these files can be accessed 
  directly from the host operation system rather than requiring access via the Docker container. 
* Move the credentials file from configuring the google cloud application to the `tmp` folder `mv ~/Downloads/*.json credentials.json`.
* Navigate back to the root of the repository `cd ..`.
* Start the build process of the docker image using `docker build -t gmailsorter .` . Depending on your internet 
  connection this step can take a couple of minutes. 
* Finally, once the docker container is build it can be started with `docker run -d -p 8080:8080 -v /Users/jan/Desktop/gmailsorter/tmp:/tmp -e MAILSORT_ENV_SECRET_KEY='e0f9eb0f0a16667771fa697ccbfaec952c410c6eaab54868' gmailsorter`. 
  In this command `-d` starts the docker container in daemon mode. `-p 8080:8080` redirects the port `8080` from the 
  docker container to the same port of the host system. `-v /Users/jan/Desktop/gmailsorter/tmp:/tmp` mounts the `tmp`
  directory of the repository `/Users/jan/Desktop/gmailsorter/tmp` to the `/tmp` directory of the docker container. The
  parameter `-e MAILSORT_ENV_SECRET_KEY='e0f9eb0f0a16667771fa697ccbfaec952c410c6eaab54868'` specifies the secret used 
  to encrypt the login authentication, so please do not use this key but rather create your own one. 
* Once the docker container is started successfully, you can navigate to [localhost:8080](http://localhost:8080) to 
  access the web interface. 

By default the docker container is designed to update all registered email accounts every five minutes. Depending on the
number of users and emails per user this can require quite some resources, in particular limited memory can result in
unexpected crashes. 

### Link Google account to gmailsorter
The following GIF gives an overview of the required steps, they are explained in more detail below:
![first login](_static/first_login.gif)

The web interface for gmailsorter is designed to be minimalistic.
* Navigate to the gmailsorter web interface [localhost:8080](http://localhost:8080). 
* Click the `sign in with Google` button.
* This redirects you to the `Sign in with Google` dialog where you can select the Google account you want to use with
  gmailsorter. 
* On the following `Google hasn't verified this app` screen you are informed that gmailsorter is not yet verified. Still
  you can click the `Continue` button in the bottom left corner to continue. 
* Afterwards you are informed about the required access, mark the `Select all` option to use gmailsorter with your Google
  account. At the bottom of the page confirm your choice by clicking `continue`. 
* You are then redirected to the gmailsorter webinterface. 

In the background gmailsorter starts to initialize your email account, depending on your internet connection and number
of emails in your account, this can take up to an hour. You can leave the gmailsorter web interface at this point, just
make sure the docker container continues running. 

## Python interface
To allow developers to implement their own algorithms for email sorting, gmailsorter provides an additional python 
interface. This is recommended for advanced users only. 

### Install gmailsorter package 
The `gmailsorter` is available on the conda-forge or pypi repositories and can be installed using either:
```
conda install -c conda-forge gmailsorter
```
or alternatively: 
```
pip install gmailsorter
```

### Setup Google Cloud Application 
Read the section above for the docker container, the configuration of the Google cloud console project is identical. 

### Start the web application 
The gmailsorter python application requires three environment variables: 
```
export MAILSORT_ENV_CREDENTIALS_FILE='/Users/jan/Desktop/gmailsorter/tmp/credentials.json'
export MAILSORT_ENV_DATABASE_URL='sqlite:////Users/jan/Desktop/gmailsorter/tmp/email.db'
export MAILSORT_ENV_SECRET_KEY='e0f9eb0f0a16667771fa697ccbfaec952c410c6eaab54868'
```
The credentials file `MAILSORT_ENV_CREDENTIALS_FILE` points to the credentials file you downloaded at the end of the 
previous set. The database url `MAILSORT_ENV_DATABASE_URL` defines the connection to the database as connection string.
By default gmailsorter uses a simple SQLite database, but most SQL databases are supported. Finally, the secret key 
`MAILSORT_ENV_SECRET_KEY` for the encryption of login information is exported as environment variable as well. Again, 
please do not use the secret provided here, but rather generate your own. 

Once the environment variables are specified gmailsorted can be started using `python -m gmailsorter.webapp` . The 
application can then be accessed via the web interface at [localhost:8080](http://localhost:8080).

### Link Google account to gmailsorter
Read the section above for the docker container, the linking of the Google account to gmailsorter is identical. 

### Sort emails with gmailsorter
In contrast to the webservice and the docker container the python packages does not include periodically scheduled 
updates of the database or tasks to sort your emails. Instead these can be triggered on the command line using: 
```
gmailsorter-daemon -s -c ${MAILSORT_ENV_CREDENTIALS_FILE} -d ${MAILSORT_ENV_DATABASE_URL}
```
and: 
```
gmailsorter-daemon -u -c ${MAILSORT_ENV_CREDENTIALS_FILE} -d ${MAILSORT_ENV_DATABASE_URL}
```

Here the command line options refer to the following settings:
- `-c/--credentials` path to credentials file provided by Google e.g. `credentials.json` .  
- `-d/--database` connection string to connect to database e.g. `sqlite:///email.db` .
- `-u/--update` update the local email database and retrain the machine learning model.  
- `-s/--scheduled` sort emails to email folders using the previously trained machine learning model. 

With these commands the gmailsorter service can be configured on bare metal without the need for any containerization
solution. 