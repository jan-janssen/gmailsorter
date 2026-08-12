# How gmailsorter works
This page explains what actually happens behind the scenes when `gmailsorter` sorts your emails. It is written for
curious users who want to understand the mechanics before trusting a program to move their emails around - no prior
machine learning knowledge required. If you are looking for setup instructions instead, see
[Preparation](preparation) and [Configuration](configuration). If you are looking for the Python API, see
[Developer](developer).

## The big picture
Regardless of whether you use the hosted [gmailsorter.com](https://gmailsorter.com) service, the Docker container or
the plain Python package, `gmailsorter` is built from the same three building blocks:

* **Your Google Mail account** - the source of truth for your emails and labels, accessed exclusively through the
  official [Gmail API](https://developers.google.com/gmail/api/guides). `gmailsorter` never reads your mailbox
  through any other channel and never stores your Google password.
* **A local database** - a SQL database (SQLite by default, though any database supported by
  [SQLAlchemy](https://www.sqlalchemy.org/) works) that keeps a private copy of your email metadata, your login
  token and your trained models. In the Docker container and the plain Python package this database lives entirely
  on your own machine.
* **One shared machine learning model** - a single classifier trained purely on your own historic emails, which
  predicts every label at once and is used to recommend a label for each new email that arrives in your
  `mailsortinbox` folder.

A background job (the `gmailsorter-daemon`, packaged as a cron job in the Docker container, or triggered manually
from the command line) repeats a simple loop every few minutes: fetch, store, train, predict, move.

## The fetch-store-train-predict-move loop

### 1. Fetch
`gmailsorter` asks the Gmail API for the list of message IDs that currently carry a given label (for example your
`mailsortinbox` label, or - during the initial import - every label you already sorted your inbox into). Only
message IDs and metadata are requested at this stage, so this step is cheap and fast even for large mailboxes.

### 2. Store
For every message ID that is not yet known locally, `gmailsorter` downloads the message and splits it into several
normalized tables in the local database: the message content and subject, its thread, its `to`/`cc`/`from`
addresses and the labels currently assigned to it. Messages that disappear from the server (for example because you
deleted them) are marked as deleted rather than removed, so your training history stays intact. This mirrors how a
relational database would model any many-to-many relationship - one email can have many recipients and many labels,
so each of those gets its own table linked back to the email by its ID.

### 3. Train
This is the step that is easy to get wrong when described casually, so let's be precise: **gmailsorter does not
read the text of your emails to judge similarity.** Instead it looks at the metadata surrounding each email you
have already sorted:

* who sent it, and the domain of the sender (e.g. `@newsletter.example.com`),
* everyone it was addressed to or copied on,
* and which labels you have assigned to it.

Each of these values is turned into a binary "yes/no" column through
[one-hot encoding](https://en.wikipedia.org/wiki/One-hot) (implemented in
[`gmailsorter/ml/encoding.py`](https://github.com/jan-janssen/gmailsorter/blob/main/gmailsorter/ml/encoding.py)) -
so instead of one column "sender", you get one column per sender that is either `1` or `0`. Because most of these
columns are `0` for any given email, they are kept as a sparse matrix rather than a dense table, which keeps memory
use low even for large mailboxes. The email thread is deliberately left out of this encoding: a thread ID is close
to unique per email, so turning it into a column would let the model memorize individual training threads instead
of learning a pattern that generalizes to new mail.

`gmailsorter` then trains a single [random forest classifier](https://en.wikipedia.org/wiki/Random_forest) that
predicts every label at once (see
[`gmailsorter/ml/model.py`](https://github.com/jan-janssen/gmailsorter/blob/main/gmailsorter/ml/model.py)), answering
the question "which of my labels does this email belong to, based on who sent it, who else received it and what
other labels tend to go together?". Training one shared model instead of a separate model per label lets related
labels (e.g. several senders from the same domain) reinforce each other during training, and keeps both memory use
and the size of the model stored in the database roughly constant as you add more labels. In practice this captures
the intuition most people actually sort emails by - the sender, the mailing list or the group of people involved -
rather than trying to summarize free text.

The trained model is serialized and stored back in your local database, together with the exact list of columns
it was trained on, so it can be reloaded without retraining every time.

### 4. Predict
When a new email lands in your `mailsortinbox` folder, `gmailsorter` encodes it using the very same columns the
model was trained on and asks it "how confident are you that this email belongs to each of your labels?". The
label with the highest confidence wins, but only if that confidence clears the `recommendation_ratio` threshold
(90% by default). If no label is confident enough, the email is simply left where it is until the next run, once
more training data has made the model more confident.

### 5. Move
If a label was recommended with sufficient confidence, `gmailsorter` calls the Gmail API to remove the
`mailsortinbox` label and add the recommended label - the same action you would take by hand by dragging the email
into a folder. Nothing is deleted or archived silently; the email simply moves to the folder you would have put it
in yourself.

## Learning from your corrections
`gmailsorter` does not try to be clever about disagreements - it relies entirely on your labels. If you move an
email to a different label than the one `gmailsorter` suggested, that correction becomes part of the training data
the next time models are retrained (step 3), because training always reads the labels that are currently on your
emails, not the labels `gmailsorter` last predicted. There is no separate feedback API to call; simply sorting your
email as you normally would is enough.

## What is stored, and where
The local database contains:

* your email metadata (subject, thread, sender, recipients, labels and dates) - not a shared, cross-user index. Each
  row is scoped to a `user_id`, so a single database can serve multiple accounts without mixing their data.
* your Google OAuth token (access token, refresh token and expiry), so you do not have to sign in again every few
  minutes.
* your trained model, serialized with [pickle](https://docs.python.org/3/library/pickle.html).

When you run the Docker container or the plain Python package yourself, this database lives exclusively in the
`tmp` folder on your own machine - nothing is shared with the [gmailsorter.com](https://gmailsorter.com) service or
any other third party. The [gmailsorter.com](https://gmailsorter.com) service uses the same code, but the database
is naturally hosted on that service's infrastructure instead of yours - see [Configuration](configuration) to pick
the deployment that matches your comfort level.

## Limitations to be aware of
* The model only learns from labels you already applied by hand, so a brand-new label with very few emails behind
  it will rarely reach the 90% confidence needed to be suggested - this is intentional, to avoid confidently wrong
  guesses, but it does mean new folders take a little time to "warm up".
* Because the model deliberately ignores email body text, two emails with very similar content but no overlapping
  sender or recipients will not be linked by `gmailsorter` today. See
  [Developer - Future directions](developer) for the direction this may take next.
