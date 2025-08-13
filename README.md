# OCI MCP Server

Model Context Protocol (MCP) server exposing **Oracle Cloud Infrastructure** tools, resources and prompts.

- 🔧 Tools: list/inspect **Compute**, **Autonomous Databases**, **Object Storage**, instance actions, quick security checks, **(experimental)** cost summaries
- 📚 Resources: `oci://compartments` etc.
- 🧠 Prompts: `oci_analysis_prompt`
- 🖥️ Works with Claude Desktop via stdio transport

> Built with the official [MCP Python SDK](https://modelcontextprotocol.io/quickstart/server) and the [OCI Python SDK](https://oracle-cloud-infrastructure-python-sdk.readthedocs.io).

## Quick start

```bash
git clone https://github.com/karthiksuku/oci-mcp.git
cd oci-mcp
chmod +x install.sh
./install.sh
### Auth Prerequisites
- OCI CLI configured. By default this server reads credentials from `~/.oci/config`.
  - Create it with: `oci setup config`
  - macOS/Linux: `~/.oci/config`
  - Windows: `%USERPROFILE%\.oci\config`
  - Override via `OCI_CONFIG_FILE=/path/to/config` or a `.env` file.
# ensure you've run: oci setup config
python oci_mcp_server.py  # starts stdio MCP server
```

### Add to Claude Desktop

Add to `~/.claude/claude_desktop_config.json`:
```jsonc
{
  "mcpServers": {
    "oci-infrastructure": {
      "command": "python",
      "args": ["/ABSOLUTE/PATH/oci-mcp/oci_mcp_server.py"],
      "env": { "OCI_CONFIG_FILE": "/Users/<you>/.oci/config" }
    }
  }
}
```

Open Claude Desktop → *Connect to server* → select **oci-infrastructure**.

## Required IAM policies (examples)

Grant read-only for discovery (adjust compartment OCIDs and groups):

```
Allow group MyGroup to read instances in tenancy
Allow group MyGroup to read virtual-network-family in tenancy
Allow group MyGroup to read autonomous-database-family in tenancy
Allow group MyGroup to read objectstorage-namespaces in tenancy
Allow group MyGroup to read buckets in tenancy
Allow group MyGroup to read usage-reports in tenancy
```

For instance actions:

```
Allow group MyGroup to manage instance-family in compartment <COMP_OCID>
```

## Tools

- `list_compute_instances(compartment_ocid=None, lifecycle_state=None)`
- `get_instance_details(instance_id)`
- `instance_action(instance_id, action)` — actions: START, STOP, RESET, SOFTRESET, SOFTSTOP
- `list_autonomous_databases(compartment_ocid=None)`
- `list_storage_buckets(compartment_ocid=None)`
- `list_compartments()`
- `perform_security_assessment(compartment_ocid=None)`
- `get_tenancy_cost_summary(start_time_iso, end_time_iso, granularity="DAILY")` *(experimental; requires Usage API access)*

See [`examples/sample_queries.md`](examples/sample_queries.md) for ideas.

## Configuration

- Uses `~/.oci/config` by default (created via `oci setup config`).
- Can also read explicit env vars from `.env` (see `.env.example`).
- Optional: `DEFAULT_COMPARTMENT_OCID` to scope queries.

## Notes

- Cost summary uses the Usage API if available.
- Networking/security heuristics are conservative (non-invasive read-only calls).
- This repo is a base—extend with OKE, LB, Budgets, Events, etc.

## License

MIT
