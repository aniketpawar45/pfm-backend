import os
import io
import httpx
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from api.core.config import settings
from api.services.ai_service import AIService
from api.services.db_service import DBService

class TelegramService:
    @classmethod
    def get_api_url(cls) -> str:
        token = getattr(settings, "TELEGRAM_BOT_TOKEN", None)
        if not token:
            token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        
        if isinstance(token, str):
            token = token.strip(" '\"")
            
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable is missing or empty.")
            
        return f"https://api.telegram.org/bot{token}"

    @classmethod
    async def send_message(cls, chat_id: int, text: str) -> int | None:
        url = f"{cls.get_api_url()}/sendMessage"
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML"
                })
                data = response.json()
                if data.get("ok"):
                    return data["result"]["message_id"]
            except Exception as e:
                print(f"Failed to send Telegram message: {str(e)}")
        return None

    @classmethod
    async def edit_message(cls, chat_id: int, message_id: int, text: str):
        if not message_id:
            return
        url = f"{cls.get_api_url()}/editMessageText"
        async with httpx.AsyncClient() as client:
            try:
                await client.post(url, json={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": text,
                    "parse_mode": "HTML"
                })
            except Exception as e:
                print(f"Failed to edit Telegram message: {str(e)}")

    @classmethod
    async def send_summary_report(cls, chat_id: int, query_arg: str = ""):
        try:
            summary = DBService.get_summary(chat_id, query_arg=query_arg)
            
            if summary["count"] == 0:
                await cls.send_message(
                    chat_id, 
                    f"📊 <b>{summary['title']}</b>\n\nNo transactions logged for this period!"
                )
                return

            cat_breakdown = "\n".join([
                f"  • {cat}: ₹{amt:,.2f}" for cat, amt in summary["categories"].items()
            ]) or "  • None"

            report = (
                f"📊 <b>{summary['title']}</b>\n\n"
                f"📥 <b>Total Income:</b> ₹{summary['total_income']:,.2f}\n"
                f"📤 <b>Total Expenses:</b> ₹{summary['total_expense']:,.2f}\n"
                f"🔄 <b>Total Transfers:</b> ₹{summary['total_transfer']:,.2f}\n"
                f"💰 <b>Net Balance:</b> ₹{summary['net_balance']:,.2f}\n\n"
                f"🏷️ <b>Expense Categories:</b>\n{cat_breakdown}\n\n"
                f"<i>Total records analyzed: {summary['count']}</i>"
            )
            await cls.send_message(chat_id, report)
        except Exception as e:
            await cls.send_message(chat_id, f"❌ <b>Error generating summary</b>\n<code>{str(e)}</code>")

    @classmethod
    async def send_chart_report(cls, chat_id: int, query_arg: str = ""):
        try:
            title, categories = DBService.get_category_data_for_chart(chat_id, query_arg=query_arg)
            
            if not categories:
                await cls.send_message(
                    chat_id, 
                    f"📊 <b>{title}</b>\n\nNo expense records found to generate a chart!"
                )
                return

            labels = list(categories.keys())
            amounts = list(categories.values())

            plt.figure(figsize=(7, 7))
            plt.style.use('dark_background')
            
            colors = ['#ff9999', '#66b3ff', '#99ff99', '#ffcc99', '#c2c2f0', '#ffb3e6', '#c4e1ff']
            
            wedges, texts, autotexts = plt.pie(
                amounts, 
                labels=labels, 
                autopct='%1.1f%%', 
                startangle=140, 
                colors=colors[:len(labels)],
                wedgeprops=dict(width=0.4, edgecolor='w')
            )
            
            plt.setp(autotexts, size=10, weight="bold")
            plt.setp(texts, size=11)
            plt.title(f"Expense Breakdown\n{title}", fontsize=14, pad=20, weight='bold', color='white')

            buf = io.BytesIO()
            plt.savefig(buf, format='png', bbox_inches='tight', transparent=True)
            buf.seek(0)
            plt.close()

            url = f"{cls.get_api_url()}/sendPhoto"
            async with httpx.AsyncClient() as client:
                files = {"photo": ("chart.png", buf.read(), "image/png")}
                data = {
                    "chat_id": chat_id,
                    "caption": f"📊 <b>Visual Expense Breakdown — {title}</b>",
                    "parse_mode": "HTML"
                }
                await client.post(url, data=data, files=files)

        except Exception as e:
            await cls.send_message(chat_id, f"❌ <b>Error generating chart</b>\n<code>{str(e)}</code>")

    @classmethod
    async def process_natural_language(cls, chat_id: int, text_input: str = None, audio_bytes: bytes = None):
        msg_id = await cls.send_message(
            chat_id, 
            "🔄 <b>[25%]</b> Analyzing input & extracting financial data..."
        )

        try:
            if msg_id:
                await cls.edit_message(
                    chat_id, 
                    msg_id, 
                    "🔄 <b>[60%]</b> Processing items through AI model..."
                )

            parsed_data = AIService.parse_transaction(text_input=text_input, audio_bytes=audio_bytes)
            
            if msg_id:
                await cls.edit_message(
                    chat_id, 
                    msg_id, 
                    "🔄 <b>[90%]</b> Validating amounts & saving to Supabase ledger..."
                )

            DBService.save_transactions(chat_id, parsed_data)

            if isinstance(parsed_data, list):
                if not parsed_data:
                    await cls.edit_message(chat_id, msg_id, "🤖 <b>No transactions found</b> in your message.")
                    return
                
                valid_items = [item for item in parsed_data if item.get("is_transaction", True)]
                if not valid_items:
                    await cls.edit_message(
                        chat_id, 
                        msg_id, 
                        "🤖 <b>PFM Assistant</b>\nSend me expenses, income notes, or itemized lists to log them!"
                    )
                    return

                missing_amount_items = [item for item in valid_items if item.get("amount") is None]
                if missing_amount_items:
                    item_desc = missing_amount_items[0].get("description") or "transaction"
                    await cls.edit_message(
                        chat_id, 
                        msg_id, 
                        f"⚠️ <b>Incomplete Entry Detected</b>\nI noticed an item ('<code>{item_desc}</code>'), but the amount is missing. Please specify how much."
                    )
                    return

                if len(valid_items) == 1:
                    item = valid_items[0]
                    desc = item.get("description") or "Miscellaneous"
                    amount = item.get("amount")
                    t_type = item.get("type", "expense")
                    t_category = item.get("category", "Miscellaneous")
                    t_date = item.get("date", "Today")

                    final_text = (
                        f"✨ <b>Transaction Logged & Saved!</b>\n\n"
                        f"🔹 <b>Description:</b> {desc}\n"
                        f"💰 <b>Amount:</b> ₹{amount:,.2f}\n"
                        f"📂 <b>Type:</b> {t_type.capitalize()}\n"
                        f"🏷️ <b>Category:</b> {t_category}\n"
                        f"📅 <b>Date:</b> {t_date}"
                    )
                    await cls.edit_message(chat_id, msg_id, final_text)
                    return

                formatted_list = "\n".join([
                    f"• <b>{item.get('description') or 'Miscellaneous'}</b>: ₹{item.get('amount'):,.2f} <i>({item.get('type', 'expense')})</i>" 
                    for item in valid_items
                ])
                
                final_text = (
                    f"✨ <b>Bulk Transactions Logged & Saved!</b>\n"
                    f"<i>Processed & saved <b>{len(valid_items)}</b> items</i>\n\n"
                    f"{formatted_list}"
                )
                await cls.edit_message(chat_id, msg_id, final_text)
                return

            if isinstance(parsed_data, dict):
                if not parsed_data.get("is_transaction", True):
                    await cls.edit_message(
                        chat_id, 
                        msg_id, 
                        "🤖 <b>PFM Assistant</b>\nSend me expenses, income notes, or itemized lists to log them!"
                    )
                    return

                if parsed_data.get("amount") is None:
                    await cls.edit_message(chat_id, msg_id, "⚠️ <b>Amount Missing</b>")
                    return

                desc = parsed_data.get("description") or "Miscellaneous"
                amount = parsed_data.get("amount")
                t_type = parsed_data.get("type", "expense")
                t_category = parsed_data.get("category", "Miscellaneous")
                t_date = parsed_data.get("date", "Today")

                final_text = (
                    f"✨ <b>Transaction Logged & Saved!</b>\n\n"
                    f"🔹 <b>Description:</b> {desc}\n"
                    f"💰 <b>Amount:</b> ₹{amount:,.2f}\n"
                    f"📂 <b>Type:</b> {t_type.capitalize()}\n"
                    f"🏷️ <b>Category:</b> {t_category}\n"
                    f"📅 <b>Date:</b> {t_date}"
                )
                await cls.edit_message(chat_id, msg_id, final_text)
                return
            
        except Exception as e:
            error_msg = f"❌ <b>Error Occurred</b>\n<code>{str(e)}</code>"
            if msg_id:
                await cls.edit_message(chat_id, msg_id, error_msg)
            else:
                await cls.send_message(chat_id, error_msg)

    @classmethod
    async def process_update(cls, update: dict):
        message = update.get("message") or update.get("edited_message")
        if not message:
            return

        chat_id = message["chat"]["id"]
        text = message.get("text", "").strip()
        voice = message.get("voice")

        text_lower = text.lower()
        
        # Summary Command Handler
        if text_lower.startswith("/summary") or text_lower.startswith("/report") or text_lower.startswith("/month"):
            parts = text.split(maxsplit=1)
            query_arg = parts[1] if len(parts) > 1 else ""
            await cls.send_summary_report(chat_id, query_arg=query_arg)
            return

        # Chart Command Handler
        if text_lower.startswith("/chart") or text_lower.startswith("/graph"):
            parts = text.split(maxsplit=1)
            query_arg = parts[1] if len(parts) > 1 else ""
            await cls.send_chart_report(chat_id, query_arg=query_arg)
            return

        audio_bytes = None
        if voice:
            file_id = voice["file_id"]
            async with httpx.AsyncClient() as client:
                file_info_resp = await client.get(f"{cls.get_api_url()}/getFile?file_id={file_id}")
                file_path = file_info_resp.json()["result"]["file_path"]
                token = getattr(settings, "TELEGRAM_BOT_TOKEN", None) or os.getenv("TELEGRAM_BOT_TOKEN", "")
                token = str(token).strip(" '\"")
                file_resp = await client.get(f"https://api.telegram.org/file/bot{token}/{file_path}")
                audio_bytes = file_resp.content

        if text or audio_bytes:
            await cls.process_natural_language(chat_id, text_input=text, audio_bytes=audio_bytes)