from pydantic import BaseModel, ConfigDict


class APIModel(BaseModel):
    """Base for every request/response model — rejects unknown fields on
    input rather than silently ignoring them (a typo'd field name should be
    a 422, not a request that quietly does something other than intended)."""

    model_config = ConfigDict(extra="forbid")
