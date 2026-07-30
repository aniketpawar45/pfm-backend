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
        first_emi_date: str = None
    ) -> dict:
        supabase = cls.get_client()
        s_date = datetime.strptime(first_emi_date, "%Y-%m-%d").date() if first_emi_date else datetime.now().date()

        if interest_rate == 0:
            emi_amt = principal / tenure_months
        else:
            monthly_rate = (interest_rate / 100.0) / 12.0
            emi_amt = principal * monthly_rate * ((1 + monthly_rate) ** tenure_months) / (((1 + monthly_rate) ** tenure_months) - 1)
        emi_amt = round(emi_amt, 2)

        # 1. Determine how many EMIs have already passed compared to the current month
        curr_year = s_date.year
        curr_month = s_date.month
        
        IST = timezone(timedelta(hours=5, minutes=30))
        current_month_str = datetime.now(IST).strftime("%Y-%m")

        installments = []
        passed_emis_count = 0

        for i in range(tenure_months):
            month_str = f"{curr_year}-{curr_month:02d}"
            
            # If the scheduled month is strictly in the past, mark it as already paid
            if month_str < current_month_str:
                status = "paid"
                passed_emis_count += 1
            else:
                status = "pending"
                
            installments.append({
                "chat_id": chat_id,
                "installment_month": month_str,
                "emi_amount": emi_amt,
                "status": status
            })
            
            curr_month += 1
            if curr_month > 12:
                curr_month = 1
                curr_year += 1

        # 2. Re-calculate the actual remaining principal after deducting past EMIs
        if interest_rate == 0:
            remaining_amount = principal - (passed_emis_count * emi_amt)
        else:
            monthly_rate = (interest_rate / 100.0) / 12.0
            # Amortization formula to find remaining balance after X payments
            remaining_amount = principal * (((1 + monthly_rate)**tenure_months) - ((1 + monthly_rate)**passed_emis_count)) / (((1 + monthly_rate)**tenure_months) - 1)
            
        remaining_amount = max(0.0, round(remaining_amount, 2))
        loan_status = "closed" if remaining_amount == 0 else "active"

        loan_record = {
            "chat_id": chat_id,
            "name": name,
            "lender_type": lender_type,
            "priority": priority,
            "principal": principal,
            "interest_rate": interest_rate,
            "tenure_months": tenure_months,
            "emi_amount": emi_amt,
            "remaining_amount": remaining_amount,
            "start_date": s_date.isoformat(),
            "status": loan_status
        }
        
        # 3. Save to database
        loan_res = supabase.table("loans").insert(loan_record).execute()
        if not loan_res.data:
            raise ValueError("Failed to create loan record.")

        created_loan = loan_res.data[0]
        loan_id = created_loan["id"]

        for inst in installments:
            inst["loan_id"] = loan_id

        supabase.table("loan_installments").insert(installments).execute()
        
        # Attach these virtual fields just so the Telegram bot can show the user what happened
        created_loan["pending_emis"] = tenure_months - passed_emis_count
        created_loan["passed_emis"] = passed_emis_count
        
        return created_loan


    @classmethod
    def get_user_loans(cls, chat_id: int) -> list:
        """Fetches active loans and dynamically counts the number of pending EMIs for each."""
        supabase = cls.get_client()
        res = supabase.table("loans").select("*").eq("chat_id", chat_id).eq("status", "active").execute()
        loans = res.data or []
        
        if loans:
            # Query all pending installments for this user at once
            inst_res = supabase.table("loan_installments").select("loan_id").eq("chat_id", chat_id).eq("status", "pending").execute()
            pending_installments = inst_res.data or []
            
            # Count them up by loan_id
            pending_counts = {}
            for inst in pending_installments:
                lid = inst["loan_id"]
                pending_counts[lid] = pending_counts.get(lid, 0) + 1
                
            # Attach the count back to the loan objects so the frontend can display it
            for l in loans:
                l["pending_emis"] = pending_counts.get(l["id"], 0)
                
        return loans
