# KijijiToDiscord
A Discord bot written using the discord.py library to scrape ads from Kijiji search urls and post them to discord.

Made for educational purposes only, to get the hang of BeautifulSoup, discord.py, and asyncio.

Written and tested with Python 3.9.6.

## Instructions:
1. Clone this repository and enter the directory
2. Install requirements using ``pip install -r requirements.txt``
3. Copy .env.dist to .env and fill it in
4. Run the bot using ``python bot.py``

## Commands:
All commands have a prefix, by default it is "?" (e.g. ?setchannel #channel)
|Command|Description|
|---|---|
|addurl|Add url to list of urls for scraping|
|removeurl|Remove a url from the list of urls for scraping|
|setchannel #channel|Sets the channel to which the ads will be posted. If a channel is not set, ads won't be posted|
|notify keyword|Makes bot tag you if an ad with the specified keyword is found. Maximum 32 characters per keyword|
|unnotify keyword|Stops the bot from tagging you for ads with the specified keyword|
|viewnotify|View all the keyword notifications you have setup|
