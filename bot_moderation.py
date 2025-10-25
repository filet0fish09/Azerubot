import discord
from discord.ext import commands
from discord import app_commands
import json
from datetime import datetime, timedelta
import asyncio
import os  # pour récupérer le token depuis les variables d'environnement

# ---------- CONFIG ----------
TOKEN = os.getenv("DISCORD_TOKEN")  # Ton token Discord ici via variable d'environnement
MUTE_ROLE_NAME = "Muted"  # Nom du rôle pour mute
MUTE_DUREES = {2: 10, 3: 60}  # Durée des mutes automatiques en minutes (niveau 2 et 3 warns)

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------- GESTION DES CASIERS ----------
def charger_casiers():
    try:
        with open("casiers.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def sauvegarder_casiers(casiers):
    with open("casiers.json", "w") as f:
        json.dump(casiers, f, indent=4)

casiers = charger_casiers()

def ajouter_infraction(membre: discord.Member, type_infraction: str, raison: str, moderateur: str):
    id_membre = str(membre.id)
    if id_membre not in casiers:
        casiers[id_membre] = []
    casiers[id_membre].append({
        "type": type_infraction,
        "raison": raison,
        "moderateur": moderateur,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    sauvegarder_casiers(casiers)

# ---------- SANCTIONS AUTOMATIQUES ----------
async def appliquer_sanction(interaction: discord.Interaction, membre: discord.Member):
    id_membre = str(membre.id)
    warns = [i for i in casiers.get(id_membre, []) if i['type'] == 'warn']
    nb_warns = len(warns)

    if nb_warns in MUTE_DUREES:
        role = discord.utils.get(interaction.guild.roles, name=MUTE_ROLE_NAME)
        if not role:
            role = await interaction.guild.create_role(name=MUTE_ROLE_NAME, reason="Création automatique du rôle Muted")
            for channel in interaction.guild.channels:
                await channel.set_permissions(role, send_messages=False, speak=False)
        await membre.add_roles(role, reason=f"Mute automatique {nb_warns} warns")
        ajouter_infraction(membre, "mute", f"Mute automatique {MUTE_DUREES[nb_warns]} min ({nb_warns} warns)", "Bot")
        await interaction.channel.send(f"🔇 {membre.mention} a été mute {MUTE_DUREES[nb_warns]} minutes ({nb_warns} warns).")
        await asyncio.sleep(MUTE_DUREES[nb_warns] * 60)
        await membre.remove_roles(role)

    elif nb_warns == 4:
        await membre.kick(reason="Kick automatique 4 warns")
        ajouter_infraction(membre, "kick", "Kick automatique 4 warns", "Bot")
        await interaction.channel.send(f"👢 {membre.mention} a été kické automatiquement (4 warns).")

    elif nb_warns >= 5:
        await membre.ban(reason="Ban automatique 5 warns")
        ajouter_infraction(membre, "ban", "Ban automatique 5 warns", "Bot")
        await interaction.channel.send(f"🔨 {membre.mention} a été banni automatiquement (5 warns).")

# ---------- ÉVÉNEMENTS ----------
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ {bot.user} est connecté et prêt !")

# ---------- COMMANDES ----------
@bot.tree.command(name="warn", description="Avertit un membre.")
@app_commands.describe(membre="Le membre à avertir", raison="Raison de l'avertissement")
async def warn(interaction: discord.Interaction, membre: discord.Member, raison: str):
    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("🚫 Tu n’as pas la permission d’avertir.", ephemeral=True)
        return
    ajouter_infraction(membre, "warn", raison, interaction.user.name)
    await interaction.response.send_message(f"⚠️ {membre.mention} a été averti pour : **{raison}**")
    await appliquer_sanction(interaction, membre)

@bot.tree.command(name="kick", description="Expulse un membre du serveur.")
@app_commands.describe(membre="Le membre à expulser", raison="Raison de l'expulsion")
async def kick(interaction: discord.Interaction, membre: discord.Member, raison: str = "Aucune raison donnée"):
    if not interaction.user.guild_permissions.kick_members:
        await interaction.response.send_message("🚫 Tu n’as pas la permission d’expulser.", ephemeral=True)
        return
    await membre.kick(reason=raison)
    ajouter_infraction(membre, "kick", raison, interaction.user.name)
    await interaction.response.send_message(f"👢 {membre.mention} a été expulsé. Raison : **{raison}**")

@bot.tree.command(name="ban", description="Bannit un membre du serveur.")
@app_commands.describe(membre="Le membre à bannir", raison="Raison du bannissement")
async def ban(interaction: discord.Interaction, membre: discord.Member, raison: str = "Aucune raison donnée"):
    if not interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message("🚫 Tu n’as pas la permission de bannir.", ephemeral=True)
        return
    await membre.ban(reason=raison)
    ajouter_infraction(membre, "ban", raison, interaction.user.name)
    await interaction.response.send_message(f"🔨 {membre.mention} a été banni. Raison : **{raison}**")

@bot.tree.command(name="unban", description="Débannit un utilisateur.")
@app_commands.describe(utilisateur="Nom#tag ou ID de l'utilisateur à débannir")
async def unban(interaction: discord.Interaction, utilisateur: str):
    if not interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message("🚫 Tu n’as pas la permission de débannir.", ephemeral=True)
        return
    bans = await interaction.guild.bans()
    for entry in bans:
        user = entry.user
        if utilisateur == str(user) or utilisateur == str(user.id):
            await interaction.guild.unban(user)
            ajouter_infraction(user, "unban", "Débanni", interaction.user.name)
            await interaction.response.send_message(f"✅ {user} a été débanni.")
            return
    await interaction.response.send_message("⚠️ Utilisateur introuvable dans la liste des bannis.", ephemeral=True)

@bot.tree.command(name="mute", description="Réduit au silence un membre.")
@app_commands.describe(membre="Le membre à mute", raison="Raison du mute")
async def mute(interaction: discord.Interaction, membre: discord.Member, raison: str = "Aucune raison donnée"):
    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("🚫 Tu n’as pas la permission de mute.", ephemeral=True)
        return
    role = discord.utils.get(interaction.guild.roles, name=MUTE_ROLE_NAME)
    if not role:
        role = await interaction.guild.create_role(name=MUTE_ROLE_NAME, reason="Création automatique du rôle Muted")
        for channel in interaction.guild.channels:
            await channel.set_permissions(role, send_messages=False, speak=False)
    await membre.add_roles(role, reason=raison)
    ajouter_infraction(membre, "mute", raison, interaction.user.name)
    await interaction.response.send_message(f"🔇 {membre.mention} a été mute pour : **{raison}**")

@bot.tree.command(name="unmute", description="Rend la parole à un membre.")
@app_commands.describe(membre="Le membre à unmute")
async def unmute(interaction: discord.Interaction, membre: discord.Member):
    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("🚫 Tu n’as pas la permission de unmute.", ephemeral=True)
        return
    role = discord.utils.get(interaction.guild.roles, name=MUTE_ROLE_NAME)
    if role in membre.roles:
        await membre.remove_roles(role)
        ajouter_infraction(membre, "unmute", "Fin du mute", interaction.user.name)
        await interaction.response.send_message(f"🔊 {membre.mention} a été unmute.")
    else:
        await interaction.response.send_message("⚠️ Ce membre n’est pas mute.", ephemeral=True)

@bot.tree.command(name="casier", description="Affiche le casier judiciaire d'un membre.")
@app_commands.describe(membre="Le membre dont tu veux voir le casier")
async def casier(interaction: discord.Interaction, membre: discord.Member):
    id_membre = str(membre.id)
    if id_membre not in casiers or len(casiers[id_membre]) == 0:
        await interaction.response.send_message(f"✅ {membre.mention} n’a aucun antécédent.")
        return
    embed = discord.Embed(
        title=f"Casier judiciaire de {membre.name}",
        color=discord.Color.orange()
    )
    for infraction in casiers[id_membre]:
        embed.add_field(
            name=f"🔹 {infraction['type'].capitalize()} — {infraction['date']}",
            value=f"**Raison :** {infraction['raison']}\n**Modérateur :** {infraction['moderateur']}",
            inline=False
        )
    await interaction.response.send_message(embed=embed)

# ---------- LANCEMENT ----------
bot.run(TOKEN)
