import os
import requests
from api.core.config import settings

class TelegramService:
    @classmethod
    def get_token(cls) -> str:
        token = getattr(settings, "TELEGRAM_TOKEN", None) or os.getenv("TELEGRAM_TOKEN", "") or os.getenv("TELEGRAM_BOT_TOKEN", "")
        return str(token).strip("'\" ")

    @classmethod
    def send_message(cls, chat_id: int, text: str, reply_markup: dict = None) -> dict:
        token = cls.get_token()
        if not token:
            return {}
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            response = requests.post(url, json=payload, timeout=10)
            return response.json()
        except Exception as e:
            print(f"Failed to send telegram message: {str(e)}")
            return {}

    @classmethod
    def edit_message(cls, chat_id: int, message_id: int, text: str, reply_markup: dict = None) -> dict:
        token = cls.get_token()
        if not token:
            return {}
        url = f"https://api.telegram.org/bot{token}/editMessageText"
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            response = requests.post(url, json=payload, timeout=10)
            return response.json()
        except Exception as e:
            print(f"Failed to edit telegram message: {str(e)}")
            return {}

    @classmethod
    def send_photo(cls, chat_id: int, photo_path: str, caption: str = "") -> dict:
        token = cls.get_token()
        if not token:
            return {}
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        try:
            with open(photo_path, "rb") as photo_file:
                files = {"photo": photo_file}
                data = {"chat_id": chat_id, "caption": caption, "parse_mode": "Markdown"}
                response = requests.post(url, data=data, files=files, timeout=15)
                return response.json()
        except Exception as e:
            print(f"Failed to send photo: {str(e)}")
            return {}

    @classmethod
    def send_document(cls, chat_id: int, doc_bytes: bytes, filename: str, caption: str = "") -> dict:
        token = cls.get_token()
        if not token:
            return {}
        url = f"https://api.telegram.org/bot{token}/sendDocument"
        try:
            files = {"document": (filename, doc_bytes)}
            data = {"chat_id": chat_id, "caption": caption, "parse_mode": "Markdown"}
            response = requests.post(url, data=data, files=files, timeout=15)
            return response.json()
        except Exception as e:
            print(f"Failed to send document: {str(e)}")
            return {}

    @classmethod
    def build_delete_keyboard(cls, records: list, total_pages: int, current_page: int, query_arg: str, selected_ids: set) -> dict:
        inline_keyboard = []
        for r in records:
            tx_id = r["id"]
            is_selected = tx_id in selected_ids
            check = "✅" if is_selected else "⬜"
            desc = r.get("description", "Misc")
            amt = float(r.get("amount", 0))
            t_type = r.get("type", "expense")
            emoji = "📉" if t_type == "expense" else ("📈" if t_type == "income" else "🔄")
            label = f"{check} {emoji} {r.get('date')} | {desc[:15]} | {amt:,.0f}"
            
            inline_keyboard.append([{
                "text": label,
                "callback_data": f"del_toggle_{tx_id}_{query_arg if query_arg else 'None'}_{current_page}"
            }])
        
        nav_row = []
        if current_page > 0:
            nav_row.append({
                "text": "⬅️ Prev",
                "callback_data": f"del_page_{query_arg if query_arg else 'None'}_{current_page - 1}"
            })
        nav_row.append({
            "text": f"Page {current_page + 1}/{total_pages or 1}",
            "callback_data": "noop"
        })
        if current_page < total_pages - 1:
            nav_row.append({
                "text": "Next ➡️",
                "callback_data": f"del_page_{query_arg if query_arg else 'None'}_{current_page + 1}"
            })
        if nav_row:
            inline_keyboard.append(nav_row)

        action_row = []
        if selected_ids:
            action_row.append({
                "text": f"🗑️ Confirm Delete ({len(selected_ids)})",
                "callback_data": f"del_confirm_{query_arg if query_arg else 'None'}"
            })
        action_row.append({
            "text": "❌ Cancel",
            "callback_data": "del_cancel"
        })
        inline_keyboard.append(action_row)

        return {"inline_keyboard": inline_keyboard}
