import os
import requests
from api.core.config import settings

class TelegramService:
    @classmethod
    def get_bot_token(cls):
        token = getattr(settings, "TELEGRAM_BOT_TOKEN", None) or os.getenv("TELEGRAM_BOT_TOKEN", "")
        return str(token).strip("'\" ")

    @classmethod
    def send_message(cls, chat_id: int, text: str, reply_markup: dict = None):
        token = cls.get_bot_token()
        if not token:
            print("TELEGRAM_BOT_TOKEN is missing.")
            return False
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            resp = requests.post(url, json=payload)
            return resp.status_code == 200
        except Exception as e:
            print(f"Failed to send Telegram message: {e}")
            return False

    @classmethod
    def send_photo(cls, chat_id: int, photo_path: str, caption: str = ""):
        token = cls.get_bot_token()
        if not token:
            return False
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        try:
            with open(photo_path, 'rb') as photo:
                files = {'photo': photo}
                data = {'chat_id': chat_id, 'caption': caption, 'parse_mode': 'Markdown'}
                resp = requests.post(url, data=data, files=files)
                return resp.status_code == 200
        except Exception as e:
            print(f"Failed to send photo: {e}")
            return False

    @classmethod
    def send_document(cls, chat_id: int, doc_bytes: bytes, filename: str, caption: str = ""):
        token = cls.get_bot_token()
        if not token:
            return False
        url = f"https://api.telegram.org/bot{token}/sendDocument"
        try:
            files = {'document': (filename, doc_bytes, 'text/csv')}
            data = {'chat_id': chat_id, 'caption': caption, 'parse_mode': 'Markdown'}
            resp = requests.post(url, data=data, files=files)
            return resp.status_code == 200
        except Exception as e:
            print(f"Failed to send document: {e}")
            return False

    @classmethod
    def edit_message(cls, chat_id: int, message_id: int, text: str, reply_markup: dict = None):
        token = cls.get_bot_token()
        if not token:
            return False
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
            resp = requests.post(url, json=payload)
            return resp.status_code == 200
        except Exception as e:
            print(f"Failed to edit Telegram message: {e}")
            return False

    @classmethod
    def build_delete_keyboard(cls, records: list, total_pages: int, current_page: int, query_arg: str, selected_ids: set) -> dict:
        inline_keyboard = []
        q_str = query_arg if query_arg else "None"
        
        for r in records:
            tx_id = r["id"]
            is_selected = tx_id in selected_ids
            checkbox = "✅" if is_selected else "⬜️"
            t_type = r["type"].upper()
            desc = r["description"]
            amt = float(r["amount"])
            date_str = r["date"]
            
            button_text = f"{checkbox} [{date_str}] {desc} - ₹{amt:,.2f} ({t_type})"
            callback_data = f"del_toggle_{tx_id}_{q_str}_{current_page}"
            inline_keyboard.append([{"text": button_text, "callback_data": callback_data}])

        nav_row = []
        if current_page > 0:
            nav_row.append({"text": "⬅️ Prev", "callback_data": f"del_page_{q_str}_{current_page - 1}"})
        nav_row.append({"text": f"Page {current_page + 1}/{total_pages}", "callback_data": "noop"})
        if current_page < total_pages - 1:
            nav_row.append({"text": "Next ➡️", "callback_data": f"del_page_{q_str}_{current_page + 1}"})
        
        if nav_row:
            inline_keyboard.append(nav_row)

        action_row = [
            {"text": "🗑️ Delete Selected", "callback_data": f"del_confirm_{q_str}"},
            {"text": "❌ Cancel", "callback_data": "del_cancel"}
        ]
        inline_keyboard.append(action_row)

        return {"inline_keyboard": inline_keyboard}

    @classmethod
    def set_bot_commands(cls) -> bool:
        token = cls.get_bot_token()
        if not token:
            return False
        url = f"https://api.telegram.org/bot{token}/setMyCommands"
        commands = [
            {"command": "start", "description": "Launch PFM Bot & Menu"},
            {"command": "setsalary", "description": "Set monthly base salary"},
            {"command": "budget", "description": "Check Safe House Budget & guardrails"},
            {"command": "addloan", "description": "Add new loan & payment schedule"},
            {"command": "loans", "description": "View active loans & amortization"},
            {"command": "summary", "description": "View monthly financial breakdown"},
            {"command": "report", "description": "View detailed financial statement"},
            {"command": "statistics", "description": "View analytics & daily spend rate"},
            {"command": "chart", "description": "Generate visual expense pie chart"},
            {"command": "export", "description": "Download CSV transaction report"},
            {"command": "delete", "description": "Interactive paginated transaction manager"}
        ]
        try:
            resp = requests.post(url, json={"commands": commands})
            return resp.status_code == 200 and resp.json().get("ok", False)
        except Exception as e:
            print(f"Failed to set bot commands: {e}")
            return False
