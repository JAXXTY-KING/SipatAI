ALTER TABLE farm_parcels
    ADD COLUMN IF NOT EXISTS source_attribution TEXT;
