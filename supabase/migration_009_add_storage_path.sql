-- ================================================================
-- Migration 009: Add storage_path to product_images
-- ================================================================

ALTER TABLE public.product_images ADD COLUMN IF NOT EXISTS storage_path text;
