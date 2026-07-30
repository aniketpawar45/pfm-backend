# 🤖 Salary-Anchored PFM Telegram Bot & FastAPI Backend

An intelligent, secure, and feature-rich Personal Finance Manager (PFM) bot powered by FastAPI, Supabase, Groq AI (Llama-3.3-70b), and Matplotlib, deployed serverlessly on Vercel.

---

## 🚀 Tech Stack

*   **Backend Framework**: FastAPI (Python)
*   **Database**: Supabase (PostgreSQL)
*   **AI Engine**: Groq API (`llama-3.3-70b-versatile`) for natural language parsing and financial advisory
*   **Data Visualization**: Matplotlib (Dark-themed analytics charts)
*   **Hosting & Automation**: Vercel (Serverless functions + Daily Cron Jobs)
*   **Messaging Interface**: Telegram Bot API

---

## 📋 Comprehensive Feature List

### ⚙️ Setup & Budgeting
*   `/setsalary [amount]` — Set or update your monthly base salary to anchor your budget limits.
*   `/budget` — Check your **Safe House Budget** and financial guardrails. Tracks base salary, extra income, total inflows, mandatory EMIs, actual spending, and real-time utilization status (🟢 Safe, 🟡 Warning, 🟠 Critical, 🔴 Breached).

### 💳 Debt & Loan Management
*   `/addloan` — Add new loans and amortization schedules (supports principal amount, tenure in months, interest rates, and custom start dates with auto-calculation of past/pending EMIs).
*   `/loans` — View your active loan portfolio, remaining balances, paid percentages, and upcoming EMIs.
*   `/deleteloan [Name]` — Remove a loan and its associated payment schedule entirely.

### 🔄 Subscriptions (Auto-Billing)
*   `/addsub` — Add recurring bills (e.g., Netflix, Gym) specifying name, amount, cycle (`monthly` or `yearly`), and next billing date.
*   `/subs` — List all active subscriptions and calculate your average monthly financial drain.
*   `/delsub [Name]` — Remove a subscription from auto-tracking.

### 🧠 AI & Analytics
*   `/ask [question]` — Get personalized AI financial advice based directly on your transaction data and financial profile (powered by Groq).
*   **Natural Language Expense Logging** — Type naturally to log expenses or income (e.g., *"Paid ₹500 for lunch"* or *"Received salary"*). The AI parses amounts, categories, and descriptions, and automatically matches incoming payments against active loan EMIs.
*   `/summary` or `/report` — Get a monthly financial breakdown of total income, expenses, net balance, and category-wise spending.
*   `/statistics` — Deep analytics covering savings rates, average daily spend, and largest single expenses.
*   `/chart` — Generate and receive a custom dark-themed expense category distribution pie chart.
*   `/export` — Download a complete CSV transaction statement directly in Telegram.
*   `/delete` — Interactive inline-keyboard transaction manager to browse and select multiple transactions for deletion.

### ⏰ Automated Background Tasks
*   **Vercel Cron**: Configured to run automatically every day at **7:05 AM IST** (`35 1 * * *`) via the `/cron/daily` endpoint to handle automated subscription alerts and system checks.

---

## 🔒 Security & Authentication
*   **Bulletproof Gatekeeper**: Protected by an `ALLOWED_TELEGRAM_IDS` environment variable check. Unauthorized users are blocked instantly with an access-restricted notice.