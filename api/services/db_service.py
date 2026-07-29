import os
import re
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
    def save_transactions(cls, chat_id: int, parsed_data: dict | list) -> int:
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
            return 0

        supabase.table("transactions").insert(valid_records).execute()
        return len(valid_records)

    @classmethod
    def parse_date_range(cls, query_arg: str) -> tuple[str, str, str]:
        IST = timezone(timedelta(hours=5, minutes=30))
        now_ist = datetime.now(IST)
        today = now_ist.date()
        
        query_arg = query_arg.strip().lower()
        
        # 1. Default (Empty) -> Current Month
        if not query_arg:
            start = now_ist.replace(day=1).date().isoformat()
            end = today.isoformat()
            return start, end, f"Monthly Summary ({now_ist.strftime('%B %Y')})"

        parts = query_arg.split()
        
        # 2. Relative Keywords
        if query_arg in ["daily", "today", "day"]:
            d = today.isoformat()
            return d, d, f"Daily Summary ({now_ist.strftime('%d %b %Y')})"
        if query_arg in ["weekly", "week"]:
            start = (today - timedelta(days=today.weekday())).isoformat()
            end = today.isoformat()
            return start, end, f"Weekly Summary (Since {start})"
        if query_arg in ["yearly", "year"]:
            start = now_ist.replace(month=1, day=1).date().isoformat()
            end = today.isoformat()
            return start, end, f"Yearly Summary ({now_ist.strftime('%Y')})"
        if query_arg in ["monthly", "month"]:
            start = now_ist.replace(day=1).date().isoformat()
            end = today.isoformat()
            return start, end, f"Monthly Summary ({now_ist.strftime('%B %Y')})"

        months = {
            'jan': 1, 'january': 1, 'feb': 2, 'february': 2, 'mar': 3, 'march': 3,
            'apr': 4, 'april': 4, 'may': 5, 'jun': 6, 'june': 6, 'jul': 7, 'july': 7,
            'aug': 8, 'august': 8, 'sep': 9, 'september': 9, 'oct': 10, 'october': 10,
            'nov': 11, 'november': 11, 'dec': 12, 'december': 12
        }

        # 3. Year only e.g. "2025"
        if re.match(r'^\d{4}$', query_arg):
            year = int(query_arg)
            return f"{year}-01-01", f"{year}-12-31", f"Yearly Summary ({year})"

        # 4. Month name or month number only e.g. "july", "jun", or "6"
        month_num = None
        if query_arg in months:
            month_num = months[query_arg]
        elif query_arg.isdigit():
            val = int(query_arg)
            if 1 <= val <= 12:
                month_num = val

        if month_num and len(parts) == 1:
            year = now_ist.year
            last_day = calendar.monthrange(year, month_num)[1]
            start = f"{year}-{month_num:02d}-01"
            end = f"{year}-{month_num:02d}-{last_day:02d}"
            month_name = calendar.month_name[month_num]
            return start, end, f"Summary for {month_name} {year}"

        # 5. Day + Month e.g. "5 jun", "15 july", "5 june 2026"
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
                    return target_date, target_date, f"Summary for {date_obj.strftime('%d %B %Y')}"
                except ValueError:
                    pass

        # Fallback to current month
        start = now_ist.replace(day=1).date().isoformat()
        end = today.isoformat()
        return start, end, f"Monthly Summary ({now_ist.strftime('%B %Y')})"

    @classmethod
    def get_summary(cls, chat_id: int, query_arg: str = "") -> dict:
        supabase = cls.get_client()
        start_date, end_date, title = cls.parse_date_range(query_arg)
        
        response = supabase.table("transactions")\
            .select("*")\
            .eq("chat_id", chat_id)\
            .gte("date", start_date)\
            .lte("date", end_date)\
            .execute()
        
        records = response.data or []
        
        total_expense = sum(float(r["amount"]) for r in records if r["type"] == "expense")
        total_income = sum(float(r["amount"]) for r in records if r["type"] == "income")
        total_transfer = sum(float(r["amount"]) for r in records if r["type"] == "transfer")
        
        categories = {}
        for r in records:
            if r["type"] == "expense":
                cat = r["category"] or "Miscellaneous"
                categories[cat] = categories.get(cat, 0.0) + float(r["amount"])
                
        sorted_categories = dict(sorted(categories.items(), key=lambda item: item[1], reverse=True))
        
        return {
            "title": title,
            "total_expense": total_expense,
            "total_income": total_income,
            "total_transfer": total_transfer,
            "net_balance": total_income - total_expense,
            "categories": sorted_categories,
            "count": len(records)
        }