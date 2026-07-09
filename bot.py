import discord
from discord.ext import commands
import asyncio
from typing import Dict, Optional
import os

# Настройки бота
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Хранилище активных комнат
active_rooms: Dict[int, dict] = {}


class CharacterRoom:
    def __init__(self, creator: discord.Member, channel: discord.TextChannel,
                 role: discord.Role, description: str = ""):
        self.creator = creator
        self.channel = channel
        self.role = role
        self.description = description
        self.applicants: Dict[str, dict] = {}
        self.is_open = True
        self.main_message: Optional[discord.Message] = None

    async def create_room_message(self):
        """Создает основное сообщение комнаты"""
        embed = discord.Embed(
            title=f"📋 Поиск: {self.role.name}",
            description=self.description or f"Комната для отбора кандидатов на роль {self.role.mention}",
            color=self.role.color if self.role.color != discord.Color.default() else discord.Color.blue()
        )
        embed.add_field(name="Создатель", value=self.creator.mention, inline=True)
        embed.add_field(name="Роль", value=self.role.mention, inline=True)
        embed.add_field(name="Статус", value="🟢 Открыта", inline=True)
        embed.add_field(
            name="Как подать заявку",
            value=f"Отправьте ссылку на персонажа с ролью {self.role.mention} в этот чат!",
            inline=False
        )
        embed.set_footer(text=f"ID комнаты: {self.channel.id} | Роль: {self.role.name}")

        self.main_message = await self.channel.send(
            content=f"{self.role.mention} - открыт набор!",
            embed=embed
        )
        return self.main_message

    async def add_applicant(self, user: discord.Member, character_url: str):
        """Добавляет заявку от участника"""
        if not self.is_open:
            return False, "Комната закрыта для новых заявок!"

        if str(user.id) in self.applicants:
            return False, "Вы уже подали заявку!"

        if self.role not in user.roles:
            return False, f"У вас нет роли {self.role.mention}!"

        self.applicants[str(user.id)] = {
            'user': user,
            'character_url': character_url,
            'status': 'pending'
        }

        embed = discord.Embed(
            title=f"Заявка от {user.display_name}",
            description=f"📝 [Ссылка на персонажа]({character_url})",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="Роль", value=self.role.mention, inline=True)
        embed.add_field(name="Статус", value="⏳ На рассмотрении", inline=True)
        embed.add_field(name="Участник", value=user.mention, inline=True)

        application_message = await self.channel.send(embed=embed)
        self.applicants[str(user.id)]['message'] = application_message

        await application_message.add_reaction("✅")
        await application_message.add_reaction("❌")

        return True, "Заявка успешно подана!"

    async def process_selection(self, reaction_user: discord.Member,
                                message: discord.Message, emoji: str):
        """Обрабатывает выбор создателя"""
        if reaction_user.id != self.creator.id:
            return

        for user_id, applicant in self.applicants.items():
            if applicant.get('message') and applicant['message'].id == message.id:
                if applicant['status'] != 'pending':
                    return

                user = applicant['user']

                if emoji == "✅":
                    applicant['status'] = 'accepted'
                    await self.notify_applicant(user, True)
                    embed = message.embeds[0]
                    embed.color = discord.Color.green()
                    embed.set_field_at(2, name="Статус", value="✅ Принят!", inline=True)
                    await message.edit(embed=embed)
                    await message.clear_reactions()

                elif emoji == "❌":
                    applicant['status'] = 'rejected'
                    await self.notify_applicant(user, False)
                    embed = message.embeds[0]
                    embed.color = discord.Color.red()
                    embed.set_field_at(2, name="Статус", value="❌ Отклонен", inline=True)
                    await message.edit(embed=embed)
                    await message.clear_reactions()

                await self.check_all_processed()
                break

    async def notify_applicant(self, user: discord.Member, accepted: bool):
        """Отправляет уведомление участнику"""
        try:
            if accepted:
                embed = discord.Embed(
                    title="✅ Заявка принята!",
                    description=f"Ваша заявка на роль **{self.role.name}** одобрена!",
                    color=discord.Color.green()
                )
            else:
                embed = discord.Embed(
                    title="❌ Заявка отклонена",
                    description=f"Ваша заявка на роль **{self.role.name}** отклонена.",
                    color=discord.Color.red()
                )

            embed.add_field(name="Роль", value=self.role.mention, inline=True)
            embed.add_field(name="Канал", value=self.channel.mention, inline=True)
            await user.send(embed=embed)
        except discord.Forbidden:
            if accepted:
                await self.channel.send(f"{user.mention} ✅ Заявка принята!", delete_after=10)
            else:
                await self.channel.send(f"{user.mention} ❌ Заявка отклонена.", delete_after=10)

    async def check_all_processed(self):
        """Проверяет, все ли заявки обработаны"""
        all_processed = all(
            applicant['status'] != 'pending'
            for applicant in self.applicants.values()
        )

        if all_processed and self.applicants:
            self.is_open = False
            if self.main_message:
                embed = self.main_message.embeds[0]
                embed.set_field_at(2, name="Статус", value="🔴 Закрыта", inline=True)
                await self.main_message.edit(embed=embed)

    async def close_room(self):
        """Закрывает комнату"""
        self.is_open = False
        if self.main_message:
            embed = self.main_message.embeds[0]
            embed.set_field_at(2, name="Статус", value="🔴 Закрыта", inline=True)
            await self.main_message.edit(embed=embed)

        for user_id, applicant in self.applicants.items():
            if applicant['status'] == 'pending':
                applicant['status'] = 'rejected'
                await self.notify_applicant(applicant['user'], False)


@bot.command(name='create_room')
async def create_room(ctx, role: discord.Role = None, *, description: str = ""):
    """Создает комнату для отбора персонажей"""
    if role is None:
        await ctx.send("❌ Укажите роль! Пример: `!create_room @Маг Нужен маг`", delete_after=10)
        return

    if ctx.channel.id in active_rooms:
        await ctx.send("❌ В этом канале уже есть активная комната!", delete_after=10)
        return

    room = CharacterRoom(ctx.author, ctx.channel, role, description)
    active_rooms[ctx.channel.id] = room
    await room.create_room_message()

    await ctx.message.delete()

    confirm_msg = await ctx.send(f"✅ Комната для роли {role.mention} создана!")
    await asyncio.sleep(5)
    await confirm_msg.delete()


@bot.command(name='close_room')
async def close_room(ctx):
    """Закрывает активную комнату"""
    if ctx.channel.id not in active_rooms:
        await ctx.send("❌ В этом канале нет активной комнаты!", delete_after=10)
        return

    room = active_rooms[ctx.channel.id]
    if ctx.author.id != room.creator.id:
        await ctx.send("❌ Только создатель может закрыть комнату!", delete_after=10)
        return

    await room.close_room()
    del active_rooms[ctx.channel.id]
    await ctx.send("🔒 Комната закрыта!", delete_after=10)


@bot.command(name='room_status')
async def room_status(ctx):
    """Показывает статус комнаты"""
    if ctx.channel.id not in active_rooms:
        await ctx.send("❌ В этом канале нет активной комнаты!", delete_after=10)
        return

    room = active_rooms[ctx.channel.id]

    embed = discord.Embed(
        title=f"Статус комнаты: {room.role.name}",
        color=room.role.color if room.role.color != discord.Color.default() else discord.Color.blue()
    )
    embed.add_field(name="Роль", value=room.role.mention, inline=True)
    embed.add_field(name="Статус", value="🟢 Открыта" if room.is_open else "🔴 Закрыта", inline=True)
    embed.add_field(name="Создатель", value=room.creator.mention, inline=True)
    embed.add_field(name="Всего заявок", value=str(len(room.applicants)), inline=True)

    accepted = sum(1 for a in room.applicants.values() if a['status'] == 'accepted')
    rejected = sum(1 for a in room.applicants.values() if a['status'] == 'rejected')
    pending = sum(1 for a in room.applicants.values() if a['status'] == 'pending')

    embed.add_field(name="✅ Принято", value=str(accepted), inline=True)
    embed.add_field(name="❌ Отклонено", value=str(rejected), inline=True)
    embed.add_field(name="⏳ Ожидают", value=str(pending), inline=True)

    await ctx.send(embed=embed, delete_after=30)


@bot.event
async def on_message(message):
    """Обрабатывает сообщения с ссылками"""
    if message.author.bot:
        return

    if message.channel.id in active_rooms:
        room = active_rooms[message.channel.id]

        if message.author.id == room.creator.id:
            await bot.process_commands(message)
            return

        if 'http://' in message.content or 'https://' in message.content:
            words = message.content.split()
            url = next((word for word in words if word.startswith(('http://', 'https://'))), None)

            if url:
                success, response = await room.add_applicant(message.author, url)
                if success:
                    await message.add_reaction("✅")
                    await asyncio.sleep(2)
                    await message.delete()
                else:
                    await message.reply(f"❌ {response}", delete_after=10)
        else:
            await message.reply(f"❌ Отправьте ссылку на персонажа!", delete_after=10)
            await asyncio.sleep(5)
            await message.delete()

    await bot.process_commands(message)


@bot.event
async def on_reaction_add(reaction, user):
    """Обрабатывает реакции создателя"""
    if user.bot:
        return

    if reaction.message.channel.id in active_rooms:
        room = active_rooms[reaction.message.channel.id]

        if user.id == room.creator.id:
            if str(reaction.emoji) in ["✅", "❌"]:
                await room.process_selection(user, reaction.message, str(reaction.emoji))


@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user.name} запущен и готов к работе!')
    print(f'ID бота: {bot.user.id}')
    print('------')


# Запуск бота
if __name__ == "__main__":
    TOKEN = os.environ.get('DISCORD_TOKEN')  # Railway передает токен через переменные окружения
    if not TOKEN:
        print("❌ DISCORD_TOKEN не найден в переменных окружения!")
        exit(1)
    bot.run(TOKEN)