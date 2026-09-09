import uuid

from pydantic import BaseModel, ConfigDict, Field


class ProviderServicesUpdate(BaseModel):
    service_ids: list[uuid.UUID] = Field(
        min_length=0,
        description="List of services offered by the provider",
    )


class ProviderServiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID

    provider_id: uuid.UUID

    service_id: uuid.UUID

    is_active: bool
