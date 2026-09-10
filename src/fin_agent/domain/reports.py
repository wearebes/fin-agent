"""Chart data is generated from provider observations, never from model prose."""

from typing import Literal

from pydantic import BaseModel, Field


class ReportSeries(BaseModel):
    name: str
    values: list[float | None]


class ReportChart(BaseModel):
    title: str
    kind: Literal["line", "bar"]
    unit: str
    labels: list[str]
    series: list[ReportSeries]
    source: str
    note: str


class ReportMetric(BaseModel):
    label: str
    value: float
    unit: str
    context: str


class ReportData(BaseModel):
    captured_at: str
    narrative: Literal["ai", "data_only"]
    metrics: list[ReportMetric] = Field(default_factory=list)
    charts: list[ReportChart] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    summary: list[str] = Field(default_factory=list)
