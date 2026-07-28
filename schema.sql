-- Paste this entire file into the Supabase SQL Editor and click RUN
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

DO $$ BEGIN CREATE TYPE account_type AS ENUM ('checking', 'savings', 'credit', 'cash', 'investment'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE transaction_type AS ENUM ('income', 'expense', 'transfer'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    telegram_chat_id BIGINT UNIQUE,
    link_code VARCHAR(64) UNIQUE,
    full_name TEXT,
    currency VARCHAR(3) DEFAULT 'USD',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.accounts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    type account_type NOT NULL,
    balance NUMERIC(19, 4) DEFAULT 0.0000,
    is_archived BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMPTZ DEFAULT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.categories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    type transaction_type NOT NULL,
    parent_category_id UUID REFERENCES public.categories(id) ON DELETE SET NULL,
    deleted_at TIMESTAMPTZ DEFAULT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    account_id UUID NOT NULL REFERENCES public.accounts(id) ON DELETE CASCADE,
    category_id UUID REFERENCES public.categories(id) ON DELETE SET NULL,
    amount NUMERIC(19, 4) NOT NULL,
    type transaction_type NOT NULL,
    transaction_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    description TEXT,
    is_recurring BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMPTZ DEFAULT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    table_name TEXT NOT NULL,
    record_id UUID NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('INSERT', 'UPDATE', 'DELETE')),
    old_data JSONB,
    new_data JSONB,
    user_id UUID,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION public.process_audit_log() RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.audit_logs (table_name, record_id, action, old_data, new_data, user_id)
    VALUES (TG_TABLE_NAME, COALESCE(NEW.id, OLD.id), TG_OP, CASE WHEN TG_OP IN ('UPDATE', 'DELETE') THEN row_to_json(OLD)::JSONB ELSE NULL END, CASE WHEN TG_OP IN ('INSERT', 'UPDATE') THEN row_to_json(NEW)::JSONB ELSE NULL END, COALESCE(auth.uid(), COALESCE(NEW.user_id, OLD.user_id)));
    RETURN NULL;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER audit_accounts_trigger AFTER INSERT OR UPDATE OR DELETE ON public.accounts FOR EACH ROW EXECUTE FUNCTION process_audit_log();
CREATE TRIGGER audit_transactions_trigger AFTER INSERT OR UPDATE OR DELETE ON public.transactions FOR EACH ROW EXECUTE FUNCTION process_audit_log();

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.transactions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Profiles Isolation" ON public.profiles FOR ALL USING (auth.uid() = id);
CREATE POLICY "Accounts Isolation" ON public.accounts FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Categories Isolation" ON public.categories FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Transactions Isolation" ON public.transactions FOR ALL USING (auth.uid() = user_id);
