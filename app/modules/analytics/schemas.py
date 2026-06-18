"""Analytics dashboard DTOs."""

from __future__ import annotations

from pydantic import BaseModel


class AdminMetric(BaseModel):
    id: str
    label: str
    value: str | int | float
    delta: str | None = None
    deltaDir: str | None = None
    deltaColor: str | None = None


class WeeklyBar(BaseModel):
    week: str
    count: int


class ServiceMixBar(BaseModel):
    service: str
    pct: float
    color: str


class PaymentMixBar(BaseModel):
    method: str
    pct: float
    color: str


class StatusBreakdown(BaseModel):
    label: str
    count: int
    pct: float
    color: str


class AlertItem(BaseModel):
    id: str
    message: str
    severity: str
    cta: str | None = None
    ctaHref: str | None = None


class AdminAgent(BaseModel):
    id: str
    fullName: str
    initials: str
    email: str
    skills: list[str]
    load: int
    capacity: int
    twoFa: bool
    role: str
    status: str
    activeCases: int
    completedTotal: int
    avgTurnaround: str
    slaPercent: float
    rating: float


class AnalyticsResponse(BaseModel):
    metrics: list[AdminMetric]
    weeklyBars: list[WeeklyBar]
    serviceMix: list[ServiceMixBar]
    paymentMix: list[PaymentMixBar]
    statusBreakdown: list[StatusBreakdown]
    alerts: list[AlertItem]
    agents: list[AdminAgent]
