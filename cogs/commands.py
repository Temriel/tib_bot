import discord
from discord import app_commands
from discord.ext import commands
import config

class commander(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        print('Command cog loaded.')

    @app_commands.command(name='hello', description='Say hi!')
    async def hello(self, interaction: discord.Interaction):
        await interaction.response.send_message(f'Hello, {interaction.user.mention}.')
    
    @app_commands.command(name='ping', description='See the ping.')
    async def ping(self, interaction: discord.Interaction):
        bot_latency = round(self.client.latency * 1000)
        await interaction.response.send_message(f'Pong! Current ping is {bot_latency}ms.')

    @app_commands.command(name='canvas', description='See a canvas.')
    @app_commands.describe(
        canvas='Canvas number',
        display='Choose whether to use a custom display or not.'
    )
    @app_commands.choices(display=[
        app_commands.Choice(name='Initial', value='initial'),
        app_commands.Choice(name='Final', value='final'),
        app_commands.Choice(name='Activity', value='activity'),
        app_commands.Choice(name='Age', value='age'),
        app_commands.Choice(name='Virgin', value='virgin'),
        app_commands.Choice(name='Milliseconds', value='milliseconds'),
        app_commands.Choice(name='Minutes', value='minutes'),
        app_commands.Choice(name='Seconds', value='seconds'),
        app_commands.Choice(name='Combined', value='combined'),
        ]
    )
    async def canvas(self, interaction: discord.Interaction, canvas: str, display: app_commands.Choice[str] = None):
        displayed = display.value if display else 'final'
        await interaction.response.defer(ephemeral=False, thinking=True)
        try:
            filename = f'canvas-{canvas}_{displayed}.png'
            path = f'{config.pxlslog_explorer_dir}/pxls-final-canvas/canvas-{canvas}-{displayed}.png'
            file = discord.File(path, filename=filename)
            embed = discord.Embed(title=f'Canvas {canvas}, {displayed}.', )
            embed.set_image(url=f'attachment://{filename}')
            await interaction.followup.send(embed=embed, file=file)
            print(f'Sending canvas {canvas}, {displayed}')
        except Exception as e:
            await interaction.followup.send(f'Log files are... weird for c6, c17, c28, and c30a. If this error occured when trying to view those canvases, Tem knows about it already xd. If it was unrelated to those four, please ping Temriel!', ephemeral=True)
            print(f'An error occurred: {e}')

async def setup(client):
    await client.add_cog(commander(client))