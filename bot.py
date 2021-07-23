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

bot = commands.Bot(command_prefix='?')
guild_channels = {}
scrape_urls = {}

@bot.event
async def on_ready():
    print('Starting up KijijiBot.')
    print('Initializing SQLite tables.')
    try:
        bot.db = sqlite3.connect(os.getenv('DB_PATH'))
        bot.db.execute("""
            CREATE TABLE IF NOT EXISTS guild_channels (
                id INTEGER PRIMARY KEY,
                guild VARCHAR(32) UNIQUE NOT NULL,
                channel VARCHAR(32) NOT NULL
            )
        """)
        bot.db.execute("""
            CREATE TABLE IF NOT EXISTS track_urls (
                id INTEGER PRIMARY KEY,
                guild VARCHAR(32) NOT NULL,
                url VARCHAR(128) NOT NULL
            )
        """)
        bot.db.execute("""
            CREATE TABLE IF NOT EXISTS keyword_pings (
                id INTEGER PRIMARY KEY,
                user VARCHAR(64) NOT NULL,
                keyword VARCHAR(32) NOT NULL
            )
        """)
        bot.db.execute("""
            CREATE TABLE IF NOT EXISTS seen_ads (
                id INTEGER PRIMARY KEY,
                ad_id INT NOT NULL,
                timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        bot.db.commit()
        print('SQLite tables initialized.')
    except Exception as e:
        print(f'Unexpected error while loading SQLite database: \n {e}')

    cur = bot.db.cursor()
    print('Loading guilds and their channels')
    for guild_id, channel_id in cur.execute('SELECT guild, channel FROM guild_channels'):
            guild = bot.get_guild(int(guild_id))
            channel = bot.get_channel(int(channel_id))
            guild_channels[guild] = channel
            

    print('Loading scrape URLs')
    for guild_id, url in cur.execute('SELECT guild, url FROM track_urls'):
        guild = bot.get_guild(int(guild_id))
        if not (guild in scrape_urls):
            scrape_urls[guild] = []
        scrape_urls[guild].append(url)

    print('Scheduling scraper task.')
    run_scraper.start()
    print('All done!')

@tasks.loop(minutes=5)
async def run_scraper():
    scraper = Scraper(scrape_urls)
    await scraper.execute()
    cur = bot.db.cursor()
    for guild, ads in scraper.get_ads().items():
        if(await get_ad_dump_channel(guild)):
            chan = await get_ad_dump_channel(guild)
            for ad_map in ads:
                url = ad_map['url']
                ad_list = ad_map['ads']
                for ad in ad_list:
                    ad_id = int(ad['id'])
                    cur.execute('SELECT EXISTS(SELECT 1 FROM seen_ads WHERE ad_id=? LIMIT 1)', (ad_id,))
                    exists = cur.fetchone()[0]
                    if exists == 0:
                        bot.db.execute('INSERT INTO seen_ads(ad_id) VALUES(?)', (ad_id,))
                        bot.db.commit()
                        await chan.send(await format_ad(ad))
                        

@bot.command()
async def addurl(ctx, url: str):
    """Adds a url for kijiji bot to track."""
    if url in scrape_urls:
        await ctx.send('This URL is already being tracked.')
    elif re.match(r'^https:\/\/www\.kijiji\.ca\/b-[\w+-]+(\/[\w+-]+)?(\/[\w+-]+)?\/[\w+-]+$', url):
        res = requests.get(url, headers={'User-Agent': os.getenv('USER_AGENT')})
        if res.status_code == 200 and 'showing' in res.text:
                bot.db.execute('INSERT INTO track_urls(guild, url) VALUES(?,?)', (ctx.message.guild.id, url))
                bot.db.commit()
                if not (ctx.message.guild in scrape_urls):
                    scrape_urls[ctx.message.guild] = []
                scrape_urls[ctx.message.guild].append(url)
                await ctx.send('Added URL for tracking!')
        else:
            await ctx.send('Cannot parse Kijiji URL. Make sure that the URL you provided actually shows ads.')
    else:
        await ctx.send('Invalid Kijiji URL. Make sure you are copying the URL from your browser and that there are no extra query params.')

@bot.command()
async def setchannel(ctx, channel: discord.TextChannel = None):
    if not (ctx.message.guild in guild_channels) or guild_channels[ctx.message.guild] != channel:
        bot.db.execute('INSERT OR REPLACE INTO guild_channels(guild, channel) VALUES(?,?)', (ctx.message.guild.id, channel.id))
        bot.db.commit()
        guild_channels[ctx.message.guild] = channel
        await ctx.send(f'Done! All ads will be sent to {channel.mention}.')
    else:
        await ctx.send(f'All ads are already going into {channel.mention}.')
        
@setchannel.error
async def setchannel_error(ctx, error):
    if isinstance(error, discord.ext.commands.errors.ChannelNotFound):
        await ctx.send('Channel could not be found and was not set as a result.')

async def get_ad_dump_channel(guild):
    if guild in guild_channels:
        return guild_channels[guild]
    return None

async def format_ad(ad_dic):
    return dedent(f"""
        ====================================================
        :newspaper: **New Kijiji Ad (ID: {ad_dic['id']})!**
        Title: ``{ad_dic['title']}``
        Price: ``{ad_dic['price']}``
        Description:```{ad_dic['desc']}```
        {ad_dic['url']}
    """)

bot.run(os.getenv('DISCORD_TOKEN'))
