-- ╔══════════════════════════════════════════════════════════════╗
-- ║  TaskFlow Pro — Supabase Setup                               ║
-- ║  Run this entire file in: Supabase → SQL Editor → New Query  ║
-- ╚══════════════════════════════════════════════════════════════╝


-- Step 1: Create the tasks table
-- ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.tasks (
    id           TEXT        PRIMARY KEY,
    name         TEXT        NOT NULL,
    category     TEXT        DEFAULT 'General',
    priority     TEXT        DEFAULT 'Medium',
    due_date     TEXT,
    status       TEXT        DEFAULT 'pending',
    is_deleted   BOOLEAN     DEFAULT FALSE,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    notes        TEXT
);


-- Step 2: Add check constraints for data integrity
-- ──────────────────────────────────────────────────────────────

ALTER TABLE public.tasks
    ADD CONSTRAINT tasks_priority_check
    CHECK (priority IN ('High', 'Medium', 'Low'));

ALTER TABLE public.tasks
    ADD CONSTRAINT tasks_status_check
    CHECK (status IN ('pending', 'completed'));

ALTER TABLE public.tasks
    ADD CONSTRAINT tasks_category_check
    CHECK (category IN ('Work', 'Study', 'Personal', 'Health', 'Finance', 'General'));


-- Step 3: Index for faster queries
-- ──────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_tasks_status     ON public.tasks (status);
CREATE INDEX IF NOT EXISTS idx_tasks_priority   ON public.tasks (priority);
CREATE INDEX IF NOT EXISTS idx_tasks_is_deleted ON public.tasks (is_deleted);
CREATE INDEX IF NOT EXISTS idx_tasks_due_date   ON public.tasks (due_date);


-- Step 4: Enable Row Level Security
-- ──────────────────────────────────────────────────────────────

ALTER TABLE public.tasks ENABLE ROW LEVEL SECURITY;


-- Step 5: RLS Policies — Public access via anon key
-- (This is an internship eval project — no auth required)
-- ──────────────────────────────────────────────────────────────

-- Allow reading all tasks
CREATE POLICY "anon_select"
    ON public.tasks
    FOR SELECT
    TO anon
    USING (true);

-- Allow inserting new tasks
CREATE POLICY "anon_insert"
    ON public.tasks
    FOR INSERT
    TO anon
    WITH CHECK (true);

-- Allow updating tasks (for sync / complete / soft-delete)
CREATE POLICY "anon_update"
    ON public.tasks
    FOR UPDATE
    TO anon
    USING (true)
    WITH CHECK (true);

-- Allow hard delete (not used by app, but available)
CREATE POLICY "anon_delete"
    ON public.tasks
    FOR DELETE
    TO anon
    USING (true);




