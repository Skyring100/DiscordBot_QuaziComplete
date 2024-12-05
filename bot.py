import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
import pin_functions

#startup
load_dotenv(".env")
TOKEN: str = os.getenv("TOKEN")
client = commands.Bot(command_prefix="Q.", intents=discord.Intents.all())
@client.event
async def on_ready():
    await client.tree.sync()
    print("Quazi Clone online")

#commands
@client.tree.command(name="hello_world", description="Say hello to my little friend!")
async def hello_world(interaction: discord.Interaction):
    await interaction.response.send_message("Hello World!")

@client.tree.command(name="spam", description="Spam a message")
async def spam(interaction: discord.Interaction, message: str, amount: int = 5):
    await interaction.response.send_message("What have you done", ephemeral=True)
    for i in range(amount):
        await interaction.channel.send(message)

@client.tree.command(name="change_led", description="Changes LED on hardware")
async def change_led(interaction: discord.Interaction, isOn: bool):
    pin_functions.change_led(isOn)
    await interaction.response.send_message("LED changed")

client.run(TOKEN)