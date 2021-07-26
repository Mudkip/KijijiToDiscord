from dotenv import load_dotenv

load_dotenv()

import discord
import os
import sqlite3
import re
import requests
from textwrap import dedent
from discord.ext import commands, tasks
from scraper import Scraper

bot = commands.Bot(command_prefix="?")
guild_channels = {}
scrape_urls = {}
keyword_pings = {}


@bot.event
async def on_ready():
    print("Starting up KijijiBot.")
    print("Initializing SQLite tables.")
    try:
        bot.db = sqlite3.connect(os.getenv("DB_PATH"))
        bot.db.execute(
            """
            CREATE TABLE IF NOT EXISTS guild_channels (
                id INTEGER PRIMARY KEY,
                guild VARCHAR(32) UNIQUE NOT NULL,
                channel VARCHAR(32) NOT NULL
            )
        """
        )
        bot.db.execute(
            """
            CREATE TABLE IF NOT EXISTS track_urls (
                id INTEGER PRIMARY KEY,
                guild VARCHAR(32) NOT NULL,
                url VARCHAR(128) NOT NULL
            )
        """
        )
        bot.db.execute(
            """
            CREATE TABLE IF NOT EXISTS keyword_pings (
                id INTEGER PRIMARY KEY,
                user VARCHAR(32) NOT NULL,
                guild VARCHAR(32) NOT NULL,
                keyword VARCHAR(32) NOT NULL,
                UNIQUE (user, guild, keyword)
            )
        """
        )
        bot.db.execute(
            """
            CREATE TABLE IF NOT EXISTS seen_ads (
                ad_id INT NOT NULL,
                guild VARCHAR(32) NOT NULL,
                timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (ad_id, guild)
            )
        """
        )
        bot.db.commit()
        print("SQLite tables initialized.")
    except Exception as e:
        print(f"Unexpected error while loading SQLite database: \n {str(e)}")

    print("Loading guilds and their channels")
    cur = bot.db.cursor()
    for guild_id, channel_id in cur.execute(
        "SELECT guild, channel FROM guild_channels"
    ):
        guild = bot.get_guild(int(guild_id))
        channel = bot.get_channel(int(channel_id))
        guild_channels[guild] = channel

    print("Loading notification requests")
    for guild_id, user_id, keyword in cur.execute(
        "SELECT guild, user, keyword FROM keyword_pings"
    ):
        guild = bot.get_guild(int(guild_id))
        if guild not in keyword_pings:
            keyword_pings[guild] = {}

        if keyword not in keyword_pings[guild]:
            keyword_pings[guild][keyword] = []

        keyword_pings[guild][keyword].append(await bot.fetch_user(int(user_id)))

    print("Loading scrape URLs")
    for guild_id, url in cur.execute("SELECT guild, url FROM track_urls"):
        guild = bot.get_guild(int(guild_id))
        if not (guild in scrape_urls):
            scrape_urls[guild] = []
        scrape_urls[guild].append(url)

    print("Scheduling scraper task.")
    run_scraper.start()
    print("All done!")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("A parameter is missing. Check help.")


@tasks.loop(minutes=5)
async def run_scraper():
    await bot.wait_until_ready()
    scraper = Scraper(scrape_urls)
    await scraper.execute()
    cur = bot.db.cursor()
    for guild, ads in scraper.get_ads().items():
        if await get_ad_dump_channel(guild):
            chan = await get_ad_dump_channel(guild)
            for ad_map in ads:
                url = ad_map["url"]
                ad_list = ad_map["ads"]
                for ad in ad_list:
                    ad_id = int(ad["id"])
                    cur.execute(
                        "SELECT EXISTS(SELECT 1 FROM seen_ads WHERE ad_id=? AND guild=? LIMIT 1)",
                        (ad_id, guild.id),
                    )
                    exists = cur.fetchone()[0]
                    if exists == 0:
                        bot.db.execute(
                            "INSERT INTO seen_ads(ad_id, guild) VALUES(?,?)",
                            (ad_id, guild.id),
                        )
                        await chan.send(await format_ad(ad, guild))
                bot.db.commit()


@bot.command()
async def addurl(ctx, url: str):
    """Adds a url for kijiji bot to track"""

    if ctx.message.guild in scrape_urls and url in scrape_urls[ctx.message.guild]:
        await ctx.send("This URL is already being tracked.")
    elif re.match(
        r"^https:\/\/www\.kijiji\.ca\/b-[\w+-]+(\/[\w+-]+)?(\/[\w+-]+)?\/[\w+-]+$", url
    ):
        res = requests.get(url, headers={"User-Agent": os.getenv("USER_AGENT")})
        if res.status_code == 200 and "showing" in res.text:
            bot.db.execute(
                "INSERT INTO track_urls(guild, url) VALUES(?,?)",
                (ctx.message.guild.id, url),
            )
            bot.db.commit()
            if not (ctx.message.guild in scrape_urls):
                scrape_urls[ctx.message.guild] = []
            scrape_urls[ctx.message.guild].append(url)
            await ctx.send("Added URL for tracking!")
        else:
            await ctx.send(
                "Cannot parse Kijiji URL. Make sure that the URL you provided actually shows ads."
            )
    else:
        await ctx.send(
            "Invalid Kijiji URL. Make sure you are copying the URL from your browser and that there are no extra query params."
        )


@bot.command()
async def listurls(ctx):
    """Prints a list of URLs being tracked in a guild"""
    if ctx.message.guild in scrape_urls:
        to_send = "List of Kijiji URLs being tracked: \n"
        for url in scrape_urls[ctx.message.guild]:
            to_send = to_send + "<" + url + ">\n"
        await ctx.send(to_send)
    else:
        await ctx.send(
            "There are no Kijiji URLs currently being tracked for this guild."
        )


@bot.command()
async def removeurl(ctx, url: str):
    """Removes a URL from tracking"""
    if ctx.message.guild in scrape_urls and url in scrape_urls[ctx.message.guild]:
        scrape_urls[ctx.message.guild].remove(url)
        bot.db.execute(
            "DELETE FROM track_urls WHERE url=? AND guild=?",
            (url, ctx.message.guild.id),
        )
        bot.db.commit()
        await ctx.send("That URL won't be tracked anymore")
    else:
        await ctx.send("Nothing to do. URL is not being tracked.")


@bot.command()
async def notify(ctx, *, keyword: str):
    """Makes bot ping you if an ad with the provided keyword is found. Maximum 32 characters per keyword."""
    if len(keyword) > 32:
        await ctx.send("The maximum length of a keyword is currently 32 characters.")
    else:
        author = ctx.message.author
        guild = ctx.message.guild

        if guild not in keyword_pings:
            keyword_pings[guild] = {}

        if keyword not in keyword_pings[guild]:
            keyword_pings[guild][keyword] = []

        keyword_pings[guild][keyword].append(author)

        bot.db.execute(
            "INSERT OR IGNORE INTO keyword_pings(user, guild, keyword) VALUES(?,?,?)",
            (author.id, guild.id, keyword),
        )
        bot.db.commit()
        await ctx.send(
            "Ok. You will be pinged if an ad with the provided keyword is found."
        )


@bot.command()
async def unnotify(ctx, *, keyword: str):
    """Stops the bot from pinging you for a certain keyword"""
    author = ctx.message.author
    guild = ctx.message.guild
    if (
        guild not in keyword_pings
        or keyword not in keyword_pings[guild]
        or author not in keyword_pings[guild][keyword]
    ):
        await ctx.send("You did not setup notifications for this keyword.")
    else:
        keyword_pings[guild][keyword].remove(author)
        bot.db.execute(
            "DELETE FROM keyword_pings WHERE user = ? AND guild = ? AND keyword = ?",
            (author.id, guild.id, keyword),
        )
        bot.db.commit()

        await ctx.send("Ok. You will not be pinged for this keyword anymore.")


@bot.command()
async def viewnotify(ctx):
    """View all the keyword notifications you have setup"""
    author = ctx.message.author.id
    guild = ctx.message.guild.id
    cur = bot.db.cursor()
    keyword_string = ""
    keywords = cur.execute(
        "SELECT keyword FROM keyword_pings WHERE user = ? AND guild = ?",
        (author, guild),
    )
    for keyword in keywords:
        keyword_string += discord.utils.escape_mentions(keyword[0]) + "\n"
    if keyword_string != "":
        await ctx.send(
            f"You have setup notifications for the following keywords:\n{keyword_string}"
        )
    else:
        await ctx.send("You do not have any keyword notifications setup.")


@bot.command()
async def setchannel(ctx, channel: discord.TextChannel = None):
    """Sets the channel for the ad dumps"""
    if (
        not (ctx.message.guild in guild_channels)
        or guild_channels[ctx.message.guild] != channel
    ):
        bot.db.execute(
            "INSERT OR REPLACE INTO guild_channels(guild, channel) VALUES(?,?)",
            (ctx.message.guild.id, channel.id),
        )
        bot.db.commit()
        guild_channels[ctx.message.guild] = channel
        await ctx.send(f"Done! All ads will be sent to {channel.mention}.")
    else:
        await ctx.send(f"All ads are already going into {channel.mention}.")


@setchannel.error
async def setchannel_error(ctx, error):
    if isinstance(error, discord.ext.commands.errors.ChannelNotFound):
        await ctx.send("Channel could not be found and was not set as a result.")


async def get_ad_dump_channel(guild):
    if guild in guild_channels:
        return guild_channels[guild]
    return None


async def format_ad(ad_dic, guild):
    base_message = dedent(
        f"""
        ===========================================
        :newspaper: **Kijiji Ad - {ad_dic['title']}!**
        Title: ``{ad_dic['title']}``
        Price: ``{ad_dic['price']}``
        Description:```{ad_dic['desc']}```
        {ad_dic['url']}\n
    """
    )

    if guild in keyword_pings:
        for keyword, users in keyword_pings[guild].items():
            if keyword in ad_dic["title"] or keyword in ad_dic["desc"]:
                for user in users:
                    base_message += user.mention

    return base_message


bot.run(os.getenv("DISCORD_TOKEN"))
