-- ╔══════════════════════════════════════════════════════════════════════╗
-- ║  TaskFlow Pro — Supabase Setup (Final)                               ║
-- ║  Run this entire file in: Supabase → SQL Editor → New Query          ║
-- ║  Safe to re-run on existing tables (IF NOT EXISTS / DROP IF EXISTS)  ║
-- ╚══════════════════════════════════════════════════════════════════════╝


-- ══════════════════════════════════════════════════════════════════════
-- Step 1: Create the tasks table (with all columns)
-- ══════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS public.tasks (
    id                   TEXT          PRIMARY KEY,
    name                 TEXT          NOT NULL,
    category             TEXT          DEFAULT 'General',
    priority             TEXT          DEFAULT 'Medium',
    due_date             TEXT,
    due_time             TEXT,
    status               TEXT          DEFAULT 'pending',
    is_deleted           BOOLEAN       DEFAULT FALSE,
    created_at           TIMESTAMPTZ   DEFAULT NOW(),
    completed_at         TIMESTAMPTZ,
    notes                TEXT,
    reminder_at          TIMESTAMPTZ,
    reminder_sent        BOOLEAN       NOT NULL DEFAULT FALSE,
    recurrence           TEXT          NOT NULL DEFAULT 'none',
    recurrence_end_date  TEXT
);


-- ══════════════════════════════════════════════════════════════════════
-- Step 2: Constraints
-- ══════════════════════════════════════════════════════════════════════

ALTER TABLE public.tasks
    DROP CONSTRAINT IF EXISTS tasks_priority_check;
ALTER TABLE public.tasks
    ADD CONSTRAINT tasks_priority_check
    CHECK (priority IN ('High', 'Medium', 'Low'));

ALTER TABLE public.tasks
    DROP CONSTRAINT IF EXISTS tasks_status_check;
ALTER TABLE public.tasks
    ADD CONSTRAINT tasks_status_check
    CHECK (status IN ('pending', 'completed'));

ALTER TABLE public.tasks
    DROP CONSTRAINT IF EXISTS tasks_category_check;
ALTER TABLE public.tasks
    ADD CONSTRAINT tasks_category_check
    CHECK (category IN ('Work', 'Study', 'Personal', 'Health', 'Finance', 'General'));

ALTER TABLE public.tasks
    DROP CONSTRAINT IF EXISTS tasks_recurrence_check;
ALTER TABLE public.tasks
    ADD CONSTRAINT tasks_recurrence_check
    CHECK (recurrence = ANY(ARRAY[
        'none'::text,
        'daily'::text,
        'weekly'::text,
        'weekdays'::text,
        'monthly'::text
    ]));


-- ══════════════════════════════════════════════════════════════════════
-- Step 3: Indexes
-- ══════════════════════════════════════════════════════════════════════

CREATE INDEX IF NOT EXISTS idx_tasks_status
    ON public.tasks (status);

CREATE INDEX IF NOT EXISTS idx_tasks_priority
    ON public.tasks (priority);

CREATE INDEX IF NOT EXISTS idx_tasks_is_deleted
    ON public.tasks (is_deleted);

CREATE INDEX IF NOT EXISTS idx_tasks_due_date
    ON public.tasks (due_date);

-- Full index on reminder_at (ordering / range queries)
CREATE INDEX IF NOT EXISTS idx_tasks_reminder_at
    ON public.tasks USING btree (reminder_at)
    TABLESPACE pg_default;

-- Partial index — only unsent, non-null reminders (reminder daemon query)
CREATE INDEX IF NOT EXISTS idx_tasks_reminder_pending
    ON public.tasks (reminder_at)
    WHERE reminder_sent = FALSE AND reminder_at IS NOT NULL;


-- ══════════════════════════════════════════════════════════════════════
-- Step 4: Row Level Security
-- ══════════════════════════════════════════════════════════════════════

ALTER TABLE public.tasks ENABLE ROW LEVEL SECURITY;


-- ══════════════════════════════════════════════════════════════════════
-- Step 5: RLS Policies (anon key — internship eval, no auth required)
-- ══════════════════════════════════════════════════════════════════════

DROP POLICY IF EXISTS "anon_select" ON public.tasks;
CREATE POLICY "anon_select"
    ON public.tasks FOR SELECT TO anon
    USING (true);

DROP POLICY IF EXISTS "anon_insert" ON public.tasks;
CREATE POLICY "anon_insert"
    ON public.tasks FOR INSERT TO anon
    WITH CHECK (true);

DROP POLICY IF EXISTS "anon_update" ON public.tasks;
CREATE POLICY "anon_update"
    ON public.tasks FOR UPDATE TO anon
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "anon_delete" ON public.tasks;
CREATE POLICY "anon_delete"
    ON public.tasks FOR DELETE TO anon
    USING (true);


-- ══════════════════════════════════════════════════════════════════════
-- Verify — uncomment and run to confirm everything looks correct
-- ══════════════════════════════════════════════════════════════════════

-- SELECT column_name, data_type, column_default, is_nullable
-- FROM information_schema.columns
-- WHERE table_name = 'tasks'
-- ORDER BY ordinal_position;
