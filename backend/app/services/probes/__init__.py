"""Live, issue-scoped probe packs.

Each probe module collects real system facts for one domain and turns them into
deterministic findings - without consulting the knowledge base. The registry
maps a domain name to its ``investigate`` callable.
"""
from __future__ import annotations

from app.services.probes.base import ProbeContext, ProbeOutcome
from app.services.probes import (
    application,
    audio,
    bluetooth,
    display,
    drivers,
    input_devices,
    network,
    performance,
    printer,
    storage,
    usb,
    wifi,
    webcam,
    windows_update,
)

REGISTRY = {
    "bluetooth": bluetooth.investigate,
    "wifi": wifi.investigate,
    "network": network.investigate,
    "audio": audio.investigate,
    "printer": printer.investigate,
    "display": display.investigate,
    "usb": usb.investigate,
    "storage": storage.investigate,
    "performance": performance.investigate,
    "windows_update": windows_update.investigate,
    "application": application.investigate,
    "input": input_devices.investigate,
    "mouse": input_devices.investigate,
    "keyboard": input_devices.investigate,
    "webcam": webcam.investigate,
    "driver": drivers.investigate,
}

__all__ = ["REGISTRY", "ProbeContext", "ProbeOutcome"]
