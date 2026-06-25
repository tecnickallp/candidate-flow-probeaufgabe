from datetime import datetime, timezone

from pydantic import BaseModel, Field


class JobListing(BaseModel):
    title: str
    tasks: list[str] = Field(default_factory=list)
    employer_benefits: list[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    company_name: str
    website_url: str
    industry: str = ""
    benefits: list[str] = Field(default_factory=list)
    vibe: str = ""
    jobs: list[JobListing] = Field(default_factory=list)
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_storage_dict(self) -> dict:
        return {
            "company_name": self.company_name,
            "website_url": self.website_url,
            "industry": self.industry,
            "benefits": self.benefits,
            "vibe": self.vibe,
            "jobs": [job.model_dump() for job in self.jobs],
            "analyzed_at": self.analyzed_at.isoformat(),
        }
