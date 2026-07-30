import os
import tempfile
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from fastapi import APIRouter, Request, HTTPException
from api.services.telegram_service import TelegramService
from api.services.db_service import DBService
from api.services.ai_service import AIService

router = APIRouter()

@router.get("/setup-menu")
async def setup_menu():
    success = TelegramService.set_bot_commands()
    if success:
        return {"status": "success", "message": "Telegram command menu successfully registered!"}
    raise HTTPException(status_code=500, detail="Failed to register bot commands. Check your TELEGRAM_BOT_TOKEN.")

@router.post("/webhook")
async def telegram_webhook(request: Request):
    try:
        body = await request.json()
        
        # 1. EXTRACT CHAT ID EARLY FOR AUTHENTICATION
        chat_id = None
        if "callback_query" in body:
            chat_id = body["callback_query"]["message"]["chat"]["id"]
        elif "message" in body:
            chat_id = body["message"]["chat"]["id"]

        if not chat_id:
            return {"ok": True}

        # 2. STRICT AUTHENTICATION GATEKEEPER
        allowed_ids_env = os.getenv("ALLOWED_TELEGRAM_IDS", "")
        
        # If the env var is missing entirely, lock everyone out for safety
        if not allowed_ids_env:
            TelegramService.send_message(
                chat_id, 
                f"⚠️ **System Locked**\n\nAuthentication is not configured in Vercel. \n"
                f"Please add your Telegram ID (`{chat_id}`) to the ALLOWED_TELEGRAM_IDS environment variable and redeploy."
            )
            return {"ok": True}

        # Parse the allowed IDs
        allowed_ids = []
        for id_str in allowed_ids_env.split(","):
            try:
                allowed_ids.append(int(id_str.strip()))
            except ValueError:
                pass
        
        # If the user's ID is not in the list, block them immediately
        if chat_id not in allowed_ids:
            TelegramService.send_message(
                chat_id, 
                f"⛔️ **Unauthorized Access**\n\nYour Telegram ID is `{chat_id}`.\n"
                "You do not have permission to interact with this Personal Finance Manager."
            )
            return {"ok": True}
        
        # --- PROCEED WITH NORMAL BOT LOGIC ---

        # Handle Callback Queries (Inline Keyboards for Delete / Pagination)
        if "callback_query" in body:
            callback = body["callback_query"]
            message_id = callback["message"]["message_id"]
            data = callback.get("data", "")
            
            if data.startswith("del_page_"):
                # Example data: del_page_None_1 -> parts = ['del', 'page', 'None', '1']
                parts = data.split("_")
                query_arg = parts[2] if len(parts) > 2 and parts[2] != "None" else ""
                page = int(parts[-1])
                
                title, records, total_records, total_pages, selected_ids = DBService.get_cached_delete_view(chat_id, query_arg, page=page)
                keyboard = TelegramService.build_delete_keyboard(records, total_pages, page, query_arg, selected_ids)
                TelegramService.edit_message(chat_id, message_id, f"🗑️ **{title}**\nSelect transactions to delete:", keyboard)
                
            elif data.startswith("del_toggle_"):
                # Example data: del_toggle_123_None_0 -> parts = ['del', 'toggle', '123', 'None', '0']
                parts = data.split("_")
                tx_id = int(parts[2])
                query_arg = parts[3] if len(parts) > 3 and parts[3] != "None" else ""
                page = int(parts[-1])
                
                title, records, total_records, total_pages, selected_ids = DBService.get_cached_delete_view(chat_id, query_arg, page=page, toggle_tx_id=tx_id)
                keyboard = TelegramService.build_delete_keyboard(records, total_pages, page, query_arg, selected_ids)
                TelegramService.edit_message(chat_id, message_id, f"🗑️ **{title}**\nSelect transactions to delete:", keyboard)
                
            elif data.startswith("del_confirm_"):
                query_arg = data.split("_")[-1]
                if query_arg == "None":
                    query_arg = ""
                deleted_count = DBService.confirm_and_delete(chat_id)
                TelegramService.edit_message(chat_id, message_id, f"✅ Successfully deleted {deleted_count} transaction(s).")
                
            elif data == "del_cancel":
                DBService.clear_user_selections(chat_id)
                TelegramService.edit_message(chat_id, message_id, "❌ Deletion cancelled.")
                
            return {"ok": True}

        if "message" not in body:
            return {"ok": True}

        message = body["message"]
        text = message.get("text")

        if not text:
            return {"ok": True}

        text_stripped = text.strip()

        # Handle Commands
        if text_stripped.startswith("/start"):
            TelegramService.set_bot_commands()

            welcome_msg = (
                "🤖 **Welcome to your Salary-Anchored PFM Bot!**\n\n"
                "Your intelligent financial co-pilot for automated budgeting, debt tracking, and expense logging.\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "⚙️ **SETUP & BUDGETING**\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "• `/setsalary [amount]` — Set monthly base salary\n"
                "• `/budget` — Check Safe House Budget & guardrails\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "💳 **DEBT & LOAN MANAGEMENT**\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "• `/addloan` — Add new loan & payment schedule\n"
                "• `/loans` — View active liabilities & amortization\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "📊 **REPORTS & ANALYTICS**\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "• `/summary` or `/report` — Monthly financial breakdown\n"
                "• `/statistics` — Deep analytics & spending metrics\n"
                "• `/chart` — Visual expense category pie chart\n"
                "• `/export` — Download full CSV transaction report\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "🗑️ **TRANSACTION CONTROL**\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "• `/delete` — Interactive paginated transaction manager\n\n"
                "💡 **Pro Tip:** You can also type naturally! *(e.g., 'Paid ₹500 for lunch' or paste a grocery list).*'"
            )
            TelegramService.send_message(chat_id, welcome_msg)

        elif text_stripped.startswith("/setsalary"):
            parts = text_stripped.split()
            if len(parts) < 2:
                TelegramService.send_message(chat_id, "⚠️ Usage: `/setsalary [amount]` (e.g., `/setsalary 75000`)")
            else:
                try:
                    amount = float(parts[1])
                    DBService.set_user_salary(chat_id, amount)
                    TelegramService.send_message(chat_id, f"✅ Base monthly salary successfully updated to **{amount:,.2f}**.")
                except ValueError:
                    TelegramService.send_message(chat_id, "⚠️ Invalid amount format. Please provide a valid number.")

        elif text_stripped.startswith("/budget"):
            parts = text_stripped.split()
            year_month = parts[1] if len(parts) > 1 else None
            if not year_month:
                from datetime import datetime, timezone, timedelta
                IST = timezone(timedelta(hours=5, minutes=30))
                year_month = datetime.now(IST).strftime("%Y-%m")
            
            b_data = DBService.get_monthly_budget_guardrail(chat_id, year_month)
            status_emoji = {"safe": "🟢", "warning": "🟡", "critical": "🟠", "breached": "🔴"}.get(b_data["warning_status"], "🟢")
            
            msg = (
                f"📊 **Safe House Budget ({b_data['year_month']})**\n\n"
                f"• **Base Salary:** {b_data['base_salary']:,.2f}\n"
                f"• **Extra Income:** {b_data['extra_income']:,.2f}\n"
                f"• **Total Inflows:** {b_data['total_inflow']:,.2f}\n"
                f"• **Mandatory EMIs:** {b_data['total_emis']:,.2f}\n"
                f"-----------------------------------\n"
                f"• **Safe House Budget:** {b_data['safe_house_budget']:,.2f}\n"
                f"• **Actual Spent:** {b_data['actual_house_spent']:,.2f}\n"
                f"• **Utilization:** {b_data['percentage_used']}% {status_emoji}\n"
                f"• **Status:** {b_data['warning_status'].upper()}"
            )
            TelegramService.send_message(chat_id, msg)

        elif text_stripped.startswith("/addloan"):
            content = text_stripped.replace("/addloan", "").strip()
            parts = [p.strip() for p in content.split("|")]
            if len(parts) < 6:
                TelegramService.send_message(
                    chat_id,
                    "⚠️ **Format error:** Missing parameters.\n\n"
                    "Use: `/addloan Name | bank/family | high/low | Principal | Interest% | Months`\n"
                    "Example: `/addloan Sushma | family | high | 150000 | 0 | 6`"
                )
            else:
                try:
                    name = parts[0]
                    lender_type = parts[1].lower()
                    priority = parts[2].lower()
                    principal = float(parts[3])
                    interest_rate = float(parts[4])
                    tenure_months = int(parts[5])

                    loan = DBService.add_loan_with_schedule(
                        chat_id=chat_id,
                        name=name,
                        lender_type=lender_type,
                        priority=priority,
                        principal=principal,
                        interest_rate=interest_rate,
                        tenure_months=tenure_months
                    )
                    TelegramService.send_message(
                        chat_id,
                        f"✅ **Loan Added Successfully!**\n\n"
                        f"• **Name:** {loan['name']}\n"
                        f"• **Principal:** {loan['principal']:,.2f}\n"
                        f"• **Monthly EMI:** {loan['emi_amount']:,.2f}\n"
                        f"• **Tenure:** {loan['tenure_months']} months"
                    )
                except Exception as e:
                    TelegramService.send_message(chat_id, f"⚠️ Error adding loan: {str(e)}")

        elif text_stripped.startswith("/loans"):
            loans = DBService.get_user_loans(chat_id)
            if not loans:
                TelegramService.send_message(chat_id, "ℹ️ You have no active or recorded loans.")
            else:
                msg = "📋 **Your Loan Portfolio:**\n\n"
                for l in loans:
                    rem = float(l['remaining_amount'])
                    prin = float(l['principal'])
                    paid_pct = ((prin - rem) / prin * 100) if prin > 0 else 0
                    msg += (
                        f"• **{l['name']}** ({l['lender_type'].capitalize()})\n"
                        f"  Remaining: {rem:,.2f} / {prin:,.2f} ({paid_pct:.1f}% paid)\n"
                        f"  EMI: {float(l['emi_amount']):,.2f} | Priority: {l['priority'].upper()}\n\n"
                    )
                TelegramService.send_message(chat_id, msg)

        elif text_stripped.startswith("/summary") or text_stripped.startswith("/report"):
            parts = text_stripped.split(maxsplit=1)
            query_arg = parts[1] if len(parts) > 1 else ""
            summary = DBService.get_summary(chat_id, query_arg)
            
            msg = (
                f"📈 **{summary['title']}**\n\n"
                f"• **Total Income:** {summary['total_income']:,.2f}\n"
                f"• **Total Expenses:** {summary['total_expense']:,.2f}\n"
                f"• **Net Balance:** {summary['net_balance']:,.2f}\n"
                f"• **Transactions Logged:** {summary['count']}\n\n"
                f"🏷️ **Category Breakdown:**\n"
            )
            for cat, amt in summary["categories"].items():
                msg += f"• {cat}: {amt:,.2f}\n"
            TelegramService.send_message(chat_id, msg)

        elif text_stripped.startswith("/statistics"):
            parts = text_stripped.split(maxsplit=1)
            query_arg = parts[1] if len(parts) > 1 else ""
            stats = DBService.get_statistics(chat_id, query_arg)
            
            msg = (
                f"📊 **Financial Statistics & Analytics ({stats['title']})**\n\n"
                f"• **Total Inflows:** {stats['total_income']:,.2f}\n"
                f"• **Total Outflows:** {stats['total_expense']:,.2f}\n"
                f"• **Net Savings:** {stats['net_balance']:,.2f}\n"
                f"• **Savings Rate:** {stats['savings_rate']:.1f}%\n"
                f"• **Average Daily Spend:** {stats['avg_daily_spend']:,.2f}\n"
                f"• **Largest Single Expense:** {stats['max_expense']:,.2f}\n"
                f"• **Total Transactions Logged:** {stats['transaction_count']}"
            )
            TelegramService.send_message(chat_id, msg)

        elif text_stripped.startswith("/chart"):
            parts = text_stripped.split(maxsplit=1)
            query_arg = parts[1] if len(parts) > 1 else ""
            title, categories = DBService.get_category_data_for_chart(chat_id, query_arg)
            
            if not categories:
                TelegramService.send_message(chat_id, "ℹ️ No expense data available to generate chart for this period.")
            else:
                fig, ax = plt.subplots(figsize=(8, 6))
                fig.patch.set_facecolor('#1e1e1e')
                ax.set_facecolor('#1e1e1e')
                
                labels = list(categories.keys())
                sizes = list(categories.values())
                colors = ['#ff9999','#66b3ff','#99ff99','#ffcc99','#c2c2f0','#ffb3e6','#c4e1ff']
                
                wedges, texts, autotexts = ax.pie(
                    sizes, labels=labels, autopct='%1.1f%%', startangle=140,
                    colors=colors[:len(labels)], textprops=dict(color="white")
                )
                plt.setp(autotexts, size=9, weight="bold")
                plt.setp(texts, size=10)
                ax.set_title(f"Expense Distribution - {title}", color="white", fontsize=14, pad=20)
                
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                    plt.savefig(tmp.name, format='png', bbox_inches='tight', facecolor=fig.get_facecolor(), edgecolor='none')
                    tmp_path = tmp.name
                plt.close(fig)
                
                TelegramService.send_photo(chat_id, tmp_path, caption=f"📊 Expense Chart: {title}")
                try:
                    os.unlink(tmp_path)
                except:
                    pass

        elif text_stripped.startswith("/export"):
            parts = text_stripped.split(maxsplit=1)
            query_arg = parts[1] if len(parts) > 1 else ""
            filename, title, records = DBService.get_transactions_for_export(chat_id, query_arg)
            
            if not records:
                TelegramService.send_message(chat_id, "ℹ️ No transactions found to export.")
            else:
                import csv
                import io
                output = io.StringIO()
                writer = csv.writer(output)
                writer.writerow(["ID", "Date", "Type", "Category", "Description", "Amount"])
                for r in records:
                    writer.writerow([r.get("id"), r.get("date"), r.get("type"), r.get("category"), r.get("description"), r.get("amount")])
                
                csv_bytes = output.getvalue().encode('utf-8')
                TelegramService.send_document(chat_id, csv_bytes, filename, caption=f"📁 Transaction Statement: {title}")

        elif text_stripped.startswith("/delete"):
            parts = text_stripped.split(maxsplit=1)
            query_arg = parts[1] if len(parts) > 1 else ""
            title, records, total_records, total_pages, selected_ids = DBService.get_cached_delete_view(chat_id, query_arg, page=0)
            
            if not records:
                TelegramService.send_message(chat_id, f"ℹ️ No transactions found for '{title}'.")
            else:
                keyboard = TelegramService.build_delete_keyboard(records, total_pages, 0, query_arg, selected_ids)
                TelegramService.send_message(chat_id, f"🗑️ **{title}**\nSelect transactions to delete:", keyboard)

        else:
            parsed = AIService.parse_transaction(text_stripped)
            
            is_valid = False
            if isinstance(parsed, dict):
                is_valid = parsed.get("is_transaction", True)
            elif isinstance(parsed, list):
                is_valid = len(parsed) > 0 and all(isinstance(item, dict) and item.get("is_transaction", True) for item in parsed)

            if not parsed or not is_valid:
                TelegramService.send_message(chat_id, "🤖 I didn't quite catch that. You can log expenses, extra income, or pay EMIs naturally!")
            else:
                results = DBService.save_transactions(chat_id, parsed)
                for res in results:
                    if res.get("is_auto_emi"):
                        TelegramService.send_message(
                            chat_id,
                            f"✅ **EMI Auto-Matched & Paid!**\n\n"
                            f"• **Loan:** {res.get('loan_name')}\n"
                            f"• **Installment:** {res.get('installment_month')}\n"
                            f"• **Amount:** {float(res.get('amount', 0)):,.2f}\n"
                            f"• **Remaining Principal:** {float(res.get('remaining_principal', 0)):,.2f}\n"
                            f"• **Status:** {res.get('loan_status').upper()}"
                        )
                    else:
                        t_type = res.get("type", "expense").capitalize()
                        TelegramService.send_message(
                            chat_id,
                            f"✅ **{t_type} Logged Successfully!**\n\n"
                            f"• **Description:** {res.get('description')}\n"
                            f"• **Category:** {res.get('category')}\n"
                            f"• **Amount:** {float(res.get('amount', 0)):,.2f}\n"
                            f"• **Date:** {res.get('date')}"
                        )

        return {"ok": True}
    except Exception as e:
        print(f"Webhook Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
