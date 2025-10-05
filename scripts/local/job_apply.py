#!/usr/bin/env python3
"""
📝 Job Application Script
Simple script to apply to jobs locally.
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ronin.apps.job_automation.application.appliers import SeekApplier
from ronin.core.config import load_config
from ronin.services.airtable_service import AirtableManager


def main():
    """Main job application function."""
    print("📝 Starting job applications...")

    try:
        # Load configuration
        config = load_config()
        print("📋 Configuration loaded")

        # Initialize applier and Airtable manager
        applier = SeekApplier()
        airtable_manager = AirtableManager()
        print("✅ Job applier and Airtable manager initialized")

        # Get jobs from Airtable that haven't been applied to yet
        print("📋 Fetching jobs from Airtable view...")

        # Get jobs from the specific view for applications
        view_id = "viwlfrTkkE2krqpRy"
        job_records = airtable_manager.table.all(view=view_id)

        if not job_records:
            print("ℹ️ No jobs found in the application view")
            print("💡 Try running 'make search' first to discover new jobs")
            return

        print(f"📋 Found {len(job_records)} jobs to apply to")

        # Apply to first few jobs (limit to avoid overwhelming)
        max_applications = min(3, len(job_records))
        successful_applications = 0

        for i, record in enumerate(job_records[:max_applications], 1):
            fields = record["fields"]
            job_title = fields.get("Title", "N/A")
            company_name = fields.get("Company Name", "N/A")
            job_url = fields.get("URL", "")
            job_description = fields.get("Description", "")

            print(f"\n📝 Applying to job {i}/{max_applications}: {job_title}")
            print(f"   Company: {company_name}")
            print(f"   URL: {job_url}")

            try:
                # Extract job ID from URL for Seek jobs
                job_id = ""
                if "seek.com.au" in job_url:
                    # Extract job ID from Seek URL
                    parts = job_url.split("/")
                    for part in parts:
                        if part.isdigit():
                            job_id = part
                            break

                # Apply to the job
                result = applier.apply_to_job(
                    job_id=job_id,
                    job_description=job_description,
                    score=0,  # Default score
                    tech_stack=[],  # Default tech stack
                    company_name=company_name,
                    title=job_title,
                )

                if result == "APPLIED":
                    print(f"✅ Successfully applied to {job_title} at {company_name}")

                    # Update job status in Airtable to "APPLIED"
                    airtable_manager.update_record(record["id"], {"Status": "APPLIED"})
                    print(f"📝 Updated job status to 'APPLIED' in Airtable")

                    successful_applications += 1
                elif result == "STALE":
                    print(
                        f"⏭️  Job is no longer advertised: {job_title} at {company_name}"
                    )

                    # Update job status in Airtable to "STALE"
                    airtable_manager.update_record(record["id"], {"Status": "STALE"})
                    print(f"📝 Updated job status to 'STALE' in Airtable")
                else:
                    print(f"❌ Failed to apply to {job_title} at {company_name}")

            except Exception as e:
                print(f"❌ Error applying to {job_title}: {e}")

        print(f"\n🎉 Application process complete!")
        print(
            f"✅ Successfully applied to {successful_applications}/{max_applications} jobs"
        )

    except Exception as e:
        print(f"❌ Error during job applications: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
