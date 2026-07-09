import discord
from discord.ext import commands
from discord import ui
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

# ============================================
# МОДАЛЬНОЕ ОКНО ДЛЯ СОЗДАНИЯ КОМНАТЫ
# ============================================

class CreateRoomModal(ui.Modal, title="Создание комнаты"):
    def __init__(self, role: discord.Role):
        super().__init__()
        self.role = role
    
    description = ui.TextInput(
        label="Описание комнаты",
        placeholder="Например: Нужен маг для рейда в подземелье",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        if interaction.channel.id in active_rooms:
            await interaction.response.send_message(
                "❌ В этом канале уже есть активная комната!", 
                ephemeral=True
            )
            return
        
        room = CharacterRoom(
            creator=interaction.user,
            channel=interaction.channel,
            role=self.role,
            description=self.description.value
        )
        active_rooms[interaction.channel.id] = room
        
        await interaction.response.send_message(
            f"✅ Комната для роли {self.role.mention} создается...", 
            ephemeral=True
        )
        
        await room.create_room_message()

# ============================================
# МОДАЛЬНОЕ ОКНО ДЛЯ ПОДАЧИ ЗАЯВКИ
# ============================================

class ApplicationModal(ui.Modal, title="Подать заявку"):
    def __init__(self, room):
        super().__init__()
        self.room = room
    
    character_name = ui.TextInput(
        label="Имя персонажа",
        placeholder="Введите имя вашего персонажа",
        max_length=100
    )
    
    character_url = ui.TextInput(
        label="Ссылка на персонажа",
        placeholder="https://example.com/my-character",
        max_length=500
    )
    
    class_description = ui.TextInput(
        label="Класс/Описание",
        placeholder="Например: Маг 80 уровня",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        success, response = await self.room.add_applicant(
            interaction.user, 
            self.character_url.value,
            self.character_name.value,
            self.class_description.value
        )
        
        if success:
            await interaction.response.send_message(
                "✅ Ваша заявка успешно подана!", 
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ {response}", 
                ephemeral=True
            )

# ============================================
# КЛАСС КОМНАТЫ
# ============================================

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
        """Создает основное сообщение комнаты с кнопками"""
        embed = discord.Embed(
            title=f"📋 Набор: {self.role.name}",
            description=self.description or f"Поиск кандидатов на роль {self.role.mention}",
            color=self.role.color if self.role.color != discord.Color.default() else discord.Color.blue()
        )
        embed.add_field(name="👑 Создатель", value=self.creator.mention, inline=True)
        embed.add_field(name="🎭 Роль", value=self.role.mention, inline=True)
        embed.add_field(name="📊 Статус", value="🟢 Открыт набор", inline=True)
        embed.add_field(
            name="📝 Как участвовать",
            value=f"Нажмите кнопку **«Отправить заявку»** ниже\n"
                  f"Требуется роль: {self.role.mention}",
            inline=False
        )
        embed.add_field(
            name="📈 Статистика",
            value="Заявок: 0 | Принято: 0 | Отклонено: 0 | Ожидают: 0",
            inline=False
        )
        embed.set_footer(text=f"ID комнаты: {self.channel.id}")
        
        # Создаем view с кнопками
        view = RoomView(self)
        
        self.main_message = await self.channel.send(
            content=f"{self.role.mention} - открыт набор!",
            embed=embed,
            view=view
        )
        return self.main_message
    
    async def update_main_message(self):
        """Обновляет основное сообщение комнаты"""
        if not self.main_message:
            return
        
        embed = self.main_message.embeds[0]
        
        # Обновляем статус
        if not self.is_open:
            embed.set_field_at(2, name="📊 Статус", value="🔴 Набор закрыт", inline=True)
        else:
            embed.set_field_at(2, name="📊 Статус", value="🟢 Открыт набор", inline=True)
        
        # Обновляем статистику
        total = len(self.applicants)
        accepted = sum(1 for a in self.applicants.values() if a['status'] == 'accepted')
        rejected = sum(1 for a in self.applicants.values() if a['status'] == 'rejected')
        pending = sum(1 for a in self.applicants.values() if a['status'] == 'pending')
        
        stats = f"Заявок: {total} | Принято: {accepted} | Отклонено: {rejected} | Ожидают: {pending}"
        embed.set_field_at(4, name="📈 Статистика", value=stats, inline=False)
        
        # Обновляем view (убираем кнопки если закрыто)
        view = RoomView(self) if self.is_open else None
        
        await self.main_message.edit(embed=embed, view=view)
    
    async def add_applicant(self, user: discord.Member, character_url: str, 
                           character_name: str = "", class_description: str = ""):
        """Добавляет заявку от участника"""
        if not self.is_open:
            return False, "Набор в комнату закрыт!"
            
        if str(user.id) in self.applicants:
            return False, "Вы уже подали заявку!"
        
        if self.role not in user.roles:
            return False, f"У вас нет роли {self.role.mention}!"
        
        # Сохраняем заявку
        self.applicants[str(user.id)] = {
            'user': user,
            'character_url': character_url,
            'character_name': character_name,
            'class_description': class_description,
            'status': 'pending'
        }
        
        # Создаем сообщение с заявкой
        embed = discord.Embed(
            title=f"📝 Заявка от {user.display_name}",
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        
        if character_name:
            embed.add_field(name="👤 Персонаж", value=character_name, inline=True)
        if class_description:
            embed.add_field(name="⚔️ Класс", value=class_description, inline=True)
        
        embed.add_field(name="🔗 Ссылка", value=f"[Открыть]({character_url})", inline=False)
        embed.add_field(name="📌 Статус", value="⏳ На рассмотрении", inline=True)
        embed.add_field(name="👤 Участник", value=user.mention, inline=True)
        embed.set_footer(text=f"ID заявки: {user.id}")
        
        # Создаем view с кнопками для создателя
        view = ApplicationView(self, user)
        
        application_message = await self.channel.send(embed=embed, view=view)
        self.applicants[str(user.id)]['message'] = application_message
        
        # Обновляем основное сообщение
        await self.update_main_message()
        
        return True, "Заявка успешно подана!"
    
    async def process_selection(self, interaction: discord.Interaction, 
                                user: discord.Member, accepted: bool):
        """Обрабатывает выбор создателя"""
        if interaction.user.id != self.creator.id:
            await interaction.response.send_message(
                "❌ Только создатель комнаты может принимать решения!", 
                ephemeral=True
            )
            return
        
        applicant = self.applicants.get(str(user.id))
        if not applicant or applicant['status'] != 'pending':
            await interaction.response.send_message(
                "❌ Эта заявка уже обработана!", 
                ephemeral=True
            )
            return
        
        if accepted:
            applicant['status'] = 'accepted'
            await self.notify_applicant(user, True)
            
            # Обновляем сообщение заявки
            if applicant.get('message'):
                embed = applicant['message'].embeds[0]
                embed.color = discord.Color.green()
                embed.set_field_at(
                    len(embed.fields) - 2, 
                    name="📌 Статус", 
                    value="✅ Принят!", 
                    inline=True
                )
                await applicant['message'].edit(embed=embed, view=None)
        else:
            applicant['status'] = 'rejected'
            await self.notify_applicant(user, False)
            
            # Обновляем сообщение заявки
            if applicant.get('message'):
                embed = applicant['message'].embeds[0]
                embed.color = discord.Color.red()
                embed.set_field_at(
                    len(embed.fields) - 2, 
                    name="📌 Статус", 
                    value="❌ Отклонен", 
                    inline=True
                )
                await applicant['message'].edit(embed=embed, view=None)
        
        await interaction.response.send_message(
            f"{'✅ Принято' if accepted else '❌ Отклонено'}!", 
            ephemeral=True
        )
        
        # Обновляем основное сообщение
        await self.update_main_message()
        
        # Проверяем, все ли заявки обработаны
        await self.check_all_processed()
    
    async def notify_applicant(self, user: discord.Member, accepted: bool):
        """Отправляет уведомление участнику"""
        try:
            if accepted:
                embed = discord.Embed(
                    title="✅ Заявка принята!",
                    description=f"Ваша заявка на роль **{self.role.name}** одобрена создателем {self.creator.mention}!",
                    color=discord.Color.green()
                )
            else:
                embed = discord.Embed(
                    title="❌ Заявка отклонена",
                    description=f"Ваша заявка на роль **{self.role.name}** была отклонена.",
                    color=discord.Color.red()
                )
            
            embed.add_field(name="Роль", value=self.role.mention, inline=True)
            embed.add_field(name="Канал", value=self.channel.mention, inline=True)
            await user.send(embed=embed)
        except discord.Forbidden:
            if accepted:
                await self.channel.send(
                    f"{user.mention} ✅ Ваша заявка на роль {self.role.mention} принята!", 
                    delete_after=30
                )
            else:
                await self.channel.send(
                    f"{user.mention} ❌ Ваша заявка на роль {self.role.mention} отклонена.", 
                    delete_after=30
                )
    
    async def check_all_processed(self):
        """Проверяет, все ли заявки обработаны"""
        all_processed = all(
            applicant['status'] != 'pending' 
            for applicant in self.applicants.values()
        )
        
        if all_processed and self.applicants:
            await self.close_room(auto=True)
    
    async def close_room(self, auto=False):
        """Закрывает комнату"""
        self.is_open = False
        
        if auto:
            # Отклоняем необработанные заявки
            for user_id, applicant in self.applicants.items():
                if applicant['status'] == 'pending':
                    applicant['status'] = 'rejected'
                    await self.notify_applicant(applicant['user'], False)
                    if applicant.get('message'):
                        embed = applicant['message'].embeds[0]
                        embed.color = discord.Color.red()
                        embed.set_field_at(
                            len(embed.fields) - 2, 
                            name="📌 Статус", 
                            value="❌ Набор закрыт", 
                            inline=True
                        )
                        await applicant['message'].edit(embed=embed, view=None)
        
        await self.update_main_message()

# ============================================
# VIEW С КНОПКАМИ ДЛЯ ОСНОВНОГО СООБЩЕНИЯ
# ============================================

class RoomView(ui.View):
    def __init__(self, room: CharacterRoom):
        super().__init__(timeout=None)
        self.room = room
    
    @ui.button(label="📝 Отправить заявку", style=discord.ButtonStyle.green, custom_id="apply_button")
    async def apply_button(self, interaction: discord.Interaction, button: ui.Button):
        """Кнопка для подачи заявки"""
        if interaction.user.id == self.room.creator.id:
            await interaction.response.send_message(
                "❌ Создатель комнаты не может подать заявку!", 
                ephemeral=True
            )
            return
        
        if str(interaction.user.id) in self.room.applicants:
            await interaction.response.send_message(
                "❌ Вы уже подали заявку!", 
                ephemeral=True
            )
            return
        
        if self.room.role not in interaction.user.roles:
            await interaction.response.send_message(
                f"❌ У вас нет роли {self.room.role.mention}!", 
                ephemeral=True
            )
            return
        
        # Открываем модальное окно для заполнения заявки
        modal = ApplicationModal(self.room)
        await interaction.response.send_modal(modal)
    
    @ui.button(label="📊 Статистика", style=discord.ButtonStyle.blurple, custom_id="stats_button")
    async def stats_button(self, interaction: discord.Interaction, button: ui.Button):
        """Кнопка для просмотра статистики"""
        total = len(self.room.applicants)
        accepted = sum(1 for a in self.room.applicants.values() if a['status'] == 'accepted')
        rejected = sum(1 for a in self.room.applicants.values() if a['status'] == 'rejected')
        pending = sum(1 for a in self.room.applicants.values() if a['status'] == 'pending')
        
        embed = discord.Embed(
            title=f"📊 Статистика набора: {self.room.role.name}",
            color=discord.Color.blue()
        )
        embed.add_field(name="📝 Всего заявок", value=str(total), inline=True)
        embed.add_field(name="✅ Принято", value=str(accepted), inline=True)
        embed.add_field(name="❌ Отклонено", value=str(rejected), inline=True)
        embed.add_field(name="⏳ Ожидают", value=str(pending), inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @ui.button(label="🔒 Закрыть набор", style=discord.ButtonStyle.red, custom_id="close_room_button")
    async def close_room_button(self, interaction: discord.Interaction, button: ui.Button):
        """Кнопка для закрытия комнаты (только для создателя)"""
        if interaction.user.id != self.room.creator.id:
            await interaction.response.send_message(
                "❌ Только создатель может закрыть набор!", 
                ephemeral=True
            )
            return
        
        await self.room.close_room()
        await interaction.response.send_message(
            "🔒 Набор закрыт!", 
            ephemeral=True
        )

# ============================================
# VIEW С КНОПКАМИ ДЛЯ ЗАЯВКИ (для создателя)
# ============================================

class ApplicationView(ui.View):
    def __init__(self, room: CharacterRoom, applicant: discord.Member):
        super().__init__(timeout=None)
        self.room = room
        self.applicant = applicant
    
    @ui.button(label="✅ Принять", style=discord.ButtonStyle.green, custom_id="accept_button")
    async def accept_button(self, interaction: discord.Interaction, button: ui.Button):
        """Кнопка для принятия заявки"""
        await self.room.process_selection(interaction, self.applicant, True)
    
    @ui.button(label="❌ Отклонить", style=discord.ButtonStyle.red, custom_id="reject_button")
    async def reject_button(self, interaction: discord.Interaction, button: ui.Button):
        """Кнопка для отклонения заявки"""
        await self.room.process_selection(interaction, self.applicant, False)

# ============================================
# СЛЭШ-КОМАНДЫ ДЛЯ УДОБСТВА
# ============================================

@bot.tree.command(name="create_room", description="Создать комнату для набора")
async def create_room_command(interaction: discord.Interaction, role: discord.Role, description: str = ""):
    """Создает комнату для отбора персонажей"""
    if interaction.channel.id in active_rooms:
        await interaction.response.send_message(
            "❌ В этом канале уже есть активная комната!", 
            ephemeral=True
        )
        return
    
    room = CharacterRoom(
        creator=interaction.user,
        channel=interaction.channel,
        role=role,
        description=description
    )
    active_rooms[interaction.channel.id] = room
    
    await interaction.response.send_message(
        f"✅ Комната для роли {role.mention} создается...", 
        ephemeral=True
    )
    
    await room.create_room_message()

@bot.tree.command(name="close_room", description="Закрыть активную комнату")
async def close_room_command(interaction: discord.Interaction):
    """Закрывает активную комнату"""
    if interaction.channel.id not in active_rooms:
        await interaction.response.send_message(
            "❌ В этом канале нет активной комнаты!", 
            ephemeral=True
        )
        return
    
    room = active_rooms[interaction.channel.id]
    if interaction.user.id != room.creator.id:
        await interaction.response.send_message(
            "❌ Только создатель может закрыть комнату!", 
            ephemeral=True
        )
        return
    
    await room.close_room()
    del active_rooms[interaction.channel.id]
    await interaction.response.send_message("🔒 Комната закрыта!", ephemeral=True)

@bot.tree.command(name="setup", description="Создать панель управления для создания комнат")
@commands.has_permissions(administrator=True)
async def setup_command(interaction: discord.Interaction):
    """Создает панель управления с кнопками выбора ролей"""
    embed = discord.Embed(
        title="🎯 Создание комнаты для набора",
        description="Выберите роль, для которой хотите открыть набор:",
        color=discord.Color.blue()
    )
    embed.set_footer(text="Нажмите на кнопку ниже и укажите роль")
    
    view = SetupView()
    await interaction.response.send_message(embed=embed, view=view)

class SetupView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @ui.button(label="🎭 Создать комнату", style=discord.ButtonStyle.green, custom_id="setup_create_room")
    async def create_room_button(self, interaction: discord.Interaction, button: ui.Button):
        """Открывает меню выбора роли"""
        # Создаем select menu с ролями
        roles = interaction.guild.roles[1:26]  # Первые 25 ролей (кроме @everyone)
        
        if not roles:
            await interaction.response.send_message("❌ Нет доступных ролей!", ephemeral=True)
            return
        
        options = [
            discord.SelectOption(label=role.name, value=str(role.id))
            for role in roles
        ]
        
        select = RoleSelect(options)
        view = ui.View()
        view.add_item(select)
        
        await interaction.response.send_message(
            "Выберите роль для набора:", 
            view=view, 
            ephemeral=True
        )

class RoleSelect(ui.Select):
    def __init__(self, options):
        super().__init__(placeholder="Выберите роль...", options=options)
    
    async def callback(self, interaction: discord.Interaction):
        role_id = int(self.values[0])
        role = interaction.guild.get_role(role_id)
        
        if role:
            modal = CreateRoomModal(role)
            await interaction.response.send_modal(modal)
        else:
            await interaction.response.send_message("❌ Роль не найдена!", ephemeral=True)

# ============================================
# ЗАПУСК БОТА
# ============================================

@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user.name} запущен и готов к работе!')
    print(f'ID бота: {bot.user.id}')
    
    # Синхронизируем слэш-команды
    try:
        synced = await bot.tree.sync()
        print(f"✅ Синхронизировано {len(synced)} слэш-команд")
    except Exception as e:
        print(f"❌ Ошибка синхронизации: {e}")
    
    print('------')

# Запуск бота
if __name__ == "__main__":
    TOKEN = os.environ.get('DISCORD_TOKEN')
    if not TOKEN:
        print("❌ DISCORD_TOKEN не найден в переменных окружения!")
        exit(1)
    bot.run(TOKEN)
