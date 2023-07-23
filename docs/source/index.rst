.. gmailsorter documentation master file, created by
   sphinx-quickstart on Sun Jul 9 20:20:20 2023.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

gmailsorter - Similarity based email sorting for Google Mail
============================================================
In 2020 there were `306.4 billion e-mails <https://www.statista.com/statistics/456500/daily-number-of-e-mails-worldwide/>`_
sent and received daily. This number is estimated to increase by 4% yearly, resulting in over 376.4 billion e-mails by
2025. While email as medium for internal communication in large enterprises is slowly replaced by instant messaging
solutions and business communication platforms, these solutions fail to address the primary challenge, namely the
communication between employees from different companies. So addressing the `stress and productivity lost <https://affect.media.mit.edu/pdfs/16.Mark-CHI_Email.pdf>`_
resulting from interruptions caused by the increase of daily emails is the motivation for the development of gmailsorter.

As a first step gmailsorter creates a barrier between you and your email. Just like a personal guardian it blocks emails
from your inbox and filters them into categories, so you can read the emails you care about when you have time and no
longer have them interrupt your work. Second in contrast to other automated solutions, gmailsorter is designed to
seamlessly integrate into your existing workflow:

* Gmailsorter is a server-side application, so you can continue using your favorite email client. In addition, the
  Gmailsorter user interface is minimalistic so you can configure it once and then forget about it.
* Gmailsorter adopts the email labels you suggest and filters your emails accordingly. It is based on the believe that
  the structure how you sort your ideas, documents and emails is very personal and you know what works best for you.
* Gmailsorter learns from your reactions. When you disagree with a suggested email label and modify it, Gmailsorter
  takes this feedback into account for the next suggestions.

So you can think about gmailsorter like a virtual assistant. It learns how you want your emails to be sorted based on
their similarity to previous emails you assigned to the same label. All the communication with gmailsorter is handled
via your Google Mail account. Following there simple steps:

* Gmailsorter takes your new emails and moves them from your inbox to its inbox.
* Afterwards Gmailsorter scans the content of your email, calculates the similarity to all existing emails and then based
  on the email labels you assigned to all your previous emails it predicts the email label for the new email.
* If you agree with this suggestion you do have to do anything. But if you disagree with the suggestion, you can simply
  change the email label, on the one hand this overwrites the suggestion from Gmailsorter and on the other hand Gmailsorter
  takes your modification into account when it retrains its model for making suggestions.

To learn more about Gmailsorter please have a look at the documentation below.

Documentation
-------------

.. toctree::
   :maxdepth: 2

   preparation
   configuration
   support
   developer