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
        
        # Calculate EMI using reducing balance formula
        if interest_rate == 0:
            emi_amt = principal / tenure_months
        else:
            monthly_rate = (interest_rate / 100.0) / 12.0
            emi_amt = principal * monthly_rate * ((1 + monthly_rate) ** tenure_months) / (((1 + monthly_rate) ** tenure_months) - 1)
        emi_amt = round(emi_amt, 2)

        # 1. Insert Loan Record
        loan_record = {
            "chat_id": chat_id,
            "name": name,
            "lender_type": lender_type, # 'bank' or 'family'
            "priority": priority,       # 'high', 'medium', 'low'
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

        # 2. Automatically generate monthly installment schedule
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
            # Increment month safely
            if curr_date.month == 12:
                curr_date = curr_date.replace(year=curr_date.year + 1, month=1)
            else:
                curr_date = curr_date.replace(month=curr_date.month + 1)

        supabase.table("loan_installments").insert(installments).execute()
        return created_loan

    @classmethod
    def pay_loan_installment_by_month(cls, chat_id: int, loan_id: int, installment_month: str) -> dict:
        """
        Marks a specific month's EMI as paid, reduces remaining loan balance, 
        and logs it as an expense transaction in the general ledger.
        """
        supabase = cls.get_client()
        
        # Verify loan ownership
        loan_res = supabase.table("loans").select("*").eq("id", loan_id).eq("chat_id", chat_id).execute()
        if not loan_res.data:
            raise ValueError("Loan not found.")
        loan = loan_res.data[0]

        # Verify installment exists and is pending
        inst_res = supabase.table("loan_installments").select("*").eq("loan_id", loan_id).eq("installment_month", installment_month).execute()
        if not inst_res.data:
            raise ValueError(f"No installment found for month {installment_month}.")
        
        installment = inst_res.data[0]
        if installment["status"] == "paid":
            raise ValueError(f"Installment for {installment_month} is already paid!")

        emi_amt = float(installment["emi_amount"])
        new_remaining = max(0.0, float(loan["remaining_amount"]) - emi_amt)
        new_status = "closed" if new_remaining == 0 else "active"

        today_str = datetime.now().date().isoformat()

        # 1. Update Installment Status
        supabase.table("loan_installments").update({
            "status": "paid",
            "paid_date": today_str
        }).eq("id", installment["id"]).execute()

        # 2. Update Loan Remaining Principal & Status
        supabase.table("loans").update({
            "remaining_amount": new_remaining,
            "status": new_status
        }).eq("id", loan_id).execute()

        # 3. Log EMI payment as a standard expense in the main ledger
        tx_record = {
            "chat_id": chat_id,
            "description": f"EMI: {loan['name']} ({installment_month})",
            "amount": emi_amt,
            "type": "expense",
            "category": "Loans & EMIs",
            "date": today_str
        }
        supabase.table("transactions").insert(tx_record).execute()

        return {
            "loan_name": loan["name"],
            "installment_month": installment_month,
            "emi_paid": emi_amt,
            "remaining_principal": new_remaining,
            "loan_status": new_status
        }

    @classmethod
    def get_monthly_budget_guardrail(cls, chat_id: int, year_month: str) -> dict:
        """
        Computes Salary - Total EMIs due for the month = Safe House Expense Budget.
        Checks current month's house expenses against this buffer.
        """
        supabase = cls.get_client()
        
        # 1. Get base salary
        base_salary = cls.get_user_salary(chat_id)

        # 2. Get extra variable incomes logged for this specific month
        incomes_res = supabase.table("incomes").select("amount").eq("chat_id", chat_id).gte("date", f"{year_month}-01").lte("date", f"{year_month}-31").execute()
        extra_income = sum(float(inc["amount"]) for inc in (incomes_res.data or []))
        total_inflow = base_salary + extra_income

        # 3. Get total mandatory EMIs scheduled for this month
        inst_res = supabase.table("loan_installments").select("emi_amount, status").eq("chat_id", chat_id).eq("installment_month", year_month).execute()
        installments = inst_res.data or []
        total_emis = sum(float(inst["emi_amount"]) for inst in installments)
        paid_emis = sum(float(inst["emi_amount"]) for inst in installments if inst["status"] == "paid")

        # 4. Calculate House Expense Buffer
        safe_house_budget = total_inflow - total_emis

        # 5. Get actual house expenses spent so far this month
        tx_res = supabase.table("transactions").select("amount, category").eq("chat_id", chat_id).eq("type", "expense").neq("category", "Loans & EMIs").gte("date", f"{year_month}-01").lte("date", f"{year_month}-31").execute()
        actual_house_spent = sum(float(tx["amount"]) for tx in (tx_res.data or []))

        # 6. Budget Warning Level Calculation
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
