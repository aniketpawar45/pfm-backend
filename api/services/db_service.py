import os
import re
import csv
import io
import math
import calendar
from datetime import datetime, timezone, timedelta
from supabase import create_client
from api.core.config import settings

class DBService:
    _delete_sessions = {}  # chat_id -> {"records": [...], "title": str, "query_arg": str}
    _selections_cache = {} # chat_id -> set of selected transaction IDs

    @classmethod
    def get_client(cls):
        url = getattr(settings, "SUPABASE_URL", None) or os.getenv("SUPABASE_URL", "")
        key = getattr(settings, "SUPABASE_KEY", None) or os.getenv("SUPABASE_KEY", "") or os.getenv("SUPABASE_ANON_KEY", "")
        url = str(url).strip("'\" ")
        key = str(key).strip("'\" ")
        if not url or not key:
            raise ValueError("SUPABASE_URL or SUPABASE_KEY is missing from environment variables.")
        return create_client(url, key)

    @classmethod
    def save_transactions(cls, chat_id: int, parsed_data: dict | list) -> list:
        supabase = cls.get_client()
        items = parsed_data if isinstance(parsed_data, list) else [parsed_data]
        valid_records = []
        income_records = []
        processed_results = []

        IST = timezone(timedelta(hours=5, minutes=30))
        current_month_str = datetime.now(IST).strftime("%Y-%m")

        for item in items:
            if not item.get("is_transaction", True) or item.get("amount") is None:
                continue
            
            tx_type = item.get("type", "expense")
            desc = item.get("description") or "Miscellaneous"
            amt = float(item.get("amount"))
            cat = item.get("category") or "Miscellaneous"
            t_date = item.get("date") or datetime.now(IST).date().isoformat()
            is_emi = item.get("is_emi_payment", False)
            lender_name = (item.get("lender_name") or "").strip().lower()

            matched_loan = None
            if is_emi or lender_name or "emi" in desc.lower():
                loans_res = supabase.table("loans").select("*").eq("chat_id", chat_id).eq("status", "active").execute()
                active_loans = loans_res.data or []
                
                for loan in active_loans:
                    loan_name_lower = loan["name"].lower()
                    if lender_name and lender_name in loan_name_lower:
                        matched_loan = loan
                        break
                    if not matched_loan and (loan_name_lower in desc.lower() or desc.lower() in loan_name_lower):
                        matched_loan = loan
                        break

            if matched_loan:
                inst_res = supabase.table("loan_installments").select("*").eq("loan_id", matched_loan["id"]).eq("status", "pending").order("installment_month").execute()
                installments = inst_res.data or []
                
                target_inst = None
                for inst in installments:
                    if inst["installment_month"] == current_month_str:
                        target_inst = inst
                        break
                if not target_inst and installments:
                    target_inst = installments[0]

                if target_inst:
                    inst_month = target_inst["installment_month"]
                    new_remaining = max(0.0, float(matched_loan["remaining_amount"]) - amt)
                    new_status = "closed" if new_remaining == 0 else "active"

                    supabase.table("loan_installments").update({
                        "status": "paid",
                        "paid_date": t_date
                    }).eq("id", target_inst["id"]).execute()

                    supabase.table("loans").update({
                        "remaining_amount": new_remaining,
                        "status": new_status
                    }).eq("id", matched_loan["id"]).execute()

                    tx_record = {
                        "chat_id": chat_id,
                        "description": f"EMI: {matched_loan['name']} ({inst_month})",
                        "amount": amt,
                        "type": "expense",
                        "category": "Loans & EMIs",
                        "date": t_date
                    }
                    tx_resp = supabase.table("transactions").insert(tx_record).execute()
                    
                    if tx_resp.data:
                        processed_results.append({
                            **tx_resp.data[0],
                            "is_auto_emi": True,
                            "loan_name": matched_loan["name"],
                            "installment_month": inst_month,
                            "remaining_principal": new_remaining,
                            "loan_status": new_status
                        })
                    continue

            valid_records.append({
                "chat_id": chat_id,
                "description": desc,
                "amount": amt,
                "type": tx_type,
                "category": cat,
                "date": t_date
            })

            if tx_type == "income":
                income_records.append({
                    "chat_id": chat_id,
                    "source_name": desc,
                    "amount": amt,
                    "category": cat,
                    "date": t_date
                })

        if valid_records:
            response = supabase.table("transactions").insert(valid_records).execute()
            for r in (response.data or []):
                processed_results.append({**r, "is_auto_emi": False})

        if income_records:
            try:
                supabase.table("incomes").insert(income_records).execute()
            except Exception as e:
                print(f"Failed to sync income record to incomes table: {str(e)}")

        return processed_results

    @classmethod
    def parse_delete_query(cls, query_arg: str) -> tuple[str, str | None, str | None, str]:
        IST = timezone(timedelta(hours=5, minutes=30))
        now_ist = datetime.now(IST)
        query_arg = query_arg.strip().lower()
        months = {
            'jan': 1, 'january': 1, 'feb': 2, 'february': 2, 'mar': 3, 'march': 3,
            'apr': 4, 'april': 4, 'may': 5, 'jun': 6, 'june': 6, 'jul': 7, 'july': 7,
            'aug': 8, 'august': 8, 'sep': 9, 'september': 9, 'oct': 10, 'october': 10,
            'nov': 11, 'november': 11, 'dec': 12, 'december': 12
        }
        if not query_arg:
            return "all", None, None, "Recent Transactions"
        parts = query_arg.split()
        if re.match(r'^\d{4}$', query_arg):
            year = int(query_arg)
            return "range", f"{year}-01-01", f"{year}-12-31", f"Transactions in {year}"
        if len(parts) == 1 and query_arg in months:
            month_num = months[query_arg]
            year = now_ist.year
            last_day = calendar.monthrange(year, month_num)[1]
            return "range", f"{year}-{month_num:02d}-01", f"{year}-{month_num:02d}-{last_day:02d}", f"Transactions in {calendar.month_name[month_num]} {year}"
        return "all", None, None, "Recent Transactions"

    @classmethod
    def load_delete_session(cls, chat_id: int, query_arg: str = ""):
        supabase = cls.get_client()
        mode, start_date, end_date, title = cls.parse_delete_query(query_arg)
        query = supabase.table("transactions").select("*").eq("chat_id", chat_id)
        if mode == "range":
            query = query.gte("date", start_date).lte("date", end_date)
        response = query.order("date", desc=True).order("id", desc=True).execute()
        records = response.data or []
        cls._delete_sessions[chat_id] = {"records": records, "title": title, "query_arg": query_arg}
        cls._selections_cache[chat_id] = set()
        return records, title

    @classmethod
    def get_cached_delete_view(cls, chat_id: int, query_arg: str = "", page: int = 0, page_size: int = 5, toggle_tx_id: int | None = None):
        session = cls._delete_sessions.get(chat_id)
        if not session or session.get("query_arg") != query_arg:
            records, title = cls.load_delete_session(chat_id, query_arg)
        else:
            records = session["records"]
            title = session["title"]
        if toggle_tx_id is not None:
            if chat_id not in cls._selections_cache:
                cls._selections_cache[chat_id] = set()
            if toggle_tx_id in cls._selections_cache[chat_id]:
                cls._selections_cache[chat_id].remove(toggle_tx_id)
            else:
                cls._selections_cache[chat_id].add(toggle_tx_id)
        total_records = len(records)
        total_pages = math.ceil(total_records / page_size) if total_records > 0 else 1
        if page >= total_pages and total_pages > 0:
            page = max(0, total_pages - 1)
        start_idx = page * page_size
        paginated_records = records[start_idx:start_idx + page_size]
        selected_ids = cls._selections_cache.get(chat_id, set())
        return title, paginated_records, total_records, total_pages, selected_ids

    @classmethod
    def clear_user_selections(cls, chat_id: int):
        if chat_id in cls._selections_cache:
            cls._selections_cache[chat_id].clear()
        if chat_id in cls._delete_sessions:
            cls._delete_sessions.pop(chat_id, None)

    @classmethod
    def confirm_and_delete(cls, chat_id: int) -> int:
        selected_ids = list(cls._selections_cache.get(chat_id, set()))
        if not selected_ids:
            return 0
        supabase = cls.get_client()
        del_resp = supabase.table("transactions").delete().in_("id", selected_ids).eq("chat_id", chat_id).execute()
        cls.clear_user_selections(chat_id)
        return len(del_resp.data or [])

    @classmethod
    def parse_date_range(cls, query_arg: str) -> tuple[str, str, str]:
        IST = timezone(timedelta(hours=5, minutes=30))
        now_ist = datetime.now(IST)
        today = now_ist.date()
        query_arg = query_arg.strip().lower()
        if not query_arg:
            start = now_ist.replace(day=1).date().isoformat()
            end = today.isoformat()
            return start, end, f"Monthly Summary ({now_ist.strftime('%B %Y')})"
        return start, end, "Summary"

    @classmethod
    def get_summary(cls, chat_id: int, query_arg: str = "") -> dict:
        supabase = cls.get_client()
        start_date, end_date, title = cls.parse_date_range(query_arg)
        response = supabase.table("transactions").select("*").eq("chat_id", chat_id).gte("date", start_date).lte("date", end_date).execute()
        records = response.data or []
        total_expense = sum(float(r["amount"]) for r in records if r["type"] == "expense")
        total_income = sum(float(r["amount"]) for r in records if r["type"] == "income")
        total_transfer = sum(float(r["amount"]) for r in records if r["type"] == "transfer")
        categories = {}
        for r in records:
            if r["type"] == "expense":
                cat = r["category"] or "Miscellaneous"
                categories[cat] = categories.get(cat, 0.0) + float(r["amount"])
        return {
            "title": title, "total_expense": total_expense, "total_income": total_income,
            "total_transfer": total_transfer, "net_balance": total_income - total_expense,
            "categories": dict(sorted(categories.items(), key=lambda item: item[1], reverse=True)), "count": len(records)
        }

    @classmethod
    def get_category_data_for_chart(cls, chat_id: int, query_arg: str = "") -> tuple[str, dict]:
        supabase = cls.get_client()
        start_date, end_date, title = cls.parse_date_range(query_arg)
        response = supabase.table("transactions").select("*").eq("chat_id", chat_id).eq("type", "expense").gte("date", start_date).lte("date", end_date).execute()
        records = response.data or []
        categories = {}
        for r in records:
            cat = r["category"] or "Miscellaneous"
            categories[cat] = categories.get(cat, 0.0) + float(r["amount"])
        return title, dict(sorted(categories.items(), key=lambda item: item[1], reverse=True))

    @classmethod
    def get_transactions_for_export(cls, chat_id: int, query_arg: str = "") -> tuple[str, str, list]:
        supabase = cls.get_client()
        start_date, end_date, title = cls.parse_date_range(query_arg)
        response = supabase.table("transactions").select("*").eq("chat_id", chat_id).gte("date", start_date).lte("date", end_date).order("date", desc=True).execute()
        return f"PFM_Export_{start_date}_to_{end_date}.csv", title, (response.data or [])

    @classmethod
    def set_user_salary(cls, chat_id: int, base_salary: float) -> dict:
        supabase = cls.get_client()
        data = {
            "chat_id": chat_id,
            "base_salary": base_salary,
            "updated_at": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()
        }
        res = supabase.table("user_profiles").upsert(data, on_conflict="chat_id").execute()
        return res.data[0] if res.data else {}

    @classmethod
    def get_user_salary(cls, chat_id: int) -> float:
        supabase = cls.get_client()
        res = supabase.table("user_profiles").select("base_salary").eq("chat_id", chat_id).execute()
        if res.data:
            return float(res.data[0].get("base_salary", 0.0))
        return 0.0

    @classmethod
    def add_loan_with_schedule(
        cls, 
        chat_id: int, 
        name: str, 
        lender_type: str, 
        priority: str, 
        principal: float, 
        interest_rate: float, 
        tenure_months: int, 
        start_date_str: str = None
    ) -> dict:
        supabase = cls.get_client()
        s_date = datetime.strptime(start_date_str, "%Y-%m-%d").date() if start_date_str else datetime.now().date()
        
        if interest_rate == 0:
            emi_amt = principal / tenure_months
        else:
            monthly_rate = (interest_rate / 100.0) / 12.0
            emi_amt = principal * monthly_rate * ((1 + monthly_rate) ** tenure_months) / (((1 + monthly_rate) ** tenure_months) - 1)
        emi_amt = round(emi_amt, 2)

        loan_record = {
            "chat_id": chat_id,
            "name": name,
            "lender_type": lender_type,
            "priority": priority,
            "principal": principal,
            "interest_rate": interest_rate,
            "tenure_months": tenure_months,
            "emi_amount": emi_amt,
            "remaining_amount": principal,
            "start_date": s_date.isoformat(),
            "status": "active"
        }
        loan_res = supabase.table("loans").insert(loan_record).execute()
        if not loan_res.data:
            raise ValueError("Failed to create loan record.")
        
        created_loan = loan_res.data[0]
        loan_id = created_loan["id"]

        installments = []
        curr_date = s_date
        for i in range(tenure_months):
            month_str = curr_date.strftime("%Y-%m")
            installments.append({
                "loan_id": loan_id,
                "chat_id": chat_id,
                "installment_month": month_str,
                "emi_amount": emi_amt,
                "status": "pending"
            })
            if curr_date.month == 12:
                curr_date = curr_date.replace(year=curr_date.year + 1, month=1)
            else:
                curr_date = curr_date.replace(month=curr_date.month + 1)

        supabase.table("loan_installments").insert(installments).execute()
        return created_loan

    @classmethod
    def get_user_loans(cls, chat_id: int) -> list:
        supabase = cls.get_client()
        res = supabase.table("loans").select("*").eq("chat_id", chat_id).execute()
        return res.data or []

    @classmethod
    def get_monthly_budget_guardrail(cls, chat_id: int, year_month: str) -> dict:
        supabase = cls.get_client()
        base_salary = cls.get_user_salary(chat_id)

        # Fetch incomes for this month, but exclude any records categorized as 'Salary' to prevent double counting
        incomes_res = supabase.table("incomes").select("amount, category, source_name").eq("chat_id", chat_id).gte("date", f"{year_month}-01").lte("date", f"{year_month}-31").execute()
        
        extra_income = 0.0
        for inc in (incomes_res.data or []):
            cat = (inc.get("category") or "").lower()
            src = (inc.get("source_name") or "").lower()
            if "salary" not in cat and "salary" not in src:
                extra_income += float(inc["amount"])

        total_inflow = base_salary + extra_income

        inst_res = supabase.table("loan_installments").select("emi_amount, status").eq("chat_id", chat_id).eq("installment_month", year_month).execute()
        installments = inst_res.data or []
        total_emis = sum(float(inst["emi_amount"]) for inst in installments)
        paid_emis = sum(float(inst["emi_amount"]) for inst in installments if inst["status"] == "paid")

        safe_house_budget = total_inflow - total_emis

        tx_res = supabase.table("transactions").select("amount, category").eq("chat_id", chat_id).eq("type", "expense").neq("category", "Loans & EMIs").gte("date", f"{year_month}-01").lte("date", f"{year_month}-31").execute()
        actual_house_spent = sum(float(tx["amount"]) for tx in (tx_res.data or []))

        percentage_used = (actual_house_spent / safe_house_budget * 100) if safe_house_budget > 0 else 100.0

        warning_status = "safe"
        if percentage_used >= 100:
            warning_status = "breached"
        elif percentage_used >= 90:
            warning_status = "critical"
        elif percentage_used >= 75:
            warning_status = "warning"

        return {
            "year_month": year_month,
            "base_salary": base_salary,
            "extra_income": extra_income,
            "total_inflow": total_inflow,
            "total_emis": total_emis,
            "paid_emis": paid_emis,
            "safe_house_budget": safe_house_budget,
            "actual_house_spent": actual_house_spent,
            "percentage_used": round(percentage_used, 1),
            "warning_status": warning_status
        }
