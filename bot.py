import discord
from discord.ext import commands
import datetime
import asyncio
from collections import defaultdict

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=['!', '$'], intents=intents)

# =========================================================
# ⚙️ قسم الإعدادات ورقع الـ IDs
# =========================================================

# 1. ID قناة لوق الحماية والأمن (Security Logs)
SECURITY_LOG_CHANNEL_ID = 1556359696712077342

# 2. ID قناة لوق الأحداث العامة (General Logs: رسائل، دخول، صوتيات)
GENERAL_LOG_CHANNEL_ID = 1556359448228921426

# 3. IDs الرولات المعفية من الحماية (WhiteList)
EXEMPT_ROLE_IDS = [
    1556343205572776156,
]

# 4. ID الرتبة الوحيدة التي تعطى للمخالف عند تجريده من رتبه
PUNISHMENT_ROLE_ID = 1556348066976768041

# رابط الـ GIF الخاص بأوامر Dictator
DICTATOR_GIF_URL = "https://cdn.discordapp.com/attachments/1555034446133207080/1555701682653102080/statue.gif?backend=b2&ex=6ac375d8&is=6ac22458&hm=888b3d6b51358cb13af29e64223e97de1d3be1298012a44135d6d758654be4e8&"

# =========================================================

user_message_logs = defaultdict(list)


def is_owner(ctx):
    """التحقق من أن منفذ الأمر هو صاحب السيرفر"""
    return ctx.author.id == ctx.guild.owner_id


def is_protected_or_exempt(member, guild):
    """التحقق مما إذا كان العضو معفياً من الحماية"""
    if member.id == guild.owner_id or member.id == bot.user.id:
        return True

    member_role_ids = [role.id for role in member.roles]
    for exempt_id in EXEMPT_ROLE_IDS:
        if exempt_id in member_role_ids:
            return True

    return False


async def punish_member(member, reason):
    """سحب جميع الرتب وإعطاء رتبة العقاب المحددة"""
    punish_role = member.guild.get_role(PUNISHMENT_ROLE_ID)
    roles_to_keep = [punish_role] if punish_role else []
    try:
        await member.edit(roles=roles_to_keep, reason=reason)
    except Exception as e:
        print(f"حدث خطأ أثناء سحب الرتب من {member.name}: {e}")


async def send_log(guild, channel_id, title, description, color=discord.Color.blue()):
    """دالة إرسال السجلات إلى قناة محددة عبر الـ ID"""
    log_channel = guild.get_channel(channel_id)
    if log_channel:
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        await log_channel.send(embed=embed)
    else:
        print(f"⚠️️ تحذير: لم يتم العثور على قناة السجلات ذات الـ ID: {channel_id}")


@bot.event
async def on_ready():
    print(f'✅ تم تشغيل البوت بنجاح باسم: {bot.user}')

# ==========================================
# 1. نظام الحماية من السبيام (Anti-Spam) -> Security Log
# ==========================================

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        await bot.process_commands(message)
        return

    if is_protected_or_exempt(message.author, message.guild):
        await bot.process_commands(message)
        return

    now = datetime.datetime.now(datetime.timezone.utc)
    user_id = message.author.id
    
    user_message_logs[user_id].append((now, message))
    
    user_message_logs[user_id] = [
        (msg_time, msg) for msg_time, msg in user_message_logs[user_id]
        if (now - msg_time).total_seconds() <= 3
    ]

    if len(user_message_logs[user_id]) >= 5:
        messages_to_delete = [msg for _, msg in user_message_logs[user_id]]
        user_message_logs[user_id].clear()

        try:
            await message.channel.delete_messages(messages_to_delete)
        except Exception:
            for msg in messages_to_delete:
                try:
                    await msg.delete()
                except Exception:
                    pass

        try:
            duration = datetime.timedelta(days=2)
            await message.author.timeout(duration, reason="Anti-Spam Triggered")
        except Exception as e:
            print(f"تعذر إعطاء تايم أوت: {e}")

        await send_log(
            message.guild,
            SECURITY_LOG_CHANNEL_ID,
            "🚨 حماية السبيام (Anti-Spam)",
            f"**المخالف:** {message.author.mention}\n**الإجراء:** تايم أوت لمدة **يومين** + حذف الرسائل.\n**القناة:** {message.channel.mention}",
            discord.Color.red()
        )

    await bot.process_commands(message)

# ==========================================
# 2. نظام حماية السيرفر (Anti-Nuke / Actions) -> Security Log
# ==========================================

@bot.event
async def on_member_ban(guild, user):
    async for entry in guild.audit_logs(action=discord.AuditLogAction.ban, limit=1):
        executor = entry.user
        executor_member = guild.get_member(executor.id)

        if not executor_member or is_protected_or_exempt(executor_member, guild):
            return

        await punish_member(executor_member, "Security: Mass Ban")
        await guild.unban(user, reason="Security: Auto Unban")

        await send_log(
            guild,
            SECURITY_LOG_CHANNEL_ID,
            "🚨 محاولة تخريب (Anti-Ban)",
            f"حاول {executor.mention} حظر {user.mention}.\nتم سحب رتبه وإعطاؤه رتبة العقاب وإلغاء الحظر.",
            discord.Color.red()
        )


@bot.event
async def on_member_remove(guild, member):
    async for entry in guild.audit_logs(action=discord.AuditLogAction.kick, limit=1):
        if entry.target.id == member.id:
            executor = entry.user
            executor_member = guild.get_member(executor.id)

            if not executor_member or is_protected_or_exempt(executor_member, guild):
                return

            await punish_member(executor_member, "Security: Unauthorized Kick")

            await send_log(
                guild,
                SECURITY_LOG_CHANNEL_ID,
                "🚨 محاولة تخريب (Anti-Kick)",
                f"حاول {executor.mention} طرد {member.mention}.\nتم سحب رتبه وإعطاؤه رتبة العقاب.",
                discord.Color.red()
            )


@bot.event
async def on_guild_channel_delete(channel):
    guild = channel.guild
    async for entry in guild.audit_logs(action=discord.AuditLogAction.channel_delete, limit=1):
        executor = entry.user
        executor_member = guild.get_member(executor.id)

        if not executor_member or is_protected_or_exempt(executor_member, guild):
            return

        await punish_member(executor_member, "Security: Channel Deletion")

        await send_log(
            guild,
            SECURITY_LOG_CHANNEL_ID,
            "🚨 محاولة تخريب (Anti-Channel Delete)",
            f"حاول {executor.mention} حذف قناة `{channel.name}`.\nتم سحب رتبه وإعطاؤه رتبة العقاب.",
            discord.Color.red()
        )


@bot.event
async def on_guild_role_delete(role):
    guild = role.guild
    async for entry in guild.audit_logs(action=discord.AuditLogAction.role_delete, limit=1):
        executor = entry.user
        executor_member = guild.get_member(executor.id)

        if not executor_member or is_protected_or_exempt(executor_member, guild):
            return

        await punish_member(executor_member, "Security: Role Deletion")

        await send_log(
            guild,
            SECURITY_LOG_CHANNEL_ID,
            "🚨 محاولة تخريب (Anti-Role Delete)",
            f"حاول {executor.mention} حذف رتبة `{role.name}`.\nتم سحب رتبه وإعطاؤه رتبة العقاب.",
            discord.Color.red()
        )

# ==========================================
# 3. نظام السجلات العامة (General Logs) -> General Log
# ==========================================

@bot.event
async def on_message_edit(before, after):
    if before.author.bot or before.content == after.content:
        return
    await send_log(
        before.guild,
        GENERAL_LOG_CHANNEL_ID,
        "✏️ تعديل رسالة",
        f"**الكاتب:** {before.author.mention}\n**القناة:** {before.channel.mention}\n**قبل:** {before.content}\n**بعد:** {after.content}",
        discord.Color.gold()
    )


@bot.event
async def on_message_delete(message):
    if message.author.bot:
        return
    await send_log(
        message.guild,
        GENERAL_LOG_CHANNEL_ID,
        "🗑 حذف رسالة",
        f"**الكاتب:** {message.author.mention}\n**القناة:** {message.channel.mention}\n**المحتوى:** {message.content}",
        discord.Color.orange()
    )


@bot.event
async def on_member_join(member):
    await send_log(
        member.guild,
        GENERAL_LOG_CHANNEL_ID,
        "📥 دخول عضو جديد",
        f"انضم {member.mention} ({member.name}) للسيرفر.",
        discord.Color.green()
    )


@bot.event
async def on_voice_state_update(member, before, after):
    if before.channel != after.channel:
        if after.channel is not None:
            await send_log(member.guild, GENERAL_LOG_CHANNEL_ID, "🎙 دخول روم صوتي", f"دخل {member.mention} إلى `{after.channel.name}`")
        if before.channel is not None:
            await send_log(member.guild, GENERAL_LOG_CHANNEL_ID, "🎙️ خروج من روم صوتي", f"خرج {member.mention} من `{before.channel.name}`")

# ==========================================
# 4. أوامر الإدارة (صاحب السيرفر فقط)
# ==========================================

@bot.command(name="dictatorban")
@commands.check(is_owner)
async def dictatorban(ctx, user: discord.User, *, reason="Dictator Ban Execution"):
    try:
        await ctx.guild.ban(user, reason=reason)
        
        embed = discord.Embed(
            title="# READY GOD",
            description=f"تم حظر {user.mention} بنجاح.",
            color=discord.Color.dark_red()
        )
        embed.set_image(url=DICTATOR_GIF_URL)
        
        await ctx.send(content=" READY GOD", embed=embed)
        
        await send_log(
            ctx.guild,
            SECURITY_LOG_CHANNEL_ID,
            "👑 Dictator Ban",
            f"**المنفذ:** {ctx.author.mention}\n**المستهدف:** {user.mention} ({user.id})\n**السبب:** {reason}",
            discord.Color.dark_red()
        )
    except Exception as e:
        await ctx.send(f"❌ تعذر تنفيذ الأمر: {e}")


@bot.command(name="dictator")
@commands.check(is_owner)
async def dictator(ctx, user: discord.User = None):
    target_text = f" إلى {user.mention}" if user else ""
    
    embed = discord.Embed(
        title="# READY GOD",
        description=f"تحذير مستبد{target_text} ⚡",
        color=discord.Color.dark_red()
    )
    embed.set_image(url=DICTATOR_GIF_URL)
    
    await ctx.send(content="# READY GOD", embed=embed)


@bot.command()
@commands.check(is_owner)
async def ban(ctx, member: discord.Member, *, reason="لم يتم ذكر سبب"):
    await member.ban(reason=reason)
    await ctx.send(f"✅ تم حظر {member.mention}.")
    await send_log(ctx.guild, SECURITY_LOG_CHANNEL_ID, "🔨 باند", f"**المنفذ:** {ctx.author.mention}\n**المستهدف:** {member.mention}\n**السبب:** {reason}", discord.Color.red())


@bot.command()
@commands.check(is_owner)
async def unban(ctx, user_id: int):
    user = await bot.fetch_user(user_id)
    await ctx.guild.unban(user)
    await ctx.send(f"✅ تم فك الحظر عن {user.name}.")
    await send_log(ctx.guild, SECURITY_LOG_CHANNEL_ID, "🔓 فك باند", f"**المنفذ:** {ctx.author.mention}\n**المستهدف:** {user.name}", discord.Color.green())


@bot.command()
@commands.check(is_owner)
async def kick(ctx, member: discord.Member, *, reason="لم يتم ذكر سبب"):
    await member.kick(reason=reason)
    await ctx.send(f"✅ تم طرد {member.mention}.")
    await send_log(ctx.guild, SECURITY_LOG_CHANNEL_ID, "👞 طرد", f"**المنفذ:** {ctx.author.mention}\n**المستهدف:** {member.mention}\n**السبب:** {reason}", discord.Color.orange())


@bot.command()
@commands.check(is_owner)
async def timeout(ctx, member: discord.Member, minutes: int, *, reason="لم يتم ذكر سبب"):
    duration = datetime.timedelta(minutes=minutes)
    await member.timeout(duration, reason=reason)
    await ctx.send(f"🔇 تم إعطاء تايم أوت لـ {member.mention} لمدة {minutes} دقيقة.")
    await send_log(ctx.guild, SECURITY_LOG_CHANNEL_ID, "🔇 تايم أوت", f"**المنفذ:** {ctx.author.mention}\n**المستهدف:** {member.mention}\n**المدة:** {minutes} دقيقة", discord.Color.purple())


@bot.command()
@commands.check(is_owner)
async def untimeout(ctx, member: discord.Member):
    await member.timeout(None)
    await ctx.send(f"🔊 تم فك التايم أوت عن {member.mention}.")
    await send_log(ctx.guild, SECURITY_LOG_CHANNEL_ID, "🔊 فك تايم أوت", f"**المنفذ:** {ctx.author.mention}\n**المستهدف:** {member.mention}", discord.Color.blue())


@bot.command()
@commands.check(is_owner)
async def clear(ctx, amount: int = 10):
    await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"🧹 تم مسح {amount} رسالة.", delete_after=3)
    await send_log(ctx.guild, GENERAL_LOG_CHANNEL_ID, "🧹 مسح رسائل", f"**المنفذ:** {ctx.author.mention}\n**القناة:** {ctx.channel.mention}\n**العدد:** {amount}")


@dictatorban.error
@dictator.error
@ban.error
@unban.error
@kick.error
@timeout.error
@untimeout.error
@clear.error
async def owner_only_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("❌ هذا الأمر مخصص حصرياً لصاحب السيرفر (Owner).")

# ضع توكن البوت هنا
bot.run('MTU1NTk1MTg2NDA2NTgxODY4Ng.Gner8s.yj7FbKYG9jZcJr0IDBy6495Be9Mz68atwMvqDU')