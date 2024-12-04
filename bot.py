import discord
from discord.ext import commands
from dotenv import load_dotenv
import os

load_dotenv(".env")
TOKEN: str = os.getenv("TOKEN")

client = commands.Bot(command_prefix="Q.", intents=discord.Intents.all())

@client.event
async def on_ready():
    await client.tree.sync()
    print("Quazi Clone online")

@client.tree.command(name="hello_world", description="Say hello to my little friend!")
async def hello_world(interaction: discord.Interaction):
    await interaction.response.send_message("Hello World!")

client.run(TOKEN)