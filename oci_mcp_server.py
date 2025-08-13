#!/usr/bin/env python3
"""
OCI MCP Server
- Tools for Compute / DB / Object Storage discovery and simple actions
- Resource providers (e.g., compartments)
- A prompt for summarizing findings

Transports: stdio (default)
"""

from __future__ import annotations

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

# MCP (official Python SDK)
from mcp.server.fastmcp import FastMCP

# OCI SDK
import oci
from oci.util import to_dict

# ---------- Logging & env ----------
load_dotenv()
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("oci-mcp")

# ---------- OCI helper ----------

class OCIManager:
    """Simple manager to create OCI clients using ~/.oci/config or env-based auth."""

    def __init__(self) -> None:
        self.config = self._load_config()
        self.signer = None  # for instance principals etc.

    def _load_config(self) -> Dict[str, Any]:
        # Prefer config file if present
        cfg_file = os.getenv("OCI_CONFIG_FILE", os.path.expanduser("~/.oci/config"))
        profile = os.getenv("OCI_CONFIG_PROFILE", "DEFAULT")
        if os.path.exists(cfg_file):
            log.info(f"Using OCI config file: {cfg_file} [{profile}]")
            return oci.config.from_file(cfg_file, profile_name=profile)

        # Else try explicit env vars
        env_keys = ("OCI_USER_OCID","OCI_FINGERPRINT","OCI_TENANCY_OCID","OCI_REGION","OCI_KEY_FILE")
        if all(os.getenv(k) for k in env_keys):
            cfg = {
                "user": os.environ["OCI_USER_OCID"],
                "fingerprint": os.environ["OCI_FINGERPRINT"],
                "tenancy": os.environ["OCI_TENANCY_OCID"],
                "region": os.environ["OCI_REGION"],
                "key_file": os.environ["OCI_KEY_FILE"],
            }
            log.info("Using explicit OCI env var configuration")
            return cfg

        # Finally, try instance principals (for servers running on OCI)
        try:
            self.signer = oci.auth.signers.get_resource_principals_signer()
            region = os.getenv("OCI_REGION", "ap-melbourne-1")
            cfg = {"region": region, "tenancy": os.getenv("OCI_TENANCY_OCID", "")}
            log.info("Using instance/resource principals signer")
            return cfg
        except Exception:
            raise RuntimeError(
                "No OCI credentials found. Run `oci setup config` or set env vars "
                "(OCI_USER_OCID, OCI_FINGERPRINT, OCI_TENANCY_OCID, OCI_REGION, OCI_KEY_FILE)."
            )

    def get_client(self, service: str):
        """Return an OCI service client bound to configured region/signer."""
        service = service.lower()
        kwargs = {}
        if self.signer:
            kwargs["signer"] = self.signer

        if service in ("identity", "iam"):
            return oci.identity.IdentityClient(self.config, **kwargs)
        if service in ("compute", "core"):
            return oci.core.ComputeClient(self.config, **kwargs)
        if service in ("network", "virtualnetwork", "vcn"):
            return oci.core.VirtualNetworkClient(self.config, **kwargs)
        if service in ("database", "db"):
            return oci.database.DatabaseClient(self.config, **kwargs)
        if service in ("object_storage", "objectstorage", "os"):
            return oci.object_storage.ObjectStorageClient(self.config, **kwargs)
        if service in ("usage", "usage_api", "cost"):
            try:
                return oci.usage_api.UsageapiClient(self.config, **kwargs)  # type: ignore[attr-defined]
            except Exception as e:
                raise RuntimeError("Usage API client not available; check OCI SDK version.") from e

        raise ValueError(f"Unknown OCI service: {service}")


oci_manager = OCIManager()

# Utility: default compartment
def _default_compartment() -> Optional[str]:
    return os.getenv("DEFAULT_COMPARTMENT_OCID") or oci_manager.config.get("tenancy")

# Utility: safe dict conversion for OCI models/collections
def _to_clean_dict(x: Any) -> Any:
    try:
        return to_dict(x)
    except Exception:
        return json.loads(json.dumps(x, default=str))


# ---------- MCP server ----------

mcp = FastMCP("oci-mcp-server")

@mcp.tool()
def list_compute_instances(compartment_ocid: Optional[str] = None,
                           lifecycle_state: Optional[str] = None) -> List[Dict[str, Any]]:
    """List Compute instances.
    Args:
        compartment_ocid: Compartment OCID (defaults to tenancy if omitted)
        lifecycle_state: Optional filter (e.g., RUNNING, STOPPED)
    Returns:
        Array of instance summaries (OCID, display_name, shape, lifecycle_state, time_created)
    """
    comp = compartment_ocid or _default_compartment()
    assert comp, "No compartment OCID available"
    compute = oci_manager.get_client("compute")
    items = []
    for inst in oci.pagination.list_call_get_all_results(
        compute.list_instances, compartment_id=comp
    ).data:
        if lifecycle_state and inst.lifecycle_state != lifecycle_state:
            continue
        items.append({
            "id": inst.id,
            "display_name": inst.display_name,
            "shape": inst.shape,
            "lifecycle_state": inst.lifecycle_state,
            "time_created": inst.time_created.isoformat() if inst.time_created else None,
            "compartment_id": inst.compartment_id,
            "availability_domain": getattr(inst, "availability_domain", None),
        })
    return items


@mcp.tool()
def get_instance_details(instance_id: str) -> Dict[str, Any]:
    """Get detailed info for a Compute instance, including VNICs and public IPs.
    Args:
        instance_id: The OCID of the instance
    """
    compute = oci_manager.get_client("compute")
    vcn = oci_manager.get_client("network")

    inst = compute.get_instance(instance_id).data
    details: Dict[str, Any] = {
        "id": inst.id,
        "display_name": inst.display_name,
        "shape": inst.shape,
        "lifecycle_state": inst.lifecycle_state,
        "time_created": inst.time_created.isoformat() if inst.time_created else None,
        "metadata": inst.metadata,
        "extended_metadata": inst.extended_metadata,
    }

    # VNIC attachments -> VNICs
    attachments = oci.pagination.list_call_get_all_results(
        compute.list_vnic_attachments,
        compartment_id=inst.compartment_id,
        instance_id=inst.id,
    ).data

    vnics = []
    for att in attachments:
        vnic = vcn.get_vnic(att.vnic_id).data
        vnics.append({
            "id": vnic.id,
            "display_name": vnic.display_name,
            "hostname_label": vnic.hostname_label,
            "private_ip": vnic.private_ip,
            "public_ip": vnic.public_ip,
            "subnet_id": vnic.subnet_id,
            "is_primary": vnic.is_primary,
        })
    details["vnics"] = vnics
    return details


@mcp.tool()
def instance_action(instance_id: str, action: str) -> Dict[str, Any]:
    """Perform a safe instance action (START, STOP, RESET, SOFTRESET, SOFTSTOP).
    Args:
        instance_id: Instance OCID
        action: One of START, STOP, RESET, SOFTRESET, SOFTSTOP
    """
    compute = oci_manager.get_client("compute")
    action = action.upper()
    valid = {"START","STOP","RESET","SOFTRESET","SOFTSTOP"}
    if action not in valid:
        raise ValueError(f"Invalid action '{action}'. Allowed: {sorted(valid)}")
    resp = compute.instance_action(instance_id=instance_id, action=action)
    return {"status": resp.status, "headers": dict(resp.headers)}


@mcp.tool()
def list_autonomous_databases(compartment_ocid: Optional[str] = None) -> List[Dict[str, Any]]:
    """List Autonomous Databases in a compartment (defaults to tenancy)."""
    comp = compartment_ocid or _default_compartment()
    assert comp, "No compartment OCID available"
    db = oci_manager.get_client("database")
    items = []
    for adb in oci.pagination.list_call_get_all_results(
        db.list_autonomous_databases, compartment_id=comp
    ).data:
        items.append({
            "id": adb.id,
            "db_name": adb.db_name,
            "display_name": adb.display_name,
            "lifecycle_state": adb.lifecycle_state,
            "db_workload": adb.db_workload,
            "cpu_core_count": getattr(adb, "cpu_core_count", None),
            "data_storage_size_in_tbs": getattr(adb, "data_storage_size_in_tbs", None),
            "is_auto_scaling_enabled": getattr(adb, "is_auto_scaling_enabled", None),
            "connection_strings": _to_clean_dict(getattr(adb, "connection_strings", {})),
        })
    return items


@mcp.tool()
def list_storage_buckets(compartment_ocid: Optional[str] = None) -> List[Dict[str, Any]]:
    """List Object Storage buckets in the configured region for the given compartment."""
    comp = compartment_ocid or _default_compartment()
    assert comp, "No compartment OCID available"
    osvc = oci_manager.get_client("object_storage")
    namespace = osvc.get_namespace().data
    buckets = oci.pagination.list_call_get_all_results(
        osvc.list_buckets, namespace_name=namespace, compartment_id=comp
    ).data
    return [{"name": b.name, "created": b.time_created.isoformat(), "namespace": namespace} for b in buckets]


@mcp.tool()
def list_compartments() -> List[Dict[str, Any]]:
    """List accessible compartments in the tenancy (including subtrees)."""
    identity = oci_manager.get_client("identity")
    tenancy_id = oci_manager.config["tenancy"]
    comps = oci.pagination.list_call_get_all_results(
        identity.list_compartments,
        compartment_id=tenancy_id,
        compartment_id_in_subtree=True,
        access_level="ACCESSIBLE",
    ).data
    return [{"id": c.id, "name": c.name, "lifecycle_state": c.lifecycle_state, "is_accessible": c.is_accessible} for c in comps]


@mcp.tool()
def perform_security_assessment(compartment_ocid: Optional[str] = None) -> Dict[str, Any]:
    """Basic security posture checks (public IPs, wide-open rules). Read-only heuristics."""
    comp = compartment_ocid or _default_compartment()
    assert comp, "No compartment OCID available"

    compute = oci_manager.get_client("compute")
    net = oci_manager.get_client("network")

    findings: Dict[str, Any] = {"public_instances": [], "wide_open_nsg_rules": [], "wide_open_sec_list_rules": []}

    # Instances with public IPs
    for inst in oci.pagination.list_call_get_all_results(compute.list_instances, compartment_id=comp).data:
        vnic_atts = oci.pagination.list_call_get_all_results(
            compute.list_vnic_attachments, compartment_id=comp, instance_id=inst.id
        ).data
        for att in vnic_atts:
            vnic = net.get_vnic(att.vnic_id).data
            if vnic.public_ip:
                findings["public_instances"].append({"instance_id": inst.id, "name": inst.display_name, "public_ip": vnic.public_ip})

    # Security Lists allowing 0.0.0.0/0 inbound
    for vcn in oci.pagination.list_call_get_all_results(net.list_vcns, compartment_id=comp).data:
        sec_lists = oci.pagination.list_call_get_all_results(net.list_security_lists, compartment_id=comp, vcn_id=vcn.id).data
        for sl in sec_lists:
            for rule in sl.ingress_security_rules or []:
                src = getattr(rule, "source", "")
                if src == "0.0.0.0/0":
                    findings["wide_open_sec_list_rules"].append({"security_list_id": sl.id, "vcn": vcn.display_name, "proto": rule.protocol})

        # NSGs
        nsgs = oci.pagination.list_call_get_all_results(net.list_network_security_groups, compartment_id=comp, vcn_id=vcn.id).data
        for nsg in nsgs:
            rules = oci.pagination.list_call_get_all_results(net.list_network_security_group_security_rules, network_security_group_id=nsg.id).data
            for r in rules:
                src = getattr(r, "source", "") or getattr(r, "source_type", "")
                if getattr(r, "direction", "INGRESS") == "INGRESS" and getattr(r, "source", "") == "0.0.0.0/0":
                    findings["wide_open_nsg_rules"].append({"nsg_id": nsg.id, "name": nsg.display_name, "proto": r.protocol})

    return findings


@mcp.tool()
def get_tenancy_cost_summary(start_time_iso: Optional[str] = None,
                             end_time_iso: Optional[str] = None,
                             granularity: str = "DAILY") -> Dict[str, Any]:
    """Summarize tenancy costs using Usage API (requires permissions).
    Args:
        start_time_iso: ISO8601 start (defaults: now-7d)
        end_time_iso: ISO8601 end (defaults: now)
        granularity: DAILY or MONTHLY
    """
    try:
        usage = oci_manager.get_client("usage_api")
    except Exception as e:
        raise RuntimeError("Usage API not available; upgrade OCI SDK and permissions.") from e

    if not end_time_iso:
        end = datetime.utcnow()
    else:
        end = datetime.fromisoformat(end_time_iso.replace("Z",""))
    if not start_time_iso:
        start = end - timedelta(days=7)
    else:
        start = datetime.fromisoformat(start_time_iso.replace("Z",""))

    tenant_id = oci_manager.config["tenancy"]
    details = oci.usage_api.models.RequestSummarizedUsagesDetails(
        tenant_id=tenant_id,
        time_usage_started=start,
        time_usage_ended=end,
        granularity=granularity,
        query_type="COST",
        group_by=["service"],
        forecast=False,
    )
    resp = usage.request_summarized_usages(request_summarized_usages_details=details)
    rows = [to_dict(x) for x in resp.data.items] if getattr(resp.data, "items", None) else []
    total = sum((r.get("computed_amount", 0) or 0) for r in rows)
    return {"start": start.isoformat()+"Z", "end": end.isoformat()+"Z", "granularity": granularity, "total_computed_amount": total, "items": rows}


# ----------- Resources -----------

@mcp.resource("oci://compartments")
def resource_compartments() -> Dict[str, Any]:
    """Resource listing compartments (id, name)."""
    return {"compartments": list_compartments()}


# ----------- Prompts -----------

@mcp.prompt("oci_analysis_prompt")
def oci_analysis_prompt() -> str:
    """A helper prompt to analyze OCI state returned by the tools."""
    return (
        "You are an expert Oracle Cloud architect. Given the JSON outputs from tools like "
        "`list_compute_instances`, `perform_security_assessment`, and `get_tenancy_cost_summary`, "
        "produce a concise assessment covering security, cost, and reliability. "
        "Highlight risky public exposure, suggest least-privilege hardening, recommend cost optimizations "
        "(stop idle instances, enable ADB auto-scaling), and note any missing monitoring/alerts."
    )


def main() -> None:
    # Start stdio transport
    mcp.run()


if __name__ == "__main__":
    main()
