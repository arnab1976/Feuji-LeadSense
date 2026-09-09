# Demo CSV pack (per-source, full-field)

Each file has **50 observations** and uses a realistic export-style schema:

`external_id, full_name, first_name, last_name, email, title, company_name, location, profile_url, phone, industry, employee_count, tech_stack, segment, source_hint, notes`

Each source/list now has its **own dataset file**; files are not reused across connectors.

Workflow files:

- `salesforce_bfsi_prospect_list.csv`
- `salesforce_technology_buyers_crm.csv`
- `hubspot_lifesciences_list.csv`
- `hubspot_bfsi_nurture_list.csv`
- `zoominfo_tech_enrichment_pack.csv`
- `zoominfo_pharma_enrichment_pack.csv`
- `apollo_saas_targets.csv`
- `apollo_bfsi_targets.csv`
- `csv_url_mixed_industry_feed.csv`
- `web_profile_public_team_pages.csv`
- `manual_upload_technology_buyers.csv`
- `manual_upload_lifesciences.csv`
- `manual_upload_bfsi.csv`

Legacy aliases remain for compatibility with older demo flows.
