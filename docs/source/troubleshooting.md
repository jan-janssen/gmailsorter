# Troubleshooting
`gmailsorter` is under active development, so things occasionally go wrong. This page collects fixes for the
problems users run into most often - most of them previously only existed as answers to individual
[GitHub issues](https://github.com/jan-janssen/gmailsorter/issues). If your problem is not listed here, please
[open a new issue](https://github.com/jan-janssen/gmailsorter/issues/new) - real questions become the next entry on
this page.

## Understanding the status page
Once you are logged in, the gmailsorter web interface shows the status of four steps for your account:

* `mailsortinbox label configured` - whether the `mailsortinbox` label from [Preparation](preparation) exists.
* `email filter configured` - whether the filter that redirects new emails into `mailsortinbox` exists.
* `machine learning model update` - whether your local email database was synchronized and the machine learning
  models were (re-)trained, see [How gmailsorter works](architecture).
* `email sorting` - whether new emails in `mailsortinbox` were most recently sorted successfully.

Each entry is colour coded: <span style="color:MediumSeaGreen;">green</span> means the step last completed
successfully, <span style="color:Orange;">orange</span> means it is queued or currently running, and
<span style="color:Tomato;">red</span> means it failed. A single failed or in-progress step is normal right after
you sign in for the first time - the initial import of a large mailbox can take up to an hour.

## Email sorting is stuck or shows an error
If `email sorting` or `machine learning model update` stays red or orange for a long time (well beyond the initial
import), a **Reset Status** button appears below the status list. Clicking it clears the stuck status so the next
scheduled run starts fresh - it does not touch your emails or labels, it only resets the internal bookkeeping.

If the button does not appear even though a step is failing, you can trigger the same reset directly by visiting
the `/reset` page of your gmailsorter instance while logged in, for example `https://gmailsorter.com/reset` for the
hosted service, or `http://localhost:8080/reset` if you are running your own Docker container or Python
installation.

If the status keeps failing right after a reset, check the next section - a failing status is frequently caused by
an expired or revoked login token rather than a problem with the sorting itself.

## "Token has been expired or revoked" / "Insufficient Permission"
Google access tokens can stop working if they expire, if you changed your Google account password, or if you (or
Google) revoked gmailsorter's access. Both errors are fixed the same way:

1. Open [Google Account - Third-party apps & services](https://myaccount.google.com/connections) while logged into
   the Google account you use with gmailsorter.
2. Find `gmailsorter` (or the name you gave your own OAuth client if you configured your own Google Cloud project,
   see [Configuration](configuration)) in the list and remove its access.
3. Go back to the gmailsorter web interface, log out if necessary, and sign in again with `sign in with Google`.
4. On the permissions screen, make sure to select **all** requested permissions - `Insufficient Permission` errors
   are almost always caused by a scope that was not granted during login.

## I run my own Docker container and it keeps crashing
The background daemon updates every registered account on a schedule (by default every five minutes, see
[Configuration](configuration)). If you self-host gmailsorter for many accounts or very large mailboxes, this can
require more memory than the container has available, which shows up as unexpected container restarts. Reducing the
number of accounts sharing one container, or increasing the memory available to Docker, resolves this.

## Still stuck?
Please [open an issue on GitHub](https://github.com/jan-janssen/gmailsorter/issues) with as much detail as you can
provide - the Google Cloud project setup you followed, whether you use the hosted service, Docker or the Python
package, and the exact error message or status you see. See [Support](support) for how the project is maintained.
