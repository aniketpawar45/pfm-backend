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
        for item in items:
            if not item.get("is_transaction", True) or item.get("amount") is None:
                continue
                
            valid_records.append({
                "chat_id": chat_id,
                "description": item.get("description") or "Miscellaneous",
                "amount": float(item.get("amount")),
                "type": item.get("type", "expense"),
                "category": item.get("category") or "Miscellaneous",
                "date": item.get("date") or datetime.now().date().isoformat()
            })
            
        if not valid_records:
            return []

        response = supabase.table("transactions").insert(valid_records).execute()
        return response.data or []

    @classmethod
    def parse_delete_query(cls, query_arg: str) -> tuple[str, str | None, str | None, str]:
        IST = timezone(timedelta(hours=5, minutes=30))
        now_ist = datetime.now(IST)
        today = now_ist.date()
        
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

        if len(parts) == 1 and query_arg.isdigit():
            day = int(query_arg)
            year = now_ist.year
            month = now_ist.month
            try:
                target_date = datetime(year, month, day).date().isoformat()
                return "range", target_date, target_date, f"Transactions on {datetime(year, month, day).strftime('%d %B %Y')}"
            except ValueError:
                pass

        if len(parts) >= 2 and parts[0].isdigit():
            day = int(parts[0])
            m_token = parts[1]
            m_num = months.get(m_token, None)
            if not m_num and m_token.isdigit():
                m_num = int(m_token)
            
            if m_num and 1 <= m_num <= 12:
                year = now_ist.year
                if len(parts) >= 3 and parts[2].isdigit() and len(parts[2]) == 4:
                    year = int(parts[2])
                try:
                    target_date = datetime(year, m_num, day).date().isoformat()
                    date_obj = datetime(year, m_num, day)
                    return "range", target_date, target_date, f"Transactions on {date_obj.strftime('%d %B %Y')}"
                except ValueError:
                    pass

        return "all", None, None, "Recent Transactions"

    @classmethod
    def get_delete_page_data(cls, chat_id: int, query_arg: str = "", page: int = 0, page_size: int = 5) -> tuple[str, list, int, int, list]:
        supabase = cls.get_client()
        mode, start_date, end_date, title = cls.parse_delete_query(query_arg)
        
        query = supabase.table("transactions").select("*", count="exact").eq("chat_id", chat_id)
        if mode == "range":
            query = query.gte("date", start_date).lte("date", end_date)
            
        response = query.order("date", desc=True).order("id", desc=True).execute()
        all_records = response.data or []
        
        total_records = len(all_records)
        total_pages = math.ceil(total_records / page_size) if total_records > 0 else 1
        if page >= total_pages and total_pages > 0:
            page = max(0, total_pages - 1)
            
        start_idx = page * page_size
        paginated_records = all_records[start_idx:start_idx + page_size]
        
        # Get active selections quickly
        sel_resp = supabase.table("user_selections").select("transaction_id").eq("chat_id", chat_id).execute()
        selected_ids = [row["transaction_id"] for row in (sel_resp.data or [])]
        
        return title, paginated_records, total_records, total_pages, selected_ids

    @classmethod
    def toggle_selection(cls, chat_id: int, tx_id: int) -> list:
        supabase = cls.get_client()
        existing = supabase.table("user_selections").select("transaction_id").eq("chat_id", chat_id).eq("transaction_id", tx_id).execute()
        if existing.data:
            supabase.table("user_selections").delete().eq("chat_id", chat_id).eq("transaction_id", tx_id).execute()
        else:
            supabase.table("user_selections").insert({"chat_id": chat_id, "transaction_id": tx_id}).execute()
            
        sel_resp = supabase.table("user_selections").select("transaction_id").eq("chat_id", chat_id).execute()
        return [row["transaction_id"] for row in (sel_resp.data or [])]

    @classmethod
    def clear_user_selections(cls, chat_id: int):
        supabase = cls.get_client()
        supabase.table("user_selections").delete().eq("chat_id", chat_id).execute()

    @classmethod
    def confirm_and_delete(cls, chat_id: int) -> int:
        supabase = cls.get_client()
        sel_resp = supabase.table("user_selections").select("transaction_id").eq("chat_id", chat_id).execute()
        selected_ids = [row["transaction_id"] for row in (sel_resp.data or [])]
        if not selected_ids:
            return 0
            
        del_resp = supabase.table("transactions")\
            .delete()\
            .in_("id", selected_ids)\
            .eq("chat_id", chat_id)\
            .execute()
            
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
    def get_category_drilldown_data(cls, chat_id: int, category_query: str) -> tuple[str, list]:
        supabase = cls.get_client()
        category_query = category_query.strip().lower()
        IST = timezone(timedelta(hours=5, minutes=30))
        now_ist = datetime.now(IST)
        start_of_month = now_ist.replace(day=1).date().isoformat()
        response = supabase.table("transactions").select("*").eq("chat_id", chat_id).gte("date", start_of_month).order("date", desc=True).execute()
        records = response.data or []
        filtered = [r for r in records if category_query in (r.get("category") or "").lower()]
        return category_query.capitalize(), filtered
