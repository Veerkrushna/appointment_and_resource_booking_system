import uuid

from pydantic import BaseModel, Field


class ServiceProvidersAssign(BaseModel):
    provider_ids: list[uuid.UUID] = Field(
        min_length=1,
        description="List of providers to assign to the service",
    )


class ServiceProvidersUpdate(BaseModel):
    provider_ids: list[uuid.UUID] = Field(
        default_factory=list,
        description="Complete list of providers assigned to the service",
    )
