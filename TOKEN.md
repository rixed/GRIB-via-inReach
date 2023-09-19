How to renew the token
======================

When you got the expired token error message after running main.py, stop it (^C).

Get rid of the expired token:

$ mv .token /tmp

Then run the app again:

$ python3 main.py

It will now tell:

> Please visit this URL to authorize this application: https://accounts.google.com/o/oauth2/...

On a browser, go to that URL, select one of the authorized account and then accept everything.
The last redirect will fail, trying to access localhost (thinking it will access the google lib auth client service).

You can copy and paste the URL and execute it with wget from the docker instance where main.py is running.
(Running again `docker exec -i vaudoomap bash` to get another shell)

From now on you have a new token (in .token) and the app has started.
