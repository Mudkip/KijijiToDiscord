from dotenv import load_dotenv

load_dotenv()

import os
import aiohttp
import asyncio
from bs4 import BeautifulSoup


class Scraper:
    def __init__(self, guild_scrapes):
        self.guild_scrapes = guild_scrapes
        self.ad_map = {}

    def get_ads(self):
        return self.ad_map

    async def fetch(self, session, guild, url):
        try:
            async with session.get(url) as res:
                text = await res.text()
                ads = await self.extract_ads(text)
                return url, guild, ads
        except Exception as e:
            print(f"Error fetching ads from url {url}: " + str(e))

    async def extract_ads(self, text):
        soup = BeautifulSoup(text, "html.parser")
        ad_divs = soup.find_all("div", class_="search-item")
        ads = []
        for ad in ad_divs:
            info = ad.find("div", class_="info-container")
            desc = (
                info.find("div", class_="description")
                .find(text=True, recursive=False)
                .strip()
            )
            title = (
                info.find("a", class_="title").find(text=True, recursive=False).strip()
            )
            price = (
                info.find("div", class_="price")
                .find(text=True, recursive=False)
                .strip()
            )
            ads.append(
                {
                    "id": ad["data-listing-id"],
                    "url": "https://www.kijiji.ca" + ad["data-vip-url"],
                    "title": title.replace("`", "'").replace("*", ""),
                    "price": price if price else "Not specified",
                    "desc": desc.replace("`", "'") if desc else "Not specified",
                }
            )
        return ads

    async def execute(self):
        tasks = []
        async with aiohttp.ClientSession(
            headers={"User-Agent": os.getenv("USER_AGENT")}
        ) as session:
            for guild, urls in self.guild_scrapes.items():
                for url in urls:
                    tasks.append(self.fetch(session, guild, url))

            ad_urls = await asyncio.gather(*tasks)

            for ads in ad_urls:
                if ads is not None:
                    if not (ads[1] in self.ad_map):
                        self.ad_map[ads[1]] = []
                    self.ad_map[ads[1]].append({"url": ads[0], "ads": ads[2]})
