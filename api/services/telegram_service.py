import os
import io
import csv
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
    async def send_message(cls, chat_id: int, text: str, reply_markup: dict = None) -> int | None:
        url = f"{cls.get_api_url()}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, json=payload)
                data = response.json()
                if data.get("ok"):
                    return data["result"]["message_id"]
            except Exception as e:
                print(f"Failed to send Telegram message: {str(e)}")
        return None

    @classmethod
    async def edit_message(cls, chat_id: int, message_id: int, text: str, reply_markup: dict = None):
        if not message_id:
            return
        url = f"{cls.get_api_url()}/editMessageText"
        payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML"}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        else:
            payload["reply_markup"] = {"inline_keyboard": []}
        async with httpx.AsyncClient() as client:
            try:
                await client.post(url, json=payload)
            except Exception as e:
                print(f"Failed to edit Telegram message: {str(e)}")

    @classmethod
    async def answer_callback_query(cls, callback_query_id: str, text: str = ""):
        url = f"{cls.get_api_url()}/answerCallbackQuery"
        async with httpx.AsyncClient() as client:
            try:
                await client.post(url, json={"callback_query_id": callback_query_id, "text": text})
            except Exception as e:
                print(f"Failed to answer callback query: {str(e)}")

    @classmethod
    def build_delete_keyboard(cls, records: list, selected_ids: set, page: int, total_pages: int, query_arg: str) -> dict:
        keyboard = []
        for r in records:
            tx_id = r["id"]
            is_selected = tx_id in selected_ids
            
            icon = "🟢" if is_selected else "⚪"
            desc = r.get("description") or "Misc"
            amt = float(r.get("amount", 0))
            date = r.get("date")
            
            btn_text = f"{icon} {date} | {desc} — ₹{amt:,.2f}"
            keyboard.append([{"text": btn_text, "callback_data": f"del_t:{tx_id}:{page}:{query_arg}"}])
            
        nav_row = []
        if page > 0:
            nav_row.append({"text": "⬅️ Prev", "callback_data": f"del_pg:{page - 1}:{query_arg}"})
        
        nav_row.append({"text": f"📄 {page + 1}/{total_pages}", "callback_data": "del_noop"})
        
        if page < total_pages - 1:
            nav_row.append({"text": "Next ➡️", "callback_data": f"del_pg:{page + 1}:{query_arg}"})
            
        keyboard.append(nav_row)
        
        count = len(selected_ids)
        action_row = [
            {"text": f"🗑️ Confirm Delete ({count})", "callback_data": "del_confirm"},
            {"text": "❌ Cancel", "callback_data": "del_cancel"}
        ]
        keyboard.append(action_row)
        return {"inline_keyboard": keyboard}

    @classmethod
    async def send_delete_menu(cls, chat_id: int, query_arg: str = "", page: int = 0):
        try:
            if page == 0:
                DBService.clear_user_selections(chat_id)
                
            title, records, total_records, total_pages, selected_ids = DBService.get_delete_page_data(chat_id, query_arg=query_arg, page=page, page_size=5)
            
            if total_records == 0:
                await cls.send_message(chat_id, f"🗑️ <b>Delete Manager — {title}</b>\n\nNo transactions found matching your query.")
                return

            text = (
                f"🗑️ <b>Delete Manager — {title}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"🟢 <b>Selected Items:</b> {len(selected_ids)}\n"
                f"⚪ <b>Total Records:</b> {total_records}\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"<i>Page {page + 1} of {total_pages} (5 items/page)</i>"
            )
            markup = cls.build_delete_keyboard(records, selected_ids, page, total_pages, query_arg)
            await cls.send_message(chat_id, text, reply_markup=markup)
        except Exception as e:
            await cls.send_message(chat_id, f"❌ <b>Error opening delete menu</b>\n<code>{str(e)}</code>")

    @classmethod
    async def update_delete_menu(cls, chat_id: int, message_id: int, query_arg: str = "", page: int = 0, toggle_tx_id: int | None = None):
        try:
            if toggle_tx_id is not None:
                DBService.toggle_selection(chat_id, toggle_tx_id)
                
            title, records, total_records, total_pages, selected_ids = DBService.get_delete_page_data(chat_id, query_arg=query_arg, page=page, page_size=5)
            
            text = (
                f"🗑️ <b>Delete Manager — {title}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"🟢 <b>Selected Items:</b> {len(selected_ids)}\n"
                f"⚪ <b>Total Records:</b> {total_records}\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"<i>Page {page + 1} of {total_pages} (5 items/page)</i>"
            )
            markup = cls.build_delete_keyboard(records, selected_ids, page, total_pages, query_arg)
            await cls.edit_message(chat_id, message_id, text, reply_markup=markup)
        except Exception as e:
            print(f"Failed to update delete menu: {str(e)}")

    @classmethod
    async def send_summary_report(cls, chat_id: int, query_arg: str = ""):
        try:
            summary = DBService.get_summary(chat_id, query_arg=query_arg)
            if summary["count"] == 0:
                await cls.send_message(chat_id, f"📊 <b>{summary['title']}</b>\n\nNo transactions logged for this period!")
                return
            cat_breakdown = "\n".join([f"  • {cat}: ₹{amt:,.2f}" for cat, amt in summary["categories"].items()]) or "  • None"
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
                await cls.send_message(chat_id, f"📊 <b>{title}</b>\n\nNo expense records found to generate a chart!")
                return
            labels = list(categories.keys())
            amounts = list(categories.values())
            plt.figure(figsize=(7, 7))
            plt.style.use('dark_background')
            colors = ['#ff9999', '#66b3ff', '#99ff99', '#ffcc99', '#c2c2f0', '#ffb3e6', '#c4e1ff']
            wedges, texts, autotexts = plt.pie(
                amounts, labels=labels, autopct='%1.1f%%', startangle=140,
                colors=colors[:len(labels)], wedgeprops=dict(width=0.4, edgecolor='w')
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
                data = {"chat_id": chat_id, "caption": f"📊 <b>Visual Expense Breakdown — {title}</b>", "parse_mode": "HTML"}
                await client.post(url, data=data, files=files)
        except Exception as e:
            await cls.send_message(chat_id, f"❌ <b>Error generating chart</b>\n<code>{str(e)}</code>")

    @classmethod
    async def send_csv_export(cls, chat_id: int, query_arg: str = ""):
        try:
            filename, title, records = DBService.get_transactions_for_export(chat_id, query_arg=query_arg)
            if not records:
                await cls.send_message(chat_id, f"📁 <b>Export Failed</b>\nNo transactions found for export.")
                return
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["ID", "Date", "Type", "Category", "Description", "Amount (INR)", "Chat ID"])
            for r in records:
                writer.writerow([r.get("id"), r.get("date"), r.get("type"), r.get("category"), r.get("description"), r.get("amount"), r.get("chat_id")])
            csv_bytes = output.getvalue().encode('utf-8')
            buf = io.BytesIO(csv_bytes)
            buf.seek(0)
            url = f"{cls.get_api_url()}/sendDocument"
            async with httpx.AsyncClient() as client:
                files = {"document": (filename, buf.read(), "text/csv")}
                data = {"chat_id": chat_id, "caption": f"📁 <b>CSV Transaction Export</b>\n{title}", "parse_mode": "HTML"}
                await client.post(url, data=data, files=files)
        except Exception as e:
            await cls.send_message(chat_id, f"❌ <b>Error exporting CSV</b>\n<code>{str(e)}</code>")

    @classmethod
    async def send_drilldown_report(cls, chat_id: int, category_query: str):
        try:
            cat_name, records = DBService.get_category_drilldown_data(chat_id, category_query)
            if not records:
                await cls.send_message(chat_id, f"🔍 <b>Category Drill-down: {cat_name}</b>\nNo transactions found for this category this month.")
                return
            total_amt = sum(float(r["amount"]) for r in records if r["type"] == "expense")
            items_str = "\n".join([f"  • {r['date']} - <b>{r['description']}</b>: ₹{float(r['amount']):,.2f}" for r in records])
            report = (
                f"🔍 <b>Drill-down: {cat_name} (This Month)</b>\n\n{items_str}\n\n"
                f"💰 <b>Total Spent on {cat_name}:</b> ₹{total_amt:,.2f}\n<i>Total items: {len(records)}</i>"
            )
            await cls.send_message(chat_id, report)
        except Exception as e:
            await cls.send_message(chat_id, f"❌ <b>Error generating drill-down</b>\n<code>{str(e)}</code>")

    @classmethod
    async def process_natural_language(cls, chat_id: int, text_input: str = None, audio_bytes: bytes = None):
        msg_id = await cls.send_message(chat_id, "🔄 <b>[25%]</b> Analyzing input & extracting financial data...")
        try:
            if msg_id:
                await cls.edit_message(chat_id, msg_id, "🔄 <b>[60%]</b> Processing items through AI model...")
            parsed_data = AIService.parse_transaction(text_input=text_input, audio_bytes=audio_bytes)
            if msg_id:
                await cls.edit_message(chat_id, msg_id, "🔄 <b>[90%]</b> Validating amounts & saving to Supabase ledger...")
            saved_records = DBService.save_transactions(chat_id, parsed_data)

            if isinstance(parsed_data, list):
                if not parsed_data or not saved_records:
                    await cls.edit_message(chat_id, msg_id, "🤖 <b>No transactions found</b> in your message.")
                    return
                formatted_list = "\n".join([f"• <b>{r.get('description')}</b>: ₹{r.get('amount'):,.2f} <i>({r.get('type')})</i>" for r in saved_records])
                final_text = f"✨ <b>Bulk Transactions Logged & Saved!</b>\n<i>Processed & saved <b>{len(saved_records)}</b> items</i>\n\n{formatted_list}"
                await cls.edit_message(chat_id, msg_id, final_text)
                return

            if isinstance(parsed_data, dict):
                if not parsed_data.get("is_transaction", True) or not saved_records:
                    await cls.edit_message(chat_id, msg_id, "🤖 <b>PFM Assistant</b>\nSend me expenses, income notes, or itemized lists to log them!")
                    return
                record = saved_records[0]
                final_text = (
                    f"✨ <b>Transaction Logged & Saved!</b>\n\n"
                    f"🔹 <b>Description:</b> {record.get('description')}\n"
                    f"💰 <b>Amount:</b> ₹{record.get('amount'):,.2f}\n"
                    f"📂 <b>Type:</b> {record.get('type', 'expense').capitalize()}\n"
                    f"🏷️ <b>Category:</b> {record.get('category')}\n"
                    f"📅 <b>Date:</b> {record.get('date')}"
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
        callback_query = update.get("callback_query")
        if callback_query:
            query_id = callback_query["id"]
            data = callback_query.get("data", "")
            message = callback_query.get("message")
            chat_id = message["chat"]["id"] if message else callback_query["from"]["id"]
            message_id = message["message_id"] if message else None

            if data == "del_noop":
                await cls.answer_callback_query(query_id, "Page indicator")
                return

            if data.startswith("del_t:"):
                parts = data.split(":", 3)
                tx_id = int(parts[1])
                page = int(parts[2])
                query_arg = parts[3] if len(parts) > 3 else ""
                
                await cls.answer_callback_query(query_id, "Selection updated")
                if message_id:
                    await cls.update_delete_menu(chat_id, message_id, query_arg=query_arg, page=page, toggle_tx_id=tx_id)
                return

            if data.startswith("del_pg:"):
                parts = data.split(":", 2)
                page = int(parts[1])
                query_arg = parts[2] if len(parts) > 2 else ""
                
                await cls.answer_callback_query(query_id, f"Page {page + 1}")
                if message_id:
                    await cls.update_delete_menu(chat_id, message_id, query_arg=query_arg, page=page, toggle_tx_id=None)
                return

            if data == "del_confirm":
                deleted_count = DBService.confirm_and_delete(chat_id)
                await cls.answer_callback_query(query_id, f"Deleted {deleted_count} transactions")
                if message_id:
                    await cls.edit_message(
                        chat_id, 
                        message_id, 
                        f"🗑️ <b>Transactions Deleted Successfully</b>\n<i>Removed {deleted_count} selected entries from your ledger.</i>"
                    )
                return

            if data == "del_cancel":
                DBService.clear_user_selections(chat_id)
                await cls.answer_callback_query(query_id, "Deletion cancelled")
                if message_id:
                    await cls.edit_message(chat_id, message_id, "❌ <b>Deletion cancelled.</b>")
                return
            return

        message = update.get("message") or update.get("edited_message")
        if not message:
            return

        chat_id = message["chat"]["id"]
        text = message.get("text", "").strip()
        voice = message.get("voice")

        text_lower = text.lower()
        
        if text_lower.startswith("/delete") or text_lower.startswith("/remove"):
            parts = text.split(maxsplit=1)
            query_arg = parts[1] if len(parts) > 1 else ""
            await cls.send_delete_menu(chat_id, query_arg=query_arg, page=0)
            return

        if text_lower.startswith("/summary") or text_lower.startswith("/report") or text_lower.startswith("/month"):
            parts = text.split(maxsplit=1)
            query_arg = parts[1] if len(parts) > 1 else ""
            await cls.send_summary_report(chat_id, query_arg=query_arg)
            return

        if text_lower.startswith("/chart") or text_lower.startswith("/graph"):
            parts = text.split(maxsplit=1)
            query_arg = parts[1] if len(parts) > 1 else ""
            await cls.send_chart_report(chat_id, query_arg=query_arg)
            return

        if text_lower.startswith("/export") or text_lower.startswith("/csv"):
            parts = text.split(maxsplit=1)
            query_arg = parts[1] if len(parts) > 1 else ""
            await cls.send_csv_export(chat_id, query_arg=query_arg)
            return

        if text_lower.startswith("/drilldown") or text_lower.startswith("/category"):
            parts = text.split(maxsplit=1)
            query_arg = parts[1] if len(parts) > 1 else ""
            if not query_arg:
                await cls.send_message(chat_id, "⚠️ Please specify a category name, e.g., `/drilldown food`")
                return
            await cls.send_drilldown_report(chat_id, category_query=query_arg)
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
