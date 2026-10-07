-- Authored disposable Supabase example. Run only in a test database that provides auth.uid().
-- Two synthetic users share the finite tenant model; the checker reads catalogs, never these rows.
CREATE ROLE db_owner NOLOGIN NOSUPERUSER NOBYPASSRLS;
CREATE ROLE user_a LOGIN NOSUPERUSER NOBYPASSRLS;
CREATE ROLE user_b LOGIN NOSUPERUSER NOBYPASSRLS;
CREATE TABLE public.cpd_records (owner_id uuid NOT NULL, note text NOT NULL);
ALTER TABLE public.cpd_records OWNER TO db_owner;
INSERT INTO public.cpd_records VALUES
 ('00000000-0000-0000-0000-000000000001', 'synthetic A'),
 ('00000000-0000-0000-0000-000000000002', 'synthetic B');
GRANT USAGE ON SCHEMA public, auth TO user_a, user_b;
GRANT SELECT ON public.cpd_records TO user_a, user_b;
ALTER TABLE public.cpd_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cpd_records FORCE ROW LEVEL SECURITY;
CREATE POLICY cpd_own_rows ON public.cpd_records FOR SELECT TO PUBLIC USING (owner_id = auth.uid());
-- For each test session, SET ROLE user_a/user_b and SET request.jwt.claim.sub to the corresponding UUID.
-- Restricted: each user reads their own row.
-- Mutation 1: ALTER TABLE public.cpd_records DISABLE ROW LEVEL SECURITY;
-- Repair 1: ALTER TABLE public.cpd_records ENABLE ROW LEVEL SECURITY;
-- Mutation 2: ALTER POLICY cpd_own_rows ON public.cpd_records USING (true);
-- Repair 2: ALTER POLICY cpd_own_rows ON public.cpd_records USING (owner_id = auth.uid());
-- Either mutation lets user A read both rows. The declaration stays unchanged.
-- execution_authorized false; hardware_authorized false; industrial_release_authorized false;
-- release_allowed false; physical_validation false; simulation true; self_approved false.
