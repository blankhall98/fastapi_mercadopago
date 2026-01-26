from pydantic import BaseModel

class PlanOut(BaseModel):
    code: str
    name: str
    kind: str
    price: float
    currency: str
    access_duration_days: int | None

    class Config:
        from_attributes = True

class CreateOneTimeLinkIn(BaseModel):
    plan_code: str

class CreateOneTimeLinkOut(BaseModel):
    preference_id : str
    init_point : str

class CreateRecurringLinkIn(BaseModel):
    plan_code: str

class CreateRecurringLinkOut(BaseModel):
    preapproval_id: str
    init_point: str

class CancelRecurringIn(BaseModel):
    plan_code: str

class CancelRecurringOut(BaseModel):
    preapproval_id: str
    status: str
