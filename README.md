# 🤖 Salary-Anchored PFM Telegram Bot

A high-performance, intelligent Personal Finance Management (PFM) Telegram bot built on **FastAPI**, deployed on **Vercel**, and backed by **Supabase**. It prioritizes debt management, automated budget guardrails, and precise tracking of bank and personal loans using a strict **"Salary-First"** financial engine.

---

## 🛠️ Tech Stack & Architecture

* **Backend Framework:** FastAPI (Python)
* **Hosting / Runtime:** Vercel (Serverless Functions)
* **Database:** Supabase (PostgreSQL with Row Level Security)
* **AI Parsing Engine:** Groq API (`llama-3.3-70b-versatile`) for natural language extraction
* **Interface:** Telegram Bot API (with inline keyboard callbacks & matplotlib charts)

---

## 💡 Core Financial Engine: The "Salary-First" Model

The system enforces strict financial discipline by locking away mandatory monthly debt obligations before allowing lifestyle spending to be tracked:

$$\text{Total Monthly Inflow} = \text{Base Salary} + \text{Variable Extra Incomes}$$

$$\text{Safe House Budget} = \text{Total Monthly Inflow} - \text{Mandatory EMIs for the Month}$$

The bot continuously evaluates your lifestyle spending against your Safe House Budget and triggers warnings at specific thresholds:
* 🟢 **Safe:** Under 75% utilized
* 🟡 **Warning:** 75% – 89% utilized
* 🟠 **Critical:** 90% – 99% utilized
* 🔴 **Breached:** 100%+ utilized

---

## 🚀 Commands & Natural Language Guide

### 1. Salary & Budget Configuration
* **`/setsalary [amount]`**
  * *Example:* `/setsalary 75000`
  * *Description:* Sets your predictable monthly baseline income to anchor your budget guardrails.
* **`/budget [YYYY-MM]`**
  * *Example:* `/budget` or `/budget 2026-07`
  * *Description:* Displays your current or specific month's inflow breakdown, total EMIs, safe house budget, and utilization percentage.

### 2. Loan & Liability Management
* **`/addloan [Name] | [bank/family] | [high/low] | [Principal] | [InterestRate%] | [TenureMonths]`**
  * *Example:* `/addloan Sushma | family | high | 150000 | 0 | 6`
  * *Description:* Adds a loan, calculates the reducing-balance or flat EMI, and automatically generates a month-by-month installment schedule (`YYYY-MM`) in the database.
* **`/loans`**
  * *Example:* `/loans`
  * *Description:* Lists all active liabilities, remaining principal balances, priority tiers, lender types, and paid percentages.

### 3. Natural Language Transaction & EMI Logging
You don't need rigid syntax for everyday tracking. The AI parser processes natural language inputs directly:

* **Logging Expenses:**
  * *Example:* `"Paid 450 for lunch at McDonald's"`
  * *Example:* `"Spent 2400 on groceries"`
* **Logging Variable Extra Incomes (Passive addition without altering baseline salary):**
  * *Example:* `"I received 10000 extra from freelance"`
  * *Example:* `"Got a bonus of 15000"`
* **Automatic EMI / Loan Repayment Matching:**
  * *Example:* `"I have paid 24k emi to Sushma"`
  * *Description:* The bot automatically matches the lender name against your active loan list, locates the current month's pending installment, marks it as paid, reduces your remaining loan principal, and logs the expense under `Loans & EMIs`.

### 4. Financial Reports & Management
* **`/summary [Month/Year]`**
  * *Example:* `/summary` or `/summary July` or `/summary 2026`
  * *Description:* Generates a complete financial snapshot showing total income, total expenses, net balance, and category-wise breakdowns.
* **`/chart [Month/Year]`**
  * *Example:* `/chart`
  * *Description:* Renders and sends a clean dark-themed visual pie chart of your expense categories.
* **`/export`**
  * *Example:* `/export`
  * *Description:* Generates and uploads a downloadable `.csv` statement of your transaction ledger.
* **`/delete [Month/Year]`**
  * *Example:* `/delete` or `/delete June`
  * *Description:* Opens an interactive inline-keyboard manager allowing you to select and safely delete incorrect or duplicate transactions across paginated views.
