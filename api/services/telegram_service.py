import os
import io
import csv
import httpx
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import datetime, timezone, timedelta
from api.core.config import settings
from api.services.ai_service import AIService
from api.services.db_service import DBService

class TelegramService:
    @classmethod
    def get_api_url(cls) -> str:
        token = getattr(settings, "TELEGRAM_BOT_TOKEN", None) or os.getenv("TELEGRAM_BOT_TOKEN", "")
        token = str(token).strip(" '\"")
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
                await client.post(url, json={"callback_query_id": callback_query_id, "text": text, "cache_time": 0})
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
            title, records, total_records, total_pages, selected_ids = DBService.get_cached_delete_view(chat_id, query_arg=query_arg, page=page, page_size=5)
            if total_records == 0:
                await cls.send_message(chat_id, f"🗑️ <b>Delete Manager — {title}</b>\n\nNo transactions found.")
                return
            text = (
                f"🗑️ <b>Delete Manager — {title}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"🟢 <b>Selected Items:</b> {len(selected_ids)}\n"
                f"⚪ <b>Total Records:</b> {total_records}\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"<i>Page {page + 1} of {total_pages}</i>"
            )
            markup = cls.build_delete_keyboard(records, selected_ids, page, total_pages, query_arg)
            await cls.send_message(chat_id, text, reply_markup=markup)
        except Exception as e:
            await cls.send_message(chat_id, f"❌ Error: <code>{str(e)}</code>")

    @classmethod
    async def update_delete_menu(cls, chat_id: int, message_id: int, query_arg: str = "", page: int = 0, toggle_tx_id: int | None = None):
        try:
            title, records, total_records, total_pages, selected_ids = DBService.get_cached_delete_view(
                chat_id, query_arg=query_arg, page=page, page_size=5, toggle_tx_id=toggle_tx_id
            )
            text = (
                f"🗑️ <b>Delete Manager — {title}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"🟢 <b>Selected Items:</b> {len(selected_ids)}\n"
                f"⚪ <b>Total Records:</b> {total_records}\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"<i>Page {page + 1} of {total_pages}</i>"
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
            await cls.send_message(chat_id, f"❌ Error: <code>{str(e)}</code>")

    @classmethod
    async def send_chart_report(cls, chat_id: int, query_arg: str = ""):
        try:
            title, categories = DBService.get_category_data_for_chart(chat_id, query_arg=query_arg)
            if not categories:
                await cls.send_message(chat_id, f"📊 <b>{title}</b>\n\nNo expense records found!")
                return
            labels = list(categories.keys())
            amounts = list(categories.values())
            plt.figure(figsize=(7, 7))
            plt.style.use('dark_background')
            colors = ['#ff9999', '#66b3ff', '#99ff99', '#ffcc99', '#c2c2f0', '#ffb3e6']
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
                data = {"chat_id": chat_id, "caption": f"📊 <b>Visual Breakdown — {title}</b>", "parse_mode": "HTML"}
                await client.post(url, data=data, files=files)
        except Exception as e:
            await cls.send_message(chat_id, f"❌ Error: <code>{str(e)}</code>")

    @classmethod
    async def send_csv_export(cls, chat_id: int, query_arg: str = ""):
        try:
            filename, title, records = DBService.get_transactions_for_export(chat_id, query_arg=query_arg)
            if not records:
                await cls.send_message(chat_id, "📁 No transactions found for export.")
                return
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["ID", "Date", "Type", "Category", "Description", "Amount (INR)", "Chat ID"])
            for r in records:
                writer.writerow([r.get("id"), r.get("date"), r.get("type"), r.get("category"), r.get("description"), r.get("amount"), r.get("chat_id")])
            buf = io.BytesIO(output.getvalue().encode('utf-8'))
            buf.seek(0)
            url = f"{cls.get_api_url()}/sendDocument"
            async with httpx.AsyncClient() as client:
                files = {"document": (filename, buf.read(), "text/csv")}
                data = {"chat_id": chat_id, "caption": f"📁 <b>CSV Export</b>\n{title}", "parse_mode": "HTML"}
                await client.post(url, data=data, files=files)
        except Exception as e:
            await cls.send_message(chat_id, f"❌ Error: <code>{str(e)}</code>")

    @classmethod
    async def send_loans_report(cls, chat_id: int):
        try:
            loans = DBService.get_user_loans(chat_id)
            if not loans:
                await cls.send_message(chat_id, "🏦 <b>Loan Manager</b>\n\nNo loans logged.\n<i>Add with: /addloan Name | bank/family | high/low | Principal | Interest% | TenureMonths</i>")
                return
            
            lines = ["🏦 <b>Active Loans & Liabilities</b>\n━━━━━━━━━━━━━━━━━━━"]
            for l in loans:
                paid_pct = ((float(l["principal"]) - float(l["remaining_amount"])) / float(l["principal"])) * 100
                lines.append(
                    f"📌 <b>{l['name']}</b> (ID: {l['id']})\n"
                    f"  • Type: {l['lender_type'].upper()} | Priority: <b>{l['priority'].upper()}</b>\n"
                    f"  • Remaining: ₹{float(l['remaining_amount']):,.2f} / ₹{float(l['principal']):,.2f} ({paid_pct:.1f}% paid)\n"
                    f"  • Monthly EMI: ₹{float(l['emi_amount']):,.2f}\n"
                    f"  • Status: <i>{l['status'].capitalize()}</i>\n"
                )
            lines.append("<i>Pay EMI: /payemi [loan_id] [YYYY-MM] (e.g. /payemi 1 2026-07)</i>")
            await cls.send_message(chat_id, "\n".join(lines))
        except Exception as e:
            await cls.send_message(chat_id, f"❌ Error: <code>{str(e)}</code>")

    @classmethod
    async def send_budget_guardrail_report(cls, chat_id: int, year_month: str = None):
        try:
            target_month = year_month or datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m")
            b = DBService.get_monthly_budget_guardrail(chat_id, target_month)
            
            status_emoji = {"safe": "🟢", "warning": "🟡", "critical": "🟠", "breached": "🔴"}.get(b["warning_status"], "🟢")
            
            report = (
                f"🛡️ <b>House Budget Guardrail ({target_month})</b>\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"💵 Base Salary: ₹{b['base_salary']:,.2f}\n"
                f"➕ Extra Incomes: ₹{b['extra_income']:,.2f}\n"
                f"📥 Total Monthly Inflow: ₹{b['total_inflow']:,.2f}\n"
                f"📤 Mandatory EMIs: ₹{b['total_emis']:,.2f}\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"🏠 <b>Safe House Budget:</b> ₹{b['safe_house_budget']:,.2f}\n"
                f"💸 <b>Actual House Spent:</b> ₹{b['actual_house_spent']:,.2f}\n"
                f"📊 <b>Budget Utilized:</b> {b['percentage_used']}% {status_emoji}\n"
            )
            await cls.send_message(chat_id, report)
        except Exception as e:
            await cls.send_message(chat_id, f"❌ Error: <code>{str(e)}</code>")

    @classmethod
    async def process_natural_language(cls, chat_id: int, text_input: str = None, audio_bytes: bytes = None):
        msg_id = await cls.send_message(chat_id, "🔄 Analyzing transaction & checking guardrails...")
        try:
            parsed_data = AIService.parse_transaction(text_input=text_input, audio_bytes=audio_bytes)
            saved_records = DBService.save_transactions(chat_id, parsed_data)

            current_month = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m")
            budget_info = DBService.get_monthly_budget_guardrail(chat_id, current_month)
            warning_suffix = ""
            if budget_info["warning_status"] in ["warning", "critical", "breached"]:
                warning_suffix = f"\n\n⚠️ <b>BUDGET ALERT:</b> You have utilized <b>{budget_info['percentage_used']}%</b> of your safe house budget!"

            if isinstance(parsed_data, list):
                if not saved_records:
                    await cls.edit_message(chat_id, msg_id, "🤖 No valid transactions found.")
                    return
                list_str = "\n".join([f"• <b>{r.get('description')}</b>: ₹{r.get('amount'):,.2f}" for r in saved_records])
                await cls.edit_message(chat_id, msg_id, f"✨ <b>Bulk Transactions Logged ({len(saved_records)})</b>\n\n{list_str}{warning_suffix}")
                return

            if isinstance(parsed_data, dict):
                if not parsed_data.get("is_transaction", True) or not saved_records:
                    await cls.edit_message(chat_id, msg_id, "🤖 Send me expenses or commands to manage your finance.")
                    return
                record = saved_records[0]
                await cls.edit_message(chat_id, msg_id, f"✨ <b>Transaction Logged!</b>\n\n🔹 {record.get('description')}: ₹{record.get('amount'):,.2f} ({record.get('category')}){warning_suffix}")
        except Exception as e:
            if msg_id:
                await cls.edit_message(chat_id, msg_id, f"❌ Error: <code>{str(e)}</code>")

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
                await cls.answer_callback_query(query_id, "")
                return
            if data.startswith("del_t:"):
                parts = data.split(":", 3)
                await cls.answer_callback_query(query_id, "")
                if message_id:
                    await cls.update_delete_menu(chat_id, message_id, query_arg=parts[3], page=int(parts[2]), toggle_tx_id=int(parts[1]))
                return
            if data.startswith("del_pg:"):
                parts = data.split(":", 2)
                await cls.answer_callback_query(query_id, "")
                if message_id:
                    await cls.update_delete_menu(chat_id, message_id, query_arg=parts[2], page=int(parts[1]), toggle_tx_id=None)
                return
            if data == "del_confirm":
                cnt = DBService.confirm_and_delete(chat_id)
                await cls.answer_callback_query(query_id, f"Deleted {cnt} entries")
                if message_id:
                    await cls.edit_message(chat_id, message_id, f"🗑️ Successfully deleted {cnt} entries.")
                return
            if data == "del_cancel":
                DBService.clear_user_selections(chat_id)
                await cls.answer_callback_query(query_id, "Cancelled")
                if message_id:
                    await cls.edit_message(chat_id, message_id, "❌ Deletion cancelled.")
                return
            return

        message = update.get("message") or update.get("edited_message")
        if not message:
            return

        chat_id = message["chat"]["id"]
        text = message.get("text", "").strip()
        text_lower = text.lower()

        if text_lower.startswith("/delete") or text_lower.startswith("/remove"):
            parts = text.split(maxsplit=1)
            await cls.send_delete_menu(chat_id, query_arg=parts[1] if len(parts) > 1 else "", page=0)
            return

        if text_lower.startswith("/summary") or text_lower.startswith("/report"):
            parts = text.split(maxsplit=1)
            await cls.send_summary_report(chat_id, query_arg=parts[1] if len(parts) > 1 else "")
            return

        if text_lower.startswith("/chart") or text_lower.startswith("/graph"):
            parts = text.split(maxsplit=1)
            await cls.send_chart_report(chat_id, query_arg=parts[1] if len(parts) > 1 else "")
            return

        if text_lower.startswith("/export") or text_lower.startswith("/csv"):
            parts = text.split(maxsplit=1)
            await cls.send_csv_export(chat_id, query_arg=parts[1] if len(parts) > 1 else "")
            return

        if text_lower.startswith("/loans") or text_lower.startswith("/loan"):
            await cls.send_loans_report(chat_id)
            return

        if text_lower.startswith("/setsalary"):
            try:
                salary = float(text.split()[1])
                DBService.set_user_salary(chat_id, salary)
                await cls.send_message(chat_id, f"✅ Base salary configured to ₹{salary:,.2f}")
            except Exception:
                await cls.send_message(chat_id, "⚠️ Usage: <code>/setsalary [amount]</code>")
            return

        if text_lower.startswith("/addincome"):
            try:
                parts = text.split(maxsplit=1)[1].split("|")
                amount = float(parts[0].strip())
                source = parts[1].strip() if len(parts) > 1 else "Extra Income"
                supabase = DBService.get_client()
                today_str = datetime.now(timezone(timedelta(hours=5, minutes=30))).date().isoformat()
                supabase.table("incomes").insert({
                    "chat_id": chat_id,
                    "source_name": source,
                    "amount": amount,
                    "category": "Extra Income",
                    "date": today_str
                }).execute()
                supabase.table("transactions").insert({
                    "chat_id": chat_id,
                    "description": source,
                    "amount": amount,
                    "type": "income",
                    "category": "Extra Income",
                    "date": today_str
                }).execute()
                await cls.send_message(chat_id, f"✅ <b>Extra Income Logged!</b>\n\n💰 Source: {source}\n📥 Amount: ₹{amount:,.2f}")
            except Exception as e:
                await cls.send_message(chat_id, f"⚠️ Usage: <code>/addincome [Amount] | [Source Name]</code>\nError: {str(e)}")
            return

        if text_lower.startswith("/budget"):
            parts = text.split(maxsplit=1)
            await cls.send_budget_guardrail_report(chat_id, year_month=parts[1].strip() if len(parts) > 1 else None)
            return

        if text_lower.startswith("/addloan"):
            try:
                parts = text.split(maxsplit=1)[1].split("|")
                name = parts[0].strip()
                l_type = parts[1].strip().lower()
                priority = parts[2].strip().lower()
                principal = float(parts[3].strip())
                rate = float(parts[4].strip())
                tenure = int(parts[5].strip())
                
                loan = DBService.add_loan_with_schedule(chat_id, name, l_type, priority, principal, rate, tenure)
                await cls.send_message(chat_id, f"✅ <b>Loan Added Successfully!</b>\n\n📌 {loan['name']}\n💳 EMI: ₹{loan['emi_amount']:,.2f}/month")
            except Exception as e:
                await cls.send_message(chat_id, f"⚠️ Format error: <code>{str(e)}</code>\nUse: <code>/addloan Name | bank/family | high/low | Principal | Interest% | Months</code>")
            return

        if text_lower.startswith("/payemi"):
            try:
                parts = text.split()
                loan_id = int(parts[1])
                inst_month = parts[2]
                res = DBService.pay_loan_installment_by_month(chat_id, loan_id, inst_month)
                await cls.send_message(chat_id, f"💸 <b>EMI Paid & Logged!</b>\n\n📌 {res['loan_name']} ({res['installment_month']})\n💳 Paid: ₹{res['emi_paid']:,.2f}\n📉 Remaining: ₹{res['remaining_principal']:,.2f}")
            except Exception as e:
                await cls.send_message(chat_id, f"⚠️ Usage: <code>/payemi [loan_id] [YYYY-MM]</code>\nError: {str(e)}")
            return

        if text:
            await cls.process_natural_language(chat_id, text_input=text)