"""Tracing and metrics helpers."""

from __future__ import annotations

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from prometheus_client import make_asgi_app

from app.core.config import Settings


def configure_observability(app: FastAPI, settings: Settings) -> None:
    resource = Resource.create({"service.name": settings.app_name, "deployment.environment": settings.app_env})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    app.mount(settings.metrics_path, make_asgi_app())
